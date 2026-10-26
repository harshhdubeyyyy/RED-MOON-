"""Forge -> WebAssembly backend (v1, subset).

Emits a real .wasm binary (not text) for a subset of Forge:
  int (i64), bool (i32), void; functions, let/let mut, assign,
  if/else, while, return, calls, recursion, binary/unary ops.
NOT supported in v1 (clear error, not silent miscompile):
  float, str, arrays, structs, enums, match, spawn, extern,
  file I/O, print/println, args, http, clock.
WASM integer arithmetic wraps (like RISC-V, unlike Forge safe
mode) and division by zero traps — the same trade-off as the
big32 backend, stated here, not hidden.
Test it with node: node tools/run_wasm.mjs out.wasm
  (node is available in this VM; no clang/wasm-ld needed,
  because this backend writes the binary directly).
"""

from .errors import ForgeError
from . import ast_nodes as A


def uleb(n):
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            out.append(b | 0x80)
        else:
            out.append(b)
            break
    return bytes(out)


def sleb(n):
    out = bytearray()
    more = True
    while more:
        b = n & 0x7F
        n >>= 7
        if (n == 0 and not (b & 0x40)) or (n == -1 and (b & 0x40)):
            more = False
        else:
            b |= 0x80
        out.append(b)
    return bytes(out)


def vec(items):
    return uleb(len(items)) + b"".join(items)


def section(sid, payload):
    return bytes([sid]) + uleb(len(payload)) + payload


def name(s):
    b = s.encode()
    return uleb(len(b)) + b


I32 = 0x7F
I64 = 0x7E
F64 = 0x7C


def valtype(t):
    if t == "int":
        return I64
    if t == "float":
        return F64
    if t == "bool":
        return I32
    raise ForgeError(f"wasm: type {t} is not supported (v2: int, float, bool, void only)")


