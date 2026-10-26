#!/usr/bin/env python3
"""Forge v2 compiler CLI.

Usage:
    python3 forge.py check <file.fg> [--mode safe|fast]
    python3 forge.py build <file.fg> [-o out] [--mode safe|fast] [--keep-c out.c]
    python3 forge.py run   <file.fg> [--mode safe|fast] [-- program args...]
    python3 forge.py emit  <file.fg> [--mode safe|fast]
    python3 forge.py test
Safe mode (default): checked int arithmetic + bounds-checked indexing.
Fast mode: unchecked, -O3 -march=native, for microsecond-latency work.
"""

import argparse
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from forge_lang.errors import ForgeError  # noqa: E402
from forge_lang.compiler import compile_file, build  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(prog="forge", description="Forge compiler v2")
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("check", "emit"):
        p = sub.add_parser(name)
        p.add_argument("file")
        p.add_argument("--mode", choices=["safe", "fast"], default="safe")
    p = sub.add_parser("run")
    p.add_argument("file")
    p.add_argument("--mode", choices=["safe", "fast"], default="safe")
    p.add_argument("program_args", nargs=argparse.REMAINDER, default=[])
    sub.add_parser("test")
    p = sub.add_parser("build")
    p.add_argument("file")
    p.add_argument("--mode", choices=["safe", "fast"], default="safe")
    p.add_argument("-o", "--output", default=None)
    p.add_argument("--keep-c", default=None)

    args = parser.parse_args(argv)
    try:
        if args.cmd == "check":
            compile_file(args.file, mode=args.mode)
            print("ok: no errors")
            return 0
        if args.cmd == "emit":
            c_source, _ = compile_file(args.file, mode=args.mode)
            print(c_source)
            return 0
        if args.cmd == "build":
            out = args.output or os.path.splitext(args.file)[0]
            build(args.file, out, mode=args.mode, keep_c=args.keep_c)
            print(f"built: {out} (mode={args.mode})")
            return 0
        if args.cmd == "test":
            root = os.path.dirname(os.path.abspath(__file__))
            suite = os.path.join(root, "tests", "run_tests.py")
            proc = subprocess.run([sys.executable, suite], cwd=root)
            return proc.returncode
        if args.cmd == "run":
            c_source, _ = compile_file(args.file, mode=args.mode)
            with tempfile.TemporaryDirectory(prefix="forge2_run_") as td:
                c_path = os.path.join(td, "prog.c")
                exe = os.path.join(td, "prog")
                with open(c_path, "w", encoding="utf-8") as f:
                    f.write(c_source)
                flags = (["cc", "-O3", "-march=native", "-std=gnu11"] if args.mode == "fast"
                         else ["cc", "-O2", "-std=gnu11"])
                cc = subprocess.run(flags + ["-o", exe, c_path, "-lm"],
                                    capture_output=True, text=True)
                if cc.returncode != 0:
                    raise ForgeError(f"C compiler failed:\n{cc.stderr}")
                prog_args = list(args.program_args)
                if prog_args and prog_args[0] == "--":
                    prog_args = prog_args[1:]
                proc = subprocess.run([exe] + prog_args)
                return proc.returncode
    except ForgeError as e:
        print(f"forge: error: {e}", file=sys.stderr)
        return 1
    except FileNotFoundError:
        print(f"forge: error: file not found: {args.file}", file=sys.stderr)
        return 1
    except OSError as e:
        print(f"forge: error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
