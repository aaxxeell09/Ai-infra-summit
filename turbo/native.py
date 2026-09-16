'''Bounded ctypes wrapper over the GenieX v0.6.1 native SDK.

Targets the exact ABI published in sdk/include/geniex.h at tag v0.6.1
(verified byte-identical against local/geniex-research/geniex.h).
Importing this module never loads a native library; everything native happens
in NativeRuntime.__init__.

Memory contract, mirroring the header and run.c:

- Every int32_t return value is checked; negatives raise NativeError
  carrying both the numeric code and the SDK message text.
- SDK-allocated buffers (formatted_text, full_text, the geniex_resolve_device
  strings) are freed through geniex_free using the original void* pointer.
- Python-side encoded bytes, struct arrays and the token callback stay
  referenced until the native call returns.
- geniex_init runs exactly once per runtime; geniex_deinit only in
  NativeRuntime.close() when no models remain.
'''

from __future__ import annotations

import ctypes
from contextlib import nullcontext
import json
import os
import sys
import threading
import time
from ctypes import (
    CFUNCTYPE,
    POINTER,
    Structure,
    byref,
    c_bool,
    c_char_p,
    c_double,
    c_float,
    c_int32,
    c_int64,
    c_void_p,
)
from pathlib import Path
from typing import Any, Callable

__all__ = [
    'NativeError',
    'NativeModel',
    'NativeRuntime',
    'PINNED_VERSION',
    'PinnedVersionMismatch',
]

PINNED_VERSION = '0.6.1'

# Local synthetic codes (not geniex_ErrorCode values) for wrapper-level errors.
_PINNED_MISMATCH_CODE = -990001
_MODEL_CLOSED_CODE = -990002


class NativeError(RuntimeError):
    '''A geniex C call returned a negative status code (or wrapper teardown).'''

    def __init__(self, code: int, message: str):
        super().__init__(f'GenieX error {code}: {message}')
        self.code = code
        self.message = message


class PinnedVersionMismatch(NativeError):
    '''The loaded SDK reports a version outside the pinned 0.6.1 ABI.'''

    def __init__(self, reported: str):
        super().__init__(
            _PINNED_MISMATCH_CODE,
            f'SDK version {reported!r} does not match pinned GenieX {PINNED_VERSION}',
        )
        self.reported = reported


def _version_matches(reported: str) -> bool:
    '''Accept any version string that contains the pinned 0.6.1 ABI version.

    The bridge may format the value as 0.6.1, v0.6.1 or 0.6.1-rc0, so
    containment is allowed. A longer version number (0.6.10) or a different
    series (0.7.0) is rejected.
    '''
    s = (reported or '').strip().lstrip('vV')
    idx = s.find(PINNED_VERSION)
    if idx < 0:
        return False
    nxt = s[idx + len(PINNED_VERSION): idx + len(PINNED_VERSION) + 1]
    return not nxt.isdigit()


# ---------------------------------------------------------------------------
# ctypes ABI -- mirrors sdk/include/geniex.h @ v0.6.1 (64-bit layout).
# Field order and types must not be edited without re-diffing the header.
# ---------------------------------------------------------------------------

# bool (*)(const char* token, void* user_data)
geniex_token_callback = CFUNCTYPE(c_bool, c_char_p, c_void_p)


class geniex_ProfileData(Structure):
    _fields_ = [
        ('ttft', c_int64),
        ('media_time', c_int64),
        ('prompt_time', c_int64),
        ('decode_time', c_int64),
        ('prompt_tokens', c_int64),
        ('generated_tokens', c_int64),
        ('prefill_speed', c_double),
        ('decoding_speed', c_double),
        ('draft_n_total', c_int64),
        ('draft_n_accepted', c_int64),
        ('stop_reason', c_char_p),
    ]


class geniex_ToolCall(Structure):
    _fields_ = [
        ('id', c_char_p),
        ('name', c_char_p),
        ('arguments', c_char_p),  # JSON string
    ]


class geniex_SamplerConfig(Structure):
    _fields_ = [
        ('temperature', c_float),
        ('top_p', c_float),
        ('top_k', c_int32),
        ('min_p', c_float),
        ('repetition_penalty', c_float),
        ('presence_penalty', c_float),
        ('frequency_penalty', c_float),
        ('seed', c_int32),
        ('grammar_path', c_char_p),
        ('grammar_string', c_char_p),
    ]


