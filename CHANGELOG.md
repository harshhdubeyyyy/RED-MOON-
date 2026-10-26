# Changelog — The Jal Pari Language

All notable changes are listed here. Version numbers follow
semantic versioning in spirit: 0.x means the language is usable
but breaking changes are still possible.

## 0.5.0 — 26 Oct 2026 — Engine batch: tape freeing, tensor autograd, KV-cache, scaled training

Fixed (compiler, the 0.4.0 leak):
- `forge_lang/codegen.py` now frees a block's variables
  when the block ends (`emit_free_frame`, applied to
  Block, If arms, While and For bodies). Before this,
  every array or struct created inside a loop body leaked
  once per iteration — measured on a tape loop: 1,000
  arrays allocated, 0 freed. After: 1,000 allocated,
  1,000 freed, and the scalar TinyStories program trains
  all 3 epochs in ONE process (previously OOM-killed
  twice). A subtlety found while fixing: Assign re-adds
  its target to the current frame even when declared
  outside it, so a frame frees only names absent from
  outer frames — otherwise the same value is freed twice
  (caught by a double-free in testing, fixed before ship).
- `examples/gpt_tinystories.fg` now trains 3 epochs in one
  process by default (resume still works). Single-process
  run 26 Oct 2026: train losses 4.98375, 4.49469, 4.41384;
  held-out loss 6.98368 -> 5.95341, perplexity 1078.88 ->
  385.06. Note: this differs from 0.4.0's 247.39 because
  the old split-process runs reset Adam's moments every
  epoch — an accidental regulariser. The new number is
  the methodologically cleaner one; both are recorded.

Added (tensor autograd):
- `stdlib/tensor_autograd.fg` — a tensor-level tape: one
  node per tensor op (matmul, add, bias, transpose,
  softmax, causal softmax, GELU, layernorm, mul, scale,
  gather, cross-entropy, ReLU, col-slice, concat-cols,
  reshape), with exact backward rules. Every rule is
  checked against central finite differences in
  `examples/tensor_autograd_demo.fg` (all diffs ~1e-9,
  and the demo fails itself if any diff exceeds 0.01).
- `stdlib/tgt.fg` — the gpt2 transformer rebuilt on
  tensor autograd (fused QKV, tied head, 12,608 params at
  the small size), plus tensor Adam and grad clipping.
- `examples/tgt_tinystories.fg` — same data and sizes as
  the scalar run: forward 100 nodes (scalar: 221,844),
  1500 steps in 6.5 s (4.35 ms/step), held-out loss
  6.30804 -> 5.64615, perplexity 548.97 -> 283.20.
  Sampled generation is still word salad; greedy still
  collapses (now on <unk>). Fluency is NOT claimed.

Added (KV-cache for gpt2):
- `stdlib/inference_gpt2.fg` — plain-float KV-cache step
  for any gpt2 layout (blocks, heads, separate Q/K/V).
  `examples/inference_gpt2_demo.fg` verifies it against
  full-sequence forward: max logit diff 4.44e-16
  (float rounding only). Generation past the trained
  sequence length clamps positions to seq-1 — a
  documented approximation, not a silent model change.

Added (scaled training):
- `tools/prepare_tinystories.py` gains `--out-dir`
  (default `data`); `data_scaled/` holds 500 stories,
  75,000 words, 1000-word vocab, UNK 8.5%.
- `examples/tgt_tinystories_scaled.fg` — 2 blocks,
  4 heads, d=32, hidden=64, seq=16 words, 49,664 params,
  1500 strided windows (stride 8) x 3 epochs: train
  5.45016, 4.94801, 4.86257; held-out (offset 60000)
  loss 7.02007 -> 5.24241, perplexity 1118.87 -> 189.13;
  117.6 s total, 26.1 ms/step, forward 136 nodes.
  Sampled output is still salad order, with more
  plausible fragments than at the small size.

Added (ecosystem, all verified by running):
- `docs/BENCHMARKS.md` — dot(5000): Jal Pari 8 µs,
  NumPy 29 µs, Python loops 788 µs; matmul 64x64:
  Jal Pari 615 µs, NumPy 343 µs (BLAS wins, stated
  plainly), Python 476,501 µs.
- `web/landing/index.html` — static landing page with
  the verified numbers and honest limits.
- `setup.py` + `pyproject.toml` + `bin/jalpari-pip` —
  `pip install .` verified in a clean venv
  (`jalpari-pip --version`, demo runs from another cwd).
  PyPI publication still needs the maintainer's account.
- `docs/DEBUGGING.md` — gdb-on-emitted-C recipe,
  allocation counters, and the missing piece (see below).
- `examples/cuda/mlp_train.cu` — GPU SGD trainer for
  XOR using only the verified square-matmul wrapper.
  CODE ONLY, never compiled or run (no nvcc/GPU here);
  needs a Kaggle session with Jayant's token.
- `examples/cuda/kernel.cu` comment corrected: the
  transformer kernels WERE verified on Kaggle T4 in
  0.3.0 (the old "not yet run" comment was stale).

