"""Static checker for The Jal Pari Language.

Types: int, float, bool, str, void, and [T] dynamic arrays.
Builtins:
  statement-only: print, println, push, fail
  expression: len, range, clock_micros, sqrt, exp, log, pow, abs
Rules: no null, no implicit conversion (except int->float via `as`),
immutable by default, bool conditions only, checked calls, and a
non-void function must end with a return.
"""

import copy

from .errors import ForgeError
from . import ast_nodes as A
from .generics import (parse_generic, mangle_type, substitute_type,
                       unify, contains_type_param)

SCALARS = {"int", "float", "bool", "str"}
STMT_BUILTINS = {"print", "println", "push", "fail", "assert"}
EXPR_BUILTINS = {"len", "range", "clock_micros", "sqrt", "exp", "log", "pow", "abs",
                 "read_file", "write_file", "read_bytes", "write_bytes",
                 "file_exists", "args", "parse_int", "parse_float",
                 "split", "join", "substr", "trim", "starts_with", "ends_with",
                 "http_get", "http_listen", "http_accept", "http_read_request",
                 "http_respond", "http_respond_status", "http_close",
                 "alloc_count", "free_count",
                 "parallel_dot", "parallel_matmul",
                 "arr_alloc_count", "arr_free_count"}
BUILTINS = STMT_BUILTINS | EXPR_BUILTINS


def elem_type(arr_type):
    return arr_type[1:-1] if arr_type.startswith("[") else None