class geniex_GenerationConfig(Structure):
    _fields_ = [
        ('max_tokens', c_int32),
        ('stop', POINTER(c_char_p)),
        ('stop_count', c_int32),
        ('sampler_config', POINTER(geniex_SamplerConfig)),
        ('image_paths', POINTER(c_char_p)),
        ('image_count', c_int32),
        ('audio_paths', POINTER(c_char_p)),
        ('audio_count', c_int32),
        ('sliding_window', c_bool),
        ('sliding_window_n_keep', c_int32),
    ]


class geniex_ModelConfig(Structure):
    _fields_ = [
        ('n_ctx', c_int32),
        ('n_threads', c_int32),
        ('n_threads_batch', c_int32),
        ('n_batch', c_int32),
        ('n_ubatch', c_int32),
        ('n_seq_max', c_int32),
        ('n_gpu_layers', c_int32),
        ('chat_template_path', c_char_p),
        ('chat_template_content', c_char_p),
        ('spec_type', c_char_p),
        ('spec_draft_model', c_char_p),
        ('spec_n_max', c_int32),
        ('spec_n_min', c_int32),
        ('spec_p_min', c_float),
    ]


class geniex_LlmCreateInput(Structure):
    _fields_ = [
        ('model_path', c_char_p),
        ('tokenizer_path', c_char_p),
        ('config', geniex_ModelConfig),
        ('plugin_id', c_char_p),
        ('device_id', c_char_p),
    ]


class geniex_LlmGenerateInput(Structure):
    _fields_ = [
        ('prompt_utf8', c_char_p),
        ('config', POINTER(geniex_GenerationConfig)),
        ('on_token', geniex_token_callback),
        ('user_data', c_void_p),
        ('input_ids', POINTER(c_int32)),
        ('input_ids_count', c_int32),
    ]


class geniex_LlmGenerateOutput(Structure):
    _fields_ = [
        ('full_text', c_void_p),  # SDK-allocated; geniex_free
        ('profile_data', geniex_ProfileData),
    ]


class geniex_LlmChatMessage(Structure):
    _fields_ = [
        ('role', c_char_p),
        ('content', c_char_p),
        ('tool_calls', POINTER(geniex_ToolCall)),
        ('tool_call_count', c_int32),
        ('tool_call_id', c_char_p),
        ('tool_name', c_char_p),
    ]


class geniex_LlmApplyChatTemplateInput(Structure):
    _fields_ = [
        ('messages', POINTER(geniex_LlmChatMessage)),
        ('message_count', c_int32),
        ('tools', c_char_p),
        ('enable_thinking', c_bool),
        ('add_generation_prompt', c_bool),
    ]


class geniex_LlmApplyChatTemplateOutput(Structure):
    _fields_ = [('formatted_text', c_void_p)]  # SDK-allocated; geniex_free


class geniex_ResolveDeviceInput(Structure):
    _fields_ = [
        ('plugin_id', c_char_p),
        ('model_name', c_char_p),
        ('mode', c_char_p),
        ('ngl_default', c_int32),
    ]


class geniex_ResolveDeviceOutput(Structure):
    _fields_ = [
        ('device_id', c_void_p),  # SDK-allocated; geniex_free
        ('ngl', c_int32),
        ('warning', c_void_p),  # SDK-allocated; geniex_free
    ]


def _struct_sizes_ok() -> bool:
    '''Pin the 64-bit ABI sizes; any accidental struct edit fails loudly.'''
    if ctypes.sizeof(c_void_p) != 8:
        return False
    expected = {
        geniex_ToolCall: 24,
        geniex_ProfileData: 88,
        geniex_SamplerConfig: 48,
        geniex_GenerationConfig: 72,
        geniex_ModelConfig: 80,
        geniex_LlmCreateInput: 112,
        geniex_LlmGenerateInput: 48,
        geniex_LlmGenerateOutput: 96,
        geniex_LlmChatMessage: 48,
        geniex_LlmApplyChatTemplateInput: 32,
        geniex_LlmApplyChatTemplateOutput: 8,
        geniex_ResolveDeviceInput: 32,
        geniex_ResolveDeviceOutput: 24,
    }
    return all(ctypes.sizeof(cls) == size for cls, size in expected.items())


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------


def _lib_name() -> str:
    if sys.platform == 'win32':
        return 'geniex.dll'
    if sys.platform == 'darwin':
        return 'libgeniex.dylib'
    return 'libgeniex.so'


def _sdk_dirs(sdk_dir: Path) -> list[Path]:
    '''Candidate directories holding the bridge library, priority order.'''
    return [sdk_dir / 'lib', sdk_dir]


