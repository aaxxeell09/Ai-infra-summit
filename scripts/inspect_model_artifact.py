"""Read-only artifact inventory. Never load models or infer quantization from names."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from turbo.json_io import read_json

FIELDS = {
    'geniex.json': ('name', 'version', 'type', 'architecture', 'model_type', 'quantization', 'context_size', 'model', 'tokenizer', 'chat_template'),
    'genie_config.json': ('dialog.context', 'dialog.sampler', 'dialog.tokenizer', 'dialog.engine.n-threads',
                          'dialog.engine.backend', 'dialog.engine.model', 'quantization'),
    'tokenizer_config.json': ('tokenizer_class', 'model_max_length', 'chat_template', 'bos_token', 'eos_token', 'pad_token',
                              'add_bos_token', 'add_eos_token'),
}


def _files(source):
    if source.is_symlink() or (hasattr(source, 'is_junction') and source.is_junction()):
        raise ValueError('Symlinks are not supported in artifact inventories')
    if source.is_file():
        return [(source.name, source)]
    if not source.is_dir():
        raise ValueError('Artifact must be a regular file or directory')
    rows = []
    def visit(directory):
        for entry in sorted(os.scandir(directory), key=lambda e: e.name):
            path = Path(entry.path)
            if entry.is_symlink() or (hasattr(path, 'is_junction') and path.is_junction()):
                raise ValueError('Symlinks and junctions are not supported in artifact inventories')
            if entry.is_dir(follow_symlinks=False):
                visit(path)
            elif entry.is_file(follow_symlinks=False):
                rows.append((path.relative_to(source).as_posix(), path))
            else:
                raise ValueError('Artifact contains a non-regular file')
    visit(source)
    return sorted(rows)


def _fingerprint(path):
    before = path.stat(follow_symlinks=False)
    if not stat.S_ISREG(before.st_mode):
        raise ValueError('Artifact file is not regular')
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b''):
            h.update(chunk)
    after = path.stat(follow_symlinks=False)
    if (before.st_size, before.st_mtime_ns, before.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino):
        raise ValueError('Artifact changed during inspection')
    return {'bytes': after.st_size, 'sha256': h.hexdigest()}


def _field(data, name):
    for key in name.split('.'):
        if not isinstance(data, dict) or key not in data:
            return None, False
        data = data[key]
    return data, True


def inspect_artifact(source, expected_manifest=None):
    source = Path(source).absolute()
    paths = _files(source)
    files = {name: _fingerprint(path) for name, path in paths}
    metadata = []
    configs = {}
    for name, path in paths:
        if name in FIELDS:
            data = read_json(path, require_object=True)
            configs[name] = data
            for field in FIELDS[name]:
                value, found = _field(data, field)
                if found:
                    metadata.append({'source': name, 'field': field, 'value': value})
    references = []
    genie = configs.get('genie_config.json', {})
    shards, present = _field(genie, 'dialog.engine.model.binary.ctx-bins')
    if present:
        if not isinstance(shards, list) or not shards or any(not isinstance(x, str) for x in shards):
            raise ValueError('Declared ctx-bins must be a nonempty list of paths')
        references += [('dialog.engine.model.binary.ctx-bins', value) for value in shards]
    for field in ('dialog.tokenizer.path', 'dialog.engine.backend.extensions'):
        value, present = _field(genie, field)
        if present:
            if not isinstance(value, str):
                raise ValueError('Declared artifact reference must be a path string')
            references.append((field, value))
    resolved = []
    for field, value in references:
        normalized = value.replace('\\', '/')
        relative = PurePosixPath(normalized)
        if not value or relative.is_absolute() or '..' in relative.parts or ':' in normalized:
            raise ValueError('Declared artifact reference escapes bundle')
        name = relative.as_posix()
        if name not in files:
            raise ValueError('Declared artifact reference is missing: ' + name)
        resolved.append({'source': 'genie_config.json', 'field': field, 'declared_path': value, 'inventory_path': name})
        if field == 'dialog.engine.backend.extensions':
            extension = read_json(dict(paths)[name], require_object=True)
            for key in ('devices', 'memory', 'context'):
                if key in extension:
                    metadata.append({'source': name, 'field': key, 'value': extension[key]})
    # Recheck bytes as well as paths so the metadata and inventory describe one snapshot.
    if [name for name, _ in _files(source)] != list(files) or any(_fingerprint(path) != files[name] for name, path in paths):
        raise ValueError('Artifact changed during inspection')
    canonical = json.dumps(files, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    result = {'schema_version': 'artifact-inventory-v1', 'artifact_kind': 'directory' if source.is_dir() else 'file',
              'files': files, 'total_bytes': sum(v['bytes'] for v in files.values()),
              'inventory_sha256': hashlib.sha256(canonical).hexdigest(),
              'observed_metadata': metadata, 'declared_references': resolved,
              'quantization': next((m['value'] for m in metadata if m['field'] == 'quantization'), None)}
    if expected_manifest is not None and (expected_manifest.get('files') != files or expected_manifest.get('inventory_sha256') != result['inventory_sha256']):
        raise ValueError('Artifact does not match expected inventory')
    return result


def write_manifest(source, output, result):
    source, output = Path(source).resolve(), Path(output)
    resolved = output.resolve()
    if resolved == source or (source.is_dir() and resolved.is_relative_to(source)):
        raise ValueError('Output must be outside the inspected artifact')
    if output.exists() or output.is_symlink():
        raise ValueError('Refusing to overwrite existing manifest')
    text = json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False)+'\n'
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8') as stream:
        stream.write(text)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('artifact', type=Path)
    parser.add_argument('--expected-manifest', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    try:
        expected = read_json(args.expected_manifest, require_object=True) if args.expected_manifest else None
        result = inspect_artifact(args.artifact, expected)
        output = args.output or ROOT/'local/artifact-manifests'/(result['inventory_sha256']+'.json')
        if args.expected_manifest and output.resolve() == args.expected_manifest.resolve():
            raise ValueError('Output collides with expected manifest')
        write_manifest(args.artifact, output, result)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(output)


if __name__ == '__main__':
    main()
