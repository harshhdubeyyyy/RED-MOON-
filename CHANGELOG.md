# Changelog — The Jal Pari Language

All notable changes are listed here. Version numbers follow
semantic versioning in spirit: 0.x means the language is usable
but breaking changes are still possible.

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
