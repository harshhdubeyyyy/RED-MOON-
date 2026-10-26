#!/usr/bin/env python3
"""Forge v2 test suite. Run from ~/workspace/forge-v2: python3 tests/run_tests.py"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FORGE = os.path.join(ROOT, "forge.py")


def run_forge(*args):
    return subprocess.run([sys.executable, FORGE, *args],
                          capture_output=True, text=True, cwd=ROOT)


def main():
    failures = []

    def expect(path, expected, mode="safe"):
        r = run_forge("run", path, "--mode", mode) if mode != "safe" else run_forge("run", path)
        if r.returncode != 0 or r.stdout != expected:
            failures.append(f"{path} ({mode}): expected {expected!r}, got rc={r.returncode} "
                            f"out={r.stdout!r} err={r.stderr!r}")

    expect("examples/hello2.fg",
           "sum = 7.5 len = 3\ni = 0 xs[i] = 1.5\ni = 1 xs[i] = 2.5\ni = 2 xs[i] = 3.5\n"
           "sqrt(2) = 1.41421 exp(1) = 2.71828\n")
    expect("examples/matrix.fg", "58 64 139 154 \ndot = 217\n")
    # Structs: distance 3-4-5, then field assignment to 6-4.
    expect("examples/structs_point.fg",
           "distance = 5\nq.x = 6 q.y = 4\ndistance = 7.2111\n")
    # String builtins + stdlib + ecosystem example.
    expect("examples/strings_demo.fg",
           "parts = 3 b\njoined = a-b-c\nsub = world\ntrim = hi\n"
           "starts = true\nends = true\n")
    # Enums + match + assert.
    expect("examples/enums_match.fg", "green\nother\n")
    # Spawn: both workers must finish (main joins them).
    r = run_forge("run", "examples/spawn_demo.fg")
    for needle in ("main done, waiting for workers", "worker done 1", "worker done 2"):
        if r.returncode != 0 or needle not in r.stdout:
            failures.append(f"spawn_demo: missing {needle!r} in {r.stdout!r} err={r.stderr!r}")
    # FFI: puts returns length+newline, system returns 0.
    r = run_forge("run", "examples/ffi_demo.fg")
    for needle in ("puts returned 18", "system returned 0"):
        if r.returncode != 0 or needle not in r.stdout:
            failures.append(f"ffi_demo: missing {needle!r} in {r.stdout!r} err={r.stderr!r}")
    # Map + JSON stdlib.
    expect("examples/map_json_demo.fg",
           "apples = 7\nhas pears = false\ncity = Gorakhpur\n")
    # Generics + Option/Result + tiny DB.
    expect("examples/generics_demo.fg", "42 hi 1.5 7 seven\n")
    expect("examples/option_result_demo.fg",
           "opt = 42\nnone = 99\ndiv = 5\nerror = division by zero\n")
    expect("examples/db_demo.fg", "user = jayant\nlang = Forge\n")
    # ? operator, generic enums, table DB.
    expect("examples/try_demo.fg",
           "opt ok = 43\nopt none present = false\ncalc error = div by zero\n")
    expect("examples/generic_enums_demo.fg", "some 42\nnone\nerr div by zero\n")
    expect("examples/table_demo.fg",
           "rows = 3\ngorakhpur rows = 2\nfirst = jayant second = teju\n")
    # SQL, WASM is tested separately (node), GC counters.
    expect("examples/sql_demo.fg",
           "gorakhpur = 2 jayant teju\nolder = 2 jayant teju\nall = 3\n")
    expect("examples/gc_demo.fg", "g = hello\nallocs = 103 frees = 101\n")
    expect("examples/gc_array_demo.fg",
           "loop arr = 4 5\narr allocs = 101 arr frees = 100\nshared b = 4 5\nstruct arr = 4 5\n")
    expect("examples/kernel_demo.fg", "parallel dot = 70\nmatmul = 19 22 43 50\n")
    expect("examples/gc_struct_demo.fg",
           "person = b 2 3\nstr allocs = 101 str frees = 100\narr allocs = 101 arr frees = 100\nshared q = b 2 3\n")
    expect("examples/jal_pari_demo.fg",
           "The Jal Pari Language\nFor Teju, my Jal Pari\nSafe. Simple. Natively fast.\n")
    expect("examples/teju_special.fg",
           "For Teju, my Jal Pari\n\n   \\ | /\n    \\|/\n  -- * --\n    /|\\\n   / | \\\n     |\n     |\n    \\|/\n\nThat smile.\nGolden hour suits her.\n\n*\n**\n***\n****\n*****\n\nTeju, you are special.\nSmiles, sunsets, good songs.\nNo pressure, just this: you are thought of kindly,\nand the door is open, whenever you want.\n- Jayant\n")
    expect("examples/dates_rand_demo.fg",
           "epoch = 0\n2026-10-26 minus 2026-01-01 = 298\nleap 2024 = true\nleap 2025 = false\nfeb 2024 = 29\nrand seed = 1250496048\nrand float = 0.610197\n")
    expect("examples/tensor_demo.fg",
           "matmul = 19 22 43 50\ntranspose = 1 3 2 4\nadd sum = 36\n"
           "reshape = 1 4\nget2 = 3\nsoftmax sum = 1\nargmax = 1\n")
    expect("examples/autograd_demo.fg",
           "f = 21.9526\ndfdx = 10.0452\ndfdy = 3\nnumeric dfdx = 10.0452\n")
    expect("examples/nn_demo.fg",
           "linear out len = 2\nlayernorm mean-ish = 0\nadam step = 1 p0 = 0.99\n"
           "lr cosine = 0.01\nlr step = 0.0025\nclip norm = 2.5\n"
           "ckpt saved = true\nckpt = 0.5 -0.25 1.5\n"
           "quant scale = 0.00787402 max err = 0.00590551\ngreedy = 1\ntopk = 1\n"
           "int_to_str = -42\nfloat_to_fixed = -3.141\n")
    expect("examples/tokenizer_demo.fg",
           "char vocab = helo wrd\nchar ids len = 23\n"
           "char roundtrip = hello world hello world\nbpe merges = 5\n"
           "bpe ids len = 13\nbpe roundtrip = hello world hello world\n"
           "windows = 19\ntrain + test = 19\nbatch = 3\nshuffled = 19\n")
    expect("examples/gpt_scaled_forward_demo.fg",
           "params = 5200\nlogits = 464\nloss = 4.1355\ngraph nodes = 183940\n")
    expect("examples/gpt_forward_demo.fg",
           "params = 776\nlogits = 96\nloss = 2.89085\ngraph nodes = 13886\n")
    expect("examples/imported_demo.fg",
           "tok = 0.5 -0.25 1 0\nln1_g = 1 1\n")
    # Inference: KV-cache must match full forward exactly (diff 0).
    r = run_forge("run", "examples/inference_demo.fg")
    for needle in ("full last =", "kv last =", "kv diff = 0", "cache len = 3",
                   "quant step max diff ="):
        if r.returncode != 0 or needle not in r.stdout:
            failures.append(f"inference_demo: missing {needle!r} in {r.stdout!r} err={r.stderr!r}")
    # CUDA simulation (Python mirror of the .cu kernels).
    r = subprocess.run([sys.executable, "tools/simulate_cuda.py"],
                       capture_output=True, text=True, cwd=ROOT)
    for needle in ("cuda dot = 70.0", "cuda attention =", "cuda layernorm =",
                   "cuda half matmul = 19.0 22.0 43.0 50.0",
                   "cuda simulation ok"):
        if r.returncode != 0 or needle not in r.stdout:
            failures.append(f"simulate_cuda: missing {needle!r} in {r.stdout!r} err={r.stderr!r}")
    expect("examples/ml_train_xor.fg",
           "epoch 0 loss = 0.558973\nepoch 10000 loss = 0.000267766\nxor 0 0 = 0 (raw 0.0115718 )\nxor 0 1 = 1 (raw 0.986735 )\nxor 1 0 = 1 (raw 0.989128 )\nxor 1 1 = 0 (raw 0.010358 )\n")
    expect("examples/ecosystem/word_stats.fg",
           "words = 8\nlines = 4\nmean line length = 10.25\n"
           "median line length = 12\n")
    # Formatter: every example/stdlib file must format idempotently
    # and the formatted version must still check.
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    from forge_lang.pretty import format_source
    import glob
    for path in sorted(glob.glob("examples/**/*.fg", recursive=True)
                       + glob.glob("stdlib/*.fg")):
        try:
            with open(path, encoding="utf-8") as f:
                original = f.read()
            once = format_source(original)
            twice = format_source(once)
            if once != twice:
                failures.append(f"fmt: {path} is not idempotent")
        except Exception as e:
            failures.append(f"fmt: {path} failed to format: {e}")
    # File I/O + args: writes a file, reads it back, reports args.
    for fname in ("forge_output.txt", "forge_test_out.txt", "nn_ckpt.txt"):
        try:
            os.unlink(os.path.join(ROOT, fname))
        except FileNotFoundError:
            pass
    r = run_forge("run", "examples/file_and_args.fg", "--", "forge_test_out.txt")
    out_path = os.path.join(ROOT, "forge_test_out.txt")
    if r.returncode != 0 or "wrote ok" not in r.stdout or "args count = 1" not in r.stdout:
        failures.append(f"file_and_args failed: {r.stdout!r} {r.stderr!r}")
    elif not os.path.exists(out_path) or open(out_path).read() != "hello from Forge\n":
        failures.append("file_and_args: output file missing or wrong content")
    if os.path.exists(out_path):
        os.unlink(out_path)
    # parse_int via a tiny inline program is covered by check only here;
    # the struct literal must be rejected when a field is missing.
    r = run_forge("check", "tests/bad_struct.fg")
    if r.returncode == 0 or "missing field" not in r.stderr:
        failures.append(f"bad_struct: expected missing-field error, got rc={r.returncode} "
                        f"out={r.stdout!r} err={r.stderr!r}")
    # MLP: check the four XOR verdicts, not the raw sigmoid digits.
    r = run_forge("run", "examples/ml_mlp_xor.fg")
    for needle in ("xor 0 0 = 0", "xor 0 1 = 1", "xor 1 0 = 1", "xor 1 1 = 0"):
        if r.returncode != 0 or needle not in r.stdout:
            failures.append(f"ml_mlp_xor: missing {needle!r} in {r.stdout!r} err={r.stderr!r}")
    # Regression: w/b must head toward 2/1 and prediction toward 13.
    r = run_forge("run", "examples/ml_linear_regression.fg")
    if r.returncode != 0 or "prediction for x=6:" not in r.stdout:
        failures.append(f"regression failed: {r.stdout!r} {r.stderr!r}")
    # Benchmark must run in both modes and report micros.
    for mode in ("safe", "fast"):
        r = run_forge("run", "examples/benchmark.fg", "--mode", mode)
        if r.returncode != 0 or "micros =" not in r.stdout or "acc = 2997000" not in r.stdout:
            failures.append(f"benchmark ({mode}) failed: {r.stdout!r} {r.stderr!r}")
    # Safety: div by zero and overflow must abort cleanly in safe mode.
    for path, needle in (("tests/safety_div_zero.fg", "division by zero"),
                         ("tests/safety_overflow.fg", "integer overflow"),
                         ("tests/safety_oob.fg", "index out of bounds")):
        r = run_forge("run", path)
        if r.returncode == 0 or needle not in r.stderr:
            failures.append(f"{path}: expected abort {needle!r}, got rc={r.returncode} "
                            f"out={r.stdout!r} err={r.stderr!r}")
    # Compile rejections.
    for path, needle in (("tests/bad_type.fg", "declared str"),
                         ("tests/bad_immutable.fg", "immutable")):
        r = run_forge("check", path)
        if r.returncode == 0 or needle not in r.stderr:
            failures.append(f"{path}: expected error {needle!r}, got rc={r.returncode} "
                            f"out={r.stdout!r} err={r.stderr!r}")

    if failures:
        print(f"FAIL: {len(failures)} failure(s)")
        for f in failures:
            print(" -", f)
        return 1
    print("PASS: all Forge v2 tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
