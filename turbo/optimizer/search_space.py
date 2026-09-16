"""Declarative search spaces bound to evidence read from this repository.

A parameter enters hardware search only when its support was established by
reading the code that consumes it. Generic QAIRT or llama.cpp documentation is
not evidence here: the frozen runner rejects unknown configuration keys outright
(``eval/run_secretary_eval.py``) and the native layer rejects several keys per
plugin (``turbo/native.py``), so a plausible-sounding knob that neither accepts
would waste a hardware slot and produce an uninterpretable refusal.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from turbo.experiments import digest

SCHEMA = 'local-turbo.autotune-search-space.v1'

SUPPORTED = 'supported'
UNSUPPORTED = 'unsupported'
UNKNOWN = 'unknown'
#: The control is real and interesting, but the current frozen runner cannot
#: express it. It stays visible so a research question is never lost, and it can
#: be planned, but it must never reach a qualified experiment.
REQUIRES_PROTOCOL_EXTENSION = 'requires_protocol_extension'
#: The control can be exercised, but only through a separate diagnostic probe
#: whose output is an elimination signal, never promotion evidence.
DIAGNOSTIC_ONLY = 'diagnostic_only'

#: Statuses a candidate may carry into the official, tracker-backed lane.
QUALIFIED_STATUSES = (SUPPORTED,)

BACKENDS = ('llama_cpp_cpu', 'llama_cpp_htp', 'qairt_npu')

#: Three search lanes. The lane is a property of a control on a backend, not of
#: the control alone: max_tokens is lane A on QAIRT and lane B on llama.cpp.
LANE_QAIRT_QUALIFIED = 'A_qairt_qualified'
LANE_LLAMA_MASS = 'B_llama_cpp_mass'
LANE_DIAGNOSTIC = 'C_diagnostic_or_protocol_extension'
LANES = (LANE_QAIRT_QUALIFIED, LANE_LLAMA_MASS, LANE_DIAGNOSTIC)

#: Keys the frozen runner accepts at all. Anything outside this set makes the
#: runner exit with "Unknown configuration keys" before a model is ever loaded.
RUNNER_ALLOWED_KEYS = ('sdk_dir', 'model_path', 'device', 'threads', 'context', 'threads_batch',
                       'ubatch', 'n_batch', 'spec_type', 'draft_tokens', 'plugin', 'backend',
                       'stop_after_tool_call', 'max_tokens', 'grammar', 'hardware_note')

#: Keys that identify the artifact or the backend slot rather than a treatment.
#: Mutating one of these is a different experiment, not a tuning candidate, so
#: V1 never generates them.
IDENTITY_KEYS = ('sdk_dir', 'model_path', 'device', 'plugin', 'backend', 'hardware_note')


def _parameter(name, *, status, evidence, backends, requires_restart, allowed_values=None,
               mutually_exclusive_with=(), family=None, note=None, wiring=None):
    """One control record. ``wiring`` answers a question ``support_status`` does not.

    A control can be declared in a struct and still be unreachable: the QAIRT
    sampler fields exist in the ctypes layer while no configuration path
    populates them. "Officially supported" and "actually wired" are therefore
    separate columns, and conflating them is how a search wastes hardware slots
    on a knob that changes nothing.
    """
    return {'name': name, 'support_status': status, 'evidence': evidence,
            'backends': tuple(backends), 'requires_restart': requires_restart,
            'allowed_values': None if allowed_values is None else tuple(allowed_values),
            'mutually_exclusive_with': tuple(mutually_exclusive_with),
            'family': family or name, 'note': note,
            'wiring': wiring or 'config to runtime, verified by reading the consuming code'}


#: Every mutable parameter TurboLab knows about, with the code that proves it.
#: ``allowed_values`` is a bounded enumeration, never an open range: an open
#: range invites a sweep whose points are not individually interpretable.
PARAMETERS = {
    'max_tokens': _parameter(
        'max_tokens', status=SUPPORTED, family='output_budget',
        evidence='eval/run_secretary_eval.py allows the key and records it in generation_protocol; '
                 'turbo/native.py passes it to the generation config for every plugin',
        backends=BACKENDS, requires_restart=False,
        allowed_values=(16, 24, 32, 48, 64, 96, 128, 192, 256),
        note='The frozen runner defaults to 128 when the config omits it.'),
    'stop_after_tool_call': _parameter(
        'stop_after_tool_call', status=SUPPORTED, family='stop',
        evidence='turbo/native.py:649 accepts it only when the resolved plugin is qairt and '
                 'raises for any other plugin; docs/qairt-single-action.md records the mechanism',
        backends=('qairt_npu',), requires_restart=True, allowed_values=(False, True),
        note='QAIRT-only. The GenieX v0.6.1 QAIRT wrapper rejects native stop lists, so this '
             'rides the token callback instead.'),
    'threads': _parameter(
        'threads', status=SUPPORTED, family='cpu_parallelism',
        evidence='turbo/native.py forwards it as n_threads; :658 rejects any nonzero value for qairt',
        backends=('llama_cpp_cpu', 'llama_cpp_htp'), requires_restart=True,
        allowed_values=(0, 2, 4, 6, 8, 10, 12)),
    'threads_batch': _parameter(
        'threads_batch', status=SUPPORTED, family='cpu_parallelism',
        evidence='turbo/native.py forwards it as n_threads_batch; :658 rejects it for qairt',
        backends=('llama_cpp_cpu', 'llama_cpp_htp'), requires_restart=True,
        allowed_values=(0, 2, 4, 6, 8, 10, 12)),
    'n_batch': _parameter(
        'n_batch', status=SUPPORTED, family='batching',
        evidence='turbo/native.py forwards it as n_batch; :658 rejects it for qairt',
        backends=('llama_cpp_cpu', 'llama_cpp_htp'), requires_restart=True,
        allowed_values=(0, 64, 128, 256, 512, 1024)),
    'ubatch': _parameter(
        'ubatch', status=SUPPORTED, family='batching',
        evidence='turbo/native.py forwards it as n_ubatch; :658 rejects it for qairt',
        backends=('llama_cpp_cpu', 'llama_cpp_htp'), requires_restart=True,
        allowed_values=(0, 64, 128, 256, 512)),
    'context': _parameter(
        'context', status=SUPPORTED, family='context',
        evidence='turbo/native.py:656 requires qairt context to equal the compiled artifact context, '
                 'so it is a knob for llama.cpp backends only',
        backends=('llama_cpp_cpu', 'llama_cpp_htp'), requires_restart=True,
        allowed_values=(1024, 2048, 4096, 8192)),
    'spec_type': _parameter(
        'spec_type', status=SUPPORTED, family='speculation',
        evidence='turbo/native.py encodes it for the native generation config; :658 rejects any '
                 'value other than none/empty for qairt',
        backends=('llama_cpp_cpu', 'llama_cpp_htp'), requires_restart=True,
        allowed_values=('none',),
        note='Only "none" is enumerated: no other spec_type value was observed being accepted by '
             'the pinned runtime in this repository, so the rest stay unknown.'),
    'draft_tokens': _parameter(
        'draft_tokens', status=UNKNOWN, family='speculation',
        evidence='turbo/native.py forwards it as spec_n_max, but it is inert while spec_type is '
                 'none, and no repository evidence shows a working speculative configuration',
        backends=('llama_cpp_cpu', 'llama_cpp_htp'), requires_restart=True,
        mutually_exclusive_with=('spec_type',),
        note='Inert without a working spec_type; kept visible so it is never silently swept.',
        wiring='forwarded as spec_n_max, but inert while spec_type is none, so it changes nothing today'),
    'grammar': _parameter(
        'grammar', status=REQUIRES_PROTOCOL_EXTENSION, family='schema',
        evidence='eval/run_secretary_eval.py rejects a truthy grammar: "ToolWire grammar is not '
                 'valid for the production Secretary tool contract"',
        backends=(), requires_restart=True,
        note='Refused by the frozen runner. Enabling it needs owner decision 6, not a search.',
        wiring='refused by the frozen runner before any runtime call; the pinned adapter would forward it'),
    'temperature': _parameter(
        'temperature', status=REQUIRES_PROTOCOL_EXTENSION, family='sampler',
        evidence='not in the frozen runner allowed-key set; generation_protocol hardcodes '
                 'temperature 0 in eval/run_secretary_eval.py',
        backends=(), requires_restart=True,
        note='docs/qairt-sampling.md records that the QAIRT bundle declares 0.8 and that zero is a '
             'sentinel deferring to the bundle. Changing it means changing the artifact or the '
             'frozen runner, not a config value.',
        wiring='struct field exists in the ctypes generation config, no configuration path populates it'),
    'top_k': _parameter(
        'top_k', status=REQUIRES_PROTOCOL_EXTENSION, family='sampler',
        evidence='not in the frozen runner allowed-key set; no path passes it from config to the '
                 'native sampler',
        backends=(), requires_restart=True,
        note='The QAIRT bundle declares top-k 40. Reaching it requires a new artifact or an owner '
             'approved runner contract.',
        wiring='struct field exists in the ctypes generation config, no configuration path populates it'),
    'top_p': _parameter(
        'top_p', status=REQUIRES_PROTOCOL_EXTENSION, family='sampler',
        evidence='not in the frozen runner allowed-key set; the ctypes adapter sends a fixed 1.0',
        backends=(), requires_restart=True,
        wiring='struct field exists, the adapter sends a fixed 1.0 and ignores configuration'),
    'seed': _parameter(
        'seed', status=REQUIRES_PROTOCOL_EXTENSION, family='sampler',
        evidence='not in the frozen runner allowed-key set; the adapter sends -1',
        backends=(), requires_restart=True,
        wiring='struct field exists, the adapter sends a fixed -1 and ignores configuration'),
}


def parameter(name):
    """Return the declared parameter, or an explicit unknown record.

    An unrecognised name is never treated as free: it is returned as unknown so
    the guard refuses it with a reason instead of the caller assuming absence
    means permission.
    """
    known = PARAMETERS.get(name)
    if known is not None:
        return known
    return _parameter(name, status=UNKNOWN, evidence='No declared support record in this repository',
                      backends=(), requires_restart=True)


def supported_parameters(backend):
    """Names this backend can actually vary, in declaration order."""
    return tuple(name for name, spec in PARAMETERS.items()
                 if spec['support_status'] == SUPPORTED and backend in spec['backends'])


def unsupported_parameters(backend):
    """Names that exist as knobs somewhere but not for this backend."""
    return tuple(name for name, spec in PARAMETERS.items()
                 if spec['support_status'] != SUPPORTED or backend not in spec['backends'])


def families(backend):
    """Distinct families reachable on this backend."""
    seen = []
    for name in supported_parameters(backend):
        family = PARAMETERS[name]['family']
        if family not in seen:
            seen.append(family)
    return tuple(seen)


def lane(name, backend):
    """Which search lane this control belongs to on this backend.

    Lane A is the official QAIRT path, small and qualifiable. Lane B is the
    llama.cpp mass-search path where a large declarative space genuinely exists.
    Lane C holds everything the frozen runner cannot express today, kept visible
    on purpose: losing the QAIRT sampler question because the current contract
    cannot reach it would be worse than carrying it as an open item.
    """
    spec = parameter(name)
    if spec['support_status'] == SUPPORTED and backend in spec['backends']:
        return LANE_QAIRT_QUALIFIED if backend == 'qairt_npu' else LANE_LLAMA_MASS
    return LANE_DIAGNOSTIC


def admissible_for_qualified_search(name, backend):
    """True only when a tracker-backed qualified experiment may vary this."""
    spec = parameter(name)
    return spec['support_status'] in QUALIFIED_STATUSES and backend in spec['backends']


def value_errors(name, value, backend):
    """Why this value cannot enter hardware search, or an empty list."""
    spec = parameter(name)
    errors = []
    if spec['support_status'] == UNSUPPORTED:
        errors.append(name + ': unsupported control (' + spec['evidence'] + ')')
    elif spec['support_status'] == REQUIRES_PROTOCOL_EXTENSION:
        errors.append(name + ': unsupported control in the qualified lane, it requires a protocol '
                             'extension (' + spec['evidence'] + ')')
    elif spec['support_status'] == DIAGNOSTIC_ONLY:
        errors.append(name + ': diagnostic only, it may not enter a qualified experiment ('
                      + spec['evidence'] + ')')
    elif spec['support_status'] == UNKNOWN:
        errors.append(name + ': support status unknown (' + spec['evidence'] + ')')
    elif backend not in spec['backends']:
        errors.append(name + ': not supported on backend ' + str(backend))
    allowed = spec['allowed_values']
    if allowed is not None and not any(value is option or value == option and type(value) is type(option)
                                       for option in allowed):
        errors.append(name + ': value ' + repr(value) + ' is outside the declared enumeration')
    return errors


def declared_space(backend):
    """The full declarative space for one backend, hashable for provenance."""
    space = {'schema_version': SCHEMA, 'backend': backend,
             'families': {}, 'unsupported': {}}
    for name, spec in PARAMETERS.items():
        record = {'support_status': spec['support_status'], 'evidence': spec['evidence'],
                  'requires_restart': spec['requires_restart'],
                  'allowed_values': list(spec['allowed_values']) if spec['allowed_values'] else None,
                  'mutually_exclusive_with': list(spec['mutually_exclusive_with']),
                  'note': spec['note']}
        if spec['support_status'] == SUPPORTED and backend in spec['backends']:
            space['families'].setdefault(spec['family'], {})[name] = record
        else:
            space['unsupported'][name] = record
    space['space_sha256'] = digest({k: v for k, v in space.items() if k != 'space_sha256'})
    return space


def space_size(backend):
    """How many single-variable treatments this backend can express at most.

    One treatment changes exactly one field, because turbo/campaign_plan.py
    refuses a candidate whose config differs from the control in more than one
    place. The product of the enumerations is therefore not the candidate count.
    """
    total = 0
    for name in supported_parameters(backend):
        allowed = PARAMETERS[name]['allowed_values']
        total += 0 if allowed is None else len(allowed)
    return total
