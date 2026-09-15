"""Windows PDH energy-counter deltas and process memory, no third-party code.

Energy Meter Energy units are picowatt-hours. Keep rails separate: SYS is the
meter's channel name, not a claim about wall-socket or NPU-only consumption.
"""
from __future__ import annotations
import ctypes as C
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


def energy_delta(before, after, generated_tokens=None):
    duration = after['monotonic_s'] - before['monotonic_s']
    result = {'duration_s': duration, 'channels': {}, 'unit': 'picowatt-hours',
              'scope': 'full process trial including model initialization and any warmup',
              'error': before.get('error') or after.get('error')}
    for channel, first in before['channels_pwh'].items():
        last = after['channels_pwh'].get(channel)
        if last is None or last <= first or duration <= 0:
            continue
        joules = (last - first) * 3.6e-9
        result['channels'][channel] = {'energy_j': joules, 'average_power_w': joules/duration,
            'tokens_per_joule': generated_tokens/joules if generated_tokens is not None else None}
    return result


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
