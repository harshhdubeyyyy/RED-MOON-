"""Forge v2 -> C code generator.

Safe mode (default): checked int arithmetic, bounds-checked indexing.
Fast mode (--mode fast): unchecked arithmetic/indexing, -O3 -march=native
in the driver, for C++-style microsecond-latency work. Fast mode is an
explicit opt-in: it can wrap, crash on division by zero, and read out
of bounds, exactly like unchecked C/C++.
Arrays are contiguous C arrays (good for cache and auto-vectorisation),
shared by reference on assignment, like Python lists.
"""

from .errors import ForgeError
from . import ast_nodes as A

C_SCALAR = {"int": "long long", "float": "double", "bool": "bool", "str": "char *", "void": "void"}
ARRAY_STRUCT = {"int": "ForgeIntArray", "float": "ForgeFloatArray",
                "bool": "ForgeBoolArray", "str": "ForgeStrArray"}
ARRAY_ELEM_C = {"int": "long long", "float": "double", "bool": "bool", "str": "char *"}
PUSH_FN = {"int": "forge_int_push", "float": "forge_float_push",
           "bool": "forge_bool_push", "str": "forge_str_push"}
GET_FN = {"int": "forge_int_get", "float": "forge_float_get",
          "bool": "forge_bool_get", "str": "forge_str_get"}
SET_FN = {"int": "forge_int_set", "float": "forge_float_set",
          "bool": "forge_bool_set", "str": "forge_str_set"}

HEADER = r"""#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdbool.h>
#include <math.h>
#include <time.h>

typedef struct { long long *data; long long len; long long cap; } ForgeIntArray;
typedef struct { double *data; long long len; long long cap; } ForgeFloatArray;
typedef struct { bool *data; long long len; long long cap; } ForgeBoolArray;
typedef struct { char **data; long long len; long long cap; } ForgeStrArray;

static void forge_fail(const char *msg) {
    fprintf(stderr, "forge: runtime error: %s\n", msg);
    exit(1);
}

static char *forge_copy_str(const char *s) {
    size_t n = strlen(s) + 1;
    char *p = (char *)malloc(n);
    if (!p) forge_fail("out of memory");
    memcpy(p, s, n);
    return p;
}

static char *forge_concat(const char *a, const char *b) {
    size_t na = strlen(a), nb = strlen(b);
    char *p = (char *)malloc(na + nb + 1);
    if (!p) forge_fail("out of memory");
    memcpy(p, a, na);
    memcpy(p + na, b, nb + 1);
    return p;
}

static long long forge_add(long long a, long long b) {
    long long r;
    if (__builtin_add_overflow(a, b, &r)) forge_fail("integer overflow");
    return r;
}
static long long forge_sub(long long a, long long b) {
    long long r;
    if (__builtin_sub_overflow(a, b, &r)) forge_fail("integer overflow");
    return r;
}
static long long forge_mul(long long a, long long b) {
    long long r;
    if (__builtin_mul_overflow(a, b, &r)) forge_fail("integer overflow");
    return r;
}
static long long forge_neg(long long a) {
    if (a == (-9223372036854775807LL - 1)) forge_fail("integer overflow");
    return -a;
}
static long long forge_div(long long a, long long b) {
    if (b == 0) forge_fail("division by zero");
    if (a == (-9223372036854775807LL - 1) && b == -1) forge_fail("integer overflow");
    return a / b;
}
static long long forge_mod(long long a, long long b) {
    if (b == 0) forge_fail("division by zero");
    if (a == (-9223372036854775807LL - 1) && b == -1) return 0;
    return a % b;
}

#define FORGE_ARRAY_HELPERS(CT, ST, FN) \
static void FN##_push(ST *a, CT v) { \
    if (a->len >= a->cap) { \
        long long nc = a->cap ? a->cap * 2 : 4; \
        CT *nd = (CT *)realloc(a->data, sizeof(CT) * (size_t)nc); \
        if (!nd) forge_fail("out of memory"); \
        a->data = nd; a->cap = nc; \
    } \
    a->data[a->len++] = v; \
} \
static CT FN##_get(ST a, long long i) { \
    if (i < 0 || i >= a.len) forge_fail("array index out of bounds"); \
    return a.data[i]; \
} \
static void FN##_set(ST *a, long long i, CT v) { \
    if (i < 0 || i >= a->len) forge_fail("array index out of bounds"); \
    a->data[i] = v; \
}

FORGE_ARRAY_HELPERS(long long, ForgeIntArray, forge_int)
FORGE_ARRAY_HELPERS(double, ForgeFloatArray, forge_float)
FORGE_ARRAY_HELPERS(bool, ForgeBoolArray, forge_bool)
FORGE_ARRAY_HELPERS(char *, ForgeStrArray, forge_str)

static ForgeIntArray forge_range(long long n) {
    ForgeIntArray a;
    a.len = n > 0 ? n : 0;
    a.cap = a.len;
    a.data = a.len ? (long long *)malloc(sizeof(long long) * (size_t)a.len) : NULL;
    if (a.len && !a.data) forge_fail("out of memory");
    for (long long i = 0; i < a.len; i++) a.data[i] = i;
    return a;
}

static long long forge_clock_micros(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (long long)ts.tv_sec * 1000000LL + ts.tv_nsec / 1000;
}

"""


