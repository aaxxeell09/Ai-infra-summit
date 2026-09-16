"""Lane C explicit-sampler diagnostic v1; no production readback provider exists.

This module is not imported by the frozen runner or TurboLab Lane A. The empty
trusted-adapter registry is deliberate: a config assertion or source-derived
expectation is not a native effective-sampler readback.
"""
import ctypes
import math

from turbo.native import NativeModel, geniex_LlmGenerateInput, geniex_SamplerConfig

PROTOCOL = 'qairt-explicit-sampler-diagnostic-v1'
FIELDS = ('temperature', 'top_p', 'top_k', 'seed')
TRUSTED_READBACK_ADAPTERS = ()  # Add only an audited native implementation, never config data.


class SamplerVerificationError(ValueError):
    pass


def encode_sampler(requested):
    if not isinstance(requested, dict) or set(requested) != set(FIELDS):
        raise ValueError('Explicit sampler requires exactly temperature, top_p, top_k and seed')
    for key, upper in (('temperature', 2), ('top_p', 1)):
        value = requested[key]
        if type(value) not in (int, float) or not math.isfinite(value) or not 0 < value <= upper:
            raise ValueError(key + ' must be positive and within the documented C API range; zero defers')
    for key in ('top_k', 'seed'):
        if type(requested[key]) is not int or not 1 <= requested[key] <= 2**31-1:
            raise ValueError(key + ' must be a positive signed int32; zero/negative sentinels are not explicit controls')
    sampler = geniex_SamplerConfig(temperature=requested['temperature'], top_p=requested['top_p'],
        top_k=requested['top_k'], seed=requested['seed'], min_p=0., repetition_penalty=1.,
        presence_penalty=0., frequency_penalty=0.)
    if sampler.temperature == 0 or sampler.top_p == 0:
        raise ValueError('Float32 conversion would turn an explicit value into a zero sentinel')
    return sampler


def sampler_values(sampler):
    return {key: getattr(sampler, key) for key in FIELDS}


def _verify_readback(requested, effective):
    """Compare native values to the exact ABI-normalized request, not guessed defaults."""
    try:
        actual = sampler_values(encode_sampler(effective))
    except (TypeError, ValueError, OverflowError) as exc:
        raise SamplerVerificationError('Effective sampler readback unavailable or malformed') from exc
    expected = sampler_values(encode_sampler(requested))
    if actual != expected:
        raise SamplerVerificationError('Requested sampler differs from native effective readback')
    return actual


class _GenerationProxy:
    def __init__(self, library, sampler, readback, handle):
        self.library, self.sampler, self.readback, self.handle = library, sampler, readback, handle
        self.observed = None
        self.submitted = None

    def __getattr__(self, name):
        return getattr(self.library, name)

    def geniex_llm_generate(self, handle, input_pointer, output_pointer):
        generation = ctypes.cast(input_pointer, ctypes.POINTER(geniex_LlmGenerateInput)).contents.config.contents
        original = ctypes.cast(generation.sampler_config, ctypes.c_void_p).value
        generation.sampler_config = ctypes.pointer(self.sampler)
        self.submitted = sampler_values(self.sampler)
        try:
            code = self.library.geniex_llm_generate(handle, input_pointer, output_pointer)
            if code == 0:
                observed = self.readback.read_effective_sampler_after_generation(self.handle)
                self.observed = observed
                _verify_readback(self.submitted, observed)
            return code
        finally:
            generation.sampler_config = ctypes.cast(original, ctypes.POINTER(geniex_SamplerConfig))


class _RuntimeProxy:
    def __init__(self, runtime, library):
        self.runtime, self._lib = runtime, library

    def __getattr__(self, name):
        return getattr(self.runtime, name)


