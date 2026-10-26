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
Arrays/structs are not passed through this helper in v1.
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
