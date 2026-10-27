#!/usr/bin/env python3
"""End-to-end test for Phase F checkpoint 3: tiny filesystem.

Files are identified by numeric id, not names (freestanding
rejects string values, so names wait for a later checkpoint).
Files are fixed-size at create time, stored as contiguous
256-byte blocks: file table in scratch at 0x8060 (8 slots x
16 bytes [id, used, size_words, start_block]), next-free-block
in scratch 0x8050, data blocks at 0xD000 (16 x 256 bytes, 64
words each). API returns 0 ok, -1 fail; read returns -1 as a
sentinel for missing/out-of-bounds. Delete is NOT in v1: freed
blocks are reclaimed only by reformat.

The kernel (examples/os/kernel_fs.fg) creates file 1 (4 words)
and verifies its contents, creates file 2 (70 words, spans 2
blocks) and verifies words across the block boundary, fills the
disk with file 3 (832 words = 13 blocks), checks that creating
file 4 fails, checks that an out-of-bounds write fails, then
DONE and halts.

This test also regresses a real big32 backend bug found 27 Oct
2026: argument registers used to be expression temps, so under
temp pressure the call-staging loop overwrote an argument with
another one — fs_write(1, 3, 44) stored 3 (the index) instead
of 44 (the value), and only the readback check caught it.
a-regs are now excluded from TEMPS; this test fails if that
regresses.

Expects the exact transcript KERNKKKKKDONE and halted. Exits 0
only if every test passes.
"""
import importlib.util
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FORGE = [sys.executable, os.path.join(ROOT, "forge.py")]
MODEL = os.path.expanduser("~/workspace/big32/tools/model.py")
FAILURES = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'} {name} {detail}")
    if not cond:
        FAILURES.append(name)


def word(dmem, a):
    return (dmem[a] | (dmem[a + 1] << 8) |
            (dmem[a + 2] << 16) | (dmem[a + 3] << 24))


def main():
    print("tiny filesystem (big32 model)")
    with tempfile.TemporaryDirectory() as td:
        out = os.path.join(td, "kern_fs")
        r = subprocess.run(FORGE + ["build", "--target", "big32",
                                    "--freestanding", "-o", out,
                                    "examples/os/kernel_fs.fg"],
                           capture_output=True, text=True, cwd=ROOT)
        check("builds freestanding big32", r.returncode == 0, r.stderr[-200:])
        spec = importlib.util.spec_from_file_location("big32model", MODEL)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        res = mod.run(out + ".hex")
        uart = res["uart"].decode("utf-8", "replace")
        check("exact transcript KERNKKKKKDONE", uart == "KERNKKKKKDONE",
              uart)
        check("halts", res["halted"] is True)
        d = res["dmem"]
        check("file1 contents intact",
              [word(d, 0xD000 + 4 * i) for i in range(4)] ==
              [11, 22, 33, 44])
        check("file2 boundary words intact",
              word(d, 0xD100 + 63 * 4) == 630 and
              word(d, 0xD200) == 640 and
              word(d, 0xD200 + 5 * 4) == 690)
        check("disk full (next block 16)", word(d, 0x8050) == 16)
    print(f"\n{len(FAILURES)} failure(s): {FAILURES}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    raise SystemExit(main())
