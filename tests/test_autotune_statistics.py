"""Descriptive statistics only: the tests pin down what the module refuses to say.

Synthetic evaluator rows, no archives, no frozen results and no disk. The cases
that matter most here are the negative ones: an empty sample must not read as
zero, an unpaired case must not enter a count, and no call may produce anything
resembling a significance claim.
"""
import pytest

from turbo.optimizer import statistics as st


def rows(pairs, key='case_sha256'):
    return [{key: identity, 'task_success': success} for identity, success in pairs]


def test_describe_empty_is_unknown_not_zero():
    empty = st.describe([])
    assert empty['n'] == 0
    for field in ('mean', 'median', 'stddev', 'cv', 'minimum', 'maximum'):
        assert empty[field] is None
        assert not isinstance(empty[field], (int, float))


def test_describe_reports_the_usual_fields():
    summary = st.describe([2, 4, 6])
    assert summary['n'] == 3 and summary['mean'] == 4 and summary['median'] == 4
    assert summary['minimum'] == 2 and summary['maximum'] == 6
    assert summary['stddev'] == pytest.approx(2.0)
    assert summary['cv'] == pytest.approx(0.5)
    assert set(summary) == {'n', 'mean', 'median', 'stddev', 'cv', 'minimum', 'maximum'}


def test_describe_of_a_single_value_has_no_stddev():
    summary = st.describe([7])
    assert summary['n'] == 1 and summary['mean'] == 7
    assert summary['stddev'] is None and summary['cv'] is None


def test_describe_refuses_a_non_sequence():
    with pytest.raises(ValueError):
        st.describe(5)
    with pytest.raises(ValueError):
        st.describe('123')


def test_case_deltas_counts_movement_and_net():
    control = rows([('a', False), ('b', True), ('c', True), ('d', False)])
    candidate = rows([('a', True), ('b', False), ('c', True), ('d', False)])
    result = st.case_deltas(control, candidate)
    assert result['improved'] == 1 and result['regressed'] == 1
    assert result['unchanged_correct'] == 1 and result['unchanged_incorrect'] == 1
    assert result['net'] == 0
    assert result['improved_cases'] == ['a'] and result['regressed_cases'] == ['b']
    assert result['unpaired'] == []


def test_case_deltas_reports_an_unpaired_row_and_excludes_it():
    control = rows([('a', False), ('only_control', False)])
    candidate = rows([('a', True), ('only_candidate', True)])
    result = st.case_deltas(control, candidate)
    assert result['improved'] == 1 and result['net'] == 1
    assert result['improved_cases'] == ['a']
    assert {(u['side'], u['case']) for u in result['unpaired']} == {
        ('control', 'only_control'), ('candidate', 'only_candidate')}
    assert all(u['reason'].strip() for u in result['unpaired'])


def test_case_deltas_never_pairs_by_index():
    control = rows([('a', False), ('b', True)])
    reordered = rows([('b', True), ('a', True)])
    assert st.case_deltas(control, reordered)['improved_cases'] == ['a']

    disjoint = rows([('x', True), ('y', True)])
    result = st.case_deltas(control, disjoint)
    assert (result['improved'], result['regressed']) == (0, 0)
    assert result['unchanged_correct'] == 0 and result['unchanged_incorrect'] == 0
    assert len(result['unpaired']) == 4


def test_case_deltas_prefers_case_id_when_present():
    control = [{'case_id': 'dev_001', 'case_sha256': 'left', 'task_success': False}]
    candidate = [{'case_id': 'dev_001', 'case_sha256': 'right', 'task_success': True}]
    assert st.case_deltas(control, candidate)['improved_cases'] == ['dev_001']


def test_case_deltas_refuses_a_duplicate_identity():
    with pytest.raises(ValueError):
        st.case_deltas(rows([('a', True), ('a', False)]), rows([('a', True)]))


def test_case_deltas_excludes_rows_without_a_usable_flag_or_identity():
    control = [{'case_sha256': 'a', 'task_success': None}, {'task_success': True}]
    candidate = [{'case_sha256': 'a', 'task_success': True}, {'case_sha256': 'b', 'task_success': True}]
    result = st.case_deltas(control, candidate)
    assert (result['improved'], result['regressed'], result['net']) == (0, 0, 0)
    reasons = ' | '.join(u['reason'] for u in result['unpaired'])
    assert 'task_success' in reasons and 'case_sha256' in reasons


def test_case_deltas_refuses_input_that_is_not_a_list_of_rows():
    with pytest.raises(ValueError):
        st.case_deltas('rows', [])
    with pytest.raises(ValueError):
        st.case_deltas([1], [])


def test_agreement_on_identical_repeats():
    result = st.agreement([7, 7, 7])
    assert result['n_repeats'] == 3 and result['identical'] is True
    assert result['distinct_values'] == [7] and result['spread'] == 0
    assert result['describe']['mean'] == 7 and result['describe']['stddev'] == 0.0


def test_agreement_on_differing_repeats():
    result = st.agreement([7, 9, 8])
    assert result['identical'] is False
    assert result['distinct_values'] == [7, 8, 9] and result['spread'] == 2
    assert result['describe']['n'] == 3 and result['describe']['stddev'] is not None


def test_agreement_without_observations_claims_nothing():
    result = st.agreement([])
    assert result['n_repeats'] == 0 and result['identical'] is False
    assert result['spread'] is None and result['describe']['mean'] is None


def test_agreement_refuses_values_that_are_not_correct_counts():
    for bad in ([True], [-1], [2.5], ['3'], 'abc'):
        with pytest.raises(ValueError):
            st.agreement(bad)


def test_stable_wins_requires_unanimity():
    repeats = [st.case_deltas(rows([('a', False), ('b', False), ('c', True)]),
                              rows([('a', True), ('b', True), ('c', False)])),
               st.case_deltas(rows([('a', False), ('b', False), ('c', True)]),
                              rows([('a', True), ('b', False), ('c', False)]))]
    result = st.stable_wins(repeats)
    assert result['n_repeats'] == 2
    assert result['stable_wins'] == ['a']
    assert result['stable_losses'] == ['c']
    assert result['unstable'] == ['b']


def test_a_case_that_improves_and_regresses_is_never_a_stable_win():
    repeats = [{'improved_cases': ['a'], 'regressed_cases': []},
               {'improved_cases': ['a'], 'regressed_cases': ['a']}]
    result = st.stable_wins(repeats)
    assert result['stable_wins'] == [] and result['unstable'] == ['a']


def test_stable_wins_without_repeats_claims_nothing():
    result = st.stable_wins([])
    assert result == {'n_repeats': 0, 'stable_wins': [], 'stable_losses': [], 'unstable': []}


def test_stable_wins_refuses_input_that_is_not_case_deltas():
    with pytest.raises(ValueError):
        st.stable_wins([{'improved_cases': ['a']}])
    with pytest.raises(ValueError):
        st.stable_wins('deltas')


def test_significance_statement_always_refuses():
    with pytest.raises(NotImplementedError) as raised:
        st.significance_statement(improved=5, regressed=0)
    message = str(raised.value)
    assert 'no significance test has been run' in message.lower()
    assert 'explicitly chosen test' in message
