#!/usr/bin/env python3
"""Pixel framebuffer kernel test (SOC2 simulation).

Builds examples/os/kernel_pix.fg for big32 freestanding with
the SOC2 stack top, compiles the pixel testbench against
the SOC2 sources, runs it, and checks the verdict plus the
UART transcript.

The kernel uses no RAM scratch, so no rebase step is
needed (all its literals are either small or MMIO).
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PROOF = os.path.expanduser("~/workspace/rx-proof")
BIG32 = os.path.expanduser("~/workspace/big32")
TMP = "/tmp"


def sh(args, **kw):
    return subprocess.run(args, capture_output=True, text=True, **kw)


def main():
    failures = []

    def check(name, ok, detail=""):
        print(f"  {'PASS' if ok else 'FAIL'} {name} {detail}")
        if not ok:
            failures.append(name)

    b = sh([sys.executable, os.path.join(ROOT, "forge.py"), "build",
            "--target", "big32", "--freestanding",
            "--stack-top", "0x800F0000",
            "-o", os.path.join(TMP, "kern_pix"),
            os.path.join(ROOT, "examples/os/kernel_pix.fg")])
    check("builds freestanding big32", b.returncode == 0, b.stderr[-200:])

    c = sh(["iverilog", "-o", os.path.join(PROOF, "tb_pix.vvp"),
            os.path.join(BIG32, "src/big32_core_pipe.v"),
            os.path.join(BIG32, "src/big32_soc2.v"),
            os.path.join(PROOF, "tb_pix.v")])
    check("SOC2 + testbench compile", c.returncode == 0, c.stderr[-200:])

    r = sh(["vvp", os.path.join(PROOF, "tb_pix.vvp"),
            f"+HEX={os.path.join(TMP, 'kern_pix.hex')}",
            f"+TXOUT={os.path.join(TMP, 'pix_tx.txt')}"],
           timeout=900)
    out = r.stdout + r.stderr
    verdict = [ln for ln in out.splitlines() if "PIX PASS" in ln or "PIX FAIL" in ln]
    check("pixel verdict PIX PASS", bool(verdict) and "PIX PASS" in verdict[0], str(verdict))
    try:
        tx = open(os.path.join(TMP, "pix_tx.txt"), "rb").read().decode("ascii")
    except OSError:
        tx = ""
    check("exact transcript 'KERN\\nDONE\\n'", tx == "KERN\nDONE\n", repr(tx))
    print(f"\n{len(failures)} failure(s): {failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