Still NOT done (stated, not implied):
- Fluent generation; GPU training run (code exists,
  run needs a Kaggle token); WASM strings/arrays (the
  backend is 259 lines with no linear memory at all —
  needs memory + a bump allocator + string/array ops,
  a backend rewrite, not a patch); big32 floats/structs
  (the core is integer-only, no FPU — a core extension);
  a source-level debugger (AST nodes carry line but not
  file, so `#line` mapping would misattribute stdlib
  code — needs file tracking through the parser);
  self-hosting compiler; public registry host, CI upload
  and repo rename (maintainer's clicks/accounts);
  PyPI publication; Mojo/PyTorch benchmark numbers
  (neither installed here).

## 0.4.0 — 26 Oct 2026 — TinyStories word GPT

Added:
- `tools/prepare_tinystories.py` — downloads the first 200
  stories of roneneldan/TinyStories (train split) via the HF
  datasets-server rows API, cleans them (lowercase, apostrophes
  removed, other non-letters become spaces), and writes
  `data/tinystories_vocab.txt` (500 words + <unk>), `data/`
  `tinystories_ids.txt` (24,000 word ids) and a provenance
  README. UNK rate in the kept words: 14.8% (28.5% at 200
  words — the reason vocab went to 500).
- `examples/gpt_tinystories.fg` — word-level GPT on that data,
  reusing stdlib/gpt2.fg: 2 blocks, 2 heads, d=16, hidden=32,
  seq=8 words, 500-word vocab, 12,608 params. Adam lr 0.02,
  clip 1.0, 500 strided windows (stride 4, first ~2000 words)
  x 3 epochs. Held-out test (20 windows from word offset
  20000, later stories never trained on): loss 6.98368 ->
  5.51097, perplexity 1078.88 -> 247.39 (a real 4.4x
  generalisation gain, not a training-set fit). Epoch
  training losses: 4.98375, 4.64674 (the third epoch's
  average was lost when its process was OOM-killed during
  the eval phase — see below — but its checkpoint is the
  one evaluated here).
- `examples/gpt_tinystories_eval.fg` — eval-only companion:
  loads the checkpoint and reports test loss + generation
  in its own process.
- `examples/tinystories_load_demo.fg` — suite check that the
  data files load and parse (words = 24000, vocab = 500).

Generation (from "once upon a time there was a little",
30 words): greedy still loops ("cake cake cake ...");
sampled (temp 0.8, seed 123) gives real TinyStories words
in salad order ("some needed smiled kept lot herself toys
lot careful feel idea ..."). Honest verdict: upgraded from
letter salad to word salad — the perplexity gain is the
solid result; fluent sentences are NOT claimed.

Found by running (the important limitation of this batch):
- The native backend retains each training tape's arrays,
  so one process running 1500 steps x ~221k nodes grows
  until the VM's OOM killer ends it (killed during epoch
  1 of the original single-process run, and again during
  the eval phase of the 3-epoch run). Training is therefore
  split into one-epoch processes with checkpoint resume
  (`forge run examples/gpt_tinystories.fg`,
  `... resume`, `... resume final`), and eval runs as its
  own process. Tape-memory freeing is the open compiler
  fix for 0.5.0, alongside tensor-level autograd.

Not yet done: fluent generation (needs far more data,
params and steps — OpenMythos 44M on the same dataset took
4,850 steps to reach fluent samples), GPU training loop,
tensor-level autograd, KV-cache for the gpt2 layout, public
registry host, CI upload, repo rename.

## 0.3.0 — 26 Oct 2026 — Scaled GPT + GPU-verified kernels

Added:
- `stdlib/gpt2.fg` — generalised transformer: any blocks, any
  head count, any vocab/seq/hidden sizes, with a computed param
  layout (no hard-coded offsets from gpt.fg)
- `examples/gpt_scaled.fg` — 2 blocks, 2 heads, d=16, hidden=32,
  seq=16, 29-char vocab, 5200 params, on a 411-char story:
  training loss 2.559 -> 2.364 over 3 epochs (200 windows each),
  held-out perplexity 58.1 -> 53.9 (test windows 320..327).
  Generation still loops (greedy) / rambles (sampled) — scale
  is in architecture and evaluation now, not in fluent text.
  Checkpoint save/load verified (diff ~8e-07, 6-decimal text).
- GPU kernels VERIFIED on real hardware: Kaggle notebook v4,
  2x Tesla T4, driver 580.178.04, nvcc 12.8.93 — dot 70, matmul
  19 22 43 50, embedding 1 0 0 1 1 0, layernorm ±0.999980,
  attention 1.0/0.0, 0.330238/0.669762, 0.802224/0.197776,
  half matmul 19 22 43 50 — matching simulation to 6 decimals.

Fixed in this batch (both found by running, not by reading):
- Training diverged to NaN at the larger scale: a softmax
  probability can underflow to exactly 0, and log(0) poisons
  the tape. g2_loss now adds 1e-9 before the log.
- The fp16 kernel did not compile on the first GPU run:
  `__half2double` does not exist in CUDA; fixed to
  `(double)__half2float(...)`. Notebook v3 failed to build;
  v4 is the verified run.

Not yet done: fluent generation (needs far more data and
params than 5200 on 411 chars), GPU training loop (kernels
only so far), multi-layer library packaging, public registry
host, CI upload, repo rename.

## 0.2.0 — 26 Oct 2026 — Mojo-level ML stack (tensors, autograd, tiny GPT)

The language gains the pieces that make people use a language for
LLM work, at small-model scale. Everything below is verified by
the test suite or by a recorded run; the limits are listed, not
hidden.

Added:
- `stdlib/tensor.fg` — Tensor (flat row-major + shape), matmul,
  transpose, reshape, softmax, GELU, argmax (demo: 19 22 43 50)
- `stdlib/autograd.fg` — real reverse-mode scalar tape; gradient
  matches a numeric gradient exactly at printed precision
  (df/dx 10.0452 vs numeric 10.0452), plus a sqrt node so
  LayerNorm backward is exact
- `stdlib/nn.fg` — Linear, LayerNorm, single-head causal
  attention, MLP, Adam/AdamW, cosine/step/warmup schedules,
  gradient clipping, checkpoints (float text, 6 decimals),
  int8 quantization, greedy/temperature/top-k/top-p sampling,
  and a new `parse_float` builtin (needed for checkpoint loads)
- `stdlib/tokenizer.fg` — character tokenizer + real BPE
  (23 chars -> 13 tokens on the demo text, round-trips)
- `stdlib/dataset.fg` — sliding-window next-token sequences,
  train/test split, batching, shuffling
- `stdlib/gpt.fg` + `examples/tiny_gpt.fg` — a 1-block, 1-head
  transformer (d=8, hidden=16, tied head, 776 params) trained by
  autograd + Adam on "hello world hello jal pari": loss
  2.274 -> 0.360 over 20 epochs (min 0.199 at epoch 16), in ~5 s.
  Generation is the honest weak point: greedy loops on spaces,
  temperature sampling gives varied gibberish — a 776-param model
  on one sentence is a training proof, not a language model.
- `stdlib/inference.fg` — KV-cache inference step: step-by-step
  output matches a full-sequence forward exactly (diff 0);
  quantized step differs by at most 0.026 on the demo step
- `tools/import_torch_weights.py` — imports weights from a text
  file or (with torch installed elsewhere) a .pt state dict into
  Jal Pari functions; text path verified end to end
- CUDA: fused attention, LayerNorm, embedding and fp16 matmul
  kernels added to `examples/cuda/kernel.cu`, verified by
  `tools/simulate_cuda.py` (attention 1.0/0.0, 0.330/0.670, ...)

Not yet done, and not claimed:
- The new CUDA kernels have NOT run on a real GPU yet (no nvcc
  here; a Kaggle T4 run is the remaining step, as before)
- No torch in this VM, so the .pt branch of the importer is
  provided but not run here; the text branch is verified
- No 1B model, no distributed training, no MLIR compiler — the
  beachhead is small models that train and run natively

## 0.1.0 — 26 Oct 2026 — First Jal Pari market release

Formerly Forge v2. The language itself is unchanged in this
release; this release is about making it installable and usable
by a stranger.

Added:
- `jalpari` command (`bin/jalpari`) — `jalpari run`, `jalpari --version`
- `jalpari --version` / `jalpari version` — prints "The Jal Pari Language 0.1.0"
- `scripts/install.sh` — one-command user install, checks python3
  and cc, symlinks into `~/.local/bin`, verifies with the demo
- This changelog

Included from Forge v2 (all verified by tests, see README.md):
- Types int/float/bool/str/[T], structs, enums + match, generics,
  Option/Result, `?` operator, threads, C FFI, HTTP/HTTPS, file I/O
- Safe mode (checked arithmetic, bounds-checked) and fast mode
- ML: dot/matmul, linear regression training, MLP XOR training
  by backprop (loss 0.558973 -> 0.000267766)
- Backends: native C, big32 RISC-V (simulation), WASM (int/float/bool),
  CUDA kernels (verified on Kaggle Tesla T4, dot 70, matmul 19 22 43 50)
- Tooling: `forge pkg`, `forge fmt`, `forge lsp`, `forge repl`, `forge doc`
- Examples: hello, matrix, todo CLI, Teju special, dates/rand,
  SQL/table/KV demos, high-school guide, web playground, book starter
- Dedicated to Tejaswini — Jal Pari (see DEDICATION.md)

Known limits in 0.1.0 (honest, not hidden):
- No public package registry host yet (server + Dockerfile exist)
- WASM: no strings/arrays yet; big32: no floats/structs yet
- No debugger, no fuzzing, no self-hosting compiler yet
- CI workflow is local only until uploaded via GitHub web UI
  (token lacks workflow scope)
- Repo is still called RED-MOON- on GitHub; renaming it is a
  web-UI step, and the tool file is still `forge.py` for
  compatibility — `jalpari` is the new market name for it.
