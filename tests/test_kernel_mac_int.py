#!/usr/bin/env python3
"""Interactive macOS-look desktop test (SOC2 simulation).

Builds examples/os/kernel_mac_interactive.fg for big32 freestanding
with the SOC2 stack top, compiles the interactive testbench against
the SOC2 sources, runs it, and checks the verdict plus the UART
transcript.

The kernel NEVER halts (it is an interactive loop), so the
testbench does not wait for halt: it waits out the first draw,
then scripts the pointer (click Finder title for focus, drag
Finder by (+50,+50), close Finder via its red light) and checks
pixels, plus the clock's format/position only (its value is
time-dependent and cannot be exact-checked). The simulation
takes roughly an hour at Icarus speed (~22M cycles); the
timeout below covers a full repaint per action.
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
            "-o", os.path.join(TMP, "kern_mac_int"),
            os.path.join(ROOT, "examples/os/kernel_mac_interactive.fg")])
    check("builds freestanding big32", b.returncode == 0, b.stderr[-200:])

    c = sh(["iverilog", "-o", os.path.join(PROOF, "tb_mac_int.vvp"),
            os.path.join(BIG32, "src/big32_core_pipe.v"),
            os.path.join(BIG32, "src/big32_soc2.v"),
            os.path.join(PROOF, "tb_mac_int.v")])
    check("SOC2 + testbench compile", c.returncode == 0, c.stderr[-200:])

    r = sh(["vvp", os.path.join(PROOF, "tb_mac_int.vvp"),
            f"+HEX={os.path.join(TMP, 'kern_mac_int.hex')}",
            f"+TXOUT={os.path.join(TMP, 'mac_int_tx.txt')}"],
           timeout=3600)
    out = r.stdout + r.stderr
    verdict = [ln for ln in out.splitlines()
               if "INTERACTIVE PASS" in ln or "INTERACTIVE FAIL" in ln]
    check("interactive verdict INTERACTIVE PASS",
          bool(verdict) and "INTERACTIVE PASS" in verdict[0], str(verdict))
    try:
        tx = open(os.path.join(TMP, "mac_int_tx.txt"), "rb").read().decode("ascii")
    except OSError:
        tx = ""
    check("exact transcript 'MAC\\n'", tx == "MAC\n", repr(tx))
    print(f"\n{len(failures)} failure(s): {failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