class LaneCQairtSamplerModel(NativeModel):
    """Forward explicit ABI controls with post-generation verification before acceptance.

    Unmodified NativeModel owns templating, reset, timing and output cleanup.
    No trusted real readback adapter is currently implemented, so construction
    refuses before NativeModel can create/load a model. Synthetic tests register
    their fake adapter only within the test process.
    """
    def __init__(self, runtime, path, *, requested_sampling, readback=None, **kwargs):
        self._explicit_sampler = encode_sampler(requested_sampling)
        if not isinstance(readback, TRUSTED_READBACK_ADAPTERS):
            raise SamplerVerificationError('No supported native effective-sampler readback adapter; refusing model load')
        if kwargs.get('backend') != 'qairt_npu' or kwargs.get('plugin', 'qairt') != 'qairt':
            raise ValueError('Explicit sampler diagnostic is QAIRT NPU only')
        self._requested_sampling, self._readback = dict(requested_sampling), readback
        super().__init__(runtime, path, **kwargs)

    def chat(self, messages, tools=None, *, max_tokens=128):
        if self._closed:
            raise SamplerVerificationError('Diagnostic model is closed')
        with self._lock:
            original_runtime = self.runtime
            proxy = _GenerationProxy(original_runtime._lib, self._explicit_sampler, self._readback, self._handle)
            self.runtime = _RuntimeProxy(original_runtime, proxy)
            synthetic = getattr(self._readback, 'evidence_origin', None) != 'native_runtime_readback'
            try:
                result = super()._chat_locked(messages, tools, max_tokens,
                    self._requested_sampling['temperature'], True, None, None, False)
            except SamplerVerificationError as exc:
                exc.sampling_evidence = {'requested':dict(self._requested_sampling),
                    'abi_submitted':proxy.submitted,
                    'effective_native':None if synthetic else proxy.observed,
                    'synthetic_effective':proxy.observed if synthetic else None,
                    'verification':'failed'}
                raise
            finally:
                self.runtime = original_runtime
            synthetic = getattr(self._readback, 'evidence_origin', None) != 'native_runtime_readback'
            result['sampling'] = {'protocol_version': PROTOCOL,
                'requested': dict(self._requested_sampling), 'abi_submitted': proxy.submitted,
                'effective_native': None if synthetic else proxy.observed,
                'synthetic_effective': proxy.observed if synthetic else None,
                'verification': 'synthetic_contract_only' if synthetic else 'native_readback_matched'}
            return result


def five_repeat_diagnostic(model, prompt):
    """Same model, same prompt, reset per call; exact bytes are not semantic accuracy."""
    if not isinstance(model, LaneCQairtSamplerModel):
        raise SamplerVerificationError('Five-repeat diagnostic requires the verified Lane C adapter')
    rows = []
    for index in range(5):
        try:
            result = model.chat([{'role':'user', 'content':prompt}], max_tokens=32)
            rows.append({'repeat':index+1, 'status':'returned', **result})
        except Exception as exc:
            rows.append({'repeat':index+1, 'status':'failed_verification_or_runtime',
                         'error':type(exc).__name__, 'reason':str(exc),
                         'sampling':getattr(exc, 'sampling_evidence', None)})
            break  # A verification failure stops the diagnostic; no accepted determinism result.
    complete = len(rows) == 5 and all(row['status'] == 'returned' for row in rows)
    exact = all(row['text'].encode('utf-8') == rows[0]['text'].encode('utf-8') for row in rows) if complete else None
    return {'protocol_version':PROTOCOL, 'lane':'C', 'label':'LANE_C_SAMPLER_DIAGNOSTIC',
            'qualified':False, 'promotion_evidence':False, 'requested_repeats':5,
            'attempted_repeats':len(rows),
            'completed_repeats':sum(row['status']=='returned' for row in rows),
            'all_identical_utf8_bytes':exact, 'semantic_correctness':None, 'rows':rows}


def blocked_report(config, requested, prompt):
    if not isinstance(config, dict) or config.get('backend') != 'qairt_npu' or config.get('plugin', 'qairt') != 'qairt':
        raise ValueError('Diagnostic config must explicitly select qairt_npu and the qairt plugin')
    if str(config.get('device', 'npu')).lower() not in ('npu', 'htp0'):
        raise ValueError('Diagnostic requires explicit QAIRT NPU placement')
    encoded = sampler_values(encode_sampler(requested))
    return {'protocol_version':PROTOCOL, 'lane':'C', 'label':'LANE_C_SAMPLER_DIAGNOSTIC',
        'status':'BLOCKED_EFFECTIVE_READBACK_UNAVAILABLE', 'qualified':False, 'promotion_evidence':False,
        'target_versions_declared':{'geniex':'0.6.1','qairt':'2.45'}, 'installed_versions_verified':False,
        'requested_sampling':requested, 'abi_planned':encoded, 'abi_submitted':None,
        'effective_native':None, 'effective_verification':'unavailable',
        'requested_repeats':5, 'completed_repeats':0, 'all_identical_utf8_bytes':None,
        'semantic_correctness':None, 'prompt':prompt, 'rows':[],
        'reason':'Public GenieX generation output has no effective-sampler readback; no audited native readback adapter is implemented. No model load or generation attempted.'}
