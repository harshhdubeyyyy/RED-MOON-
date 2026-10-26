"""The Jal Pari Language -> big32 (RV32IMAC) assembly code generator.

Reuses Forge's parser, checker and type inference; only the backend is
new. Target: big32 v7, single-cycle, 16KB IMEM, 64KB DMEM, UART TX
only (store byte to 0x10000000), ECALL halts (mtvec == 0).

Supported subset (v1, everything else raises a clear ForgeError):
  int (32-bit on big32, NOT Forge's 64-bit x86 int), bool,
  str literals / str variables (pointer to null-terminated static data),
  [int]/[bool]/[str] arrays, let/assign, if/else, while, for over an
  array or over range(n), functions/calls (<= 8 args, recursion works),
  return, print/println (int, bool, str), len (array or str),
  assert/fail (print message, halt with a0 = 1).
NOT supported: float, structs, enums, match, spawn, extern/FFI, file
I/O, args(), http, clock, string concatenation/comparison, push,
dynamic allocation. Arithmetic is native RISC-V (wrapping, div by
zero -> -1, rem by zero -> dividend) -- NOT Forge safe-mode aborts.

Calling convention (documented, see README "Forge on big32"):
  args a0-a7, return a0, frame pointer s0, locals in a fixed 2048-byte
  frame addressed via s0 (so sp may move for call spills). Callee
  saves ra + s0 only; caller spills every live temp register across
  a call (so t/a/s temps are effectively caller-saved). Stack starts
  at 65532 and grows down; static data lives at 0x1000 and up.
  Arrays: static slot per source site, first word = length, then
  elements (so an array literal inside a loop re-initialises the same
  slot each iteration -- a documented v1 limitation). Strings:
  null-terminated static data, initialised by _start before main.
"""

from .errors import ForgeError
from . import ast_nodes as A

UART = 0x10000000
STATIC_BASE = 0x1000
FRAME_BYTES = 2048
SP_START = 65532
# Temp pool: t0-t6, a1-a7 (a0 is return/arg0, never a temp), s2-s11.
# Caller spills live temps across calls, so all of these are safe.
TEMPS = ["t0", "t1", "t2", "t3", "t4", "t5", "t6",
         "a1", "a2", "a3", "a4", "a5", "a6", "a7",
         "s2", "s3", "s4", "s5", "s6", "s7", "s8", "s9", "s10", "s11"]


