"""Recursive-descent parser for Forge v2.

Precedence: || -> && -> == != -> < <= > >= -> + - -> * / % -> unary -> postfix -> primary
Postfix: indexing a[i], cast expr as float
"""

from .errors import ForgeError
from .lexer import tokenize
from . import ast_nodes as A


class Parser:
    def __init__(self, tokens):
        self.toks = tokens
        self.pos = 0

    def peek(self, k=0):
        return self.toks[min(self.pos + k, len(self.toks) - 1)]

    def next(self):
        tok = self.toks[self.pos]
        if tok.kind != "EOF":
            self.pos += 1
        return tok

    def at_op(self, v):
        t = self.peek()
        return t.kind == "OP" and t.value == v

    def at_kw(self, v):
        t = self.peek()
        return t.kind == "KEYWORD" and t.value == v

    def looks_like_struct_lit(self):
        # Current token is "{". A struct literal is "{" IDENT ":" ...
        # or "{" "}". This lookahead is essential: without it,
        # `for v in xs {` would be misread as a struct literal for xs.
        if not self.at_op("{"):
            return False
        nxt = self.peek(1)
        if nxt.kind == "OP" and nxt.value == "}":
            return True
        after = self.peek(2)
        return (nxt.kind == "IDENT" and after.kind == "OP" and after.value == ":")

    def expect_op(self, v):
        t = self.peek()
        if not (t.kind == "OP" and t.value == v):
            raise ForgeError(f"expected '{v}', got {self._d(t)}", t.line, t.col)
        return self.next()

    def expect_kw(self, v):
        t = self.peek()
        if not (t.kind == "KEYWORD" and t.value == v):
            raise ForgeError(f"expected '{v}', got {self._d(t)}", t.line, t.col)
        return self.next()

    def expect_ident(self):
        t = self.peek()
        if t.kind != "IDENT":
            raise ForgeError(f"expected a name, got {self._d(t)}", t.line, t.col)
        return self.next()

    @staticmethod
    def _d(tok):
        return "end of file" if tok.kind == "EOF" else repr(tok.value)

    def parse_program(self):
        imports = []
        funcs = []
        structs = []
        enums = []
        while self.peek().kind != "EOF":
            if self.at_kw("import"):
                self.next()
                tok = self.peek()
                if tok.kind != "STR":
                    raise ForgeError("import needs a string path", tok.line, tok.col)
                self.next()
                imports.append(tok.value)
                self.expect_op(";")
            elif self.at_kw("struct"):
                structs.append(self.parse_struct())
            elif self.at_kw("enum"):
                enums.append(self.parse_enum())
            elif self.at_kw("extern"):
                funcs.append(self.parse_extern())
            else:
                funcs.append(self.parse_func())
        return A.Program(imports, funcs, structs, enums)

    def parse_enum(self):
        kw = self.expect_kw("enum")
        name = self.expect_ident()
        type_params = self.parse_type_params()
        self.expect_op("{")
        variants = []
        payloads = {}
        while not self.at_op("}"):
            if self.peek().kind == "EOF":
                raise ForgeError("unterminated enum", self.peek().line, self.peek().col)
            v = self.expect_ident()
            variants.append(v.value)
            if self.at_op("("):
                self.next()
                payload = self.parse_type()
                if self.at_op(","):
                    raise ForgeError("enum variants take at most one payload type in v1",
                                     self.peek().line, self.peek().col)
                self.expect_op(")")
                payloads[v.value] = payload
            else:
                payloads[v.value] = None
            if self.at_op(",") or self.at_op(";"):
                self.next()
                continue
            if self.at_op("}"):
                break
            raise ForgeError("expected ',' or ';' between enum variants",
                             self.peek().line, self.peek().col)
        self.expect_op("}")
        ed = A.EnumDef(name.value, variants, kw.line, kw.col)
        ed.type_params = type_params
        ed.variant_payloads = payloads
        return ed

    def parse_extern(self):
        kw = self.expect_kw("extern")
        self.expect_kw("fn")
        name = self.expect_ident()
        self.expect_op("(")
        params = []
        if not self.at_op(")"):
            while True:
                pname = self.expect_ident()
                self.expect_op(":")
                ptype = self.parse_type()
                params.append((pname.value, ptype))
                if self.at_op(","):
                    self.next()
                    continue
                break
        self.expect_op(")")
        ret = "void"
        if self.at_op("->"):
            self.next()
            ret = self.parse_type()
        self.expect_op(";")
        return A.FuncDef(name.value, params, ret, A.Block([]),
                         kw.line, kw.col, is_extern=True)

    def parse_type_params(self):
        """Parse <T, U> after a fn/struct name; return [] if absent."""
        if not self.at_op("<"):
            return []
        self.next()
        params = []
        while True:
            params.append(self.expect_ident().value)
            if self.at_op(","):
                self.next()
                continue
            break
        self.expect_op(">")
        return params

    def parse_struct(self):
        kw = self.expect_kw("struct")
        name = self.expect_ident()
        type_params = self.parse_type_params()
        self.expect_op("{")
        fields = []
        while not self.at_op("}"):
            if self.peek().kind == "EOF":
                raise ForgeError("unterminated struct", self.peek().line, self.peek().col)
            fname = self.expect_ident()
            self.expect_op(":")
            ftype = self.parse_type()
            fields.append((fname.value, ftype))
            if self.at_op(",") or self.at_op(";"):
                self.next()
                continue
            if self.at_op("}"):
                break
            raise ForgeError("expected ',' or ';' between struct fields",
                             self.peek().line, self.peek().col)
        self.expect_op("}")
        return A.StructDef(name.value, fields, kw.line, kw.col, type_params)

    def parse_type(self):
        if self.at_op("["):
            self.next()
            inner = self.parse_type()
            self.expect_op("]")
            return f"[{inner}]"
        name = self.expect_ident().value
        if self.at_op("<"):
            self.next()
            args = []
            while True:
                args.append(self.parse_type())
                if self.at_op(","):
                    self.next()
                    continue
                break
            self.expect_op(">")
            return f"{name}<{', '.join(args)}>"
        return name

    def parse_func(self):
        kw = self.expect_kw("fn")
        name = self.expect_ident()
        type_params = self.parse_type_params()
        self.expect_op("(")
        params = []
        if not self.at_op(")"):
            while True:
                pname = self.expect_ident()
                self.expect_op(":")
                ptype = self.parse_type()
                params.append((pname.value, ptype))
                if self.at_op(","):
                    self.next()
                    continue
                break
        self.expect_op(")")
        ret = "void"
        if self.at_op("->"):
            self.next()
            ret = self.parse_type()
        body = self.parse_block()
        return A.FuncDef(name.value, params, ret, body, kw.line, kw.col,
                         type_params=type_params)

    def parse_block(self):
        self.expect_op("{")
        stmts = []
        while not self.at_op("}"):
            if self.peek().kind == "EOF":
                raise ForgeError("unterminated block", self.peek().line, self.peek().col)
            stmts.append(self.parse_stmt())
        self.expect_op("}")
        return A.Block(stmts)

    def parse_stmt(self):
        if self.at_kw("let"):
            kw = self.next()
            mutable = False
            if self.at_kw("mut"):
                self.next()
                mutable = True
            name = self.expect_ident()
            ann = None
            if self.at_op(":"):
                self.next()
                ann = self.parse_type()
            self.expect_op("=")
            expr = self.parse_expr()
            self.expect_op(";")
            return A.Let(name.value, mutable, ann, expr, kw.line, kw.col)
        if self.at_kw("if"):
            kw = self.next()
            cond = self.parse_expr()
            then = self.parse_block()
            els = None
            if self.at_kw("else"):
                self.next()
                if self.at_kw("if"):
                    els = A.Block([self.parse_stmt()])
                else:
                    els = self.parse_block()
            return A.If(cond, then, els, kw.line, kw.col)
        if self.at_kw("while"):
            kw = self.next()
            cond = self.parse_expr()
            body = self.parse_block()
            return A.While(cond, body, kw.line, kw.col)
        if self.at_kw("for"):
            kw = self.next()
            name = self.expect_ident()
            self.expect_kw("in")
            expr = self.parse_expr()
            body = self.parse_block()
            return A.For(name.value, expr, body, kw.line, kw.col)
        if self.at_kw("return"):
            tok = self.next()
            expr = None
            if not self.at_op(";"):
                expr = self.parse_expr()
            self.expect_op(";")
            return A.Return(expr, tok.line, tok.col)
        if self.at_kw("match"):
            kw = self.next()
            expr = self.parse_expr()
            self.expect_op("{")
            arms = []
            while not self.at_op("}"):
                if self.peek().kind == "EOF":
                    raise ForgeError("unterminated match", self.peek().line, self.peek().col)
                pat = self.expect_ident()
                binding = None
                if self.at_op("("):
                    self.next()
                    binding = self.expect_ident().value
                    self.expect_op(")")
                self.expect_op("=>")
                body = self.parse_block()
                arms.append((pat.value, binding, body))
                if self.at_op(","):
                    self.next()
            self.expect_op("}")
            return A.Match(expr, arms, kw.line, kw.col)
        if self.at_kw("spawn"):
            kw = self.next()
            expr = self.parse_expr()
            self.expect_op(";")
            if not isinstance(expr, A.Call):
                raise ForgeError("spawn needs a function call", kw.line, kw.col)
            return A.Spawn(expr, kw.line, kw.col)
        if self.at_op("{"):
            return self.parse_block()
        # General case: parse an expression, then either '=' (assignment)
        # or ';' (expression statement).
        tok = self.peek()
        expr = self.parse_expr()
        if self.at_op("="):
            self.next()
            rhs = self.parse_expr()
            self.expect_op(";")
            if isinstance(expr, A.Var):
                return A.Assign(expr.name, rhs, expr.line, expr.col)
            if isinstance(expr, A.Index):
                return A.IndexAssign(expr, rhs, expr.line, expr.col)
            if isinstance(expr, A.FieldAccess):
                return A.FieldAssign(expr, rhs, expr.line, expr.col)
            raise ForgeError("assignment target must be a variable, an index, or a field",
                             expr.line, expr.col)
        self.expect_op(";")
        return A.ExprStmt(expr, tok.line, tok.col)

    def parse_expr(self):
        return self.parse_or()

    def _level(self, sub, ops):
        left = sub()
        while self.peek().kind == "OP" and self.peek().value in ops:
            op = self.next()
            right = sub()
            left = A.BinOp(op.value, left, right, op.line, op.col)
        return left

    def parse_or(self):
        return self._level(self.parse_and, {"||"})

    def parse_and(self):
        return self._level(self.parse_equality, {"&&"})

    def parse_equality(self):
        return self._level(self.parse_comparison, {"==", "!="})

    def parse_comparison(self):
        return self._level(self.parse_additive, {"<", "<=", ">", ">="})

    def parse_additive(self):
        return self._level(self.parse_multiplicative, {"+", "-"})

    def parse_multiplicative(self):
        return self._level(self.parse_unary, {"*", "/", "%"})

    def parse_unary(self):
        tok = self.peek()
        if tok.kind == "OP" and tok.value in ("-", "!"):
            self.next()
            return A.UnaryOp(tok.value, self.parse_unary(), tok.line, tok.col)
        return self.parse_postfix()

    def parse_postfix(self):
        expr = self.parse_primary()
        while True:
            if self.at_op("?"):
                tok = self.next()
                expr = A.Try(expr, tok.line, tok.col)
                continue
            if self.at_op("["):
                tok = self.next()
                idx = self.parse_expr()
                self.expect_op("]")
                expr = A.Index(expr, idx, tok.line, tok.col)
                continue
            if self.at_op("."):
                tok = self.next()
                field = self.expect_ident()
                expr = A.FieldAccess(expr, field.value, tok.line, tok.col)
                continue
            if self.at_kw("as"):
                tok = self.next()
                target = self.parse_type()
                expr = A.Cast(expr, target, tok.line, tok.col)
                continue
            break
        return expr

    def parse_primary(self):
        tok = self.peek()
        if tok.kind == "INT":
            self.next()
            return A.IntLit(tok.value, tok.line, tok.col)
        if tok.kind == "FLOAT":
            self.next()
            return A.FloatLit(tok.value, tok.line, tok.col)
        if tok.kind == "STR":
            self.next()
            return A.StrLit(tok.value, tok.line, tok.col)
        if tok.kind == "KEYWORD" and tok.value in ("true", "false"):
            self.next()
            return A.BoolLit(tok.value == "true", tok.line, tok.col)
        if tok.kind == "IDENT":
            self.next()
            if self.at_op("("):
                self.next()
                args = []
                if not self.at_op(")"):
                    while True:
                        args.append(self.parse_expr())
                        if self.at_op(","):
                            self.next()
                            continue
                        break
                self.expect_op(")")
                return A.Call(tok.value, args, tok.line, tok.col)
            if self.looks_like_struct_lit():
                # Struct literal: Name { field: value, ... }
                self.next()
                fields = []
                if not self.at_op("}"):
                    while True:
                        fname = self.expect_ident()
                        self.expect_op(":")
                        fexpr = self.parse_expr()
                        fields.append((fname.value, fexpr))
                        if self.at_op(","):
                            self.next()
                            continue
                        break
                self.expect_op("}")
                return A.StructLit(tok.value, fields, tok.line, tok.col)
            return A.Var(tok.value, tok.line, tok.col)
        if self.at_op("("):
            self.next()
            expr = self.parse_expr()
            self.expect_op(")")
            return expr
        if self.at_op("["):
            self.next()
            elems = []
            if not self.at_op("]"):
                while True:
                    elems.append(self.parse_expr())
                    if self.at_op(","):
                        self.next()
                        continue
                    break
            self.expect_op("]")
            return A.ArrayLit(elems, tok.line, tok.col)
        raise ForgeError(f"expected an expression, got {self._d(tok)}", tok.line, tok.col)


def parse(source):
    return Parser(tokenize(source)).parse_program()