def c_type(t):
    if t in C_SCALAR:
        return C_SCALAR[t]
    if t.startswith("[") and t.endswith("]"):
        inner = t[1:-1]
        if inner in ARRAY_STRUCT:
            return ARRAY_STRUCT[inner]
    raise ForgeError(f"unsupported type for codegen: {t}")


def elem_of(arr_type):
    return arr_type[1:-1] if arr_type.startswith("[") else "int"


class Codegen:
    def __init__(self, program, mode="safe"):
        self.program = program
        self.mode = mode
        self.func_ret = {fn.name: fn.ret for fn in program.funcs}
        self.lines = []
        self.indent = 0
        self.arr_counter = 0
        self.loop_counter = 0
        self.current_fn = None
        self._types = {}

    def generate(self):
        self.lines.append(HEADER)
        for fn in self.program.funcs:
            if fn.name != "main":
                self.emit(f"{self.c_sig(fn)};")
        self.lines.append("")
        for fn in self.program.funcs:
            self.gen_func(fn)
        return "\n".join(self.lines)

    def emit(self, text=""):
        self.lines.append(("    " * self.indent) + text if text else "")

    def c_sig(self, fn):
        params = ", ".join(f"{c_type(pt)} {pn}" for pn, pt in fn.params)
        return f"{c_type(fn.ret)} {fn.name}({params if params else 'void'})"

    @staticmethod
    def c_str_literal(value):
        out = []
        for ch in value:
            mapping = {"\n": "\\n", "\t": "\\t", "\r": "\\r", "\\": "\\\\", '"': '\\"', "\0": "\\0"}
            out.append(mapping.get(ch, ch))
        return '"' + "".join(out) + '"'

    def expr_type(self, expr):
        return self._types.get(id(expr), "int")

    def attach_types(self, types):
        self._types = types

    def gen_func(self, fn):
        self.current_fn = fn.name
        sig = "int main(void)" if fn.name == "main" else self.c_sig(fn)
        self.emit(sig + " {")
        self.indent += 1
        self.gen_block(fn.body, fn.ret)
        if fn.name == "main":
            self.emit("return 0;")
        self.indent -= 1
        self.emit("}")
        self.lines.append("")
        self.current_fn = None

    def gen_block(self, block, ret_type):
        for stmt in block.stmts:
            self.gen_stmt(stmt, ret_type)

    def gen_stmt(self, stmt, ret_type):
        if isinstance(stmt, A.Block):
            self.emit("{")
            self.indent += 1
            self.gen_block(stmt, ret_type)
            self.indent -= 1
            self.emit("}")
            return
        if isinstance(stmt, A.Let):
            t = stmt.ann if (stmt.ann and isinstance(stmt.expr, A.ArrayLit)
                             and not stmt.expr.elems) else self.expr_type(stmt.expr)
            expr = self.gen_expr(stmt.expr)
            if t == "str":
                expr = f"forge_copy_str({expr})"
            self.emit(f"{c_type(t)} {stmt.name} = {expr};")
            return
        if isinstance(stmt, A.Assign):
            expr = self.gen_expr(stmt.expr)
            if self.expr_type(stmt.expr) == "str":
                expr = f"forge_copy_str({expr})"
            self.emit(f"{stmt.name} = {expr};")
            return
        if isinstance(stmt, A.IndexAssign):
            base = stmt.base.base
            if not isinstance(base, A.Var):
                raise ForgeError("index assignment target must be a variable")
            et = self.expr_type(stmt.base)
            idx = self.gen_expr(stmt.base.index)
            val = self.gen_expr(stmt.expr)
            if et == "str":
                val = f"forge_copy_str({val})"
            if self.mode == "safe":
                self.emit(f"{SET_FN[et]}(&{base.name}, {idx}, {val});")
            else:
                self.emit(f"{base.name}.data[{idx}] = {val};")
            return
        if isinstance(stmt, A.If):
            self.emit(f"if ({self.gen_expr(stmt.cond)}) {{")
            self.indent += 1
            self.gen_block(stmt.then, ret_type)
            self.indent -= 1
            if stmt.els is not None:
                self.emit("} else {")
                self.indent += 1
                self.gen_block(stmt.els, ret_type)
                self.indent -= 1
            self.emit("}")
            return
        if isinstance(stmt, A.While):
            self.emit(f"while ({self.gen_expr(stmt.cond)}) {{")
            self.indent += 1
            self.gen_block(stmt.body, ret_type)
            self.indent -= 1
            self.emit("}")
            return
        if isinstance(stmt, A.For):
            arr_type = self.expr_type(stmt.expr)
            et = elem_of(arr_type)
            arr_tmp = f"__forge_arr{self.arr_counter}"
            self.arr_counter += 1
            idx = f"__forge_i{self.loop_counter}"
            self.loop_counter += 1
            self.emit("{")
            self.indent += 1
            self.emit(f"{c_type(arr_type)} {arr_tmp} = {self.gen_expr(stmt.expr)};")
            self.emit(f"for (long long {idx} = 0; {idx} < {arr_tmp}.len; {idx}++) {{")
            self.indent += 1
            self.emit(f"{C_SCALAR[et]} {stmt.name} = {arr_tmp}.data[{idx}];")
            self.gen_block(stmt.body, ret_type)
            self.indent -= 1
            self.emit("}")
            self.indent -= 1
            self.emit("}")
            return
        if isinstance(stmt, A.Return):
            if stmt.expr is None:
                self.emit("return 0;" if self.current_fn == "main" else "return;")
            elif ret_type == "str":
                self.emit(f"return forge_copy_str({self.gen_expr(stmt.expr)});")
            else:
                self.emit(f"return {self.gen_expr(stmt.expr)};")
            return
        if isinstance(stmt, A.ExprStmt):
            call = stmt.expr
            if isinstance(call, A.Call) and call.name in ("print", "println"):
                self.gen_print(call)
                return
            if isinstance(call, A.Call) and call.name == "push":
                var = call.args[0]
                et = self.expr_type(call.args[1])
                val = self.gen_expr(call.args[1])
                if et == "str":
                    val = f"forge_copy_str({val})"
                self.emit(f"{PUSH_FN[et]}(&{var.name}, {val});")
                return
            if isinstance(call, A.Call) and call.name == "fail":
                self.emit(f'fprintf(stderr, "forge: %s\\n", {self.gen_expr(call.args[0])});')
                self.emit("exit(1);")
                return
            self.emit(f"{self.gen_expr(stmt.expr)};")
            return
        raise ForgeError(f"unsupported statement {type(stmt).__name__}")

    def gen_print(self, call):
        newline = call.name == "println"
        for idx, arg in enumerate(call.args):
            t = self.expr_type(arg)
            code = self.gen_expr(arg)
            if t == "int":
                self.emit(f'printf("%lld", {code});')
            elif t == "float":
                self.emit(f'printf("%.6g", {code});')
            elif t == "bool":
                self.emit(f'printf("%s", {code} ? "true" : "false");')
            elif t == "str":
                self.emit(f'printf("%s", {code});')
            else:
                raise ForgeError(f"cannot print a value of type {t}", call.line, call.col)
            if idx < len(call.args) - 1:
                self.emit('printf(" ");')
        if newline:
            self.emit('printf("\\n");')

    def gen_expr(self, expr):
        if isinstance(expr, A.IntLit):
            return f"{expr.value}LL"
        if isinstance(expr, A.FloatLit):
            return repr(float(expr.value))
        if isinstance(expr, A.StrLit):
            return self.c_str_literal(expr.value)
        if isinstance(expr, A.BoolLit):
            return "true" if expr.value else "false"
        if isinstance(expr, A.Var):
            return expr.name
        if isinstance(expr, A.ArrayLit):
            arr_type = self.expr_type(expr)
            if arr_type in ("[?]", "int"):
                raise ForgeError("array literal needs a known element type "
                                 "(annotate the variable or use non-empty literal)",
                                 expr.line, expr.col)
            et = elem_of(arr_type)
            struct = ARRAY_STRUCT[et]
            elem_c = ARRAY_ELEM_C[et]
            tmp = f"__forge_arr{self.arr_counter}"
            self.arr_counter += 1
            n = len(expr.elems)
            parts = [f"{struct} {tmp}"]
            body = f"{tmp}.len = {n}; {tmp}.cap = {n}; "
            body += f"{tmp}.data = " + (f"( {elem_c} *)malloc(sizeof({elem_c}) * {n})" if n else "NULL") + "; "
            for i, e in enumerate(expr.elems):
                code = self.gen_expr(e)
                if et == "str":
                    code = f"forge_copy_str({code})"
                body += f"{tmp}.data[{i}] = {code}; "
            body += f"{tmp}"
            return "({" + " ".join(parts) + "; " + body + "; })"
        if isinstance(expr, A.Index):
            et = self.expr_type(expr)
            base = self.gen_expr(expr.base)
            idx = self.gen_expr(expr.index)
            if self.mode == "safe":
                return f"{GET_FN[et]}({base}, {idx})"
            return f"({base}).data[{idx}]"
        if isinstance(expr, A.Cast):
            code = self.gen_expr(expr.expr)
            return f"(double)({code})" if expr.target == "float" else f"(long long)({code})"
        if isinstance(expr, A.UnaryOp):
            if expr.op == "-" and self.expr_type(expr.expr) == "int" and self.mode == "safe":
                return f"forge_neg({self.gen_expr(expr.expr)})"
            return f"({expr.op}{self.gen_expr(expr.expr)})"
        if isinstance(expr, A.BinOp):
            left = self.gen_expr(expr.left)
            right = self.gen_expr(expr.right)
            if expr.op == "+" and self.expr_type(expr.left) == "str":
                return f"forge_concat({left}, {right})"
            if expr.op == "==" and self.expr_type(expr.left) == "str":
                return f"(strcmp({left}, {right}) == 0)"
            if expr.op == "!=" and self.expr_type(expr.left) == "str":
                return f"(strcmp({left}, {right}) != 0)"
            if self.expr_type(expr.left) == "int" and self.expr_type(expr.right) == "int":
                if self.mode == "safe":
                    checked = {"+": "forge_add", "-": "forge_sub", "*": "forge_mul",
                               "/": "forge_div", "%": "forge_mod"}
                    if expr.op in checked:
                        return f"{checked[expr.op]}({left}, {right})"
            return f"({left} {expr.op} {right})"
        if isinstance(expr, A.Call):
            if expr.name == "len":
                arg = expr.args[0]
                code = self.gen_expr(arg)
                if self.expr_type(arg) == "str":
                    return f"strlen({code})"
                return f"({code}).len"
            if expr.name == "range":
                return f"forge_range({self.gen_expr(expr.args[0])})"
            if expr.name == "clock_micros":
                return "forge_clock_micros()"
            if expr.name in ("sqrt", "exp", "log"):
                return f"{expr.name}({self.gen_expr(expr.args[0])})"
            if expr.name == "pow":
                return f"pow({self.gen_expr(expr.args[0])}, {self.gen_expr(expr.args[1])})"
            if expr.name == "abs":
                return f"llabs({self.gen_expr(expr.args[0])})"
            args = ", ".join(self.gen_expr(a) for a in expr.args)
            return f"{expr.name}({args})"
        raise ForgeError(f"unsupported expression {type(expr).__name__}")


def generate(program, types, mode="safe"):
    gen = Codegen(program, mode=mode)
    gen.attach_types(types)
    return gen.generate()
