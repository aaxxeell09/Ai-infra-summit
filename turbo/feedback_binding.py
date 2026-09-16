"""Bind an opt-in feedback run to an already-applied exploratory recommendation."""
from .runtime_identity import binding_matches


def bound_config(service_config, recommendation, applied):
    model_id, mode = applied['model'], applied['mode']
    if recommendation.get('model_id') != model_id or mode not in recommendation.get('modes', {}):
        raise ValueError('Recommendation model/mode mismatch')
    spec = service_config['models'][model_id]
    if recommendation.get('plugin') != spec.get('plugin', 'llama_cpp'):
        raise ValueError('Recommendation plugin mismatch')
    selected = recommendation['modes'][mode]
    expected = {k: selected[k] for k in ('device', 'threads', 'context')}
    if applied.get('config') != expected:
        raise ValueError('Applied configuration differs from selected recommendation')
    if not recommendation.get('model_sha256') or not recommendation.get('runtime_binding'):
        raise ValueError('Recommendation lacks artifact identities')
    config = dict(sdk_dir=service_config['sdk_dir'], model_path=spec['path'],
                  plugin=spec.get('plugin', 'llama_cpp'), **expected)
    config['recommendation_binding'] = dict(model_id=model_id, mode=mode,
        model_sha256=recommendation['model_sha256'], runtime_binding=recommendation['runtime_binding'],
        native_config={**expected, 'plugin':config['plugin']},
        evidence=applied['evidence'], quality_qualified=False,
        scope='Applied device/threads/context; feedback grammar and task output budget are separate diagnostic controls')
    return config


def verify_bound_config(config, model_sha256, runtime_binding):
    """Fail before model creation on drift; no binding means legacy fixed-config diagnostic."""
    binding = config.get('recommendation_binding')
    if binding is None:
        return False
    if not isinstance(binding, dict) or model_sha256 != binding.get('model_sha256'):
        raise ValueError('Bound recommendation model identity changed')
    if not binding_matches(binding.get('runtime_binding'), runtime_binding):
        raise ValueError('Bound recommendation runtime identity changed')
    expected = binding.get('native_config')
    if not isinstance(expected, dict) or set(expected) != {'device','threads','context','plugin'}:
        raise ValueError('Incomplete bound native configuration')
    if {k:config.get(k) for k in expected} != expected:
        raise ValueError('Bound recommendation native configuration changed')
    if any(config.get(k,0) != 0 for k in ('threads_batch','ubatch','n_batch')) or config.get('spec_type','none') != 'none':
        raise ValueError('Unbound inference override')
    return True
