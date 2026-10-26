"""Call Forge functions from Python via ctypes.

Build the library first:
    python3 forge.py build --shared examples/py_interop/lib.fg -o /tmp/libforge.so

Then:
    from tools.forge_py import ForgeLib
    lib = ForgeLib("/tmp/libforge.so")
    lib.call_int("add", 40, 2)          # -> 42
    lib.call_str("greet", "Jayant")     # -> "hello Jayant" (freed correctly)

Types: Forge int -> c_longlong, bool -> c_bool, float -> c_double,
str -> c_char_p on the way in, and a malloc'd char* on the way out
(which this helper reads and frees with libc free, so it does not leak).
Arrays: [int] / [float] are passed as a C struct {data, len, cap, ref}
with data and ref malloc'd — Forge frees them on return (its array
GC), so Python must NOT free an input array after the call. A
returned array is read into a Python list, then its data/ref are
freed here with libc free.
Structs: only simple structs whose fields are int/str in declaration
order are supported here, via a ctypes Structure with the same layout
(str fields must be malloc'd, as for plain str arguments).
"""

import ctypes
import os

_libc = ctypes.CDLL(None)
_libc.free.argtypes = [ctypes.c_void_p]
_libc.malloc.argtypes = [ctypes.c_size_t]
_libc.malloc.restype = ctypes.c_void_p


def _c_str(s):
    """Malloc a C copy of a Python string. Forge frees string
    parameters on return (its GC), so do NOT free this pointer
    in Python after the call — Forge already did."""
    b = s.encode()
    ptr = _libc.malloc(len(b) + 1)
    ctypes.memmove(ptr, b, len(b) + 1)
    return ptr


class ForgeIntArray(ctypes.Structure):
    _fields_ = [("data", ctypes.POINTER(ctypes.c_longlong)),
                ("len", ctypes.c_longlong),
                ("cap", ctypes.c_longlong),
                ("ref", ctypes.POINTER(ctypes.c_longlong))]


class ForgeFloatArray(ctypes.Structure):
    _fields_ = [("data", ctypes.POINTER(ctypes.c_double)),
                ("len", ctypes.c_longlong),
                ("cap", ctypes.c_longlong),
                ("ref", ctypes.POINTER(ctypes.c_longlong))]


def _c_int_array(values):
    """Malloc a Forge [int] array. Forge frees it on return, so do
    NOT free it in Python after the call."""
    n = len(values)
    data = _libc.malloc(ctypes.sizeof(ctypes.c_longlong) * max(n, 1))
    arr = (ctypes.c_longlong * n).from_address(data) if n else None
    for i, v in enumerate(values):
        arr[i] = v
    ref = _libc.malloc(ctypes.sizeof(ctypes.c_longlong))
    ctypes.cast(ref, ctypes.POINTER(ctypes.c_longlong))[0] = 1
    return ForgeIntArray(ctypes.cast(data, ctypes.POINTER(ctypes.c_longlong)),
                         n, n, ctypes.cast(ref, ctypes.POINTER(ctypes.c_longlong)))


def _read_int_array(struct):
    out = [struct.data[i] for i in range(struct.len)]
    # Returned array is owned by Python now: free its data and ref.
    if struct.data:
        _libc.free(ctypes.cast(struct.data, ctypes.c_void_p))
    if struct.ref:
        _libc.free(ctypes.cast(struct.ref, ctypes.c_void_p))
    return out


def _c_float_array(values):
    n = len(values)
    data = _libc.malloc(ctypes.sizeof(ctypes.c_double) * max(n, 1))
    arr = (ctypes.c_double * n).from_address(data) if n else None
    for i, v in enumerate(values):
        arr[i] = v
    ref = _libc.malloc(ctypes.sizeof(ctypes.c_longlong))
    ctypes.cast(ref, ctypes.POINTER(ctypes.c_longlong))[0] = 1
    return ForgeFloatArray(ctypes.cast(data, ctypes.POINTER(ctypes.c_double)),
                           n, n, ctypes.cast(ref, ctypes.POINTER(ctypes.c_longlong)))


def _read_float_array(struct):
    out = [struct.data[i] for i in range(struct.len)]
    if struct.data:
        _libc.free(ctypes.cast(struct.data, ctypes.c_void_p))
    if struct.ref:
        _libc.free(ctypes.cast(struct.ref, ctypes.c_void_p))
    return out


class ForgeStrArray(ctypes.Structure):
    _fields_ = [("data", ctypes.POINTER(ctypes.c_void_p)),
                ("len", ctypes.c_longlong),
                ("cap", ctypes.c_longlong),
                ("ref", ctypes.POINTER(ctypes.c_longlong))]


