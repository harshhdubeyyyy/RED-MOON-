#!/usr/bin/env python3
"""End-to-end tests for Phase D: traps, interrupts, firmware calls.

The big32 model has no timer and no SBI emulation: ECALL/EBREAK
trap to mtvec when mtvec is non-zero and halt otherwise, and
only six CSRs exist (mstatus 768, mtvec 773, mscratch 832,
mepc 833, mcause 834, mtval 835). Phase D is fitted to that
reality:

  * CSR builtins: csr_read(csr) -> int (expression);
    csr_write/csr_set/csr_clear(csr, val) (statement-only, like
    poke32). The CSR number MUST be a literal: RISC-V CSR
    instructions take a 12-bit immediate, not a register.
  * Trap-handler hook: defining fn trap_handler() (no args, void)
    makes _start point mtvec at an assembly stub that saves all
    30 clobberable registers on the stack, passes the trap-frame
    pointer in a0 (Phase E: a handler may take one int param for
    it; no-arg handlers ignore it), calls the handler, and — if
    the handler wrote a non-zero frame pointer to mscratch — switches
    stacks before restoring and mret-ing. The stub does NOT touch
    mepc: advancing past an ecall is the handler's job (read
    mcause/mepc, write mepc+4 for ecall traps).
  * ecall(eid, arg) -> int: extension id in a7, argument in a0,
    result back in a0. On SBI firmware this is the SBI call
    primitive; on the model it traps to the program's handler.
  * Program end halts even with a handler wired: main's ending
    (and fail/assert paths) clear mtvec before the final ecall,
    since a bare ecall with mtvec set would trap, not halt.
  * Native and WASM reject all five builtins loudly (no RISC-V
    CSRs/ecall there); the checker rejects non-literal CSR
    numbers, bad arity/types, csr_write used as a value, and a
    trap_handler with parameters or a return value.

Tests:
  1. big32 model: CSR set/clear/read + mscratch round-trip +
     ecall trap -> handler -> continue, exact UART transcript,
     and the run halts (not a 1M-step slide)
  2. checker rejects non-literal CSR, bad arity, csr_write as a
     value, trap_handler with two params (big32 codegen)
  3. native + wasm reject csr_read and ecall clearly
  4. hosted control: the same big32 program builds WITHOUT
     --freestanding (CSRs/ecall are hardware, not OS)

Exits 0 only if every test passes.
"""
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FORGE = [sys.executable, os.path.join(ROOT, "forge.py")]
MODEL = os.path.expanduser("~/workspace/big32/tools/model.py")
FAILURES = []

MAIN_PROG = """fn trap_handler() {
  if csr_read(834) == 11 {
    csr_write(833, csr_read(833) + 4);
    poke32(268435456, 84);
  }
}
fn main() {
  csr_write(768, 0);
  csr_set(768, 8);
  if csr_read(768) == 8 {
    poke32(268435456, 83);
  }
  csr_clear(768, 8);
  if csr_read(768) == 0 {
    poke32(268435456, 67);
  }
  csr_write(832, 65);
  if csr_read(832) == 65 {
    poke32(268435456, 82);
  }
  let x: int = ecall(1, 65);
  poke32(268435456, 75);
}
"""


def check(name, cond, detail=""):
    if cond:
        print(f"  PASS {name}")
    else:
        print(f"  FAIL {name} {detail}")
        FAILURES.append(name)


def write_prog(d, prog, name="prog.fg"):
    path = os.path.join(d, name)
    with open(path, "w") as f:
        f.write(prog)
    return path


def big32_run(prog, *extra):
    d = tempfile.mkdtemp(prefix="traps-big32-")
    path = write_prog(d, prog)
    out = os.path.join(d, "prog")
    r = subprocess.run(FORGE + ["build", path, "--target", "big32", "-o", out] + list(extra),
                       capture_output=True, text=True, timeout=120)
    hexpath = out + ".hex"
    if r.returncode != 0 or not os.path.exists(hexpath):
        return None, r, ""
    r2 = subprocess.run([sys.executable, MODEL, hexpath],
                        capture_output=True, text=True, timeout=120)
    uart = ""
    if "uart:\n" in r2.stdout:
        uart = r2.stdout.split("uart:\n", 1)[1]
    return r2, r, uart


