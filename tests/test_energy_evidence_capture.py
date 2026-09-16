"""Synthetic PDH evidence only; no target-device measurement or native loading."""
import ctypes as C
from types import SimpleNamespace

import pytest
import turbo.telemetry as telemetry
import eval.energy_measurement as lifecycle


def meter_with_fake_pdh(read_status=0, counter_status=0, collect_status=0):
    meter = telemetry.EnergyMeter.__new__(telemetry.EnergyMeter)
    meter.query = C.c_void_p(1)
    meter.counters = {'SYS': C.c_void_p(2)}
    meter.error = None
    def read(handle, kind_pointer, raw_pointer):
        raw = raw_pointer._obj
        raw.status = counter_status
        raw.timestamp.high, raw.timestamp.low = 3, 7
        raw.first, raw.second, raw.count = 123456, 42, 1
        kind_pointer._obj.value = 0x100
        return read_status
    meter.pdh = SimpleNamespace(PdhCollectQueryData=lambda query: collect_status,
                                PdhGetRawCounterValue=read)
    return meter


def test_raw_pdh_metadata_and_host_bounds_are_retained(monkeypatch):
    times = iter([10., 11., 12.])
    monkeypatch.setattr(telemetry.time, 'perf_counter', lambda: next(times))
    sample = meter_with_fake_pdh().sample()
    assert sample['monotonic_s'] == 11.  # existing calculation timestamp retained
    assert sample['host_collection_start_s'] == 10.
    assert sample['host_collection_end_s'] == 12.
    assert sample['channels_pwh'] == {'SYS': 123456}
    assert sample['pdh_collect_status'] == 0
    assert sample['raw_counters']['SYS'] == {
        'read_status': 0, 'counter_status': 0, 'counter_type': 0x100,
        'source_timestamp_filetime_100ns': (3 << 32) | 7,
        'first_value': 123456, 'second_value': 42, 'multi_count': 1}


@pytest.mark.parametrize('read_status,counter_status', [(5, 0), (0, 5)])
def test_bad_counter_metadata_is_retained_without_valid_energy(read_status, counter_status):
    sample = meter_with_fake_pdh(read_status, counter_status).sample()
    assert sample['channels_pwh'] == {}
    raw = sample['raw_counters']['SYS']
    assert raw['read_status'] == read_status
    assert raw['counter_status'] == (None if read_status else counter_status)
    assert raw['source_timestamp_filetime_100ns'] == (None if read_status else (3 << 32) | 7)
    assert sample['host_collection_end_s'] >= sample['host_collection_start_s']


def test_collection_error_retains_host_bounds():
    sample = meter_with_fake_pdh(collect_status=5).sample()
    assert sample['pdh_collect_status'] == 5
    assert sample['error']
    assert sample['raw_counters'] == {}
    assert sample['host_collection_end_s'] >= sample['host_collection_start_s']


def test_scheme_is_not_reported_as_observed_overlay(monkeypatch):
    monkeypatch.setattr(telemetry.sys, 'platform', 'win32')
    monkeypatch.setattr(telemetry, 'power_state', lambda: {'ac_line_status': 'ac'})
    monkeypatch.setattr(telemetry.subprocess, 'run', lambda *a, **k: SimpleNamespace(
        returncode=0, stdout='Power Scheme GUID: 381b4222-f694-41f0-9685-ff5bb260df2e'))
    sample = telemetry.power_snapshot()
    assert sample['active_scheme_guid'] == '381b4222-f694-41f0-9685-ff5bb260df2e'
    assert sample['power_mode'] is None
    assert sample['observed_power_mode'] is None
    assert 'not queried' in sample['observed_power_mode_unavailable_reason']


def test_measurement_explicitly_distinguishes_declared_overlay(monkeypatch, tmp_path):
    from tests.test_energy_measurement import test_lifecycle_separates_load_warmup_idle_and_tasks
    original = lifecycle.measured_run
    captured = {}
    def record(*args, **kwargs):
        rows = original(*args, **kwargs)
        captured.update(args[1]['energy_measurement']['signature']['power_condition'])
        return rows
    monkeypatch.delenv('GENIEX_QAIRT_LIB', raising=False)
    monkeypatch.setattr(lifecycle, 'measured_run', record)
    test_lifecycle_separates_load_warmup_idle_and_tasks(monkeypatch, tmp_path)
    assert captured['declared_power_mode'] == captured['power_mode'] == 'synthetic-mode'
    assert captured['observed_power_mode'] is None
    assert 'not queried' in captured['observed_power_mode_unavailable_reason']


@pytest.mark.parametrize('override', ['', '/untracked/plugin.dll'])
def test_external_qairt_override_rejected_before_sdk_work(monkeypatch, override):
    monkeypatch.setenv('GENIEX_QAIRT_LIB', override)
    monkeypatch.setattr(lifecycle, 'validate_protocol', lambda p: p)
    monkeypatch.setattr(lifecycle.platform, 'system', lambda: 'Windows')
    def forbidden(*args, **kwargs):
        pytest.fail('SDK or meter work happened before rejecting external runtime override')
    monkeypatch.setattr(lifecycle, 'sdk_fingerprints', forbidden)
    monkeypatch.setattr(lifecycle, 'EnergySession', forbidden)
    with pytest.raises(ValueError, match='GENIEX_QAIRT_LIB'):
        lifecycle.measured_run({}, {}, [], None, forbidden, None, {}, 1, forbidden, forbidden)
