#!/usr/bin/env python3
"""Finder app stage 1 test (SOC2 simulation).

Builds examples/os/kernel_finder.fg for big32 freestanding
with the SOC2 stack top, compiles the Finder testbench against
the SOC2 sources, runs it, and checks the verdict plus the UART
transcript.

The kernel is SOC2-native (all MMIO/FS addresses are full SOC2
addresses; its FS v2 data lives in high RAM at 0x800E0000+, above
the code image, so boot_files() cannot overwrite instructions —
the old model-space FS bases 0x8060-0xE000 sat inside this
kernel's code and corrupted the press path, found 28 Oct 2026).

The testbench waits out the first draw (which lists the three
real boot-created files FILE 1/2/3 from the FS table), clicks
row 1 to select it, drags Finder by (+50,+50), and checks
pixels, plus the clock's format/position only (its value is
time-dependent and cannot be exact-checked). The simulation
takes roughly an hour at Icarus speed (~18M cycles); the
timeout below covers the full scripted sequence.
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
            "-o", os.path.join(TMP, "kern_finder"),
            os.path.join(ROOT, "examples/os/kernel_finder.fg")])
    check("builds freestanding big32", b.returncode == 0, b.stderr[-200:])

    c = sh(["iverilog", "-o", os.path.join(PROOF, "tb_mac_finder.vvp"),
            os.path.join(BIG32, "src/big32_core_pipe.v"),
            os.path.join(BIG32, "src/big32_soc2.v"),
            os.path.join(PROOF, "tb_mac_finder.v")])
    check("SOC2 + testbench compile", c.returncode == 0, c.stderr[-200:])

    r = sh(["vvp", os.path.join(PROOF, "tb_mac_finder.vvp"),
            f"+HEX={os.path.join(TMP, 'kern_finder.hex')}",
            f"+TXOUT={os.path.join(TMP, 'finder_tx.txt')}"],
           timeout=5400)
    out = r.stdout + r.stderr
    verdict = [ln for ln in out.splitlines()
               if "FINDER PASS" in ln or "FINDER FAIL" in ln]
    check("finder verdict FINDER PASS",
          bool(verdict) and "FINDER PASS" in verdict[0], str(verdict))
    try:
        tx = open(os.path.join(TMP, "finder_tx.txt"), "rb").read().decode("ascii")
    except OSError:
        tx = ""
    check("exact transcript 'MAC\\n'", tx == "MAC\n", repr(tx))
    print(f"\n{len(failures)} failure(s): {failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