def _add_windows_dll_dirs(sdk_dir: Path, lib_dir: Path) -> list[Any]:
    '''Register every DLL search directory before the first LoadLibrary.

    Windows DLL search does not recurse: the bridge in lib/ loads plugin DLLs
    from lib/<plugin>/, and plugins load their own siblings (ggml backends,
    QNN libs), so the lib dir plus every child directory is added.
    '''
    tokens: list[Any] = []
    if sys.platform != 'win32':
        return tokens
    dirs = [lib_dir]
    try:
        dirs.extend(p for p in lib_dir.iterdir() if p.is_dir())
    except OSError:
        pass
    if sdk_dir != lib_dir:
        dirs.append(sdk_dir)
    seen: set[str] = set()
    for d in dirs:
        real = os.path.realpath(str(d))
        if real in seen:
            continue
        seen.add(real)
        try:
            tokens.append(os.add_dll_directory(str(d)))
        except (OSError, FileNotFoundError):
            pass
    return tokens


def _preload_siblings(d: Path) -> None:
    '''Pre-load sibling shared libs so plugin dlopen resolves DT_NEEDED.

    RTLD_LOCAL keeps plugin siblings out of global scope (the FastRPC
    forwarder shadowing hazard documented in the official binding).
    '''
    if sys.platform == 'win32' or not d.is_dir():
        return
    flags = getattr(ctypes, 'RTLD_LOCAL', 0)
    try:
        names = sorted(os.listdir(d))
    except OSError:
        return
    for name in names:
        if name.endswith('.a') or ('.so' not in name and '.dylib' not in name):
            continue
        full = d / name
        if not full.is_file():
            continue
        try:
            ctypes.CDLL(str(full), flags)
        except OSError:
            pass  # wrong arch / missing dep; the SDK may not need it


# ---------------------------------------------------------------------------
# Runtime
# ---------------------------------------------------------------------------


