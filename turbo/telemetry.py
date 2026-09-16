"""Windows PDH energy-counter deltas and process memory, no third-party code.

Energy Meter Energy units are picowatt-hours. Keep rails separate: SYS is the
meter's channel name, not a claim about wall-socket or NPU-only consumption.
"""
from __future__ import annotations
import ctypes as C
from contextlib import contextmanager
import math
import statistics
import subprocess
import re
import sys
import time


class FileTime(C.Structure):
    _fields_ = [('low', C.c_uint32), ('high', C.c_uint32)]


class RawCounter(C.Structure):
    _fields_ = [('status', C.c_uint32), ('timestamp', FileTime),
                ('first', C.c_int64), ('second', C.c_int64), ('count', C.c_uint32)]


class MemoryCounters(C.Structure):
    _fields_ = [('cb', C.c_uint32), ('PageFaultCount', C.c_uint32)] + [
        (x, C.c_size_t) for x in ['PeakWorkingSetSize', 'WorkingSetSize',
        'QuotaPeakPagedPoolUsage', 'QuotaPagedPoolUsage', 'QuotaPeakNonPagedPoolUsage',
        'QuotaNonPagedPoolUsage', 'PagefileUsage', 'PeakPagefileUsage', 'PrivateUsage']]


class EnergyMeter:
    def __init__(self, channels=('SYS', 'GPU', 'CPU_CLUSTER_0', 'CPU_CLUSTER_1', 'CPU_CLUSTER_2')):
        self.query = C.c_void_p()
        self.counters = {}
        self.error = None
        if sys.platform != 'win32':
            self.error = 'Windows PDH unavailable on this platform'
            return
        try:
            self.pdh = C.WinDLL('pdh.dll')
            self.pdh.PdhOpenQueryW.argtypes = [C.c_wchar_p, C.c_size_t, C.POINTER(C.c_void_p)]
            self.pdh.PdhOpenQueryW.restype = C.c_uint32
            self.pdh.PdhAddEnglishCounterW.argtypes = [C.c_void_p, C.c_wchar_p, C.c_size_t, C.POINTER(C.c_void_p)]
            self.pdh.PdhAddEnglishCounterW.restype = C.c_uint32
            self.pdh.PdhCollectQueryData.argtypes = [C.c_void_p]
            self.pdh.PdhCollectQueryData.restype = C.c_uint32
            self.pdh.PdhGetRawCounterValue.argtypes = [C.c_void_p, C.POINTER(C.c_uint32), C.POINTER(RawCounter)]
            self.pdh.PdhGetRawCounterValue.restype = C.c_uint32
            self.pdh.PdhCloseQuery.argtypes = [C.c_void_p]
            self._check(self.pdh.PdhOpenQueryW(None, 0, C.byref(self.query)))
            for channel in channels:
                counter = C.c_void_p()
                code = self.pdh.PdhAddEnglishCounterW(self.query, f'\\Energy Meter({channel})\\Energy', 0, C.byref(counter))
                if code == 0:
                    self.counters[channel] = counter
        except (OSError, RuntimeError) as exc:
            self.error = str(exc)

    @staticmethod
    def _check(code):
        if code:
            raise RuntimeError(f'PDH error 0x{code:08x}')

    def sample(self):
        result = {'monotonic_s': time.perf_counter(), 'channels_pwh': {}, 'error': self.error}
        if self.error or not self.query:
            return result
        code = self.pdh.PdhCollectQueryData(self.query)
        if code:
            result['error'] = f'PDH collect error 0x{code:08x}'
            return result
        for name, handle in self.counters.items():
            raw, kind = RawCounter(), C.c_uint32()
            code = self.pdh.PdhGetRawCounterValue(handle, C.byref(kind), C.byref(raw))
            if code == 0 and raw.status in (0, 1) and raw.first >= 0:
                result['channels_pwh'][name] = raw.first
        result['monotonic_s'] = time.perf_counter()
        return result

    def close(self):
        if self.query:
            self.pdh.PdhCloseQuery(self.query)
            self.query = C.c_void_p()


class SystemPowerStatus(C.Structure):
    _fields_ = [('ac_line_status', C.c_uint8), ('battery_flag', C.c_uint8),
                ('battery_life_percent', C.c_uint8), ('reserved', C.c_uint8),
                ('battery_lifetime', C.c_uint32), ('battery_full_lifetime', C.c_uint32)]


def power_state():
    """AC/battery state via GetSystemPowerStatus; cheap, no driver work."""
    if sys.platform != 'win32':
        return {'ac_line_status': 'unavailable'}
    try:
        kernel = C.WinDLL('kernel32', use_last_error=True)
        kernel.GetSystemPowerStatus.argtypes = [C.POINTER(SystemPowerStatus)]
        kernel.GetSystemPowerStatus.restype = C.c_bool
        status = SystemPowerStatus()
        if not kernel.GetSystemPowerStatus(C.byref(status)):
            return {'ac_line_status': f'error {C.get_last_error()}',
                    'battery_percent': None, 'battery_flag': None}
        names = {0: 'battery', 1: 'ac', 255: 'unknown'}
        return {'ac_line_status': names.get(status.ac_line_status, status.ac_line_status),
                'battery_percent': None if status.battery_life_percent == 255
                                   else status.battery_life_percent,
                'battery_flag': status.battery_flag,
                'battery_saver': bool(status.reserved) if status.reserved in (0, 1) else None}
    except OSError as exc:
        return {'ac_line_status': f'error: {exc}', 'battery_percent': None,
                'battery_flag': None}