class WasmGen:
    def __init__(self, program, types):
        self.program = program
        self.types = types
        self.funcs = [f for f in program.funcs if not getattr(f, "type_params", None)]
        self.func_index = {f.name: i for i, f in enumerate(self.funcs)}
        self.func_ret = {f.name: f.ret for f in self.funcs}
        self.scopes = []
        self.locals = []  # [(valtype)] for locals after params
        self.local_count = 0

    def expr_type(self, expr):
        return self.types.get(id(expr), "int")

    def lookup(self, name):
        for scope in reversed(self.scopes):
            if name in scope:
                return scope[name]
        raise ForgeError(f"wasm: undefined variable '{name}'")

    def gen(self):
        # Validate signatures first, so errors are Forge errors, not bad binaries.
        for fn in self.funcs:
            if fn.ret not in ("void", "int", "float", "bool"):
                raise ForgeError(f"wasm: function '{fn.name}' returns {fn.ret}, not supported in v2")
            for _pn, pt in fn.params:
                if pt not in ("int", "float", "bool"):
                    raise ForgeError(f"wasm: parameter of type {pt} in '{fn.name}' is not supported in v2")
        type_entries = []
        type_index = {}
        for fn in self.funcs:
            key = (tuple(valtype(pt) for _pn, pt in fn.params),
                   tuple([valtype(fn.ret)] if fn.ret != "void" else []))
            if key not in type_index:
                type_index[key] = len(type_entries)
                params = vec([bytes([t]) for t in key[0]])
                results = vec([bytes([t]) for t in key[1]])
                type_entries.append(b"\x60" + params + results)
        type_sec = section(1, vec(type_entries))
        func_sec = section(3, vec([uleb(type_index[(tuple(valtype(pt) for _pn, pt in fn.params),
                                                  tuple([valtype(fn.ret)] if fn.ret != "void" else []))])
                                   for fn in self.funcs]))
        export_entries = []
        for i, fn in enumerate(self.funcs):
            export_entries.append(name(fn.name) + b"\x00" + uleb(i))
        export_sec = section(7, vec(export_entries))
        code_bodies = []
        for fn in self.funcs:
            code_bodies.append(self.gen_func(fn))
        code_sec = section(10, vec(code_bodies))
        return b"\x00asm\x01\x00\x00\x00" + type_sec + func_sec + export_sec + code_sec

    def gen_func(self, fn):
        self.scopes = [{pn: i for i, (pn, _pt) in enumerate(fn.params)}]
        self.locals = []
        self.local_count = len(fn.params)
        body = bytearray()
        for stmt in fn.body.stmts:
            body += self.gen_stmt(stmt)
        body += b"\x0b"  # end
        # Locals are grouped by type in WASM: (count, valtype) runs.
        runs = []
        for t in self.locals:
            if runs and runs[-1][1] == t:
                runs[-1][0] += 1
            else:
                runs.append([1, t])
        locals_vec = vec([uleb(c) + bytes([t]) for c, t in runs])
        full = locals_vec + bytes(body)
        return uleb(len(full)) + full

    def gen_block(self, block):
        self.scopes.append({})
        out = bytearray()
        for stmt in block.stmts:
            out += self.gen_stmt(stmt)
        self.scopes.pop()
        return bytes(out)

    def gen_stmt(self, stmt):
        if isinstance(stmt, A.Let):
            code = self.gen_expr(stmt.expr)
            t = stmt.ann or self.expr_type(stmt.expr)
            if t not in ("int", "float", "bool"):
                raise ForgeError(f"wasm: let of type {t} is not supported in v2")
            idx = self.local_count
            self.local_count += 1
            self.locals.append(valtype(t))
            self.scopes[-1][stmt.name] = idx
            return code + b"\x21" + uleb(idx)  # local.set
        if isinstance(stmt, A.Assign):
            idx = self.lookup(stmt.name)
            return self.gen_expr(stmt.expr) + b"\x21" + uleb(idx)
        if isinstance(stmt, A.Return):
            if stmt.expr is None:
                return b"\x0f"
            return self.gen_expr(stmt.expr) + b"\x0f"
        if isinstance(stmt, A.If):
            cond = self.gen_expr(stmt.cond)
            out = cond + b"\x04\x40"  # if, empty blocktype
            out += self.gen_block(stmt.then)
            if stmt.els is not None:
                out += b"\x05" + self.gen_block(stmt.els)
            out += b"\x0b"
            return out
        if isinstance(stmt, A.While):
            # block { loop { if !cond br 1; body; br 0 } }
            out = b"\x02\x40\x03\x40"
            out += self.gen_expr(stmt.cond)
            out += b"\x45\x0d\x01"  # i32.eqz, br_if 1 (exit block)
            out += self.gen_block(stmt.body)
            out += b"\x0c\x00\x0b\x0b"  # br 0, end loop, end block
            return out
        if isinstance(stmt, A.Block):
            return self.gen_block(stmt)
        if isinstance(stmt, A.ExprStmt):
            code = self.gen_expr(stmt.expr)
            # Drop a non-void call result.
            if isinstance(stmt.expr, A.Call) and self.func_ret.get(stmt.expr.name, "void") != "void":
                code += b"\x1a"
            return code
        raise ForgeError(f"wasm: statement {type(stmt).__name__} is not supported in v1")

    def gen_expr(self, expr):
        if isinstance(expr, A.IntLit):
            return b"\x42" + sleb(int(expr.value))
        if isinstance(expr, A.FloatLit):
            import struct as _struct
            return b"\x44" + _struct.pack("<d", float(expr.value))
        if isinstance(expr, A.StrLit):
            raise ForgeError("wasm: strings are not supported in v1")
        if isinstance(expr, A.BoolLit):
            return b"\x41" + sleb(1 if expr.value else 0)
        if isinstance(expr, A.Var):
            return b"\x20" + uleb(self.lookup(expr.name))
        if isinstance(expr, A.UnaryOp):
            inner = self.gen_expr(expr.expr)
            if expr.op == "-":
                if self.expr_type(expr.expr) == "float":
                    return inner + b"\x9a"  # f64.neg
                # WASM has no integer neg: 0 - x.
                return b"\x42\x00" + inner + b"\x7d"  # i64.const 0, x, i64.sub
            if expr.op == "!":
                return inner + b"\x45"  # i32.eqz
            raise ForgeError(f"wasm: unary {expr.op} is not supported in v1")
        if isinstance(expr, A.BinOp):
            lt = self.expr_type(expr.left)
            left = self.gen_expr(expr.left)
            right = self.gen_expr(expr.right)
            if lt == "int":
                ops = {"+": 0x7C, "-": 0x7D, "*": 0x7E, "/": 0x7F, "%": 0x81,
                       "==": 0x51, "!=": 0x52, "<": 0x53, ">": 0x55, "<=": 0x57, ">=": 0x59}
            elif lt == "float":
                ops = {"+": 0xA0, "-": 0xA1, "*": 0xA2, "/": 0xA3,
                       "==": 0x61, "!=": 0x62, "<": 0x63, ">": 0x64, "<=": 0x65, ">=": 0x66}
            elif lt == "bool":
                ops = {"&&": 0x71, "||": 0x72, "==": 0x46, "!=": 0x47}
            else:
                raise ForgeError(f"wasm: binary op on {lt} is not supported in v1")
            if expr.op not in ops:
                raise ForgeError(f"wasm: operator {expr.op} on {lt} is not supported in v2")
            return left + right + bytes([ops[expr.op]])
        if isinstance(expr, A.Cast):
            inner = self.gen_expr(expr.expr)
            src = self.expr_type(expr.expr)
            if src == "int" and expr.target == "float":
                return inner + b"\xb9"  # f64.convert_i64_s
            if src == "float" and expr.target == "int":
                return inner + b"\xb0"  # i64.trunc_f64_s
            raise ForgeError(f"wasm: cast {src} -> {expr.target} is not supported in v2")
        if isinstance(expr, A.Call):
            if expr.name not in self.func_index:
                raise ForgeError(f"wasm: call to '{expr.name}' is not supported in v1 "
                                 f"(builtins, print, arrays, and strings are out)")
            out = bytearray()
            for a in expr.args:
                out += self.gen_expr(a)
            out += b"\x10" + uleb(self.func_index[expr.name])
            return bytes(out)
        raise ForgeError(f"wasm: expression {type(expr).__name__} is not supported in v1")


def generate_wasm(program, types):
    return WasmGen(program, types).gen()
