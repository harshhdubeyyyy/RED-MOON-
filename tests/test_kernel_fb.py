#!/usr/bin/env python3
"""Framebuffer kernel test (SOC2 simulation).

Builds examples/os/kernel_fb.fg for big32 freestanding with
the SOC2 stack top, compiles the framebuffer testbench
against the SOC2 sources, runs it, and checks the verdict
plus the UART transcript.

The kernel uses no RAM scratch, so no rebase step is
needed (all its literals are either small or MMIO).
"""
import os
import re
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

    # 1. Build the kernel.
    b = sh([sys.executable, os.path.join(ROOT, "forge.py"), "build",
            "--target", "big32", "--freestanding",
            "--stack-top", "0x800F0000",
            "-o", os.path.join(TMP, "kern_fb"),
            os.path.join(ROOT, "examples/os/kernel_fb.fg")])
    check("builds freestanding big32", b.returncode == 0, b.stderr[-200:])

    # 2. Compile the testbench.
    c = sh(["iverilog", "-o", os.path.join(PROOF, "tb_fb.vvp"),
            os.path.join(BIG32, "src/big32_core_pipe.v"),
            os.path.join(BIG32, "src/big32_soc2.v"),
            os.path.join(PROOF, "tb_fb.v")])
    check("SOC2 + testbench compile", c.returncode == 0, c.stderr[-200:])

    # 3. Run and check.
    r = sh(["vvp", os.path.join(PROOF, "tb_fb.vvp"),
            f"+HEX={os.path.join(TMP, 'kern_fb.hex')}",
            f"+TXOUT={os.path.join(TMP, 'fb_tx.txt')}"],
           timeout=600)
    out = r.stdout + r.stderr
    verdict = [ln for ln in out.splitlines() if "FB PASS" in ln or "FB FAIL" in ln]
    check("framebuffer verdict FB PASS", bool(verdict) and "FB PASS" in verdict[0], str(verdict))
    try:
        tx = open(os.path.join(TMP, "fb_tx.txt"), "rb").read().decode("ascii")
    except OSError:
        tx = ""
    check("exact transcript 'KERN\\nDONE\\n'", tx == "KERN\nDONE\n", repr(tx))
    print(f"\n{len(failures)} failure(s): {failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
