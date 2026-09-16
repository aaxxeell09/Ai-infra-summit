"""Real-device tune/apply/inference cycle over stdio MCP and loopback HTTP.

This is an integration smoke, not the frozen correctness benchmark or a paired
performance comparison. Results may contain local paths; review before sharing.
"""
import argparse
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time
from http.server import ThreadingHTTPServer

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from turbo.service import Engine, handler


def checked_rpc_reply(line, expected_id):
    """Reject ambiguous protocol replies before treating them as an operation result."""
    response = json.loads(line)
    if (not isinstance(response, dict) or response.get('jsonrpc') != '2.0'
            or type(response.get('id')) is not int
            or response['id'] != expected_id):
        raise ValueError('MCP reply identity/protocol mismatch')
    if (('result' in response) == ('error' in response)
            or not isinstance(response.get('result', response.get('error')), dict)):
        raise ValueError('MCP reply must contain exactly one result/error object')
    return response


def capture_feedback(argv, *, wire_path, stderr_path, **kwargs):
    """Keep partial wire/logs on timeout as well as completed child attempts."""
    def preserve(stdout, stderr):
        for path, value in ((wire_path, stdout), (stderr_path, stderr)):
            # TimeoutExpired may contain bytes even with encoding='utf-8'.
            path.write_bytes(value if isinstance(value, bytes)
                             else (value or '').encode('utf-8'))
    try:
        child = subprocess.run(argv, **kwargs)
    except subprocess.TimeoutExpired as exc:
        preserve(exc.stdout, exc.stderr)
        raise
    except OSError as exc:
        preserve('', 'Failed to launch feedback MCP: ' + str(exc))
        raise
    preserve(child.stdout, child.stderr)
    return child


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config', required=True)
    p.add_argument('--model-id', required=True)
    p.add_argument('--search-space', required=True, help='Path to JSON tuner axes')
    p.add_argument('--output', required=True, help='New result directory')
    p.add_argument('--feedback-mcp',action='store_true',help='Separate opt-in bound feedback diagnostic; no v2 quality claim')
    p.add_argument('--rounds', type=int, choices=(1, 2, 3), default=2)
    p.add_argument('--task-id', default='t13', help='Interactive demo fixture, not golden benchmark')
    args = p.parse_args()
    source_commit = subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    source_status = subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True).strip()
    if source_status:
        p.error('Integration evidence requires a clean source checkout; use ignored local/ for config and output')
    config = json.loads(Path(args.config).read_text(encoding='utf-8-sig'))
    search = json.loads(Path(args.search_space).read_text(encoding='utf-8-sig'))
    out = Path(args.output).resolve(); out.mkdir(parents=True, exist_ok=False)
    config.update(data_dir=str(out/'fixtures'),results_dir=str(out/'tuning'),default=args.model_id)
    engine = Engine(config)
    server = ThreadingHTTPServer(('127.0.0.1', 0), handler(engine))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    env = dict(os.environ, PYTHONPATH=str(ROOT), PYTHONUTF8='1',
               TURBO_BASE_URL=f'http://127.0.0.1:{server.server_port}')
    log = (out/'mcp-stderr.log').open('wb')
    proc = subprocess.Popen([sys.executable,'-X','utf8','-m','turbo.mcp_server'],
        stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=log,text=True,encoding='utf-8',env=env,cwd=ROOT,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    replies = queue.Queue()
    def read_replies():
        for line in proc.stdout:
            replies.put(line)
        replies.put(None)
    threading.Thread(target=read_replies,daemon=True).start()
    record = dict(scope='Integration smoke through real MCP/HTTP/native inference; no quality qualification',
                  git_commit=source_commit, dirty=False,
                  model_id=args.model_id, search_space=search, calls=[], rounds=[], completed=False)
    def save():
        (out/'integration.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
    serial = 0
    def rpc(method, params):
        nonlocal serial
        serial += 1
        proc.stdin.write(json.dumps(dict(jsonrpc='2.0',id=serial,method=method,params=params))+'\n')
        proc.stdin.flush()
        line = replies.get(timeout=150)
        if line is None: raise RuntimeError('MCP exited before replying')
        # Preserve even malformed/incorrectly addressed replies for diagnosis.
        call_record = dict(method=method, params=params, raw_reply=line)
        record['calls'].append(call_record);save()
        response = checked_rpc_reply(line, serial)
        call_record['response'] = response;save()
        if 'error' in response or response.get('result',{}).get('isError'):
            raise RuntimeError('MCP operation failed; see preserved response')
        return response['result']
    def tool(name, args):
        return rpc('tools/call',dict(name=name,arguments=args)).get('structuredContent')
    try:
        rpc('initialize',dict(protocolVersion='2025-06-18',capabilities={},clientInfo={'name':'tuner-cycle-smoke','version':'1'}))
        proc.stdin.write(json.dumps(dict(jsonrpc='2.0',method='notifications/initialized'))+'\n');proc.stdin.flush()
        for index in range(args.rounds):
            started = time.monotonic()
            round_record = dict(index=index, tune=tool('local_tune',dict(model_id=args.model_id,objective='fast',search_space=search)))
            record['rounds'].append(round_record);save()
            engine.tuning_process.thread.join(timeout=300)
            if engine.tuning_process.poll() is None:
                raise TimeoutError('Tuner still running after integration deadline')
            if engine.tuning_process.error: raise RuntimeError(engine.tuning_process.error)
            round_record['tuning_record'] = engine.tuning_process.result
            if not engine.tuning_process.result.get('recommendation_path'):
                raise RuntimeError('No eligible recommendation; see tuning record')
            mode = 'efficient' if index % 2 and 'efficient' in engine.modes()['modes'] else 'fast'
            round_record['apply'] = tool('local_apply',dict(mode=mode,model_id=args.model_id))
            round_record['inference'] = tool('local_run',dict(mode=mode,model=args.model_id,
                messages=[{'role':'user','content':'What is two plus three? Reply with just the number.'}],max_tokens=16))
            if args.feedback_mcp:
                # Batch axes are not represented by the current apply contract.
                if search.get('batch') is not None or search.get('ubatch') is not None:
                    raise ValueError('Feedback binding supports device/threads/context axes only')
                from turbo.feedback_binding import bound_config
                native_config=bound_config(config,engine.modes(),round_record['apply']['gateway_response'])
                config_path=out/f'feedback-config-{index}.json'
                config_path.write_text(json.dumps(native_config,indent=2),encoding='utf-8')
                for model in engine.loaded.values(): model.close()
                engine.loaded.clear()
                alias=args.model_id+'-'+mode
                request=[dict(jsonrpc='2.0',id=1,method='initialize',params={'protocolVersion':'2025-06-18'}),
                         dict(jsonrpc='2.0',id=2,method='tools/call',params={'name':'local_feedback_diagnostic',
                            'arguments':{'task_id':args.task_id,'model_id':alias}})]
                child=capture_feedback([sys.executable,'-X','utf8','-m','turbo.feedback_mcp','--enable-candidate',
                    '--model',alias+'='+str(config_path),'--output-root',str(out/f'feedback-{index}')],
                    wire_path=out/f'feedback-wire-{index}.jsonl',stderr_path=out/f'feedback-stderr-{index}.log',
                    input=''.join(json.dumps(r)+'\n' for r in request),capture_output=True,encoding='utf-8',
                    cwd=ROOT,env=env,timeout=210,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
                lines = [line for line in child.stdout.splitlines() if line.strip()]
                if len(lines) != 2:
                    raise ValueError('Expected exactly initialize and feedback MCP replies; wire preserved')
                initialized = checked_rpc_reply(lines[0], 1)
                if 'error' in initialized:
                    raise RuntimeError('Feedback MCP initialization failed; wire preserved')
                reply=checked_rpc_reply(lines[1], 2)
                payload=reply.get('result',{}).get('structuredContent',{})
                round_record['feedback_mcp']=reply
                round_record['secretary']=payload.get('existing_demo_verification',{})
                save()
                if child.returncode or 'error' in reply or reply.get('result',{}).get('isError'):
                    raise RuntimeError('Bound MCP diagnostic failed; original reply preserved')
                report=payload.get('report',{})
                if report.get('recommendation_binding_verified') is not True:
                    raise RuntimeError('Native diagnostic did not verify recommendation binding')
                round_record['native_config_binding_verified']=True
            else:
                round_record['secretary'] = tool('local_secretary',dict(mode=mode,task_id=args.task_id))
            round_record['elapsed_s'] = time.monotonic()-started
            save()
        record['completed'] = True
    except Exception as exc:
        record['error'] = str(exc)
        raise
    finally:
        save()
        proc.kill();proc.wait(timeout=5);log.close()
        server.shutdown();server.server_close()
        # Release models but avoid SDK deinit/reinit in this process.
        for model in engine.loaded.values(): model.close()
    print(json.dumps({'completed':True,'rounds':len(record['rounds']),
                      'secretary_passes':[r['secretary'].get('passed') for r in record['rounds']]}))


if __name__ == '__main__':
    main()
