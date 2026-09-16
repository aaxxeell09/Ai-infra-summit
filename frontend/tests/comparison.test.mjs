import test from 'node:test';
import assert from 'node:assert/strict';
import { PROMPTS, createComparisonRequest, comparisonLanes, comparisonEvidence, createPreviewComparisonProvider } from '../public/comparison.mjs';
import { normalizeSnapshot } from '../public/data.mjs';
import { readFileSync } from 'node:fs';
function snapshot() {
  const root = new URL('../../benchmarks/results/screen-01/', import.meta.url);
  const manifest = JSON.parse(readFileSync(new URL('sweep.json', root)));
  const reports = Object.fromEntries(manifest.cells.map(cell => [cell.id, JSON.parse(readFileSync(new URL(`${cell.id}.json`, root)))]));
  return normalizeSnapshot({schema_version:'local-turbo.recorded.v1',mode:'recorded',manifest,reports});
}
function request(mode = 'speed', prompt = 'quick') {
  const data = snapshot(); return createComparisonRequest(data, data.rows.find(row => row.id === 'cpu-t10'), 'decode', mode, prompt, 'comparison-1');
}
test('speed comparison carries the same model and explicit default/selected settings', () => {
  const r = request(); assert.equal(r.baseline.model_sha256, r.selected.model_sha256);
  assert.equal(r.baseline.params.n_threads, 0); assert.equal(r.selected.params.n_threads, 10);
  assert.equal(r.execution, 'sequential'); assert.equal(r.routing, null);
});
test('routing preview distinguishes example roles from calibrated model identities', () => {
  const quick = request('routing'); const hard = request('routing', 'reasoning');
  assert.equal(quick.selected, null); assert.equal(quick.routing.status, 'pending_calibration');
  assert.notEqual(comparisonLanes(quick).turbo.model, comparisonLanes(hard).turbo.model);
  assert.match(comparisonLanes(hard).turbo.configuration, /Illustrative/);
});
test('scripted preview exposes recorded speed and diagnostic energy without inventing accuracy', () => {
  const data = snapshot();
  const evidence = comparisonEvidence(data, data.rows.find(row => row.id === 'cpu-t10'));
  assert.equal(evidence.default.decode_tps, 95.950082);
  assert.equal(evidence.turbo.decode_tps, 97.90581);
  assert.ok(evidence.speed_gain_pct > 2 && evidence.speed_gain_pct < 2.1);
  assert.equal(evidence.default.energy_j, 429.0452043732);
  assert.equal(evidence.turbo.energy_j, 321.0678077976);
  assert.equal(evidence.energy_status, 'diagnostic');
  assert.equal(evidence.answer_check, 'scripted_match');
  assert.equal(evidence.accuracy_pct, null);
});
test('preview executes sequentially with equal scripted answers and no measured winner', async () => {
  const events=[]; const r=request(); const result=await createPreviewComparisonProvider({delay:1}).execute(r,{onEvent:e=>events.push(e)});
  assert.ok(events.findIndex(e=>e.type==='complete'&&e.lane==='default') < events.findIndex(e=>e.type==='start'&&e.lane==='turbo'));
  assert.equal(result.lanes.default.answer, PROMPTS[0].answer); assert.equal(result.lanes.turbo.answer, result.lanes.default.answer);
  assert.equal(result.winner,null); assert.equal(result.speedup,null);
  for(const lane of Object.values(result.lanes)){assert.equal(lane.total_time_s,null);assert.equal(lane.output_tokens,null);assert.equal(lane.quality,'not_evaluated');assert.equal(lane.configuration_applied,false);}
  assert.ok(result.lanes.turbo.animation_pace_ms < result.lanes.default.animation_pace_ms);
});
test('aborting preview stops both remaining text and the second lane', async () => {
  const controller=new AbortController();const events=[];
  await assert.rejects(createPreviewComparisonProvider({delay:0}).execute(request(),{signal:controller.signal,onEvent(e){events.push(e);if(e.type==='text')controller.abort();}}),{name:'AbortError'});
  assert.equal(events.some(e=>e.lane==='turbo'),false);
});
test('edited or unknown prompts cannot silently receive a scripted answer',async()=>{
  const r=request();r.prompt='Another question';await assert.rejects(createPreviewComparisonProvider().execute(r),/example prompts/);
  assert.throws(()=>request('speed','missing'),/Choose/);
});