class NativeRuntime:
    '''Load the pinned SDK once per sdk_dir and own the init lifecycle.'''

    _shared: dict[str, 'NativeRuntime'] = {}
    _shared_lock = threading.Lock()

    def __new__(cls, sdk_dir: str | os.PathLike[str]) -> 'NativeRuntime':
        key = os.path.realpath(os.fspath(sdk_dir))
        with cls._shared_lock:
            existing = cls._shared.get(key)
            if existing is not None and not getattr(existing, '_deinited', False):
                return existing
            inst = super().__new__(cls)
            inst._init_lock = threading.Lock()
            cls._shared[key] = inst
            return inst

    def __init__(self, sdk_dir: str | os.PathLike[str]):
        with self._init_lock:
            if getattr(self, '_ready', False):
                return
            self.sdk_dir = Path(os.path.realpath(os.fspath(sdk_dir)))
            self._dll_dir_tokens: list[Any] = []
            self._lib: ctypes.CDLL | None = None
            self._models: list['NativeModel'] = []
            self._lifecycle_lock = threading.Lock()
            self._deinited = False
            self._load_and_init()
            self._ready = True

    # -- loading ------------------------------------------------------------

    def _load_and_init(self) -> None:
        name = _lib_name()
        lib_path: Path | None = None
        lib_dir: Path | None = None
        for d in _sdk_dirs(self.sdk_dir):
            cand = d / name
            if cand.is_file():
                lib_path, lib_dir = cand, d
                break
        if lib_path is None or lib_dir is None:
            searched = ', '.join(str(d) for d in _sdk_dirs(self.sdk_dir))
            raise FileNotFoundError(f'cannot find {name} (searched: {searched})')

        # Windows: every DLL directory must be registered BEFORE LoadLibrary.
        self._dll_dir_tokens = _add_windows_dll_dirs(self.sdk_dir, lib_dir)
        os.environ['GENIEX_PLUGIN_PATH'] = str(lib_dir)
        _preload_siblings(lib_dir)

        lib = ctypes.CDLL(str(lib_path))
        self._bind(lib)
        self._lib = lib

        reported_raw = lib.geniex_version()
        reported = reported_raw.decode('utf-8', errors='replace') if reported_raw else ''
        if not _version_matches(reported):
            raise PinnedVersionMismatch(reported)

        self._check(lib.geniex_init())  # exactly once per runtime

    @staticmethod
    def _bind(lib: ctypes.CDLL) -> None:
        '''Exact argtypes/restypes for every entry point this wrapper uses.'''
        lib.geniex_get_error_message.argtypes = [c_int32]
        lib.geniex_get_error_message.restype = c_char_p
        lib.geniex_init.argtypes = []
        lib.geniex_init.restype = c_int32
        lib.geniex_deinit.argtypes = []
        lib.geniex_deinit.restype = c_int32
        lib.geniex_free.argtypes = [c_void_p]
        lib.geniex_free.restype = None
        lib.geniex_version.argtypes = []
        lib.geniex_version.restype = c_char_p
        lib.geniex_resolve_device.argtypes = [
            POINTER(geniex_ResolveDeviceInput),
            POINTER(geniex_ResolveDeviceOutput),
        ]
        lib.geniex_resolve_device.restype = c_int32
        lib.geniex_llm_create.argtypes = [POINTER(geniex_LlmCreateInput), POINTER(c_void_p)]
        lib.geniex_llm_create.restype = c_int32
        lib.geniex_llm_destroy.argtypes = [c_void_p]
        lib.geniex_llm_destroy.restype = c_int32
        lib.geniex_llm_reset.argtypes = [c_void_p]
        lib.geniex_llm_reset.restype = c_int32
        lib.geniex_llm_apply_chat_template.argtypes = [
            c_void_p,
            POINTER(geniex_LlmApplyChatTemplateInput),
            POINTER(geniex_LlmApplyChatTemplateOutput),
        ]
        lib.geniex_llm_apply_chat_template.restype = c_int32
        lib.geniex_llm_generate.argtypes = [
            c_void_p,
            POINTER(geniex_LlmGenerateInput),
            POINTER(geniex_LlmGenerateOutput),
        ]
        lib.geniex_llm_generate.restype = c_int32

    # -- error + memory helpers ----------------------------------------------

    def _check(self, code: int) -> None:
        if code >= 0:
            return
        raw = None
        if self._lib is not None:
            raw = self._lib.geniex_get_error_message(c_int32(code))
        msg = raw.decode('utf-8', errors='replace') if raw else 'unknown error'
        raise NativeError(code, msg)

    def _free(self, ptr: int | None) -> None:
        '''Free an SDK allocation with the ORIGINAL void* pointer.'''
        if ptr and self._lib is not None:
            self._lib.geniex_free(c_void_p(ptr))

    # -- lifecycle ------------------------------------------------------------

    def _register(self, model: 'NativeModel') -> None:
        with self._lifecycle_lock:
            self._models.append(model)

    def _unregister(self, model: 'NativeModel') -> None:
        with self._lifecycle_lock:
            try:
                self._models.remove(model)
            except ValueError:
                pass

    def close(self) -> None:
        '''Deinit the SDK once every model created from this runtime is closed.'''
        with self._lifecycle_lock:
            if self._deinited:
                return
            if self._models:
                raise RuntimeError(
                    'cannot deinit while models are open: '
                    + ', '.join(str(m.model_path) for m in self._models)
                )
            self._deinited = True
            if self._lib is not None:
                self._lib.geniex_deinit()
            # A tune cycle closes the SDK before running its child processes.
            # The subsequent apply must initialize a fresh runtime, never
            # retrieve this deinitialized instance from the singleton cache.
            key = os.path.realpath(os.fspath(self.sdk_dir))
            with self._shared_lock:
                if self._shared.get(key) is self:
                    del self._shared[key]
            for token in self._dll_dir_tokens:
                token.close()
            self._dll_dir_tokens.clear()

    # -- helpers ------------------------------------------------------------

    def resolve_device(
        self, plugin_id: str, mode: str, ngl_default: int = -1
    ) -> tuple[str | None, int, str | None]:
        '''Return (device_id, ngl, warning); device_id None means default.'''
        if self._deinited:
            raise RuntimeError('native runtime is closed; create a new NativeRuntime')
        assert self._lib is not None
        inp = geniex_ResolveDeviceInput(
            plugin_id=plugin_id.encode(),
            model_name=None,
            mode=(mode or 'auto').encode(),
            ngl_default=ngl_default,
        )
        out = geniex_ResolveDeviceOutput()
        self._check(self._lib.geniex_resolve_device(byref(inp), byref(out)))
        dev = ctypes.cast(out.device_id, c_char_p).value if out.device_id else None
        warn = ctypes.cast(out.warning, c_char_p).value if out.warning else None
        # Free both heap strings with the original void* pointers.
        self._free(out.device_id)
        self._free(out.warning)
        return (dev.decode() if dev else None, out.ngl, warn.decode() if warn else None)


BACKEND_CONFIGS = {
    'llama_cpp_cpu': ('llama_cpp', 'cpu'),
    'llama_cpp_htp': ('llama_cpp', 'npu'),
    'qairt_npu': ('qairt', 'npu'),
}


