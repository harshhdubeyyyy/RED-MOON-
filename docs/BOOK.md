# The Jal Pari Language — A Small Book (Starter)

Dedicated to Tejaswini — Jal Pari. See DEDICATION.md.
Formerly Forge v2; commands are still `forge.py`, files are `.fg`.

New to programming? Read [HIGH_SCHOOL_GUIDE.md](HIGH_SCHOOL_GUIDE.md)
first — it is the same language, explained in simple school-level
words, with steps to run it and real-life uses.

## Chapter 1 — Hello, Jal Pari

```forge
fn main() -> int {
    println("The Jal Pari Language");
    println("For Teju, my Jal Pari");
    return 0;
}
```

Run it: `python3 forge.py run examples/jal_pari_demo.fg`
Every program needs `fn main() -> int` ending in `return 0;`.

## Chapter 2 — Types, and what the checker refuses

`int` (64-bit), `float`, `bool`, `str`, `[T]` arrays. No null.
No implicit conversion: `x as float` and `y as int` are explicit.
Immutable by default: use `let mut` only when a variable changes.
Conditions must be `bool` — no truthy ints.

Safe mode (default) checks integer arithmetic and array bounds
and aborts with a readable message. Fast mode is `-O3 -march=native`,
unchecked — use it only for code already validated in safe mode.

## Chapter 3 — Functions, structs, enums, generics

Structs are by value, all fields required. Enums match exhaustively.
Generics are monomorphised (`Option<int>` becomes `Option_int`).
`Option`/`Result` carry a dummy value for None/error, because
there is no null — see `stdlib/option.fg` and `stdlib/result.fg`.
The `?` operator propagates Option/Result errors.

## Chapter 4 — Training a tiny model, for real

`examples/ml_linear_regression.fg` trains by gradient descent.
`examples/ml_train_xor.fg` trains a 2-2-1 MLP by backprop:
loss 0.558973 -> 0.000267766, final XOR 0/1/1/0.
That is real training — small models only. No autograd, no
random init yet (see `stdlib/rand.fg` for a deterministic LCG),
no GPU trainer, no LLM-scale training. See the honest-limits
section at the end of this book and in README.md.

## Chapter 5 — A real app

`examples/apps/todo.fg` is a todo CLI: add/list/done, stored
in `todo.txt`. It needed a new builtin, `file_exists()`, because
`read_file()` aborts on a missing file — a real language gap,
found by building a real app, and fixed in the compiler.

## Chapter 6 — Other backends, honestly

- big32: Jal Pari on a RISC-V CPU, in simulation only, int/bool/str
  subset — floats and structs are rejected there, clearly.
- WASM: int/float/bool, no strings/arrays yet. Try the playground
  in `web/playground.html` — sum, fib, and float area run in browser.
- CUDA: dot/matmul kernels, verified on a Kaggle Tesla T4
  (dot 70, matmul 19 22 43 50). CUDA is kernels, not a trainer.

## Honest limits (do not skip this chapter)

Not a Rust/Go rival yet: no GUI, no web framework, no async
server, no large package ecosystem, no public registry host
(server + Dockerfile exist, hosting needs a VPS/Render/Fly account),
no debugger, no fuzzing yet, no self-hosting compiler yet.
CI workflow upload is a manual GitHub web-UI step (token scope).

Future chapters to write: packages and the registry, WASM
strings/arrays, big32 floats/structs, a CSV+SQL app, fuzzing
and the debugger, and the self-hosting compiler.
