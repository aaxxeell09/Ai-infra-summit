"""The one place a model influences the loop, and the narrow way it may do so.

A model here does not choose a configuration, start a run or approve anything.
It proposes a search family; that proposal is schema-checked, mapped onto the
declared enumerations, and handed to the guard, which decides alone. The path
from a model's words to hardware therefore runs through two refusals that the
model cannot argue with, and an idea the contract cannot express stays in the
record as an inadmissible research item rather than disappearing.

The critic runs off the hardware path on purpose. A critique is advisory, so
waiting for one would convert an API latency into idle device time, which is the
single cost a bounded session cannot recover.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from turbo.optimizer import critic as critic_module, guard, llm, mutation, proposer

SCHEMA = 'local-turbo.autotune-advisor.v1'

#: Counter names the console and the report both use. They are separate because
#: a proposed hypothesis, an admissible one and a candidate that reached
#: hardware are three different quantities and a report that merges them
#: overstates what the model contributed.
COUNTERS = ('LLM_PROPOSER_CALLS', 'LLM_CRITIC_CALLS', 'LLM_HYPOTHESES',
            'LLM_ADMISSIBLE_HYPOTHESES', 'LLM_REJECTED_HYPOTHESES', 'LLM_API_WAIT_SECONDS')


def counters(state):
    record = state.setdefault('llm', {name: 0 for name in COUNTERS})
    for name in COUNTERS:
        record.setdefault(name, 0)
    record.setdefault('hypotheses', [])
    record.setdefault('findings', [])
    record.setdefault('failures', [])
    return record


class Advisor:
    """Proposer and critic, wired to the loop, safe when either is absent."""

    def __init__(self, state, *, proposer_client=None, critic_client=None, cache=None,
                 console=None, timeout_s=60, max_hypotheses=5):
        self.state = state
        self.proposer_client = proposer_client
        self.critic_client = critic_client
        self.cache = cache
        self.console = console
        self.timeout_s = timeout_s
        self.max_hypotheses = max_hypotheses
        self._pending = []
        counters(state)

    # ------------------------------------------------------------- reporting

    @property
    def available(self):
        return {'proposer': self.proposer_client is not None,
                'critic': self.critic_client is not None}

    def _charge(self, seconds):
        record = counters(self.state)
        record['LLM_API_WAIT_SECONDS'] = round(record['LLM_API_WAIT_SECONDS']
                                               + float(seconds or 0.0), 3)

    def _note(self, message):
        if self.console is not None:
            self.console.warn(message)

    def _record_failure(self, where, exc):
        counters(self.state)['failures'].append({'where': where, 'error': type(exc).__name__,
                                                 'detail': str(exc)[:500]})
        self._charge(getattr(exc, 'elapsed_s', 0.0))
        self._note(where + ' unavailable: ' + type(exc).__name__)

    # -------------------------------------------------------------- proposer

    def propose(self, *, backend, remaining_minutes, phase):
        """Ask for hypotheses. Returns [] when no proposer is configured.

        A missing credential is not a failure of the session: the deterministic
        search does not depend on a model, so this returns an empty list and the
        loop carries on generating from the declared enumerations.
        """
        if self.proposer_client is None:
            return []
        record = counters(self.state)
        record['LLM_PROPOSER_CALLS'] += 1
        try:
            hypotheses = proposer.propose(
                self.proposer_client, self.state, backend=backend,
                remaining_minutes=remaining_minutes, phase=phase, cache=self.cache,
                timeout_s=self.timeout_s, max_hypotheses=self.max_hypotheses)
        except (llm.LLMUnavailable, llm.LLMProtocolError) as exc:
            self._record_failure('proposer', exc)
            return []
        for hypothesis in hypotheses:
            self._charge((hypothesis.get('source') or {}).get('_elapsed_s'))
        record['LLM_HYPOTHESES'] += len(hypotheses)
        admissible = [h for h in hypotheses if h.get('admissible')]
        record['LLM_ADMISSIBLE_HYPOTHESES'] += len(admissible)
        record['LLM_REJECTED_HYPOTHESES'] += len(hypotheses) - len(admissible)
        record['hypotheses'].extend(
            {'family': h.get('family'), 'mechanism': h.get('mechanism'),
             'search_space': h.get('search_space'), 'admissible': bool(h.get('admissible')),
             'reason': h.get('reason'), 'phase': phase} for h in hypotheses)
        if self.console is not None:
            for hypothesis in hypotheses:
                if hypothesis.get('admissible'):
                    self.console.event('LLM', str(hypothesis.get('family'))[:10],
                                       'admissible: ' + ', '.join(hypothesis['search_space']))
                else:
                    self.console.event('LLM', str(hypothesis.get('family'))[:10],
                                       'inadmissible research idea: '
                                       + str(hypothesis.get('reason'))[:90])
        return hypotheses

    def candidates_from(self, hypotheses, *, control_config, backend, start_index=1):
        """Map admissible hypotheses onto bounded, deterministic candidates.

        Nothing the model wrote executes. Its parameter names and values are
        looked up in the declared enumerations, anything outside them is
        rejected with a reason and never clamped inward, and what survives is an
        ordinary candidate that the guard still has to admit.
        """
        built, rejected, index = [], [], start_index
        for hypothesis in hypotheses:
            if not hypothesis.get('admissible'):
                rejected.append((hypothesis.get('family'), None, hypothesis.get('reason')))
                continue
            candidates, refused = mutation.from_llm_space(
                control_config, backend, hypothesis['search_space'], start_index=index)
            for candidate in candidates:
                candidate['origin'] = 'llm'
                candidate['hypothesis'] = (str(hypothesis.get('mechanism'))
                                           + ' (proposed for family '
                                           + str(hypothesis.get('family')) + '; abandon if '
                                           + str(hypothesis.get('abandon_if')) + ')')
            built.extend(candidates)
            rejected.extend(refused)
            index += len(candidates)
        return built, rejected

    def families_to_explore(self, hypotheses, *, backend, fallback):
        """Which declared families the model's admissible ideas point at.

        The model cannot invent a family. It can only move attention between
        families that already exist for this backend, so an unrecognised name
        falls back rather than creating a new search space.
        """
        from turbo.optimizer import search_space as space
        declared = space.families(backend)
        wanted = []
        for hypothesis in hypotheses:
            if not hypothesis.get('admissible'):
                continue
            for name in hypothesis['search_space']:
                family = space.parameter(name)['family']
                if family in declared and family not in wanted:
                    wanted.append(family)
        return tuple(wanted) or tuple(fallback)

    # ---------------------------------------------------------------- critic

    def submit_critique(self, candidates, *, phase, hypotheses=()):
        """Start a critique without waiting for it. Returns a handle or None."""
        if self.critic_client is None or not candidates:
            return None
        payload = {'phase': phase,
                   'control': self.state['current_control'].get('name'),
                   'candidates': [{'candidate_id': c.get('candidate_id'),
                                   'family': c.get('family'), 'variable': c.get('variable'),
                                   'treatment': c.get('treatment'),
                                   'origin': c.get('origin', 'deterministic')}
                                  for c in candidates[:40]],
                   'hypotheses': [{'family': h.get('family'), 'mechanism': h.get('mechanism'),
                                   'admissible': bool(h.get('admissible'))}
                                  for h in hypotheses]}
        counters(self.state)['LLM_CRITIC_CALLS'] += 1
        try:
            handle = critic_module.submit(self.critic_client, payload, cache=self.cache,
                                          timeout_s=self.timeout_s)
        except (llm.LLMUnavailable, llm.LLMProtocolError, RuntimeError) as exc:
            self._record_failure('critic', exc)
            return None
        self._pending.append(handle)
        return handle

    def collect_critiques(self, *, wait_s=None):
        """Harvest whatever critiques are ready. Never blocks by default."""
        findings, still_pending = [], []
        for handle in self._pending:
            try:
                result = critic_module.result(handle, wait_s=wait_s)
            except (llm.LLMUnavailable, llm.LLMProtocolError) as exc:
                self._record_failure('critic', exc)
                continue
            if result is None:
                still_pending.append(handle)
                continue
            self._charge((result.get('source') or {}).get('_elapsed_s'))
            findings.extend(result['findings'])
            counters(self.state)['findings'].extend(result['findings'])
        self._pending = still_pending
        if self.console is not None:
            for finding in findings:
                self.console.event('CRITIC', str(finding.get('kind'))[:10],
                                   str(finding.get('severity')) + ': '
                                   + str(finding.get('detail'))[:80])
        return findings

    def deprioritise(self, candidates, findings):
        """Apply advisory findings without ever granting permission.

        A blocking finding removes a candidate from this round. It cannot admit
        one: guard.check has already run and will run again, and a critic that
        could wave a candidate through would be a second, weaker gate beside the
        real one.
        """
        blocked = {f.get('candidate_id') for f in findings
                   if f.get('severity') == critic_module.BLOCK and f.get('candidate_id')}
        if not blocked:
            return candidates, []
        kept = [c for c in candidates if c.get('candidate_id') not in blocked]
        dropped = [c for c in candidates if c.get('candidate_id') in blocked]
        return kept, dropped

    def report_counters(self):
        record = counters(self.state)
        return {name: record[name] for name in COUNTERS}