def _c_str_array(values):
    """Malloc a Forge [str] array. Each element is malloc'd, and Forge
    frees the elements, data, and ref on return — do NOT free in Python."""
    n = len(values)
    data = _libc.malloc(ctypes.sizeof(ctypes.c_void_p) * max(n, 1))
    ptrs = (ctypes.c_void_p * n).from_address(data) if n else None
    for i, v in enumerate(values):
        ptrs[i] = _c_str(v)
    ref = _libc.malloc(ctypes.sizeof(ctypes.c_longlong))
    ctypes.cast(ref, ctypes.POINTER(ctypes.c_longlong))[0] = 1
    return ForgeStrArray(ctypes.cast(data, ctypes.POINTER(ctypes.c_void_p)),
                         n, n, ctypes.cast(ref, ctypes.POINTER(ctypes.c_longlong)))


def _read_str_array(struct):
    out = []
    for i in range(struct.len):
        ptr = struct.data[i]
        out.append(ctypes.string_at(ptr).decode() if ptr else "")
        if ptr:
            _libc.free(ptr)
    if struct.data:
        _libc.free(ctypes.cast(struct.data, ctypes.c_void_p))
    if struct.ref:
        _libc.free(ctypes.cast(struct.ref, ctypes.c_void_p))
    return out


class ForgeLib:
    def __init__(self, path):
        if not os.path.exists(path):
            raise FileNotFoundError(path)
        self.lib = ctypes.CDLL(path)

    def _prep_args(self, args):
        out = []
        types = []
        for a in args:
            if isinstance(a, str):
                out.append(_c_str(a))
                types.append(ctypes.c_void_p)
            elif isinstance(a, bool):
                out.append(a)
                types.append(ctypes.c_bool)
            elif isinstance(a, int):
                out.append(a)
                types.append(ctypes.c_longlong)
            else:
                out.append(a)
                types.append(ctypes.c_double)
        return out, types

    def call_int(self, name, *args):
        fn = getattr(self.lib, name)
        vals, types = self._prep_args(args)
        fn.argtypes = types
        fn.restype = ctypes.c_longlong
        return fn(*vals)

    def call_float(self, name, *args):
        fn = getattr(self.lib, name)
        vals, types = self._prep_args(args)
        fn.argtypes = types
        fn.restype = ctypes.c_double
        return fn(*vals)

    def call_bool(self, name, *args):
        fn = getattr(self.lib, name)
        vals, types = self._prep_args(args)
        fn.argtypes = types
        fn.restype = ctypes.c_bool
        return fn(*vals)

    def call_int_array(self, name, values):
        """Call a Forge fn([int]) -> int, e.g. sum_arr([1,2,3]) -> 6."""
        fn = getattr(self.lib, name)
        fn.argtypes = [ForgeIntArray]
        fn.restype = ctypes.c_longlong
        return fn(_c_int_array(values))

    def call_int_array_out(self, name, values):
        """Call a Forge fn([int]) -> [int], returning a Python list."""
        fn = getattr(self.lib, name)
        fn.argtypes = [ForgeIntArray]
        fn.restype = ForgeIntArray
        return _read_int_array(fn(_c_int_array(values)))

    def call_float_array(self, name, values):
        fn = getattr(self.lib, name)
        fn.argtypes = [ForgeFloatArray]
        fn.restype = ctypes.c_double
        return fn(_c_float_array(values))

    def call_float_array_out(self, name, values):
        fn = getattr(self.lib, name)
        fn.argtypes = [ForgeFloatArray]
        fn.restype = ForgeFloatArray
        return _read_float_array(fn(_c_float_array(values)))

    def call_str_array(self, name, values):
        fn = getattr(self.lib, name)
        fn.argtypes = [ForgeStrArray]
        fn.restype = ctypes.c_void_p
        ptr = fn(_c_str_array(values))
        try:
            return ctypes.string_at(ptr).decode() if ptr else ""
        finally:
            if ptr:
                _libc.free(ptr)

    def call_str_array_out(self, name, values):
        fn = getattr(self.lib, name)
        fn.argtypes = [ForgeStrArray]
        fn.restype = ForgeStrArray
        return _read_str_array(fn(_c_str_array(values)))

    def call_struct(self, name, struct_type, struct_value, restype=ctypes.c_longlong):
        """Call a Forge fn(Struct) -> int, with a ctypes Structure value.
        Struct str fields must be malloc'd (see _c_str); Forge frees
        the struct's fields on return, so do not free them in Python."""
        fn = getattr(self.lib, name)
        fn.argtypes = [struct_type]
        fn.restype = restype
        return fn(struct_value)

    def call_str(self, name, *args):
        fn = getattr(self.lib, name)
        vals, types = self._prep_args(args)
        fn.argtypes = types
        fn.restype = ctypes.c_void_p
        ptr = fn(*vals)
        if not ptr:
            return ""
        try:
            return ctypes.string_at(ptr).decode()
        finally:
            _libc.free(ptr)