def main():
    print("big32 model: CSR + trap + halt")
    if os.path.exists(MODEL):
        r2, r, uart = big32_run(MAIN_PROG, "--freestanding")
        check("big32 trap program builds", r.returncode == 0, f"err={r.stderr!r}")
        if r2 is not None:
            check("uart transcript SCRTK", uart.strip() == "SCRTK",
                  f"uart={uart!r} full={r2.stdout!r} err={r2.stderr!r}")
            check("run halts (not a slide)",
                  "halted=True" in r2.stdout, f"out={r2.stdout!r}")
    else:
        print("  SKIP big32 (model.py not found)")

    print("checker rejections")
    cases = [
        ("csr_read non-literal",
         "fn main() -> int { let c: int = 768; return csr_read(c); }\n", "check"),
        ("csr_read arity",
         "fn main() -> int { return csr_read(768, 769); }\n", "check"),
        ("csr_read out of range",
         "fn main() -> int { return csr_read(4096); }\n", "check"),
        ("csr_write non-literal",
         "fn main() { csr_write(768, 0); let c: int = 768; csr_write(c, 1); }\n", "check"),
        ("csr_write as value",
         "fn main() { let x: int = csr_write(768, 0); }\n", "check"),
        ("ecall arity",
         "fn main() -> int { return ecall(1); }\n", "check"),
    ]
    for name, prog, cmd in cases:
        d = tempfile.mkdtemp(prefix="traps-check-")
        path = write_prog(d, prog)
        r = subprocess.run(FORGE + [cmd, path, "--freestanding"] if cmd == "check"
                           else FORGE + [cmd, path],
                           capture_output=True, text=True, timeout=60)
        check(f"checker rejects {name}", r.returncode != 0,
              f"rc={r.returncode} out={r.stdout!r} err={r.stderr!r}")

    print("big32 rejects bad trap_handler (Phase E: one int param,")
    print("the trap-frame pointer, is legal; two params are not)")
    d = tempfile.mkdtemp(prefix="traps-handler-")
    path = write_prog(d, "fn trap_handler(x: int, y: int) { }\nfn main() { }\n")
    r = subprocess.run(FORGE + ["build", path, "--target", "big32",
                                "-o", os.path.join(d, "prog")],
                       capture_output=True, text=True, timeout=60)
    check("trap_handler with two params rejected",
          r.returncode != 0 and "trap_handler" in (r.stdout + r.stderr),
          f"rc={r.returncode} out={r.stdout!r} err={r.stderr!r}")
    path = write_prog(d, "fn trap_handler(frame: int) { }\nfn main() { }\n")
    r = subprocess.run(FORGE + ["build", path, "--target", "big32",
                                "-o", os.path.join(d, "prog")],
                       capture_output=True, text=True, timeout=60)
    check("trap_handler with one int param accepted",
          r.returncode == 0,
          f"rc={r.returncode} out={r.stdout!r} err={r.stderr!r}")

    print("native + wasm rejections")
    for target, prog in [
        ("native", "fn main() -> int { return csr_read(768); }\n"),
        ("native", "fn main() -> int { return ecall(1, 65); }\n"),
        ("wasm", "fn main() -> int { return csr_read(768); }\n"),
        ("wasm", "fn main() -> int { return ecall(1, 65); }\n"),
    ]:
        d = tempfile.mkdtemp(prefix="traps-target-")
        path = write_prog(d, prog)
        args = FORGE + ["build", path, "-o", os.path.join(d, "prog")]
        if target == "wasm":
            args = FORGE + ["build", path, "--target", "wasm",
                           "-o", os.path.join(d, "prog.wasm")]
        r = subprocess.run(args, capture_output=True, text=True, timeout=60)
        check(f"{target} rejects {prog.split('return ')[1].split('(')[0]}",
              r.returncode != 0 and "big32" in (r.stdout + r.stderr),
              f"rc={r.returncode} out={r.stdout!r} err={r.stderr!r}")

    print("hosted control")
    if os.path.exists(MODEL):
        r2, r, uart = big32_run(MAIN_PROG)
        check("same program builds hosted", r.returncode == 0, f"err={r.stderr!r}")
        if r2 is not None:
            check("hosted uart SCRTK", uart.strip() == "SCRTK", f"uart={uart!r}")
    else:
        print("  SKIP hosted control (model.py not found)")

    print(f"\n{len(FAILURES)} failure(s): {FAILURES}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
