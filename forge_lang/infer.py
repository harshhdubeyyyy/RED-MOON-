"""Type inference for codegen (program already checked)."""

from . import ast_nodes as A


class Infer:
    def __init__(self, program):
        self.funcs = {fn.name: fn for fn in program.funcs}
        structs = getattr(program, "structs", None) or []
        self.structs = {sd.name: dict(sd.fields) for sd in structs}
        enums = getattr(program, "enums", None) or []
        self.enum_variants = {}
        for ed in enums:
            for v in ed.variants:
                self.enum_variants[v] = ed.name
        self.types = {}
        self.scopes = []
        self.current_ret = "void"

    def run(self, program):
        for fn in program.funcs:
            if getattr(fn, "is_extern", False):
                continue
            self.current_ret = fn.ret
            self.scopes = [{n: t for n, t in fn.params}]
            self.walk_block(fn.body)
            self.scopes = []
        return self.types

    def lookup(self, name):
        for scope in reversed(self.scopes):
            if name in scope:
                return scope[name]
        if name in self.enum_variants:
            return self.enum_variants[name]
        return "int"

    def set(self, expr, t):
        self.types[id(expr)] = t
        return t

    def walk_block(self, block):
        self.scopes.append({})
        for stmt in block.stmts:
            self.walk_stmt(stmt)
        self.scopes.pop()

    def walk_stmt(self, stmt):
        if isinstance(stmt, A.Block):
            self.walk_block(stmt)
        elif isinstance(stmt, A.Let):
            if isinstance(stmt.expr, A.ArrayLit) and stmt.ann:
                t = stmt.ann
                self.set(stmt.expr, t)
                for e in stmt.expr.elems:
                    self.walk_expr(e)
            else:
                t = self.walk_expr(stmt.expr)
                if stmt.ann:
                    t = stmt.ann
            self.scopes[-1][stmt.name] = t
        elif isinstance(stmt, A.Assign):
            self.walk_expr(stmt.expr)
        elif isinstance(stmt, A.Match):
            self.walk_expr(stmt.expr)
            for _pat, body in stmt.arms:
                self.walk_block(body)
        elif isinstance(stmt, A.Spawn):
            self.walk_expr(stmt.call)
        elif isinstance(stmt, A.FieldAssign):
            self.walk_expr(stmt.target)
            self.walk_expr(stmt.expr)
        elif isinstance(stmt, A.IndexAssign):
            self.walk_expr(stmt.base)
            self.walk_expr(stmt.expr)
        elif isinstance(stmt, A.If):
            self.walk_expr(stmt.cond)
            self.walk_block(stmt.then)
            if stmt.els is not None:
                self.walk_block(stmt.els)
        elif isinstance(stmt, A.While):
            self.walk_expr(stmt.cond)
            self.walk_block(stmt.body)
        elif isinstance(stmt, A.For):
            at = self.walk_expr(stmt.expr)
            et = at[1:-1] if at.startswith("[") else "int"
            self.scopes.append({stmt.name: et})
            for s in stmt.body.stmts:
                self.walk_stmt(s)
            self.scopes.pop()
        elif isinstance(stmt, A.Return):
            if stmt.expr is not None:
                if isinstance(stmt.expr, A.ArrayLit) and self.current_ret.startswith("["):
                    self.set(stmt.expr, self.current_ret)
                    for e in stmt.expr.elems:
                        self.walk_expr(e)
                else:
                    self.walk_expr(stmt.expr)
        elif isinstance(stmt, A.ExprStmt):
            self.walk_expr(stmt.expr)

    def walk_expr(self, expr):
        if isinstance(expr, A.IntLit):
            return self.set(expr, "int")
        if isinstance(expr, A.FloatLit):
            return self.set(expr, "float")
        if isinstance(expr, A.StrLit):
            return self.set(expr, "str")
        if isinstance(expr, A.BoolLit):
            return self.set(expr, "bool")
        if isinstance(expr, A.Var):
            return self.set(expr, self.lookup(expr.name))
        if isinstance(expr, A.ArrayLit):
            if expr.elems:
                t0 = self.walk_expr(expr.elems[0])
                for e in expr.elems[1:]:
                    self.walk_expr(e)
                return self.set(expr, f"[{t0}]")
            return self.set(expr, "[?]")
        if isinstance(expr, A.StructLit):
            fields = self.structs.get(expr.name, {})
            for fname, fexpr in expr.fields:
                if isinstance(fexpr, A.ArrayLit) and not fexpr.elems and fields.get(fname):
                    self.set(fexpr, fields[fname])
                else:
                    self.walk_expr(fexpr)
            return self.set(expr, expr.name)
        if isinstance(expr, A.FieldAccess):
            bt = self.walk_expr(expr.base)
            ft = self.structs.get(bt, {}).get(expr.field, "int")
            return self.set(expr, ft)
        if isinstance(expr, A.Index):
            bt = self.walk_expr(expr.base)
            self.walk_expr(expr.index)
            et = bt[1:-1] if bt.startswith("[") else "int"
            return self.set(expr, et)
        if isinstance(expr, A.Cast):
            self.walk_expr(expr.expr)
            return self.set(expr, expr.target)
        if isinstance(expr, A.UnaryOp):
            t = self.walk_expr(expr.expr)
            return self.set(expr, "bool" if expr.op == "!" else t)
        if isinstance(expr, A.BinOp):
            lt = self.walk_expr(expr.left)
            rt = self.walk_expr(expr.right)
            if expr.op in ("<", "<=", ">", ">=", "==", "!=", "&&", "||"):
                return self.set(expr, "bool")
            if expr.op == "+" and lt == "str":
                return self.set(expr, "str")
            return self.set(expr, lt)
        if isinstance(expr, A.Call):
            # Array literals in arguments take the parameter type.
            if expr.name not in ("print", "println", "push", "fail"):
                fn = self.funcs.get(expr.name)
                if fn:
                    for arg, (_pn, pt) in zip(expr.args, fn.params):
                        if isinstance(arg, A.ArrayLit) and pt.startswith("["):
                            self.set(arg, pt)
                            for e in arg.elems:
                                self.walk_expr(e)
                        else:
                            self.walk_expr(arg)
                    return self.set(expr, fn.ret)
            for a in expr.args:
                self.walk_expr(a)
            if expr.name in ("len", "clock_micros", "abs", "parse_int"):
                return self.set(expr, "int")
            if expr.name == "range":
                return self.set(expr, "[int]")
            if expr.name in ("args", "split"):
                return self.set(expr, "[str]")
            if expr.name in ("sqrt", "exp", "log", "pow"):
                return self.set(expr, "float")
            if expr.name in ("read_file", "join", "substr", "trim"):
                return self.set(expr, "str")
            if expr.name == "write_file":
                return self.set(expr, "bool")
            if expr.name in ("starts_with", "ends_with"):
                return self.set(expr, "bool")
            if expr.name == "http_get":
                return self.set(expr, "str")
            return self.set(expr, "void")
        return self.set(expr, "int")


def infer_types(program):
    return Infer(program).run(program)
