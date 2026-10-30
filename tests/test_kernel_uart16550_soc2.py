#!/usr/bin/env python3
"""16550 UART driver kernel — SOC2 hardware check (30 Oct 2026).

Builds kernel_uart16550.fg for SOC2 (--stack-top 0x800F0000), compiles
tb_uart16550.v against big32_core_pipe.v + big32_soc2.v, runs it, and
checks BOTH halves: the legacy-UART transcript (baud=divisor lines) and
the real 16550 device registers (dll/dlm/lcr/ier) reported by the TB.
FCR is not asserted: the SOC2 model ignores FCR writes (no register).
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BIG32 = os.path.expanduser("~/workspace/big32")
PROOF = os.path.expanduser("~/workspace/rx-proof")
TMP = "/tmp"
FAILURES = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'} {name} {detail}")
    if not cond:
        FAILURES.append(name)


def sh(args, **kw):
    return subprocess.run(args, capture_output=True, text=True, **kw)


def main():
    print("16550 uart driver (SOC2 hardware check)")
    b = sh([sys.executable, os.path.join(ROOT, "forge.py"), "build",
            "--target", "big32", "--freestanding",
            "--stack-top", "0x800F0000",
            "-o", os.path.join(TMP, "kern_uart16550"),
            os.path.join(ROOT, "examples/os/kernel_uart16550.fg")])
    check("builds freestanding big32 (SOC2 stack top)", b.returncode == 0,
          b.stderr[-300:])
    if b.returncode != 0:
        print("FAILED")
        return 1
    c = sh(["iverilog", "-o", os.path.join(PROOF, "tb_uart16550.vvp"),
            os.path.join(BIG32, "src/big32_core_pipe.v"),
            os.path.join(BIG32, "src/big32_soc2.v"),
            os.path.join(PROOF, "tb_uart16550.v")])
    check("SOC2 + testbench compile", c.returncode == 0, c.stderr[-300:])
    if c.returncode != 0:
        print("FAILED")
        return 1
    r = sh(["vvp", os.path.join(PROOF, "tb_uart16550.vvp"),
            f"+HEX={os.path.join(TMP, 'kern_uart16550.hex')}",
            f"+TXOUT={os.path.join(TMP, 'uart16550_tx.txt')}"],
           timeout=600)
    out = r.stdout + r.stderr
    print("  TB:", [ln for ln in out.splitlines()
                    if "UART16550" in ln][:8])
    check("TB verdict UART16550 PASS", "UART16550 PASS" in out, out[-500:])
    try:
        tx = open(os.path.join(TMP, "uart16550_tx.txt"), "rb").read().decode("ascii")
    except OSError:
        tx = ""
    check("exact transcript",
          tx == "9600=12\n19200=6\n38400=3\n115200=1\nDONE\n", repr(tx))
    if FAILURES:
        print("FAILED:", FAILURES)
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