def backend_options(backend=None, plugin=None, device=None, model_path=None):
    """Resolve explicit identities without replacing the SDK device resolver."""
    if backend is None:
        return plugin, device or 'cpu'
    if backend not in BACKEND_CONFIGS:
        raise ValueError(f'Unknown inference backend: {backend}')
    wanted_plugin, wanted_device = BACKEND_CONFIGS[backend]
    allowed_devices = {wanted_device}
    if backend == 'llama_cpp_htp':
        allowed_devices.add('HTP0')
    if plugin is not None and plugin != wanted_plugin:
        raise ValueError(f'{backend} conflicts with plugin {plugin}')
    if device is not None and device not in allowed_devices:
        raise ValueError(f'{backend} conflicts with device {device}')
    if backend == 'qairt_npu':
        if not model_path or not os.path.isfile(os.path.join(os.fspath(model_path), 'geniex.json')):
            raise ValueError('QAIRT model not configured: model_path must be a local bundle containing geniex.json')
    elif model_path and not os.fspath(model_path).lower().endswith('.gguf'):
        raise ValueError(f'{backend} requires a GGUF artifact')
    return wanted_plugin, device or wanted_device


def _detect_plugin(path: str) -> str:
    lower = path.lower()
    if lower.endswith('.gguf'):
        return 'llama_cpp'
    if os.path.isfile(os.path.join(path, 'geniex.json')):
        return 'qairt'
    return 'llama_cpp'


def _qairt_bundle_input(path: str) -> tuple[str, int]:
    """Resolve the C ABI's shard-file input from a compiled bundle directory.

    GenieX 0.6.1 QAIRT takes model_path.parent_path(), then reads ctx-bins
    from genie_config.json. Passing the directory itself selects its parent.
    The compiled context belongs to the artifact; n_ctx must remain zero.
    """
    supplied = Path(path)
    root = (supplied if supplied.is_dir() else supplied.parent).resolve()
    try:
        config = json.loads((root / 'genie_config.json').read_text(encoding='utf-8'))
        dialog = config['dialog']
        context = dialog['context']['size']
        shards = dialog['engine']['model']['binary']['ctx-bins']
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise ValueError('QAIRT requires a readable compiled genie_config.json') from exc
    if type(context) is not int or context <= 0:
        raise ValueError('QAIRT compiled context must be a positive integer')
    if not isinstance(shards, list) or not shards:
        raise ValueError('QAIRT bundle has no declared context shards')
    paths = []
    for name in shards:
        if not isinstance(name, str) or not name:
            raise ValueError('QAIRT context shard names must be nonempty strings')
        candidate = (root / name).resolve()
        if not candidate.is_relative_to(root) or not candidate.is_file():
            raise ValueError('QAIRT context shard is missing or outside the bundle')
        paths.append(candidate)
    if not supplied.is_dir() and supplied.resolve() not in paths:
        raise ValueError('QAIRT model file is not a declared context shard')
    if paths[0].parent != root:
        raise ValueError('QAIRT first context shard must be directly inside the bundle root')
    return str(paths[0]), context


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------


class _ToolCallStop:
    """Streaming byte matcher only; never edits the model's native output."""
    marker = b'</tool_call>'

    def __init__(self):
        self.tail = b''
        self.hit = False
        self.callbacks_after_stop = 0

    def feed(self, piece):
        if self.hit:
            self.callbacks_after_stop += 1
            return False
        combined = self.tail + (piece or b'')
        self.hit = self.marker in combined
        self.tail = combined[-(len(self.marker)-1):]
        return not self.hit


