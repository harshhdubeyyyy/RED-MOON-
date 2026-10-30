#!/usr/bin/env python3
"""Terminal-in-a-window test (SOC2 simulation).

Builds examples/os/kernel_term.fg for big32 freestanding
with the SOC2 stack top, compiles the long-wait Finder
testbench against the SOC2 sources, runs it, and checks the
verdict plus the UART transcript.

The kernel is SOC2-native (all MMIO/FS addresses are full SOC2
addresses; its FS v2 data lives in high RAM at 0x800E0000+ and
its terminal text buffer at 0x800E3000+, above the code image,
so neither can overwrite instructions).

The testbench is the long-wait variant of the Finder test:
it waits for the kernel's MAC signal (first draw done) instead
of a fixed cycle count, and it waits 14M cycles after the
click release and the drag move instead of 5.5M. The shorter
waits were calibrated for the Finder kernel's smaller repaint;
the terminal kernel's repaint is bigger (608 terminal cells),
and with 5.5M waits the checks caught the repaint mid-flight
— the window looked "gone" after the click — while the
kernel was correct all along. With 14M waits the same kernel
passes: FINDER PASS, 30 Oct 2026 01:08 IST (list, select,
drag, clock all match). The simulation takes roughly
an hour and a half at Icarus speed (~36M cycles); the
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
            "-o", os.path.join(TMP, "kern_term"),
            os.path.join(ROOT, "examples/os/kernel_term.fg")])
    check("builds freestanding big32", b.returncode == 0, b.stderr[-200:])

    c = sh(["iverilog", "-o", os.path.join(PROOF, "tb_mac_finder_longwait.vvp"),
            os.path.join(BIG32, "src/big32_core_pipe.v"),
            os.path.join(BIG32, "src/big32_soc2.v"),
            os.path.join(PROOF, "tb_mac_finder_longwait.v")])
    check("SOC2 + testbench compile", c.returncode == 0, c.stderr[-200:])

    r = sh(["vvp", os.path.join(PROOF, "tb_mac_finder_longwait.vvp"),
            f"+HEX={os.path.join(TMP, 'kern_term.hex')}",
            f"+TXOUT={os.path.join(TMP, 'term_tx.txt')}"],
           timeout=10800)
    out = r.stdout + r.stderr
    verdict = [ln for ln in out.splitlines()
               if "FINDER PASS" in ln or "FINDER FAIL" in ln]
    check("terminal verdict FINDER PASS",
          bool(verdict) and "FINDER PASS" in verdict[0], str(verdict))
    try:
        tx = open(os.path.join(TMP, "term_tx.txt"), "rb").read().decode("ascii")
    except OSError:
        tx = ""
    check("exact transcript 'MAC\\n'", tx == "MAC\n", repr(tx))
    print(f"\n{len(failures)} failure(s): {failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