class RVGen:
    def __init__(self, program, types):
        self.program = program
        self.types = types
        self.lines = []
        self.init_lines = []          # _start static-string initialisation
        self.label_n = 0
        self.free = list(TEMPS)
        self.live = []                # temps currently holding values
        self.funcs = {fn.name: fn for fn in program.funcs}
        self.env = []                 # stack of {name: (slot, type)}
        self.slot_n = 0               # locals allocated in current fn
        self.epilogue = None
        self.cur_fn = None
        self.str_slots = {}           # string value -> DMEM address
        self.arr_slots = []           # (slot id, address) in allocation order
        self.next_static = STATIC_BASE
        self.true_addr = None
        self.false_addr = None

    # ---------- utilities ----------
    def label(self, prefix):
        self.label_n += 1
        return f"{prefix}_{self.label_n}"

    def emit(self, text=""):
        self.lines.append(text)

    def alloc(self):
        if not self.free:
            raise ForgeError("expression too deep for big32 backend "
                             "(temp registers exhausted)")
        r = self.free.pop(0)
        self.live.append(r)
        return r

    def free_reg(self, r):
        if r in self.live:
            self.live.remove(r)
        if r not in self.free:
            self.free.append(r)

    def alloc_slot(self):
        self.slot_n += 1
        if self.slot_n * 4 > FRAME_BYTES:
            raise ForgeError("too many locals for big32 backend frame")
        return self.slot_n

    def slot_off(self, slot):
        return -4 * slot

    def lookup(self, name):
        for scope in reversed(self.env):
            if name in scope:
                return scope[name]
        raise ForgeError(f"unknown variable {name}")

    def expr_type(self, expr):
        return self.types.get(id(expr), "int")

    def static_addr(self, size):
        addr = self.next_static
        # Align to 4, reserve size bytes.
        self.next_static = (addr + size + 3) & ~3
        if self.next_static > 0x8000:
            raise ForgeError("static data exhausted on big32")
        return addr

    def str_addr(self, value):
        if value in self.str_slots:
            return self.str_slots[value]
        addr = self.static_addr(len(value.encode("utf-8")) + 1)
        self.str_slots[value] = addr
        # Initialisation emitted into _start (uses t0/t1, no live temps).
        self.init_lines.append(f"    li t0, {addr}")
        for b in value.encode("utf-8"):
            self.init_lines.append(f"    li t1, {b}")
            self.init_lines.append("    sb t1, 0(t0)")
            self.init_lines.append("    addi t0, t0, 1")
        self.init_lines.append("    sb zero, 0(t0)")
        return addr

    # ---------- top level ----------
    def generate(self):
        if self.program.structs:
            raise ForgeError("structs are not supported on big32 (v1)")
        if self.program.enums:
            raise ForgeError("enums are not supported on big32 (v1)")
        if "main" not in self.funcs:
            raise ForgeError("big32 target needs a main function")
        for fn in self.program.funcs:
            if getattr(fn, "is_extern", False):
                raise ForgeError("extern functions are not supported on big32")
            for _n, t in fn.params:
                if t == "float" or t.startswith("[float"):
                    raise ForgeError("float is not supported on big32 (v1)")
            if fn.ret == "float":
                raise ForgeError("float is not supported on big32 (v1)")
        # Emit functions first so string/array slots are discovered;
        # _start (with string init) is prepended at the end.
        body = []
        for fn in self.program.funcs:
            self.gen_func(fn)
        body = self.lines
        self.lines = []
        # _start: stack, static strings, call main, halt.
        self.emit("_start:")
        self.emit(f"    li sp, {SP_START}")
        self.lines.extend(self.init_lines)
        self.emit("    jal ra, main")
        self.emit("    ecall")
        self.lines.extend(body)
        self.lines.extend(self.helpers())
        return "\n".join(self.lines) + "\n"

    def helpers(self):
        # Note: true/false strings are allocated during gen_func (bool
        # printing), i.e. before _start is emitted, so their init code
        # is already in _start. Helpers must not allocate new strings
        # here (their init would never be emitted).
        h = []
        h.append("forge_print_str:")
        h.append("    addi sp, sp, -4")
        h.append("    sw ra, 0(sp)")
        h.append("forge_print_str_loop:")
        h.append("    lb t0, 0(a0)")
        h.append("    beq t0, zero, forge_print_str_done")
        h.append(f"    li t1, {UART}")
        h.append("    sb t0, 0(t1)")
        h.append("    addi a0, a0, 1")
        h.append("    j forge_print_str_loop")
        h.append("forge_print_str_done:")
        h.append("    lw ra, 0(sp)")
        h.append("    addi sp, sp, 4")
        h.append("    ret")
        h.append("forge_print_int:")
        h.append("    addi sp, sp, -4")
        h.append("    sw ra, 0(sp)")
        # INT_MIN: signed negation wraps, so print '-' then extract
        # digits unsigned (divu/remu) from the bit pattern 0x80000000.
        h.append("    li t0, -2147483648")
        h.append("    bne a0, t0, forge_print_int_sign")
        h.append(f"    li t0, {UART}")
        h.append("    li t1, 45")
        h.append("    sb t1, 0(t0)")
        h.append("    li a0, -2147483648")
        h.append("    j forge_print_int_push_u")
        h.append("forge_print_int_sign:")
        h.append("    blt a0, zero, forge_print_int_neg")
        h.append("    j forge_print_int_digits")
        h.append("forge_print_int_neg:")
        h.append(f"    li t0, {UART}")
        h.append("    li t1, 45")
        h.append("    sb t1, 0(t0)")
        h.append("    sub a0, zero, a0")
        h.append("forge_print_int_digits:")
        h.append("    beq a0, zero, forge_print_int_zero")
        h.append("    mv t3, sp")
        h.append("    li t2, 10")
        h.append("forge_print_int_push:")
        h.append("    beq a0, zero, forge_print_int_pop")
        h.append("    rem t0, a0, t2")
        h.append("    addi t0, t0, 48")
        h.append("    addi sp, sp, -4")
        h.append("    sw t0, 0(sp)")
        h.append("    div a0, a0, t2")
        h.append("    j forge_print_int_push")
        h.append("forge_print_int_push_u:")
        h.append("    mv t3, sp")
        h.append("    li t2, 10")
        h.append("forge_print_int_push_u_loop:")
        h.append("    beq a0, zero, forge_print_int_pop")
        h.append("    remu t0, a0, t2")
        h.append("    addi t0, t0, 48")
        h.append("    addi sp, sp, -4")
        h.append("    sw t0, 0(sp)")
        h.append("    divu a0, a0, t2")
        h.append("    j forge_print_int_push_u_loop")
        h.append("forge_print_int_pop:")
        h.append("    beq sp, t3, forge_print_int_done")
        h.append("    lw t0, 0(sp)")
        h.append("    addi sp, sp, 4")
        h.append(f"    li t1, {UART}")
        h.append("    sb t0, 0(t1)")
        h.append("    j forge_print_int_pop")
        h.append("forge_print_int_zero:")
        h.append(f"    li t0, {UART}")
        h.append("    li t1, 48")
        h.append("    sb t1, 0(t0)")
        h.append("forge_print_int_done:")
        h.append("    lw ra, 0(sp)")
        h.append("    addi sp, sp, 4")
        h.append("    ret")
        h.append("forge_strlen:")
        h.append("    li t0, 0")
        h.append("forge_strlen_loop:")
        h.append("    lb t1, 0(a0)")
        h.append("    beq t1, zero, forge_strlen_done")
        h.append("    addi a0, a0, 1")
        h.append("    addi t0, t0, 1")
        h.append("    j forge_strlen_loop")
        h.append("forge_strlen_done:")
        h.append("    mv a0, t0")
        h.append("    ret")
        return h

    # ---------- functions ----------
    def gen_func(self, fn):
        self.cur_fn = fn.name
        self.slot_n = 0
        self.free = list(TEMPS)
        self.live = []
        self.env = [{}]
        self.epilogue = f"{fn.name}_epilogue"
        self.emit(f"{fn.name}:")
        self.emit("    addi sp, sp, -8")
        self.emit("    sw ra, 4(sp)")
        self.emit("    sw s0, 0(sp)")
        self.emit("    mv s0, sp")
        self.emit(f"    addi sp, sp, -{FRAME_BYTES}")
        for pname, ptype in fn.params:
            slot = self.alloc_slot()
            self.env[0][pname] = (slot, ptype)
        # Store incoming args into their slots (a0-a7).
        for i, (pname, _pt) in enumerate(fn.params):
            slot, _t = self.env[0][pname]
            self.emit(f"    sw a{i}, {self.slot_off(slot)}(s0)")
        self.gen_block(fn.body)
        if fn.name == "main":
            self.emit("    ecall")
        else:
            self.emit(f"{self.epilogue}:")
            self.emit("    mv sp, s0")
            self.emit("    lw s0, 0(sp)")
            self.emit("    lw ra, 4(sp)")
            self.emit("    addi sp, sp, 8")
            self.emit("    ret")
        self.env = []
        self.cur_fn = None

    def gen_block(self, block):
        self.env.append({})
        for stmt in block.stmts:
            self.gen_stmt(stmt)
        self.env.pop()

    # ---------- statements ----------
    def gen_stmt(self, stmt):
        if isinstance(stmt, A.Block):
            self.gen_block(stmt)
            return
        if isinstance(stmt, A.Let):
            t = stmt.ann if stmt.ann else self.expr_type(stmt.expr)
            if t == "float" or t.startswith("[float"):
                raise ForgeError("float is not supported on big32 (v1)")
            r = self.gen_expr(stmt.expr)
            slot = self.alloc_slot()
            self.env[-1][stmt.name] = (slot, t)
            self.emit(f"    sw {r}, {self.slot_off(slot)}(s0)")
            self.free_reg(r)
            return
        if isinstance(stmt, A.Assign):
            slot, _t = self.lookup(stmt.name)
            r = self.gen_expr(stmt.expr)
            self.emit(f"    sw {r}, {self.slot_off(slot)}(s0)")
            self.free_reg(r)
            return
        if isinstance(stmt, A.IndexAssign):
            base = stmt.base.base
            if not isinstance(base, A.Var):
                raise ForgeError("index assignment target must be a variable on big32")
            slot, _t = self.lookup(base.name)
            ptr = self.alloc()
            self.emit(f"    lw {ptr}, {self.slot_off(slot)}(s0)")
            idx = self.gen_expr(stmt.base.index)
            val = self.gen_expr(stmt.expr)
            addr = self.alloc()
            self.emit(f"    addi {addr}, {ptr}, 4")
            self.emit(f"    slli {idx}, {idx}, 2")
            self.emit(f"    add {addr}, {addr}, {idx}")
            self.emit(f"    sw {val}, 0({addr})")
            for r in (addr, val, idx, ptr):
                self.free_reg(r)
            return
        if isinstance(stmt, A.FieldAssign):
            raise ForgeError("structs are not supported on big32 (v1)")
        if isinstance(stmt, A.Match):
            raise ForgeError("match/enums are not supported on big32 (v1)")
        if isinstance(stmt, A.Spawn):
            raise ForgeError("spawn/threads are not supported on big32 (v1)")
        if isinstance(stmt, A.If):
            els = self.label("else")
            end = self.label("endif")
            cond = self.gen_expr(stmt.cond)
            self.emit(f"    beq {cond}, zero, {els}")
            self.free_reg(cond)
            self.gen_block(stmt.then)
            self.emit(f"    j {end}")
            self.emit(f"{els}:")
            if stmt.els is not None:
                self.gen_block(stmt.els)
            self.emit(f"{end}:")
            return
        if isinstance(stmt, A.While):
            cond_l = self.label("while")
            end = self.label("wend")
            self.emit(f"{cond_l}:")
            cond = self.gen_expr(stmt.cond)
            self.emit(f"    beq {cond}, zero, {end}")
            self.free_reg(cond)
            self.gen_block(stmt.body)
            self.emit(f"    j {cond_l}")
            self.emit(f"{end}:")
            return
        if isinstance(stmt, A.For):
            self.gen_for(stmt)
            return
        if isinstance(stmt, A.Return):
            if stmt.expr is not None:
                r = self.gen_expr(stmt.expr)
                self.emit(f"    mv a0, {r}")
                self.free_reg(r)
            if self.cur_fn == "main":
                self.emit("    ecall")
            else:
                self.emit(f"    j {self.epilogue}")
            return
        if isinstance(stmt, A.ExprStmt):
            call = stmt.expr
            if isinstance(call, A.Call) and call.name in ("print", "println"):
                self.gen_print(call)
                return
            if isinstance(call, A.Call) and call.name == "assert":
                cond = self.gen_expr(call.args[0])
                ok = self.label("assert_ok")
                self.emit(f"    bne {cond}, zero, {ok}")
                self.free_reg(cond)
                msg = self.gen_expr(call.args[1])
                self.emit(f"    mv a0, {msg}")
                self.free_reg(msg)
                self.emit("    jal ra, forge_print_str")
                self.emit("    li a0, 1")
                self.emit("    ecall")
                self.emit(f"{ok}:")
                return
            if isinstance(call, A.Call) and call.name == "fail":
                msg = self.gen_expr(call.args[0])
                self.emit(f"    mv a0, {msg}")
                self.free_reg(msg)
                self.emit("    jal ra, forge_print_str")
                self.emit("    li a0, 1")
                self.emit("    ecall")
                return
            if isinstance(call, A.Call) and call.name == "push":
                raise ForgeError("push (dynamic growth) is not supported on big32 (v1)")
            r = self.gen_expr(stmt.expr)
            self.free_reg(r)
            return
        raise ForgeError(f"unsupported statement {type(stmt).__name__} on big32")

    def gen_for(self, stmt):
        # for v in range(n) { ... }
        if isinstance(stmt.expr, A.Call) and stmt.expr.name == "range":
            n = self.gen_expr(stmt.expr.args[0])
            cnt_slot = self.alloc_slot()
            var_slot = self.alloc_slot()
            self.emit(f"    sw zero, {self.slot_off(cnt_slot)}(s0)")
            top = self.label("for")
            end = self.label("forend")
            self.emit(f"{top}:")
            cnt = self.alloc()
            self.emit(f"    lw {cnt}, {self.slot_off(cnt_slot)}(s0)")
            self.emit(f"    slt {cnt}, {cnt}, {n}")
            self.emit(f"    beq {cnt}, zero, {end}")
            self.free_reg(cnt)
            # loop var = counter value
            val = self.alloc()
            self.emit(f"    lw {val}, {self.slot_off(cnt_slot)}(s0)")
            self.emit(f"    sw {val}, {self.slot_off(var_slot)}(s0)")
            self.free_reg(val)
            self.env.append({stmt.name: (var_slot, "int")})
            self.gen_block(stmt.body)
            self.env.pop()
            inc = self.alloc()
            self.emit(f"    lw {inc}, {self.slot_off(cnt_slot)}(s0)")
            self.emit(f"    addi {inc}, {inc}, 1")
            self.emit(f"    sw {inc}, {self.slot_off(cnt_slot)}(s0)")
            self.free_reg(inc)
            self.free_reg(n)
            self.emit(f"    j {top}")
            self.emit(f"{end}:")
            return
        # for v in array { ... }
        arr_t = self.expr_type(stmt.expr)
        if not arr_t.startswith("["):
            raise ForgeError("for loop over a non-array is not supported on big32")
        et = arr_t[1:-1]
        ptr = self.gen_expr(stmt.expr)
        len_slot = self.alloc_slot()
        idx_slot = self.alloc_slot()
        var_slot = self.alloc_slot()
        tmp = self.alloc()
        self.emit(f"    lw {tmp}, 0({ptr})")
        self.emit(f"    sw {tmp}, {self.slot_off(len_slot)}(s0)")
        self.free_reg(tmp)
        self.emit(f"    sw zero, {self.slot_off(idx_slot)}(s0)")
        top = self.label("for")
        end = self.label("forend")
        self.emit(f"{top}:")
        idx = self.alloc()
        ln = self.alloc()
        self.emit(f"    lw {idx}, {self.slot_off(idx_slot)}(s0)")
        self.emit(f"    lw {ln}, {self.slot_off(len_slot)}(s0)")
        self.emit(f"    slt {idx}, {idx}, {ln}")
        self.emit(f"    beq {idx}, zero, {end}")
        self.free_reg(idx)
        self.free_reg(ln)
        # element = *(ptr + 4 + idx*4)
        idx2 = self.alloc()
        addr = self.alloc()
        self.emit(f"    lw {idx2}, {self.slot_off(idx_slot)}(s0)")
        self.emit(f"    slli {idx2}, {idx2}, 2")
        self.emit(f"    add {addr}, {ptr}, {idx2}")
        self.emit(f"    lw {addr}, 4({addr})")
        self.emit(f"    sw {addr}, {self.slot_off(var_slot)}(s0)")
        self.free_reg(idx2)
        self.free_reg(addr)
        self.env.append({stmt.name: (var_slot, et)})
        self.gen_block(stmt.body)
        self.env.pop()
        inc = self.alloc()
        self.emit(f"    lw {inc}, {self.slot_off(idx_slot)}(s0)")
        self.emit(f"    addi {inc}, {inc}, 1")
        self.emit(f"    sw {inc}, {self.slot_off(idx_slot)}(s0)")
        self.free_reg(inc)
        self.free_reg(ptr)
        self.emit(f"    j {top}")
        self.emit(f"{end}:")

    def gen_print(self, call):
        newline = call.name == "println"
        for i, arg in enumerate(call.args):
            t = self.expr_type(arg)
            r = self.gen_expr(arg)
            if t == "int":
                self.emit(f"    mv a0, {r}")
                self.emit("    jal ra, forge_print_int")
            elif t == "bool":
                true_l = self.label("istrue")
                done_l = self.label("bool_done")
                self.emit(f"    bne {r}, zero, {true_l}")
                self.emit(f"    li a0, {self.str_addr('false')}")
                self.emit("    jal ra, forge_print_str")
                self.emit(f"    j {done_l}")
                self.emit(f"{true_l}:")
                self.emit(f"    li a0, {self.str_addr('true')}")
                self.emit("    jal ra, forge_print_str")
                self.emit(f"{done_l}:")
            elif t == "str":
                self.emit(f"    mv a0, {r}")
                self.emit("    jal ra, forge_print_str")
            else:
                raise ForgeError(f"cannot print a value of type {t} on big32")
            self.free_reg(r)
            if i < len(call.args) - 1:
                self.emit(f"    li t0, {UART}")
                self.emit("    li t1, 32")
                self.emit("    sb t1, 0(t0)")
        if newline:
            self.emit(f"    li t0, {UART}")
            self.emit("    li t1, 10")
            self.emit("    sb t1, 0(t0)")

    # ---------- expressions: returns a temp register ----------
    def gen_expr(self, expr):
        if isinstance(expr, A.IntLit):
            r = self.alloc()
            v = expr.value & 0xFFFFFFFF
            if v >= 0x80000000:
                v -= 0x100000000
            self.emit(f"    li {r}, {v}")
            return r
        if isinstance(expr, A.FloatLit):
            raise ForgeError("float is not supported on big32 (v1)")
        if isinstance(expr, A.StrLit):
            r = self.alloc()
            self.emit(f"    li {r}, {self.str_addr(expr.value)}")
            return r
        if isinstance(expr, A.BoolLit):
            r = self.alloc()
            self.emit(f"    li {r}, {1 if expr.value else 0}")
            return r
        if isinstance(expr, A.Var):
            slot, _t = self.lookup(expr.name)
            r = self.alloc()
            self.emit(f"    lw {r}, {self.slot_off(slot)}(s0)")
            return r
        if isinstance(expr, A.ArrayLit):
            et = self.expr_type(expr)
            if et in ("[?]", "int"):
                raise ForgeError("array literal needs a known element type on big32")
            inner = et[1:-1]
            if inner == "float":
                raise ForgeError("float arrays are not supported on big32 (v1)")
            n = len(expr.elems)
            addr = self.static_addr(4 * (n + 1))
            ptr = self.alloc()
            self.emit(f"    li {ptr}, {addr}")
            ln = self.alloc()
            self.emit(f"    li {ln}, {n}")
            self.emit(f"    sw {ln}, 0({ptr})")
            self.free_reg(ln)
            self.emit(f"    addi {ptr}, {ptr}, 4")
            for e in expr.elems:
                er = self.gen_expr(e)
                self.emit(f"    sw {er}, 0({ptr})")
                self.free_reg(er)
                self.emit(f"    addi {ptr}, {ptr}, 4")
            # ptr now points past the end; reload the base address.
            self.emit(f"    li {ptr}, {addr}")
            return ptr
        if isinstance(expr, A.StructLit):
            raise ForgeError("structs are not supported on big32 (v1)")
        if isinstance(expr, A.FieldAccess):
            raise ForgeError("structs are not supported on big32 (v1)")
        if isinstance(expr, A.Index):
            et = self.expr_type(expr)
            if et == "float":
                raise ForgeError("float arrays are not supported on big32 (v1)")
            base = self.gen_expr(expr.base)
            idx = self.gen_expr(expr.index)
            addr = self.alloc()
            self.emit(f"    addi {addr}, {base}, 4")
            self.emit(f"    slli {idx}, {idx}, 2")
            self.emit(f"    add {addr}, {addr}, {idx}")
            self.emit(f"    lw {addr}, 0({addr})")
            self.free_reg(base)
            self.free_reg(idx)
            return addr
        if isinstance(expr, A.Cast):
            if expr.target == "float":
                raise ForgeError("float is not supported on big32 (v1)")
            return self.gen_expr(expr.expr)
        if isinstance(expr, A.UnaryOp):
            r = self.gen_expr(expr.expr)
            if expr.op == "-":
                self.emit(f"    sub {r}, zero, {r}")
            elif expr.op == "!":
                self.emit(f"    xori {r}, {r}, 1")
            else:
                raise ForgeError(f"unsupported unary operator {expr.op} on big32")
            return r
        if isinstance(expr, A.BinOp):
            return self.gen_binop(expr)
        if isinstance(expr, A.Call):
            return self.gen_call(expr)
        raise ForgeError(f"unsupported expression {type(expr).__name__} on big32")

    def gen_binop(self, expr):
        # Short-circuit && / || with branches.
        if expr.op in ("&&", "||"):
            left = self.gen_expr(expr.left)
            end = self.label("logic")
            if expr.op == "&&":
                self.emit(f"    beq {left}, zero, {end}")
                right = self.gen_expr(expr.right)
                self.emit(f"    mv {left}, {right}")
                self.free_reg(right)
            else:
                self.emit(f"    bne {left}, zero, {end}")
                right = self.gen_expr(expr.right)
                self.emit(f"    mv {left}, {right}")
                self.free_reg(right)
            self.emit(f"{end}:")
            return left
        left = self.gen_expr(expr.left)
        right = self.gen_expr(expr.right)
        lt = self.expr_type(expr.left)
        if lt == "str":
            raise ForgeError("string comparison/concatenation is not supported on big32 (v1)")
        op = expr.op
        if op == "+":
            self.emit(f"    add {left}, {left}, {right}")
        elif op == "-":
            self.emit(f"    sub {left}, {left}, {right}")
        elif op == "*":
            self.emit(f"    mul {left}, {left}, {right}")
        elif op == "/":
            self.emit(f"    div {left}, {left}, {right}")
        elif op == "%":
            self.emit(f"    rem {left}, {left}, {right}")
        elif op == "<":
            self.emit(f"    slt {left}, {left}, {right}")
        elif op == ">":
            self.emit(f"    slt {left}, {right}, {left}")
        elif op == "<=":
            self.emit(f"    slt {left}, {right}, {left}")
            self.emit(f"    xori {left}, {left}, 1")
        elif op == ">=":
            self.emit(f"    slt {left}, {left}, {right}")
            self.emit(f"    xori {left}, {left}, 1")
        elif op == "==":
            self.emit(f"    xor {left}, {left}, {right}")
            self.emit(f"    sltiu {left}, {left}, 1")
        elif op == "!=":
            self.emit(f"    xor {left}, {left}, {right}")
            self.emit(f"    sltu {left}, zero, {left}")
        elif op == "&":
            self.emit(f"    and {left}, {left}, {right}")
        elif op == "|":
            self.emit(f"    or {left}, {left}, {right}")
        elif op == "^":
            self.emit(f"    xor {left}, {left}, {right}")
        elif op == "<<":
            self.emit(f"    sll {left}, {left}, {right}")
        elif op == ">>":
            self.emit(f"    sra {left}, {left}, {right}")
        else:
            raise ForgeError(f"unsupported operator {op} on big32")
        self.free_reg(right)
        return left

    def gen_call(self, expr):
        name = expr.name
        if name == "len":
            arg = expr.args[0]
            at = self.expr_type(arg)
            r = self.gen_expr(arg)
            if at == "str":
                self.emit(f"    mv a0, {r}")
                self.free_reg(r)
                self.emit("    jal ra, forge_strlen")
                out = self.alloc()
                self.emit(f"    mv {out}, a0")
                return out
            if at.startswith("["):
                self.emit(f"    lw {r}, 0({r})")
                return r
            raise ForgeError("len() of a non-array, non-string is not supported on big32")
        if name == "range":
            raise ForgeError("range() is only supported as a for-loop source on big32")
        if name in ("print", "println", "push"):
            raise ForgeError(f"{name}() cannot be used as an expression on big32")
        if name in ("sqrt", "exp", "log", "pow", "clock_micros", "read_file",
                    "write_file", "args", "parse_int", "split", "join",
                    "substr", "trim", "starts_with", "ends_with", "http_get"):
            raise ForgeError(f"builtin {name}() is not supported on big32 (v1)")
        if name not in self.funcs:
            raise ForgeError(f"unknown function {name} on big32")
        if len(expr.args) > 8:
            raise ForgeError("more than 8 function arguments are not supported on big32 (v1)")
        arg_regs = [self.gen_expr(a) for a in expr.args]
        # Spill every other live temp across the call.
        saved = [r for r in self.live if r not in arg_regs]
        if saved:
            self.emit(f"    addi sp, sp, -{4 * len(saved)}")
            for i, r in enumerate(saved):
                self.emit(f"    sw {r}, {4 * i}(sp)")
            for r in saved:
                self.live.remove(r)
        # Move args to a0-a7 via a scratch temp that is not an arg reg.
        scratch = None
        for cand in TEMPS:
            if cand not in arg_regs and cand not in self.live:
                scratch = cand
                break
        if scratch is None:
            raise ForgeError("no scratch register available for a big32 call")
        for i, r in enumerate(arg_regs):
            if r == f"a{i}":
                continue
            self.emit(f"    mv {scratch}, {r}")
            self.emit(f"    mv a{i}, {scratch}")
            self.free_reg(r)
        self.emit(f"    jal ra, {name}")
        if saved:
            for i, r in enumerate(saved):
                self.emit(f"    lw {r}, {4 * i}(sp)")
            self.emit(f"    addi sp, sp, {4 * len(saved)}")
            for r in saved:
                self.live.append(r)
        out = self.alloc()
        self.emit(f"    mv {out}, a0")
        return out


def generate_rv(program, types):
    gen = RVGen(program, types)
    return gen.generate()