class Checker:
    def __init__(self, program):
        self.program = program
        self.funcs = {}
        self.structs = {}  # name -> {field: type}
        self.struct_params = {}  # name -> [type params]
        self.enums = {}  # name -> [variants]
        self.enum_variants = {}  # variant -> enum name
        self.enum_params = {}  # enum name -> [type params]
        self.enum_payloads = {}  # enum name -> {variant: payload type or None}
        self.enum_instantiations = {}  # concrete type -> {variant: (tag, payload type)}
        self.scopes = []
        self.current_ret = "void"
        self.current_fn = None
        self.current_type_params = []
        self.func_instantiations = {}  # (name, bindings tuple) -> FuncDef
        self.struct_instantiations = {}  # concrete type -> {field: type}
        self._instantiating = set()

    def valid_type(self, t):
        if t in SCALARS or t == "void":
            return True
        if t in self.current_type_params:
            return True
        if t in self.structs or t in self.enums:
            return True
        g = parse_generic(t)
        if g is not None:
            base, args = g
            if base in self.structs:
                if len(args) != len(self.struct_params.get(base, [])):
                    return False
                return all(self.valid_type(a) for a in args)
            if base in self.enums:
                if len(args) != len(self.enum_params.get(base, [])):
                    return False
                return all(self.valid_type(a) for a in args)
            return False
        if t.startswith("[") and t.endswith("]"):
            inner = t[1:-1]
            # Arrays of structs and nested arrays are not yet supported.
            return inner in SCALARS or inner in self.current_type_params
        return False

    def enum_info_for(self, t):
        """Return (base, {variant: (tag, concrete payload type)}) for an enum type."""
        if t in self.enums and not self.enum_params.get(t):
            return t, {v: (i, self.enum_payloads[t][v])
                       for i, v in enumerate(self.enums[t])}
        g = parse_generic(t)
        if g is not None and g[0] in self.enums:
            base, args = g
            params = self.enum_params.get(base, [])
            if len(args) != len(params):
                return None
            if "?" in args:
                return None
            bindings = dict(zip(params, args))
            info = {}
            for i, v in enumerate(self.enums[base]):
                pt = self.enum_payloads[base][v]
                info[v] = (i, substitute_type(pt, bindings) if pt is not None else None)
            self.enum_instantiations[t] = info
            return base, info
        return None

    def fill_placeholder(self, provided, expected):
        """If provided is a generic type with '?' params and expected is
        the same base with concrete params, return expected; else provided."""
        gp = parse_generic(provided)
        ge = parse_generic(expected)
        if gp is not None and ge is not None and gp[0] == ge[0] and len(gp[1]) == len(ge[1]):
            if "?" in gp[1]:
                return expected
        return provided

    def struct_fields_for(self, t):
        """Concrete field dict for a struct type string, or None."""
        if t in self.structs and not self.struct_params.get(t):
            return self.structs[t]
        g = parse_generic(t)
        if g is not None:
            base, args = g
            if base not in self.structs:
                return None
            params = self.struct_params.get(base, [])
            if len(args) != len(params):
                return None
            bindings = dict(zip(params, args))
            return {f: substitute_type(ft, bindings)
                    for f, ft in self.structs[base].items()}
        return None

    def check_structs(self):
        structs = getattr(self.program, "structs", None) or []
        for sd in structs:
            if sd.name in self.structs:
                raise ForgeError(f"duplicate struct '{sd.name}'", sd.line, sd.col)
            if sd.name in SCALARS or sd.name in BUILTINS:
                raise ForgeError(f"'{sd.name}' cannot be a struct name", sd.line, sd.col)
            seen = set()
            fields = {}
            for fname, ftype in sd.fields:
                if fname in seen:
                    raise ForgeError(f"duplicate field '{fname}' in struct '{sd.name}'",
                                     sd.line, sd.col)
                seen.add(fname)
                fields[fname] = ftype
            self.structs[sd.name] = fields
            self.struct_params[sd.name] = list(getattr(sd, "type_params", None) or [])
        # Validate field types now that all struct names are known, and
        # reject recursive structs (C value fields cannot be recursive).
        for sd in structs:
            self.current_type_params = list(getattr(sd, "type_params", None) or [])
            for fname, ftype in sd.fields:
                if not self.valid_type(ftype):
                    raise ForgeError(f"unknown field type '{ftype}' in struct '{sd.name}'",
                                     sd.line, sd.col)
            self.current_type_params = []
            # Cycle check: follow struct-typed fields.
            stack = [sd.name]
            visited = set()
            while stack:
                cur = stack.pop()
                if cur in visited:
                    continue
                visited.add(cur)
                for ftype in self.structs.get(cur, {}).values():
                    if ftype in self.structs:
                        if ftype == sd.name:
                            raise ForgeError(f"recursive struct '{sd.name}' is not supported",
                                             sd.line, sd.col)
                        stack.append(ftype)

    def check_enums(self):
        enums = getattr(self.program, "enums", None) or []
        for ed in enums:
            if ed.name in self.enums or ed.name in self.structs or ed.name in SCALARS:
                raise ForgeError(f"duplicate type '{ed.name}'", ed.line, ed.col)
            seen = set()
            for v in ed.variants:
                if v in seen or v in self.enum_variants:
                    raise ForgeError(f"duplicate enum variant '{v}'", ed.line, ed.col)
                seen.add(v)
                self.enum_variants[v] = ed.name
            self.enums[ed.name] = list(ed.variants)
            self.enum_params[ed.name] = list(getattr(ed, "type_params", None) or [])
            payloads = getattr(ed, "variant_payloads", None) or {}
            self.enum_payloads[ed.name] = {v: payloads.get(v) for v in ed.variants}
            # Validate payload types (type params of this enum are allowed).
            self.current_type_params = list(getattr(ed, "type_params", None) or [])
            for v, pt in self.enum_payloads[ed.name].items():
                if pt is not None and not self.valid_type(pt):
                    raise ForgeError(f"unknown payload type '{pt}' for variant '{v}'",
                                     ed.line, ed.col)
            self.current_type_params = []

    def check(self, require_main=True):
        self.check_structs()
        self.check_enums()
        original_funcs = list(self.program.funcs)
        for fn in original_funcs:
            if fn.name in self.funcs:
                raise ForgeError(f"duplicate function '{fn.name}'", fn.line, fn.col)
            if fn.name in BUILTINS:
                raise ForgeError(f"'{fn.name}' is a builtin and cannot be redefined", fn.line, fn.col)
            self.funcs[fn.name] = fn
        if require_main and "main" not in self.funcs:
            raise ForgeError("a Forge program must define fn main()")
        if "main" in self.funcs:
            main = self.funcs["main"]
            if main.params:
                raise ForgeError("fn main() must take no arguments", main.line, main.col)
            if main.ret not in ("int", "void"):
                raise ForgeError("fn main() must return int or nothing", main.line, main.col)
        for fn in original_funcs:
            self.check_func(fn)
        # Append every generic instantiation found during checking, so
        # infer/codegen see them as ordinary concrete functions/structs.
        for inst in self.func_instantiations.values():
            if inst not in self.program.funcs:
                self.program.funcs.append(inst)
        for ctype, fields in self.struct_instantiations.items():
            from . import ast_nodes as _A
            self.program.structs.append(
                _A.StructDef(mangle_type(ctype), list(fields.items()), 0, 0))
        return self.program

    def instantiate_func(self, fn, bindings, call_line, call_col):
        """Check a concrete copy of a generic function; return it."""
        key = (fn.name, tuple(bindings[p] for p in (fn.type_params or [])))
        if key in self.func_instantiations:
            return self.func_instantiations[key]
        if key in self._instantiating:
            # Recursive call with the same instantiation: the copy is
            # being checked; its return type is already known.
            return None
        mangled = fn.name + "_" + "_".join(mangle_type(bindings[p]) for p in (fn.type_params or []))
        spec = copy.deepcopy(fn)
        spec.name = mangled
        spec.type_params = []
        spec.params = [(n, substitute_type(t, bindings)) for n, t in fn.params]
        spec.ret = substitute_type(fn.ret, bindings)
        self._substitute_let_ann(spec.body, bindings)
        self.func_instantiations[key] = spec
        self._instantiating.add(key)
        try:
            self.check_func(spec)
        finally:
            self._instantiating.discard(key)
        return spec

    def _substitute_let_ann(self, block, bindings):
        for stmt in block.stmts:
            if isinstance(stmt, A.Let) and stmt.ann:
                stmt.ann = substitute_type(stmt.ann, bindings)
            elif isinstance(stmt, A.Block):
                self._substitute_let_ann(stmt, bindings)
            elif isinstance(stmt, A.If):
                self._substitute_let_ann(stmt.then, bindings)
                if stmt.els is not None:
                    self._substitute_let_ann(stmt.els, bindings)
            elif isinstance(stmt, A.While):
                self._substitute_let_ann(stmt.body, bindings)
            elif isinstance(stmt, A.For):
                self._substitute_let_ann(stmt.body, bindings)
            elif isinstance(stmt, A.Match):
                for _pat, _bind, body in stmt.arms:
                    self._substitute_let_ann(body, bindings)

    def check_func(self, fn):
        # Save outer state: checking a generic instantiation can happen
        # in the middle of checking another function (a call site), and
        # must not wipe that function's scopes/return type.
        saved = (self.scopes, self.current_ret, self.current_fn, self.current_type_params)
        try:
            self.current_type_params = list(getattr(fn, "type_params", None) or [])
            for _, pt in fn.params:
                if not self.valid_type(pt) or pt == "void":
                    raise ForgeError(f"parameter type '{pt}' is not a value type", fn.line, fn.col)
            if not self.valid_type(fn.ret):
                raise ForgeError(f"unknown return type '{fn.ret}'", fn.line, fn.col)
            if getattr(fn, "is_extern", False):
                # No body to check; the C function must exist at link time.
                return
            if self.current_type_params:
                # Generic template: body is checked only on instantiation,
                # when every type parameter is concrete.
                return
            self.current_ret = fn.ret
            self.current_fn = fn
            self.scopes = [{n: (t, False) for n, t in fn.params}]
            self.check_block(fn.body)
            if fn.ret != "void":
                if not fn.body.stmts or not isinstance(fn.body.stmts[-1], A.Return):
                    raise ForgeError(f"function '{fn.name}' returns {fn.ret} but its body "
                                     f"does not end with a return", fn.line, fn.col)
        finally:
            self.scopes, self.current_ret, self.current_fn, self.current_type_params = saved

    def lookup(self, name, line, col):
        for scope in reversed(self.scopes):
            if name in scope:
                return scope[name]
        if name in self.enum_variants:
            return (self.enum_variants[name], False)
        raise ForgeError(f"undefined variable '{name}'", line, col)

    def check_block(self, block):
        self.scopes.append({})
        for stmt in block.stmts:
            self.check_stmt(stmt)
        self.scopes.pop()

    def check_stmt(self, stmt):
        if isinstance(stmt, A.Block):
            self.check_block(stmt)
            return
        if isinstance(stmt, A.Let):
            if stmt.name in self.scopes[-1]:
                raise ForgeError(f"variable '{stmt.name}' is already defined in this scope",
                                 stmt.line, stmt.col)
            t = self.check_expr(stmt.expr)
            if stmt.ann is not None:
                if not self.valid_type(stmt.ann) or stmt.ann == "void":
                    raise ForgeError(f"unknown type '{stmt.ann}'", stmt.line, stmt.col)
                # Fill a generic-enum placeholder from the annotation.
                filled = self.fill_placeholder(t, stmt.ann)
                if filled != t:
                    if isinstance(stmt.expr, A.Call):
                        stmt.expr.concrete_type = filled
                    t = filled
                elif isinstance(stmt.expr, A.Var) and stmt.expr.name in self.enum_variants:
                    enum_name = self.enum_variants[stmt.expr.name]
                    if parse_generic(stmt.ann) and parse_generic(stmt.ann)[0] == enum_name:
                        t = stmt.ann
                if t != stmt.ann:
                    # Empty array literal has no element type of its own.
                    if not (isinstance(stmt.expr, A.ArrayLit) and not stmt.expr.elems
                            and stmt.ann.startswith("[")):
                        raise ForgeError(f"variable '{stmt.name}' is declared {stmt.ann} "
                                         f"but initialised with {t}", stmt.line, stmt.col)
                    t = stmt.ann
            self.scopes[-1][stmt.name] = (t, stmt.mutable)
            return
        if isinstance(stmt, A.Assign):
            vt, mutable = self.lookup(stmt.name, stmt.line, stmt.col)
            if not mutable:
                raise ForgeError(f"cannot assign to immutable variable '{stmt.name}' "
                                 f"(declare it with 'let mut')", stmt.line, stmt.col)
            et = self.check_expr(stmt.expr)
            if et != vt:
                if not (isinstance(stmt.expr, A.ArrayLit) and not stmt.expr.elems
                        and vt.startswith("[")):
                    raise ForgeError(f"cannot assign {et} to {vt} variable '{stmt.name}'",
                                     stmt.line, stmt.col)
            return
        if isinstance(stmt, A.FieldAssign):
            # Outermost variable must be mutable; field type comes from
            # checking the target FieldAccess expression itself.
            node = stmt.target
            while isinstance(node, A.FieldAccess):
                node = node.base
            if not isinstance(node, A.Var):
                raise ForgeError("field assignment target must start from a variable",
                                 stmt.line, stmt.col)
            _vt, mutable = self.lookup(node.name, stmt.line, stmt.col)
            if not mutable:
                raise ForgeError(f"cannot assign to a field of immutable variable "
                                 f"'{node.name}' (declare it with 'let mut')",
                                 stmt.line, stmt.col)
            ft = self.check_expr(stmt.target)
            vt2 = self.check_expr(stmt.expr)
            if vt2 != ft:
                raise ForgeError(f"cannot assign {vt2} to field of type {ft}",
                                 stmt.line, stmt.col)
            return
        if isinstance(stmt, A.IndexAssign):
            base = stmt.base.base
            if isinstance(base, A.Var):
                vt, _mutable = self.lookup(base.name, stmt.line, stmt.col)
                et = elem_type(vt)
            elif isinstance(base, A.FieldAccess):
                # e.g. m.vals[i] = v — array contents, not a rebinding,
                # so mutability of the struct variable is not required.
                vt = self.check_expr(base)
                et = elem_type(vt)
            else:
                raise ForgeError("index assignment target must be a variable or a field",
                                 stmt.line, stmt.col)
            if et is None:
                raise ForgeError(f"cannot index a non-array value of type {vt}",
                                 stmt.line, stmt.col)
            it = self.check_expr(stmt.base.index)
            if it != "int":
                raise ForgeError("array index must be int", stmt.line, stmt.col)
            vt2 = self.check_expr(stmt.expr)
            if vt2 != et:
                raise ForgeError(f"cannot assign {vt2} to element of type {et}",
                                 stmt.line, stmt.col)
            return
        if isinstance(stmt, A.Match):
            et = self.check_expr(stmt.expr)
            info = self.enum_info_for(et)
            if info is None:
                raise ForgeError(f"match needs an enum value, got {et}",
                                 stmt.line, stmt.col)
            _base, variant_info = info
            variants = set(variant_info.keys())
            seen = set()
            has_wildcard = False
            for idx, (pat, binding, body) in enumerate(stmt.arms):
                if pat == "_":
                    has_wildcard = True
                    if idx != len(stmt.arms) - 1:
                        raise ForgeError("match wildcard '_' must be the last arm",
                                         stmt.line, stmt.col)
                    if binding is not None:
                        raise ForgeError("wildcard arm cannot bind a value", stmt.line, stmt.col)
                    self.check_block(body)
                    continue
                if pat not in variants:
                    raise ForgeError(f"'{pat}' is not a variant of enum '{et}'",
                                     stmt.line, stmt.col)
                if pat in seen:
                    raise ForgeError(f"duplicate match arm '{pat}'", stmt.line, stmt.col)
                seen.add(pat)
                _tag, payload_type = variant_info[pat]
                if payload_type is None and binding is not None:
                    raise ForgeError(f"variant '{pat}' has no payload to bind",
                                     stmt.line, stmt.col)
                if payload_type is not None and binding is None:
                    raise ForgeError(f"variant '{pat}' has a payload; write {pat}(name) => ...",
                                     stmt.line, stmt.col)
                if binding is not None:
                    # Check the arm body with the binding in scope.
                    self.scopes.append({binding: (payload_type, False)})
                    try:
                        self.check_block(body)
                    finally:
                        self.scopes.pop()
                else:
                    self.check_block(body)
            if not has_wildcard and seen != variants:
                missing = sorted(variants - seen)
                raise ForgeError(f"match is not exhaustive; missing: {', '.join(missing)}",
                                 stmt.line, stmt.col)
            return
        if isinstance(stmt, A.Spawn):
            call = stmt.call
            fn = self.funcs.get(call.name)
            if fn is None:
                raise ForgeError(f"spawn: undefined function '{call.name}'",
                                 stmt.line, stmt.col)
            if fn.ret != "void":
                raise ForgeError("spawn: function must return void", stmt.line, stmt.col)
            if len(call.args) > 1:
                raise ForgeError("spawn: function must take 0 or 1 int argument",
                                 stmt.line, stmt.col)
            if call.args and self.check_expr(call.args[0]) != "int":
                raise ForgeError("spawn: argument must be int", stmt.line, stmt.col)
            if len(fn.params) != len(call.args):
                raise ForgeError("spawn: argument count does not match function",
                                 stmt.line, stmt.col)
            return
        if isinstance(stmt, A.If):
            if self.check_expr(stmt.cond) != "bool":
                raise ForgeError("if condition must be bool", stmt.line, stmt.col)
            self.check_block(stmt.then)
            if stmt.els is not None:
                self.check_block(stmt.els)
            return
        if isinstance(stmt, A.While):
            if self.check_expr(stmt.cond) != "bool":
                raise ForgeError("while condition must be bool", stmt.line, stmt.col)
            self.check_block(stmt.body)
            return
        if isinstance(stmt, A.For):
            at = self.check_expr(stmt.expr)
            et = elem_type(at)
            if et is None:
                raise ForgeError(f"for loop needs an array, got {at}", stmt.line, stmt.col)
            self.scopes.append({stmt.name: (et, False)})
            for s in stmt.body.stmts:
                self.check_stmt(s)
            self.scopes.pop()
            return
        if isinstance(stmt, A.Return):
            if self.current_ret == "void":
                if stmt.expr is not None:
                    raise ForgeError("void function cannot return a value", stmt.line, stmt.col)
            else:
                if stmt.expr is None:
                    raise ForgeError(f"function must return {self.current_ret}",
                                     stmt.line, stmt.col)
                t = self.check_expr(stmt.expr)
                filled = self.fill_placeholder(t, self.current_ret)
                if filled != t:
                    if isinstance(stmt.expr, A.Call):
                        stmt.expr.concrete_type = filled
                    t = filled
                elif isinstance(stmt.expr, A.Var) and stmt.expr.name in self.enum_variants:
                    enum_name = self.enum_variants[stmt.expr.name]
                    if parse_generic(self.current_ret) and parse_generic(self.current_ret)[0] == enum_name:
                        t = self.current_ret
                if t != self.current_ret:
                    if not (isinstance(stmt.expr, A.ArrayLit) and not stmt.expr.elems
                            and self.current_ret.startswith("[")):
                        raise ForgeError(f"return type is {t}, function returns "
                                         f"{self.current_ret}", stmt.line, stmt.col)
            return
        if isinstance(stmt, A.ExprStmt):
            if not isinstance(stmt.expr, A.Call):
                raise ForgeError("an expression statement must be a function call",
                                 stmt.line, stmt.col)
            call = stmt.expr
            if call.name in STMT_BUILTINS:
                self.check_stmt_builtin(call)
                return
            if call.name in EXPR_BUILTINS:
                raise ForgeError(f"'{call.name}' is an expression, not a statement; "
                                 f"use its value", stmt.line, stmt.col)
            self.check_expr(call)
            return
        raise ForgeError(f"unsupported statement {type(stmt).__name__}", stmt.line, stmt.col)

    def check_stmt_builtin(self, call):
        if call.name == "assert":
            if len(call.args) != 2:
                raise ForgeError("assert() takes a bool condition and a str message",
                                 call.line, call.col)
            if self.check_expr(call.args[0]) != "bool":
                raise ForgeError("assert() condition must be bool", call.line, call.col)
            if self.check_expr(call.args[1]) != "str":
                raise ForgeError("assert() message must be str", call.line, call.col)
            return
        if call.name in ("print", "println"):
            for a in call.args:
                self.check_expr(a)
            return
        if call.name == "fail":
            if len(call.args) != 1 or self.check_expr(call.args[0]) != "str":
                raise ForgeError("fail() takes exactly one str argument", call.line, call.col)
            return
        if call.name == "push":
            if len(call.args) != 2 or not isinstance(call.args[0], (A.Var, A.FieldAccess)):
                raise ForgeError("push() takes a variable or field and a value", call.line, call.col)
            if isinstance(call.args[0], A.Var):
                vt, _m = self.lookup(call.args[0].name, call.line, call.col)
            else:
                vt = self.check_expr(call.args[0])
            et = elem_type(vt)
            if et is None:
                raise ForgeError(f"push() needs an array, got {vt}", call.line, call.col)
            vt2 = self.check_expr(call.args[1])
            if vt2 != et:
                raise ForgeError(f"push() value must be {et}, got {vt2}", call.line, call.col)
            return
        raise ForgeError(f"unknown builtin '{call.name}'", call.line, call.col)

    def check_expr(self, expr):
        if isinstance(expr, A.IntLit):
            return "int"
        if isinstance(expr, A.FloatLit):
            return "float"
        if isinstance(expr, A.StrLit):
            return "str"
        if isinstance(expr, A.BoolLit):
            return "bool"
        if isinstance(expr, A.Var):
            return self.lookup(expr.name, expr.line, expr.col)[0]
        if isinstance(expr, A.ArrayLit):
            if not expr.elems:
                return "[?]"
            t0 = self.check_expr(expr.elems[0])
            for e in expr.elems[1:]:
                if self.check_expr(e) != t0:
                    raise ForgeError("array literal elements must all have the same type",
                                     e.line, e.col)
            return f"[{t0}]"
        if isinstance(expr, A.StructLit):
            if expr.name not in self.structs:
                raise ForgeError(f"undefined struct '{expr.name}'", expr.line, expr.col)
            template_fields = self.structs[expr.name]
            params = self.struct_params.get(expr.name, [])
            provided = {}
            for fname, fexpr in expr.fields:
                if fname not in template_fields:
                    raise ForgeError(f"struct '{expr.name}' has no field '{fname}'",
                                     expr.line, expr.col)
                if fname in provided:
                    raise ForgeError(f"duplicate field '{fname}' in struct literal",
                                     expr.line, expr.col)
                provided[fname] = self.check_expr(fexpr)
            missing = [f for f in template_fields if f not in provided]
            if missing:
                raise ForgeError(f"struct literal '{expr.name}' is missing field(s): "
                                 f"{', '.join(missing)}", expr.line, expr.col)
            if params:
                # Infer the concrete type from the field values.
                bindings = {}
                for fname, ftype in template_fields.items():
                    if not unify(ftype, provided[fname], bindings, params):
                        raise ForgeError(f"field '{fname}' of '{expr.name}' must match {ftype}, "
                                         f"got {provided[fname]}", expr.line, expr.col)
                missing_p = [p for p in params if p not in bindings]
                if missing_p:
                    raise ForgeError(f"could not infer type parameter(s) {', '.join(missing_p)} "
                                     f"for struct '{expr.name}'", expr.line, expr.col)
                concrete = expr.name + "<" + ", ".join(bindings[p] for p in params) + ">"
                fields = {f: substitute_type(ft, bindings) for f, ft in template_fields.items()}
                self.struct_instantiations[concrete] = fields
                expr.concrete_type = concrete
                # Re-check field types against the concrete fields
                # (unify already ensured the type-param fields match;
                # concrete fields must match exactly, except empty arrays).
                for fname, ftype in fields.items():
                    if provided[fname] != ftype:
                        fexpr = dict(expr.fields)[fname]
                        if not (isinstance(fexpr, A.ArrayLit) and not fexpr.elems
                                and ftype.startswith("[")):
                            raise ForgeError(f"field '{fname}' of '{expr.name}' must be {ftype}, "
                                             f"got {provided[fname]}", expr.line, expr.col)
                return concrete
            fields = template_fields
            for fname, ftype in fields.items():
                if provided[fname] != ftype:
                    # Empty array literal, like in let, takes the field type.
                    fexpr = dict(expr.fields)[fname]
                    if not (isinstance(fexpr, A.ArrayLit) and not fexpr.elems
                            and ftype.startswith("[")):
                        raise ForgeError(f"field '{fname}' of '{expr.name}' must be {ftype}, "
                                         f"got {provided[fname]}", expr.line, expr.col)
            expr.concrete_type = expr.name
            return expr.name
        if isinstance(expr, A.FieldAccess):
            bt = self.check_expr(expr.base)
            fields = self.struct_fields_for(bt)
            if fields is None:
                raise ForgeError(f"cannot access a field on a non-struct value of type {bt}",
                                 expr.line, expr.col)
            if expr.field not in fields:
                raise ForgeError(f"struct '{bt}' has no field '{expr.field}'",
                                 expr.line, expr.col)
            return fields[expr.field]
        if isinstance(expr, A.Index):
            bt = self.check_expr(expr.base)
            et = elem_type(bt)
            if et is None:
                raise ForgeError(f"cannot index a non-array value of type {bt}",
                                 expr.line, expr.col)
            if self.check_expr(expr.index) != "int":
                raise ForgeError("array index must be int", expr.line, expr.col)
            return et
        if isinstance(expr, A.Cast):
            t = self.check_expr(expr.expr)
            if not self.valid_type(expr.target) or expr.target == "void":
                raise ForgeError(f"unknown cast target '{expr.target}'", expr.line, expr.col)
            if (t, expr.target) not in (("int", "float"), ("float", "int")):
                raise ForgeError(f"cannot cast {t} to {expr.target}", expr.line, expr.col)
            return expr.target
        if isinstance(expr, A.Try):
            t = self.check_expr(expr.expr)
            ret = self.current_ret
            g = parse_generic(t)
            rg = parse_generic(ret)
            if g is not None and g[0] == "Option" and rg is not None and rg[0] == "Option":
                fields = self.struct_fields_for(t)
                if not fields or fields.get("present") != "bool" or "value" not in fields:
                    raise ForgeError("? for Option needs a struct with present: bool and value fields",
                                     expr.line, expr.col)
                expr.kind = "Option"
                expr.value_type = g[1][0]
                expr.ret_type = ret
                return g[1][0]
            if g is not None and g[0] == "Result" and rg is not None and rg[0] == "Result":
                if g[1][1] != rg[1][1]:
                    raise ForgeError(f"? error type mismatch: expression is Result<_, {g[1][1]}> "
                                     f"but function returns Result<_, {rg[1][1]}>",
                                     expr.line, expr.col)
                fields = self.struct_fields_for(t)
                if not fields or fields.get("ok") != "bool" or "value" not in fields or "error" not in fields:
                    raise ForgeError("? for Result needs a struct with ok: bool, value, error fields",
                                     expr.line, expr.col)
                expr.kind = "Result"
                expr.value_type = g[1][0]
                expr.ret_type = ret
                expr.error_type = g[1][1]
                return g[1][0]
            raise ForgeError(f"? needs an Option or Result value whose type matches "
                             f"the function's return type {ret}, got {t}",
                             expr.line, expr.col)
        if isinstance(expr, A.UnaryOp):
            t = self.check_expr(expr.expr)
            if expr.op == "-" and t in ("int", "float"):
                return t
            if expr.op == "!" and t == "bool":
                return "bool"
            raise ForgeError(f"operator '{expr.op}' does not apply to {t}", expr.line, expr.col)
        if isinstance(expr, A.BinOp):
            return self.check_binop(expr)
        if isinstance(expr, A.Call):
            return self.check_call(expr)
        raise ForgeError(f"unsupported expression {type(expr).__name__}", expr.line, expr.col)

    def check_call(self, call):
        if call.name in STMT_BUILTINS:
            raise ForgeError(f"'{call.name}' can only be used as a statement, not as a value",
                             call.line, call.col)
        if call.name in self.enum_variants:
            enum_name = self.enum_variants[call.name]
            payload = self.enum_payloads[enum_name][call.name]
            params = self.enum_params.get(enum_name, [])
            if payload is None:
                if call.args:
                    raise ForgeError(f"variant '{call.name}' takes no payload", call.line, call.col)
                if params:
                    call.concrete_type = enum_name + "<" + ", ".join("?" for _ in params) + ">"
                else:
                    call.concrete_type = enum_name
                return call.concrete_type
            if len(call.args) != 1:
                raise ForgeError(f"variant '{call.name}' takes exactly one payload argument",
                                 call.line, call.col)
            at = self.check_expr(call.args[0])
            if not params:
                if at != payload:
                    raise ForgeError(f"variant '{call.name}' payload must be {payload}, got {at}",
                                     call.line, call.col)
                call.concrete_type = enum_name
                return enum_name
            bindings = {}
            if not unify(payload, at, bindings, params):
                raise ForgeError(f"variant '{call.name}' payload must match {payload}, got {at}",
                                 call.line, call.col)
            concrete_args = [bindings.get(p, "?") for p in params]
            call.concrete_type = enum_name + "<" + ", ".join(concrete_args) + ">"
            return call.concrete_type
        if call.name == "len":
            if len(call.args) != 1:
                raise ForgeError("len() takes exactly one argument", call.line, call.col)
            t = self.check_expr(call.args[0])
            if t != "str" and elem_type(t) is None:
                raise ForgeError(f"len() needs a str or array, got {t}", call.line, call.col)
            return "int"
        if call.name == "range":
            if len(call.args) != 1 or self.check_expr(call.args[0]) != "int":
                raise ForgeError("range() takes exactly one int argument", call.line, call.col)
            return "[int]"
        if call.name == "clock_micros":
            if call.args:
                raise ForgeError("clock_micros() takes no arguments", call.line, call.col)
            return "int"
        if call.name in ("alloc_count", "free_count", "arr_alloc_count", "arr_free_count"):
            if call.args:
                raise ForgeError(f"{call.name}() takes no arguments", call.line, call.col)
            return "int"
        if call.name == "parallel_dot":
            if len(call.args) != 2 or self.check_expr(call.args[0]) != "[float]" or self.check_expr(call.args[1]) != "[float]":
                raise ForgeError("parallel_dot() takes two [float] arguments", call.line, call.col)
            return "float"
        if call.name == "parallel_matmul":
            if len(call.args) != 3 or self.check_expr(call.args[0]) != "[float]" or self.check_expr(call.args[1]) != "[float]" or self.check_expr(call.args[2]) != "int":
                raise ForgeError("parallel_matmul() takes [float], [float], int", call.line, call.col)
            return "[float]"
        if call.name in ("sqrt", "exp", "log"):
            if len(call.args) != 1 or self.check_expr(call.args[0]) != "float":
                raise ForgeError(f"{call.name}() takes exactly one float argument",
                                 call.line, call.col)
            return "float"
        if call.name == "pow":
            if len(call.args) != 2:
                raise ForgeError("pow() takes exactly two arguments", call.line, call.col)
            for a in call.args:
                if self.check_expr(a) != "float":
                    raise ForgeError("pow() takes float arguments", call.line, call.col)
            return "float"
        if call.name == "abs":
            if len(call.args) != 1 or self.check_expr(call.args[0]) != "int":
                raise ForgeError("abs() takes exactly one int argument", call.line, call.col)
            return "int"
        if call.name == "file_exists":
            if len(call.args) != 1 or self.check_expr(call.args[0]) != "str":
                raise ForgeError("file_exists() takes exactly one str argument",
                                 call.line, call.col)
            return "bool"
        if call.name == "read_file":
            if len(call.args) != 1 or self.check_expr(call.args[0]) != "str":
                raise ForgeError("read_file() takes exactly one str argument",
                                 call.line, call.col)
            return "str"
        if call.name == "write_file":
            if len(call.args) != 2:
                raise ForgeError("write_file() takes exactly two arguments",
                                 call.line, call.col)
            for a in call.args:
                if self.check_expr(a) != "str":
                    raise ForgeError("write_file() takes str arguments", call.line, call.col)
            return "bool"
        if call.name == "read_bytes":
            if len(call.args) != 1 or self.check_expr(call.args[0]) != "str":
                raise ForgeError("read_bytes() takes exactly one str argument",
                                 call.line, call.col)
            return "[int]"
        if call.name == "write_bytes":
            if len(call.args) != 2:
                raise ForgeError("write_bytes() takes exactly two arguments",
                                 call.line, call.col)
            if self.check_expr(call.args[0]) != "str":
                raise ForgeError("write_bytes() takes a str path", call.line, call.col)
            if self.check_expr(call.args[1]) != "[int]":
                raise ForgeError("write_bytes() takes [int] data", call.line, call.col)
            return "bool"
        if call.name == "args":
            if call.args:
                raise ForgeError("args() takes no arguments", call.line, call.col)
            return "[str]"
        if call.name == "parse_int":
            if len(call.args) != 1 or self.check_expr(call.args[0]) != "str":
                raise ForgeError("parse_int() takes exactly one str argument",
                                 call.line, call.col)
            return "int"
        if call.name == "parse_float":
            if len(call.args) != 1 or self.check_expr(call.args[0]) != "str":
                raise ForgeError("parse_float() takes exactly one str argument",
                                 call.line, call.col)
            return "float"
        if call.name == "split":
            if len(call.args) != 2:
                raise ForgeError("split() takes exactly two arguments", call.line, call.col)
            for a in call.args:
                if self.check_expr(a) != "str":
                    raise ForgeError("split() takes str arguments", call.line, call.col)
            return "[str]"
        if call.name == "join":
            if len(call.args) != 2:
                raise ForgeError("join() takes exactly two arguments", call.line, call.col)
            if self.check_expr(call.args[0]) != "[str]":
                raise ForgeError("join() takes a [str] as its first argument",
                                 call.line, call.col)
            if self.check_expr(call.args[1]) != "str":
                raise ForgeError("join() takes a str separator", call.line, call.col)
            return "str"
        if call.name == "substr":
            if len(call.args) != 3:
                raise ForgeError("substr() takes exactly three arguments", call.line, call.col)
            if self.check_expr(call.args[0]) != "str":
                raise ForgeError("substr() takes a str as its first argument",
                                 call.line, call.col)
            for a in call.args[1:]:
                if self.check_expr(a) != "int":
                    raise ForgeError("substr() takes int start and length",
                                     call.line, call.col)
            return "str"
        if call.name == "trim":
            if len(call.args) != 1 or self.check_expr(call.args[0]) != "str":
                raise ForgeError("trim() takes exactly one str argument",
                                 call.line, call.col)
            return "str"
        if call.name in ("starts_with", "ends_with"):
            if len(call.args) != 2:
                raise ForgeError(f"{call.name}() takes exactly two arguments",
                                 call.line, call.col)
            for a in call.args:
                if self.check_expr(a) != "str":
                    raise ForgeError(f"{call.name}() takes str arguments",
                                     call.line, call.col)
            return "bool"
        if call.name == "http_get":
            if len(call.args) != 1 or self.check_expr(call.args[0]) != "str":
                raise ForgeError("http_get() takes exactly one str URL argument",
                                 call.line, call.col)
            return "str"
        if call.name == "http_listen":
            if len(call.args) != 1 or self.check_expr(call.args[0]) != "int":
                raise ForgeError("http_listen() takes exactly one int port argument",
                                 call.line, call.col)
            return "int"
        if call.name in ("http_accept", "http_close"):
            if len(call.args) != 1 or self.check_expr(call.args[0]) != "int":
                raise ForgeError(f"{call.name}() takes exactly one int fd argument",
                                 call.line, call.col)
            return "int"
        if call.name == "http_read_request":
            if len(call.args) != 1 or self.check_expr(call.args[0]) != "int":
                raise ForgeError("http_read_request() takes exactly one int client fd argument",
                                 call.line, call.col)
            return "str"
        if call.name == "http_respond":
            if len(call.args) != 2 or self.check_expr(call.args[0]) != "int" or self.check_expr(call.args[1]) != "str":
                raise ForgeError("http_respond() takes (int client fd, str body)",
                                 call.line, call.col)
            return "int"
        if call.name == "http_respond_status":
            if len(call.args) != 3 or self.check_expr(call.args[0]) != "int" or self.check_expr(call.args[1]) != "int" or self.check_expr(call.args[2]) != "str":
                raise ForgeError("http_respond_status() takes (int client fd, int status, str body)",
                                 call.line, call.col)
            return "int"
        fn = self.funcs.get(call.name)
        if fn is None:
            raise ForgeError(f"undefined function '{call.name}'", call.line, call.col)
        if len(call.args) != len(fn.params):
            raise ForgeError(f"'{call.name}' takes {len(fn.params)} argument(s), "
                             f"got {len(call.args)}", call.line, call.col)
        if getattr(fn, "type_params", None):
            # Generic call: infer bindings from argument types, then
            # check the concrete copy and rewrite this call to it.
            type_params = fn.type_params
            if self.current_type_params:
                # The caller itself is generic (its body is only
                # checked on instantiation, so this call will be
                # re-checked then with concrete types).
                arg_types = [self.check_expr(a) for a in call.args]
                bindings = {}
                ok = True
                for (pn, pt), t in zip(fn.params, arg_types):
                    if not unify(pt, t, bindings, type_params):
                        ok = False
                if not ok:
                    raise ForgeError(f"argument types do not match generic function '{call.name}'",
                                     call.line, call.col)
                # Return the substituted return type for template checking;
                # the concrete call is resolved when the caller is instantiated.
                return substitute_type(fn.ret, bindings)
            arg_types = [self.check_expr(a) for a in call.args]
            for t in arg_types:
                if contains_type_param(t, self.current_type_params):
                    raise ForgeError("generic function cannot be called with an abstract type",
                                     call.line, call.col)
            bindings = {}
            for (pn, pt), t in zip(fn.params, arg_types):
                if not unify(pt, t, bindings, type_params):
                    raise ForgeError(f"argument '{pn}' of '{call.name}' must match {pt}, got {t}",
                                     call.line, call.col)
            missing = [p for p in type_params if p not in bindings]
            if missing:
                raise ForgeError(f"could not infer type parameter(s) {', '.join(missing)} "
                                 f"for '{call.name}'", call.line, call.col)
            spec = self.instantiate_func(fn, bindings, call.line, call.col)
            if spec is not None:
                call.name = spec.name
                return spec.ret
            # Recursive instantiation in progress: return substituted ret.
            return substitute_type(fn.ret, bindings)
        for arg, (pn, pt) in zip(call.args, fn.params):
            t = self.check_expr(arg)
            filled = self.fill_placeholder(t, pt)
            if filled != t:
                if isinstance(arg, A.Call):
                    arg.concrete_type = filled
                t = filled
            if t != pt:
                if not (isinstance(arg, A.ArrayLit) and not arg.elems and pt.startswith("[")):
                    raise ForgeError(f"argument '{pn}' of '{call.name}' must be {pt}, got {t}",
                                     call.line, call.col)
        return fn.ret

    def check_binop(self, node):
        lt = self.check_expr(node.left)
        rt = self.check_expr(node.right)
        op = node.op
        if op in ("+", "-", "*", "/", "%"):
            if op == "+" and lt == "str" and rt == "str":
                return "str"
            if op == "%" and lt == "int" and rt == "int":
                return "int"
            if op in ("+", "-", "*", "/") and lt == rt and lt in ("int", "float"):
                return lt
            raise ForgeError(f"operator '{op}' needs matching int or float operands "
                             f"(or str + str), got {lt} and {rt}", node.line, node.col)
        if op in ("<", "<=", ">", ">="):
            if lt == rt and lt in ("int", "float"):
                return "bool"
            raise ForgeError(f"operator '{op}' needs matching int or float operands, "
                             f"got {lt} and {rt}", node.line, node.col)
        if op in ("==", "!="):
            if lt == rt and (lt in ("int", "float", "bool", "str") or lt in self.enums):
                return "bool"
            raise ForgeError(f"operator '{op}' needs matching int, float, bool, str or enum "
                             f"operands, got {lt} and {rt}", node.line, node.col)
        if op in ("&&", "||"):
            if lt == "bool" and rt == "bool":
                return "bool"
            raise ForgeError(f"operator '{op}' needs bool operands, got {lt} and {rt}",
                             node.line, node.col)
        raise ForgeError(f"unknown operator '{op}'", node.line, node.col)


def check(program, require_main=True):
    Checker(program).check(require_main=require_main)
