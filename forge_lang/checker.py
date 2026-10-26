"""Static checker for Forge v2.

Types: int, float, bool, str, void, and [T] dynamic arrays.
Builtins:
  statement-only: print, println, push, fail
  expression: len, range, clock_micros, sqrt, exp, log, pow, abs
Rules: no null, no implicit conversion (except int->float via `as`),
immutable by default, bool conditions only, checked calls, and a
non-void function must end with a return.
"""

from .errors import ForgeError
from . import ast_nodes as A

SCALARS = {"int", "float", "bool", "str"}
STMT_BUILTINS = {"print", "println", "push", "fail"}
EXPR_BUILTINS = {"len", "range", "clock_micros", "sqrt", "exp", "log", "pow", "abs",
                 "read_file", "write_file", "args", "parse_int",
                 "split", "join", "substr", "trim", "starts_with", "ends_with"}
BUILTINS = STMT_BUILTINS | EXPR_BUILTINS


def elem_type(arr_type):
    return arr_type[1:-1] if arr_type.startswith("[") else None


class Checker:
    def __init__(self, program):
        self.program = program
        self.funcs = {}
        self.structs = {}  # name -> {field: type}
        self.scopes = []
        self.current_ret = "void"
        self.current_fn = None

    def valid_type(self, t):
        if t in SCALARS or t == "void":
            return True
        if t in self.structs:
            return True
        if t.startswith("[") and t.endswith("]"):
            inner = t[1:-1]
            # Arrays of structs and nested arrays are not yet supported.
            return inner in SCALARS
        return False

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
        # Validate field types now that all struct names are known, and
        # reject recursive structs (C value fields cannot be recursive).
        for sd in structs:
            for fname, ftype in sd.fields:
                if not self.valid_type(ftype):
                    raise ForgeError(f"unknown field type '{ftype}' in struct '{sd.name}'",
                                     sd.line, sd.col)
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

    def check(self):
        self.check_structs()
        for fn in self.program.funcs:
            if fn.name in self.funcs:
                raise ForgeError(f"duplicate function '{fn.name}'", fn.line, fn.col)
            if fn.name in BUILTINS:
                raise ForgeError(f"'{fn.name}' is a builtin and cannot be redefined", fn.line, fn.col)
            self.funcs[fn.name] = fn
        if "main" not in self.funcs:
            raise ForgeError("a Forge program must define fn main()")
        main = self.funcs["main"]
        if main.params:
            raise ForgeError("fn main() must take no arguments", main.line, main.col)
        if main.ret not in ("int", "void"):
            raise ForgeError("fn main() must return int or nothing", main.line, main.col)
        for fn in self.program.funcs:
            self.check_func(fn)

    def check_func(self, fn):
        for _, pt in fn.params:
            if not self.valid_type(pt) or pt == "void":
                raise ForgeError(f"parameter type '{pt}' is not a value type", fn.line, fn.col)
        if not self.valid_type(fn.ret):
            raise ForgeError(f"unknown return type '{fn.ret}'", fn.line, fn.col)
        self.current_ret = fn.ret
        self.current_fn = fn
        self.scopes = [{n: (t, False) for n, t in fn.params}]
        self.check_block(fn.body)
        self.scopes = []
        if fn.ret != "void":
            if not fn.body.stmts or not isinstance(fn.body.stmts[-1], A.Return):
                raise ForgeError(f"function '{fn.name}' returns {fn.ret} but its body "
                                 f"does not end with a return", fn.line, fn.col)

    def lookup(self, name, line, col):
        for scope in reversed(self.scopes):
            if name in scope:
                return scope[name]
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
            if not isinstance(base, A.Var):
                raise ForgeError("index assignment target must be a plain variable",
                                 stmt.line, stmt.col)
            vt, _mutable = self.lookup(base.name, stmt.line, stmt.col)
            et = elem_type(vt)
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
        if call.name in ("print", "println"):
            for a in call.args:
                self.check_expr(a)
            return
        if call.name == "fail":
            if len(call.args) != 1 or self.check_expr(call.args[0]) != "str":
                raise ForgeError("fail() takes exactly one str argument", call.line, call.col)
            return
        if call.name == "push":
            if len(call.args) != 2 or not isinstance(call.args[0], A.Var):
                raise ForgeError("push() takes a variable and a value", call.line, call.col)
            vt, _m = self.lookup(call.args[0].name, call.line, call.col)
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
            fields = self.structs[expr.name]
            provided = {}
            for fname, fexpr in expr.fields:
                if fname not in fields:
                    raise ForgeError(f"struct '{expr.name}' has no field '{fname}'",
                                     expr.line, expr.col)
                if fname in provided:
                    raise ForgeError(f"duplicate field '{fname}' in struct literal",
                                     expr.line, expr.col)
                provided[fname] = self.check_expr(fexpr)
            missing = [f for f in fields if f not in provided]
            if missing:
                raise ForgeError(f"struct literal '{expr.name}' is missing field(s): "
                                 f"{', '.join(missing)}", expr.line, expr.col)
            for fname, ftype in fields.items():
                if provided[fname] != ftype:
                    raise ForgeError(f"field '{fname}' of '{expr.name}' must be {ftype}, "
                                     f"got {provided[fname]}", expr.line, expr.col)
            return expr.name
        if isinstance(expr, A.FieldAccess):
            bt = self.check_expr(expr.base)
            if bt not in self.structs:
                raise ForgeError(f"cannot access a field on a non-struct value of type {bt}",
                                 expr.line, expr.col)
            if expr.field not in self.structs[bt]:
                raise ForgeError(f"struct '{bt}' has no field '{expr.field}'",
                                 expr.line, expr.col)
            return self.structs[bt][expr.field]
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
        if call.name == "args":
            if call.args:
                raise ForgeError("args() takes no arguments", call.line, call.col)
            return "[str]"
        if call.name == "parse_int":
            if len(call.args) != 1 or self.check_expr(call.args[0]) != "str":
                raise ForgeError("parse_int() takes exactly one str argument",
                                 call.line, call.col)
            return "int"
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
        fn = self.funcs.get(call.name)
        if fn is None:
            raise ForgeError(f"undefined function '{call.name}'", call.line, call.col)
        if len(call.args) != len(fn.params):
            raise ForgeError(f"'{call.name}' takes {len(fn.params)} argument(s), "
                             f"got {len(call.args)}", call.line, call.col)
        for arg, (pn, pt) in zip(call.args, fn.params):
            t = self.check_expr(arg)
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
            if lt == rt and lt in ("int", "float", "bool", "str"):
                return "bool"
            raise ForgeError(f"operator '{op}' needs matching int, float, bool or str "
                             f"operands, got {lt} and {rt}", node.line, node.col)
        if op in ("&&", "||"):
            if lt == "bool" and rt == "bool":
                return "bool"
            raise ForgeError(f"operator '{op}' needs bool operands, got {lt} and {rt}",
                             node.line, node.col)
        raise ForgeError(f"unknown operator '{op}'", node.line, node.col)


def check(program):
    Checker(program).check()