def _finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def energy_delta(before, after, generated_tokens=None):
    first_time, last_time = before.get('monotonic_s'), after.get('monotonic_s')
    duration = last_time - first_time if _finite(first_time) and _finite(last_time) else None
    if not _finite(duration):
        duration = None
    result = {'duration_s': duration, 'channels': {}, 'unit': 'picowatt-hours',
              'scope': 'full process trial including model initialization and any warmup',
              'error': before.get('error') or after.get('error')}
    if result['error'] or duration is None or duration <= 0:
        return result
    for channel, first in (before.get('channels_pwh') or {}).items():
        last = (after.get('channels_pwh') or {}).get(channel)
        if not _finite(first) or not _finite(last) or first < 0 or last <= first:
            continue
        joules = (last - first) * 3.6e-9
        if not _finite(joules) or not _finite(joules / duration):
            continue
        result['channels'][channel] = {'energy_j': joules, 'average_power_w': joules/duration,
            'tokens_per_joule': generated_tokens/joules if _finite(generated_tokens) else None}
    return result


def power_snapshot():
    """Read power state; an active plan is not the Windows power-mode overlay."""
    result = {**power_state(), 'active_scheme_guid': None, 'power_mode': None}
    result.setdefault('battery_saver', None)
    if sys.platform == 'win32':
        try:
            proc = subprocess.run(['powercfg', '/getactivescheme'], capture_output=True,
                                  text=True, timeout=5, check=False)
            match = re.search(r'[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}', proc.stdout)
            if proc.returncode == 0 and match:
                result['active_scheme_guid'] = match.group(0).lower()
        except (OSError, subprocess.TimeoutExpired):
            pass
    return result


class EnergySession:
    """SYS observations only. Subtract runtime idle only from warm tasks.

    Per-inference and warm-task energy requires at least two explicitly observed
    counter intervals. Shorter observations remain unavailable, never zero.
    Clock/meter/sleep injection exists for synthetic tests, not estimated energy.
    """
    @staticmethod
    def validate_protocol(protocol):
        if not isinstance(protocol, dict):
            raise ValueError('energy protocol must be an object')
        if protocol.get('channel') != 'SYS':
            raise ValueError('energy protocol channel must be SYS')
        for key in ('counter_resolution_s', 'idle_window_s', 'idle_max_cv'):
            value = protocol.get(key)
            if not _finite(value) or value <= 0:
                raise ValueError(f'{key} must be finite and positive')
        if protocol['idle_window_s'] < 10 * protocol['counter_resolution_s']:
            raise ValueError('idle_window_s must span at least ten counter intervals')
        for key, minimum in (('idle_repeats', 3), ('warmup_count', 1)):
            value = protocol.get(key)
            if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
                raise ValueError(f'{key} must be an integer >= {minimum}')
        for key in ('counter_resolution_evidence', 'power_mode'):
            if not isinstance(protocol.get(key), str) or not protocol[key].strip():
                raise ValueError(f'{key} requires an explicit observation')
        return dict(protocol)

    def __init__(self, protocol, meter=None, clock=None, sleep=None):
        self.protocol = self.validate_protocol(protocol)
        self.meter = meter if meter is not None else EnergyMeter()
        self.clock = clock or time.perf_counter
        self.sleep = sleep or time.sleep
        self.idle_power_w = None
        self.last_inference = None

    def _sample(self):
        try:
            sample = dict(self.meter.sample())
            sample['monotonic_s'] = self.clock()
            invalid = []
            def sanitize(value, path):
                if isinstance(value, float) and not math.isfinite(value):
                    invalid.append(path)
                    return None
                if isinstance(value, dict):
                    return {k: sanitize(v, f'{path}.{k}') for k, v in value.items()}
                if isinstance(value, (list, tuple)):
                    return [sanitize(v, f'{path}[{i}]') for i, v in enumerate(value)]
                return value
            sample = sanitize(sample, 'sample')
            if invalid:
                sample['invalid_numeric_fields'] = invalid
                sample['error'] = sample.get('error') or 'nonfinite raw observation'
            return sample
        except Exception as exc:
            timestamp = self.clock()
            return {'monotonic_s': timestamp if _finite(timestamp) else None,
                    'channels_pwh': {}, 'error': str(exc)}

    @contextmanager
    def measure(self, scope):
        result = {'scope': scope, 'channel': 'SYS', 'raw_before': self._sample(),
                  'raw_after': None, 'gross_energy_j': None, 'duration_s': None,
                  'avg_power_w': None, 'net_energy_j': None, 'idle_power_w_used': None,
                  'unavailable_reason': None}
        try:
            yield result
        finally:
            result['raw_after'] = self._sample()
            delta = energy_delta(result['raw_before'], result['raw_after'])
            result['duration_s'] = delta['duration_s']
            channel = delta['channels'].get('SYS')
            if delta['error']:
                result['unavailable_reason'] = 'counter_error: ' + str(delta['error'])
            elif not channel:
                result['unavailable_reason'] = 'missing_stale_reset_or_invalid_counter'
            elif scope in ('inference', 'warm_task') and delta['duration_s'] < 2 * self.protocol['counter_resolution_s']:
                result['unavailable_reason'] = 'duration_below_two_counter_intervals'
            else:
                result['gross_energy_j'] = channel['energy_j']
                result['avg_power_w'] = channel['average_power_w']
                if scope == 'warm_task':
                    if self.idle_power_w is None:
                        result['unavailable_reason'] = 'stable_runtime_idle_unavailable'
                    else:
                        result['idle_power_w_used'] = self.idle_power_w
                        net = channel['energy_j'] - self.idle_power_w * delta['duration_s']
                        if net < 0:
                            result['unavailable_reason'] = 'negative_net_energy'
                        else:
                            result['net_energy_j'] = net
            if scope == 'inference':
                self.last_inference = result

    def measure_idle(self, kind):
        if kind not in ('platform', 'runtime'):
            raise ValueError('idle kind must be platform or runtime')
        samples = []
        for _ in range(self.protocol['idle_repeats']):
            with self.measure(kind + '_idle') as sample:
                self.sleep(self.protocol['idle_window_s'])
            samples.append(sample)
        powers = [s['avg_power_w'] for s in samples if s['avg_power_w'] is not None]
        complete = len(powers) == len(samples)
        mean = statistics.mean(powers) if complete else None
        cv = statistics.pstdev(powers) / mean if mean is not None and mean > 0 else None
        stable = cv is not None and cv <= self.protocol['idle_max_cv']
        if kind == 'runtime':
            self.idle_power_w = mean if stable else None
        return {'kind': kind, 'samples': samples, 'mean_power_w': mean, 'cv': cv,
                'stable': stable, 'channel': 'SYS'}

    def close(self):
        self.meter.close()


