#!/usr/bin/env python3
"""End-to-end test for Phase F checkpoint 4: filesystem v2 —
delete with block reclaim.

v1 files were contiguous runs, so deleting one stranded its
blocks. v2 uses indexed allocation: each file owns a row of up
to 16 block indices, and freed blocks go on a free-list whose
links live in the freed blocks themselves (first word = next
free block, -1 = end). Layout: bump pointer in scratch 0x8050,
free-list head in scratch 0x8054, file table in scratch 0x8060
(8 slots x 16 bytes), block map in scratch 0x8100 (8 slots x
16 entries), data blocks at 0xD000 (16 x 256 bytes).

The kernel (examples/os/kernel_fs2.fg) creates file 1 (70
words) and verifies the block boundary, deletes it, creates
file 2 (70 words) reusing the freed blocks, fills the disk
with file 3 (896 words), checks that creating file 4 fails,
deletes files 2 and 3, then creates file 5 (1024 words = the
whole disk), proving full reclaim, then DONE and halts.

Expects the exact transcript KERNKKKKKDONE, halted, and the
predicted heap state: bump pointer 16, free-list empty (-1),
and file 5's map row in free-list pop order
[15, 14, ..., 2, 0, 1]. Exits 0 only if every test passes.
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
    print("filesystem v2 delete + reclaim (big32 model)")
    with tempfile.TemporaryDirectory() as td:
        out = os.path.join(td, "kern_fs2")
        r = subprocess.run(FORGE + ["build", "--target", "big32",
                                    "--freestanding", "-o", out,
                                    "examples/os/kernel_fs2.fg"],
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
        check("bump pointer 16", word(d, 0x8050) == 16)
        check("free-list empty", word(d, 0x8054) == 4294967295)
        row = [word(d, 0x8100 + 4 * i) for i in range(16)]
        check("file5 map in pop order",
              row == [15, 14, 13, 12, 11, 10, 9, 8, 7, 6, 5, 4, 3, 2, 0, 1],
              str(row))
    print(f"\n{len(FAILURES)} failure(s): {FAILURES}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    raise SystemExit(main())
