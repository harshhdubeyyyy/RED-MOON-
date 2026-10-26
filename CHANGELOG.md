# Changelog — The Jal Pari Language

All notable changes are listed here. Version numbers follow
semantic versioning in spirit: 0.x means the language is usable
but breaking changes are still possible.

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