class ProcessMemory:
    def __init__(self, pid):
        self.handle = None
        if sys.platform != 'win32':
            return
        self.kernel = C.WinDLL('kernel32', use_last_error=True)
        self.kernel.OpenProcess.argtypes = [C.c_uint32, C.c_bool, C.c_uint32]
        self.kernel.OpenProcess.restype = C.c_void_p
        self.kernel.CloseHandle.argtypes = [C.c_void_p]
        self.psapi = C.WinDLL('psapi', use_last_error=True)
        self.psapi.GetProcessMemoryInfo.argtypes = [C.c_void_p, C.POINTER(MemoryCounters), C.c_uint32]
        self.psapi.GetProcessMemoryInfo.restype = C.c_bool
        self.handle = self.kernel.OpenProcess(0x0410, False, pid)

    def sample(self):
        if not self.handle:
            return None
        counters = MemoryCounters()
        counters.cb = C.sizeof(counters)
        if not self.psapi.GetProcessMemoryInfo(self.handle, C.byref(counters), counters.cb):
            return None
        return {'peak_working_set_mb': counters.PeakWorkingSetSize / 1024**2,
                'working_set_mb': counters.WorkingSetSize / 1024**2,
                'private_mb': counters.PrivateUsage / 1024**2}

    def close(self):
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None


def _probe_main():
    """Observe update gaps only; this does not certify hardware resolution."""
    import argparse
    import json
    from pathlib import Path
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--probe-seconds', type=float, default=60)
    parser.add_argument('--sample-interval', type=float, default=0.25)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not all(_finite(x) and x > 0 for x in (args.probe_seconds, args.sample_interval)):
        parser.error('durations must be finite and positive')
    meter, samples, update_times = EnergyMeter(), [], []
    start, previous = time.perf_counter(), None
    try:
        while True:
            sample = meter.sample()
            samples.append(sample)
            current = sample['channels_pwh'].get('SYS') if not sample.get('error') else None
            if current is not None and previous is not None and current > previous:
                update_times.append(sample['monotonic_s'])
            previous = current
            if time.perf_counter() - start >= args.probe_seconds:
                break
            time.sleep(args.sample_interval)
    finally:
        meter.close()
    output = {'kind': 'counter_update_probe', 'channel': 'SYS', 'platform': sys.platform,
              'power': power_snapshot(), 'requested_duration_s': args.probe_seconds,
              'sample_interval_s': args.sample_interval, 'raw_samples': samples,
              'observed_update_gaps_s': [b-a for a,b in zip(update_times, update_times[1:])],
              'caveat': 'Observed update gaps depend on polling and workload; not guaranteed counter resolution.'}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as handle:
        json.dump(output, handle, indent=2, allow_nan=False)


if __name__ == '__main__':
    _probe_main()