class NativeModel:
    '''One opaque geniex_LLM; every call serialized by a per-model lock.'''

    def __init__(
        self,
        runtime: NativeRuntime,
        path: str | os.PathLike[str],
        device: str | None = None,
        threads: int = 0,
        context: int | None = None,
        spec_type: str = 'none',
        draft_tokens: int = 8,
        threads_batch: int = 0,
        ubatch: int = 0,
        n_batch: int = 0,
        plugin: str | None = None,
        backend: str | None = None,
        generation_observer=None,
        stop_after_tool_call: bool = False,
    ):
        plugin, device = backend_options(backend, plugin, device, path)
        self.backend_id = backend
        self.generation_observer = generation_observer
        self.runtime = runtime
        self.model_path = os.fspath(path)
        self.device_alias = device
        self.plugin_id = plugin or _detect_plugin(self.model_path)
        if type(stop_after_tool_call) is not bool:
            raise ValueError('stop_after_tool_call must be boolean')
        if stop_after_tool_call and self.plugin_id != 'qairt':
            raise ValueError('stop_after_tool_call is an opt-in QAIRT candidate only')
        self.stop_after_tool_call = stop_after_tool_call
        self.compiled_context = None
        native_model_path = self.model_path
        if self.plugin_id == 'qairt':
            native_model_path, self.compiled_context = _qairt_bundle_input(self.model_path)
            if context not in (None, 0, self.compiled_context):
                raise ValueError('QAIRT context must match the compiled artifact; it is not a runtime knob')
            if any((threads, threads_batch, ubatch, n_batch)) or spec_type not in ('', 'none'):
                raise ValueError('QAIRT does not support llama.cpp thread/batch/speculation settings')
            context = self.compiled_context
            native_context = 0
        else:
            context = 4096 if context is None else context
            native_context = context
        self.config: dict[str, Any] = {
            'threads': threads,
            'context': context,
            'spec_type': spec_type,
            'draft_tokens': draft_tokens,
            'threads_batch': threads_batch,
            'ubatch': ubatch,
            'n_batch': n_batch,
            'plugin': self.plugin_id,
            'stop_after_tool_call': self.stop_after_tool_call,
        }
        self._lock = threading.Lock()
        self._handle: int | None = None
        self._closed = False

        lib = runtime._lib
        assert lib is not None

        # Device resolution goes through the SDK alias table (single source
        # of truth); ngl comes back resolved, cpu forces 0.
        device_id, ngl, warning = runtime.resolve_device(self.plugin_id, device)
        if warning:
            print(f'geniex: {warning}', file=sys.stderr)
        if backend is not None and device_id:
            resolved = device_id.upper()
            if ((backend == 'llama_cpp_cpu' and resolved.startswith(('HTP', 'GPU')))
                    or (backend in ('llama_cpp_htp', 'qairt_npu') and resolved.startswith(('CPU', 'GPU')))):
                raise ValueError(f'{backend} resolved to incompatible device {device_id}; refusing fallback')

        spec_type_b = None if spec_type in ('', 'none') else spec_type.encode('utf-8')
        mc = geniex_ModelConfig(
            n_ctx=int(native_context),
            n_threads=int(threads),
            n_threads_batch=int(threads_batch),
            n_batch=int(n_batch),
            n_ubatch=int(ubatch),
            n_seq_max=0,
            n_gpu_layers=ngl,
            spec_type=spec_type_b,
            spec_n_max=int(draft_tokens),
        )
        model_path_b = native_model_path.encode('utf-8')
        device_id_b = device_id.encode('utf-8') if device_id else None
        plugin_b = self.plugin_id.encode('utf-8')
        cin = geniex_LlmCreateInput(
            model_path=model_path_b,
            tokenizer_path=None,
            config=mc,
            plugin_id=plugin_b,
            device_id=device_id_b,
        )
        handle = c_void_p()
        runtime._check(lib.geniex_llm_create(byref(cin), byref(handle)))
        self._handle = handle.value
        self._device_id = device_id
        self._ngl = ngl
        self.resolution_warning = warning

        runtime._register(self)

    def provenance(self):
        """Resolver evidence, not a hardware-utilization assertion. Keep legacy fields."""
        identity = self.backend_id
        if identity is None:
            if self.plugin_id == 'qairt':
                identity = 'qairt_npu'
            elif self.plugin_id == 'llama_cpp':
                resolved = (self._device_id or '').upper()
                if resolved.startswith('HTP'):
                    identity = 'llama_cpp_htp'
                elif resolved == 'CPU' or (not resolved and self.device_alias == 'cpu'):
                    identity = 'llama_cpp_cpu'
        return {
            'backend_id': identity, 'runtime': self.plugin_id,
            'requested_device': self.device_alias, 'resolved_device': self._device_id,
            'device_resolution_warning': self.resolution_warning,
            'model_artifact_type': 'QAIRT' if self.plugin_id == 'qairt' else 'GGUF',
            'model_path_or_id': self.model_path,
            'geniex_version': PINNED_VERSION, 'qairt_version': None,
            'dispatch_verified': False,
            'context_source': 'compiled_artifact' if self.plugin_id == 'qairt' else 'model_config',
            'effective_compiled_context': self.compiled_context,
        }

    # -- chat ---------------------------------------------------------------

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | str | None = None,
        max_tokens: int = 256,
        temperature: float = 0.0,
        reset: bool = True,
        on_token: Callable[[str], bool | None] | None = None,
        grammar: str | None = None,
        greedy_zero: bool = False,
    ) -> dict[str, Any]:
        '''One assistant turn: template, generate, JSON-ready dict.

        on_token receives decoded text pieces and may return False to stop
        generation; None and True both continue. grammar is an optional BNF
        grammar string passed as SamplerConfig.grammar_string and retained
        until the generate call completes.
        '''
        if self._closed:
            raise NativeError(_MODEL_CLOSED_CODE, 'model is closed')
        with self._lock:
            return self._chat_locked(messages, tools, max_tokens, temperature, reset, on_token, grammar, greedy_zero)

    def _chat_locked(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | str | None,
        max_tokens: int,
        temperature: float,
        reset: bool,
        on_token: Callable[[str], bool | None] | None,
        grammar: str | None,
        greedy_zero: bool,
    ) -> dict[str, Any]:
        lib = self.runtime._lib
        assert lib is not None and self._handle is not None

        if reset:
            self.runtime._check(lib.geniex_llm_reset(c_void_p(self._handle)))

        keepalive: list[Any] = []
        prompt = self._apply_template(messages, tools, keepalive)

        grammar_b = grammar.encode('utf-8') if grammar else None
        if grammar_b is not None:
            keepalive.append(grammar_b)

        # GenieX 0.6.1 llama_cpp treats temperature=0 and top_k=0 as
        # unset (0.8 and 40 respectively). Force one candidate for a
        # caller's greedy request; this does not require a patched DLL.
        # Positive-temperature requests retain the existing SDK defaults.
        # Opt in only: the frozen 50-case trial of this workaround failed
        # the quality gate. Preserve the measured original default behavior.
        greedy_top_k = greedy_zero and self.plugin_id == 'llama_cpp' and float(temperature) == 0.0
        sampler = geniex_SamplerConfig(
            temperature=float(temperature),
            top_p=1.0,
            top_k=1 if greedy_top_k else 0,
            min_p=0.0,
            repetition_penalty=1.0,
            presence_penalty=0.0,
            frequency_penalty=0.0,
            seed=-1,
            grammar_string=grammar_b,  # struct retains the bytes until generate returns
        )
        gconf = geniex_GenerationConfig(max_tokens=int(max_tokens))
        gconf.sampler_config = ctypes.pointer(sampler)
        keepalive.extend([sampler, gconf])

        # Token callback: decoded str in; False stops; None/True continue.
        # CFUNCTYPE fields reject None at construction, so a no-callback call
        # gets an empty instance, which ctypes marshals as a NULL pointer.
        cb_ref = geniex_token_callback()
        state = {'alive': True}
        stopper = _ToolCallStop() if self.stop_after_tool_call else None

        def _tramp(token: bytes | None, _user: int | None) -> bool:
            if not state['alive']:
                return False
            keep_generating = stopper.feed(token) if stopper else True
            try:
                if on_token is not None:
                    cont = on_token(token.decode('utf-8', errors='replace') if token else '')
                    keep_generating = keep_generating and cont is not False
                return keep_generating
            except Exception:
                return False  # preserve existing external-callback cancellation behavior

        if on_token is not None or stopper is not None:
            cb_ref = geniex_token_callback(_tramp)
        keepalive.append(cb_ref)

        prompt_b = prompt.encode('utf-8')
        gin = geniex_LlmGenerateInput(
            prompt_utf8=prompt_b,
            config=ctypes.pointer(gconf),
            on_token=cb_ref,
            user_data=None,
        )
        gout = geniex_LlmGenerateOutput()
        keepalive.extend([gin, prompt_b, gout])

        # The SDK can populate full_text and still return an error. Release it
        # on every exit without replacing the original generation exception.
        try:
            with self.generation_observer.measure('inference') if self.generation_observer else nullcontext():
                t0 = time.perf_counter()
                code = lib.geniex_llm_generate(c_void_p(self._handle), byref(gin), byref(gout))
                total_s = time.perf_counter() - t0
            self.runtime._check(code)
            text = ''
            if gout.full_text:
                raw = ctypes.cast(gout.full_text, c_char_p).value
                text = raw.decode('utf-8', errors='replace') if raw else ''
        finally:
            state['alive'] = False
            if gout.full_text:
                original_error = sys.exc_info()[0] is not None
                pointer = gout.full_text
                gout.full_text = None
                try:
                    self.runtime._free(pointer)
                except Exception:
                    if not original_error:
                        raise

        p = gout.profile_data
        profile = {
            'ttft': int(p.ttft),
            'media_time': int(p.media_time),
            'prompt_time': int(p.prompt_time),
            'decode_time': int(p.decode_time),
            'prompt_tokens': int(p.prompt_tokens),
            'generated_tokens': int(p.generated_tokens),
            'prefill_speed': float(p.prefill_speed),
            'decoding_speed': float(p.decoding_speed),
            'draft_n_total': int(p.draft_n_total),
            'draft_n_accepted': int(p.draft_n_accepted),
            'stop_reason': p.stop_reason.decode() if p.stop_reason else None,
        }
        ttft_s = profile['ttft'] / 1e6
        return {
            'text': text,
            'generation_control': {
                'stop_after_tool_call':self.stop_after_tool_call,
                'mechanism':'qairt_token_callback' if stopper else None,
                'delimiter':'</tool_call>' if stopper else None,
                'delimiter_seen':stopper.hit if stopper else False,
                'callbacks_after_stop_request':stopper.callbacks_after_stop if stopper else 0,
                'native_text_modified':False,
            },
            'sampling': {'requested_temperature': float(temperature),
                         'sdk_top_k': sampler.top_k,
                         'greedy_via_top_k': greedy_top_k,
                         'sdk_zero_temperature_uses_default': self.plugin_id in ('llama_cpp', 'qairt'),
                         'zero_temperature_default_source': 'bundle_then_plugin' if self.plugin_id == 'qairt' else 'plugin'},
            'profile': profile,
            'timings': {'ttft': ttft_s, 'total': total_s},
            **self.provenance(),
            'backend': 'geniex',
            'device': self._device_id or self.device_alias,
            'version': PINNED_VERSION,
            'config': dict(self.config),
        }

    def _apply_template(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | str | None,
        keepalive: list[Any],
    ) -> str:
        lib = self.runtime._lib
        assert lib is not None and self._handle is not None

        n = len(messages)
        msgs = (geniex_LlmChatMessage * n)()
        keepalive.append(msgs)

        for i, m in enumerate(messages):
            role = str(m.get('role', 'user'))
            content = m.get('content')
            content_str = content if isinstance(content, str) else json.dumps(content or '')
            role_b = role.encode('utf-8')
            content_b = content_str.encode('utf-8')
            keepalive.extend([role_b, content_b])

            calls = m.get('tool_calls')
            if role == 'assistant' and calls:
                arr = (geniex_ToolCall * len(calls))()
                for j, call in enumerate(calls):
                    fn = call.get('function', {}) if isinstance(call, dict) else {}
                    cid = call.get('id')
                    name = fn.get('name')
                    args = fn.get('arguments', '{}')
                    args_str = args if isinstance(args, str) else json.dumps(args)
                    id_b = cid.encode('utf-8') if cid else None
                    name_b = name.encode('utf-8') if name else None
                    args_b = args_str.encode('utf-8')
                    keepalive.extend([b for b in (id_b, name_b, args_b) if b is not None])
                    arr[j].id = id_b
                    arr[j].name = name_b
                    arr[j].arguments = args_b
                keepalive.append(arr)
                msgs[i].tool_calls = arr
                msgs[i].tool_call_count = len(calls)

            msgs[i].role = role_b
            msgs[i].content = content_b
            if role == 'tool':
                tid = m.get('tool_call_id')
                tname = m.get('name')
                tid_b = tid.encode('utf-8') if tid else None
                tname_b = tname.encode('utf-8') if tname else None
                keepalive.extend([b for b in (tid_b, tname_b) if b is not None])
                msgs[i].tool_call_id = tid_b
                msgs[i].tool_name = tname_b

        if tools is None:
            tools_b = None
        elif isinstance(tools, str):
            tools_b = tools.encode('utf-8')
        else:
            tools_b = json.dumps(tools).encode('utf-8')
        if tools_b is not None:
            keepalive.append(tools_b)

        tin = geniex_LlmApplyChatTemplateInput(
            messages=msgs,
            message_count=n,
            tools=tools_b,
            enable_thinking=False,
            add_generation_prompt=True,
        )
        tout = geniex_LlmApplyChatTemplateOutput()
        keepalive.extend([tin, tout])
        self.runtime._check(lib.geniex_llm_apply_chat_template(c_void_p(self._handle), byref(tin), byref(tout)))

        text = ''
        if tout.formatted_text:
            raw = ctypes.cast(tout.formatted_text, c_char_p).value
            text = raw.decode('utf-8', errors='replace') if raw else ''
            self.runtime._free(tout.formatted_text)  # original void*
        return text

    # -- teardown -----------------------------------------------------------

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            if self._handle is not None:
                lib = self.runtime._lib
                assert lib is not None
                lib.geniex_llm_destroy(c_void_p(self._handle))
                self._handle = None
        self.runtime._unregister(self)

    def __enter__(self) -> 'NativeModel':
        return self

    def __exit__(self, *_exc: Any) -> None:
        self.close()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass


if not _struct_sizes_ok():
    raise AssertionError('geniex ctypes struct sizes do not match the pinned 64-bit ABI')
