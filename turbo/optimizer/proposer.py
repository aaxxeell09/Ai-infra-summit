"""Hypothesis generation: the only place a model is allowed to invent anything.

The proposer sees a compact digest of the session, never the repository and
never a case. Two reasons. Heldout cases and golden answers must stay
unreachable from the optimization loop, and a digest that fits in a page forces
the model to reason about what this session has already learned instead of
rediscovering the codebase every call.

What comes back is a hypothesis, not a decision. An idea that names a parameter
this backend cannot vary stays in the list marked inadmissible, because a
research direction that is currently unreachable is still worth recording. Only
the mutation engine and turbo.optimizer.guard decide what occupies hardware.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from turbo.optimizer import guard, search_space as space
from turbo.optimizer.api_status import classify_exception
from turbo.optimizer.llm import (LLMClient, LLMProtocolError, LLMUnavailable, STATUS_AVAILABLE,
                                 STATUS_UNAVAILABLE, call_json, credential_status, require,
                                 require_keys, require_text, response_meta)

SCHEMA = 'local-turbo.autotune-proposal.v1'

ANTHROPIC_KEY_VAR = 'ANTHROPIC_API_KEY'
ANTHROPIC_MODEL_VAR = 'ANTHROPIC_MODEL'
ANTHROPIC_WORKSPACE_VAR = 'ANTHROPIC_WORKSPACE_ID'

DEFAULT_RECENT_OUTCOMES = 8
DEFAULT_MAX_HYPOTHESES = 5

HYPOTHESIS_KEYS = ('family', 'mechanism', 'why_now', 'search_space', 'expected_signal', 'abandon_if')

#: Substrings that must never appear as a key anywhere in the digest. This is a
#: structural check, not a taste check: it is cheap, it runs on every call, and
#: it turns a future careless addition into a loud failure instead of a leak.
FORBIDDEN_DIGEST_KEYS = ('prompt', 'golden', 'expected_output', 'heldout', 'held_out',
                         'case_text', 'answer', 'transcript', 'dataset_rows')

SYSTEM_PROMPT = (
    'You propose configuration hypotheses for a bounded autotune session on an edge inference '
    'stack. You are given a compact session digest, never source code and never evaluation cases.\n'
    'Rules you must obey:\n'
    '1. Exactly one configuration field may change per treatment. Never propose a combination.\n'
    '2. Only values from the bounded enumerations in the digest are measurable.\n'
    '3. Never propose anything about energy, and never claim a measured number: the digest holds '
    'every number you are allowed to refer to.\n'
    '4. A mechanism is a causal claim about the runtime, not a restatement of the parameter name.\n'
    'Answer with a single JSON object and nothing else, no prose and no code fence:\n'
    '{"hypotheses":[{"family":str,"mechanism":str,"why_now":str,'
    '"search_space":{param:[values]},"expected_signal":str,"abandon_if":str}]}'
)


class AnthropicClient(LLMClient):
    """Anthropic adapter. The SDK reads the key from the environment itself.

    The key value therefore never passes through TurboLab code, and the model
    version is never hardcoded: a session that does not declare one fails with a
    message instead of quietly measuring against whatever the default is today.
    """

    name = 'anthropic'

    def __init__(self, *, model=None, env=os.environ, max_output_tokens=4096):
        self.status = credential_status(ANTHROPIC_KEY_VAR, env)
        declared = model if model is not None else env.get(ANTHROPIC_MODEL_VAR)
        self.model = declared if isinstance(declared, str) and declared.strip() else None
        workspace = env.get(ANTHROPIC_WORKSPACE_VAR)
        self.workspace_id = workspace.strip() if isinstance(workspace, str) and workspace.strip() else None
        self.max_output_tokens = max_output_tokens
        self._sdk_client = None

    def complete(self, system, user, *, timeout_s):
        if self.status != STATUS_AVAILABLE:
            raise LLMUnavailable(ANTHROPIC_KEY_VAR + ' is not set, so no Anthropic call is possible', category='key_unavailable')
        if not self.model:
            raise LLMUnavailable(ANTHROPIC_MODEL_VAR + ' is not set; TurboLab never assumes a model version', category='model_error')
        try:
            import anthropic
        except ImportError as exc:
            raise LLMUnavailable('The anthropic SDK is not installed in this environment', category='sdk_unavailable') from None
        try:
            if self._sdk_client is None:
                options = {'max_retries': 0}
                if self.workspace_id:
                    options['default_headers'] = {'anthropic-workspace-id': self.workspace_id}
                self._sdk_client = anthropic.Anthropic(**options)
            message = self._sdk_client.messages.create(
                model=self.model, max_tokens=self.max_output_tokens, system=system,
                messages=[{'role': 'user', 'content': user}], timeout=timeout_s)
        except Exception as exc:
            category = classify_exception(exc)
            raise LLMUnavailable('Anthropic API request failed: ' + category, category=category) from None

        blocks = [b.text for b in getattr(message, 'content', []) if getattr(b, 'type', None) == 'text']
        if not blocks:
            raise LLMProtocolError('Anthropic response carried no text block')
        return ''.join(blocks)


def _session_start_control(state):
    history = state.get('controls_history') or []
    return history[0] if history else state.get('current_control') or {}


def control_drift(state):
    """Fields of the current control that differ from the session start control."""
    start = (_session_start_control(state).get('config') or {})
    current = (state.get('current_control') or {}).get('config') or {}
    drift = {}
    for field in guard.changed_fields(start, current):
        drift[field] = {'session_start': start.get(field), 'now': current.get(field)}
    return drift


def _meaningful_outcomes(state, limit):
    """The last stage outcomes that carried information, oldest first.

    An outcome with no verdict teaches nothing and would only crowd out a real
    one, so it is dropped rather than padded into the window.
    """
    flattened = []
    for config_hash, entry in (state.get('tested_exact') or {}).items():
        for observation in entry.get('observations') or []:
            outcome = observation.get('outcome')
            if not isinstance(outcome, str) or not outcome.strip() or outcome == 'skipped':
                continue
            flattened.append({'at': observation.get('at') or '', 'config_hash': config_hash,
                              'family': entry.get('family'), 'variable': entry.get('variable'),
                              'stage': observation.get('stage'), 'outcome': outcome,
                              'net_cases': observation.get('net_cases')})
    flattened.sort(key=lambda item: (item['at'], item['config_hash'], str(item['stage'])))
    window = flattened[-limit:] if limit and limit > 0 else []
    return [{k: v for k, v in item.items() if k != 'at'} for item in window]


def _explored_parameters(state):
    """Parameter names this session already put on hardware, however recorded."""
    explored = set()
    for entry in state.get('search_spaces_attempted') or []:
        if isinstance(entry, str):
            explored.add(entry)
        elif isinstance(entry, dict):
            for key in ('parameter', 'variable', 'family', 'name'):
                value = entry.get(key)
                if isinstance(value, str):
                    explored.add(value)
    for entry in (state.get('tested_exact') or {}).values():
        variable = entry.get('variable')
        if isinstance(variable, str):
            explored.add(variable)
    return explored


def digest_leak_reasons(payload, path='digest'):
    """Every place the digest names case-level content. Empty means clean."""
    reasons = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            lowered = str(key).lower()
            if any(marker in lowered for marker in FORBIDDEN_DIGEST_KEYS):
                reasons.append(path + '.' + str(key) + ' may carry case content')
            reasons.extend(digest_leak_reasons(value, path + '.' + str(key)))
    elif isinstance(payload, list):
        for index, item in enumerate(payload):
            reasons.extend(digest_leak_reasons(item, path + '[' + str(index) + ']'))
    return reasons


def digest_for_proposer(state, *, backend, remaining_minutes, phase, recent=DEFAULT_RECENT_OUTCOMES):
    """A compact picture of the session, with no case content in it at all.

    Carries the control and how it drifted, the recent meaningful outcomes,
    family and failure-taxonomy counts, which declared spaces this backend has
    and which are already explored, the remaining budget, the phase, and the
    single-changed-field constraint with its bounded values. Case identifiers,
    case prompts, golden answers, heldout text and heldout results are all
    absent by construction and the result is checked before it is returned.
    """
    supported = space.supported_parameters(backend)
    mutable = tuple(name for name in supported if name in guard.V1_MUTABLE_KEYS)
    explored = _explored_parameters(state)
    families = {}
    for name, record in (state.get('families') or {}).items():
        deltas = record.get('net_case_deltas') or []
        families[name] = {'attempted': record.get('attempted'), 'survived_s2': record.get('survived_s2'),
                          'survived_s3': record.get('survived_s3'), 'dev35_wins': record.get('dev35_wins'),
                          'confirmed_wins': record.get('confirmed_wins'),
                          'observations_with_net_delta': len(deltas),
                          'hardware_seconds_spent': record.get('hardware_seconds_spent')}

    payload = {
        'schema_version': SCHEMA,
        'session_id': state.get('session_id'),
        'backend': backend,
        'phase': phase,
        'remaining_minutes': remaining_minutes,
        'budget_minutes': state.get('budget_minutes'),
        'energy_commissioned': bool(state.get('energy_commissioned')),
        'control': {'name': (state.get('current_control') or {}).get('name'),
                    'changed_versus_session_start': control_drift(state),
                    'promotions': (state.get('counters') or {}).get('promotions')},
        'recent_outcomes': _meaningful_outcomes(state, recent),
        'families': families,
        'failure_taxonomy': dict(state.get('failure_history') or {}),
        'search_space': {
            'space_size': space.space_size(backend),
            'declared_families': {family: [name for name in space.supported_parameters(backend)
                                           if space.PARAMETERS[name]['family'] == family]
                                  for family in space.families(backend)},
            'explored': sorted(name for name in supported if name in explored),
            'unexplored': sorted(name for name in supported if name not in explored),
            'not_available_on_this_backend': sorted(space.unsupported_parameters(backend)),
        },
        'qualified_lane': {
            'single_changed_field': True,
            'mutable_keys': list(mutable),
            'bounded_values': {name: list(space.PARAMETERS[name]['allowed_values'] or ())
                               for name in mutable},
            'note': 'turbo/campaign_plan.py refuses a candidate that differs from the control in '
                    'more than one field, and any value outside the enumeration is rejected before '
                    'it reaches hardware.',
        },
        'counters': {k: v for k, v in (state.get('counters') or {}).items()},
        'split': state.get('split'),
    }
    reasons = digest_leak_reasons(payload)
    if reasons:
        raise ValueError('Proposer digest would leak case content: ' + '; '.join(reasons))
    return payload


def admissibility(hypothesis, backend):
    """Whether this hypothesis could be turned into a runnable treatment.

    Inadmissible is a label, never a deletion: the idea stays visible in the
    session record so a human can see what the model wanted to try and why the
    current hardware contract refuses it.
    """
    declared = hypothesis['search_space']
    if not declared:
        return False, 'Hypothesis declares no parameter to vary'
    reasons = []
    for name, values in declared.items():
        if name not in guard.V1_MUTABLE_KEYS:
            reasons.append(name + ' is outside the V1 mutable allowlist')
        if name not in space.supported_parameters(backend):
            reasons.append(name + ' is not a supported control on backend ' + str(backend)
                           + ' (' + space.parameter(name)['evidence'] + ')')
            continue
        for value in values:
            reasons.extend(space.value_errors(name, value, backend))
    if len(declared) > 1:
        # Several parameters in one hypothesis is legal as a research idea, but
        # the planner can only ever run them as separate single-field
        # treatments, so it is recorded rather than silently split here.
        reasons.append('Hypothesis names ' + str(len(declared))
                       + ' parameters; each would have to run as its own single-field treatment')
    if reasons:
        return False, '; '.join(sorted(set(reasons)))
    return True, None


def validate(response, *, backend, max_hypotheses=DEFAULT_MAX_HYPOTHESES):
    """Strict schema check, then admissibility labelling. Nothing is coerced."""
    require(response, dict, 'proposal response')
    if 'hypotheses' not in response:
        raise LLMProtocolError('proposal response is missing hypotheses')
    raw = response['hypotheses']
    require(raw, list, 'hypotheses')
    if len(raw) > max_hypotheses:
        raise LLMProtocolError('Proposal returned ' + str(len(raw)) + ' hypotheses, limit is '
                               + str(max_hypotheses))
    validated = []
    for index, item in enumerate(raw):
        where = 'hypotheses[' + str(index) + ']'
        require_keys(item, HYPOTHESIS_KEYS, where)
        require_text(item['family'], where + '.family')
        require_text(item['mechanism'], where + '.mechanism')
        require_text(item['why_now'], where + '.why_now')
        require_text(item['expected_signal'], where + '.expected_signal')
        require_text(item['abandon_if'], where + '.abandon_if')
        declared = require(item['search_space'], dict, where + '.search_space')
        for name, values in declared.items():
            require(name, str, where + '.search_space key')
            require(values, list, where + '.search_space.' + name)
            if not values:
                raise LLMProtocolError(where + '.search_space.' + name + ' enumerates no value')
        hypothesis = dict(item)
        hypothesis['admissible'], hypothesis['reason'] = admissibility(hypothesis, backend)
        validated.append(hypothesis)
    return validated


def render_user_prompt(session_digest, *, max_hypotheses):
    import json
    return ('Session digest:\n'
            + json.dumps(session_digest, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False)
            + '\n\nPropose at most ' + str(max_hypotheses) + ' hypotheses as the declared JSON object.')


def propose(client, state, *, backend, remaining_minutes, phase, cache=None, timeout_s=60,
            max_hypotheses=DEFAULT_MAX_HYPOTHESES, recent=DEFAULT_RECENT_OUTCOMES, retries=1):
    """Ask for hypotheses and return them validated and labelled.

    Raises LLMProtocolError when the answer is not the declared object, and
    LLMUnavailable when there was no answer at all. Each returned hypothesis
    carries ``admissible``, ``reason`` and a ``source`` record holding the model
    identity and the timing the scheduler charges to API wait.
    """
    session_digest = digest_for_proposer(state, backend=backend, remaining_minutes=remaining_minutes,
                                         phase=phase, recent=recent)
    user = render_user_prompt(session_digest, max_hypotheses=max_hypotheses)
    response = call_json(client, SYSTEM_PROMPT, user, cache=cache, timeout_s=timeout_s, retries=retries)
    hypotheses = validate(response, backend=backend, max_hypotheses=max_hypotheses)
    meta = response_meta(response)
    for hypothesis in hypotheses:
        hypothesis['source'] = {'client': getattr(client, 'name', None),
                                'model': getattr(client, 'model', None), 'phase': phase, **meta}
    return hypotheses
