# Forge ecosystem

This is the complete tooling around the Forge language, in one
place. Everything below is implemented in this repo, not planned.

## Compiler

```
python3 forge.py check <file.fg> [--mode safe|fast]
python3 forge.py build <file.fg> [-o out] [--mode safe|fast]
python3 forge.py run   <file.fg> [--mode safe|fast] [-- args...]
python3 forge.py emit  <file.fg>
python3 forge.py test
```

Safe mode (default) checks integer arithmetic and array bounds;
fast mode is `-O3 -march=native`, unchecked, for hot code you have
already validated in safe mode.

## Package manager — `forge pkg`

```
forge pkg init [name]     # forge.toml + src/main.fg + tests/ + README
forge pkg add <path>      # vendor another package into vendor/<name>/
forge pkg build           # src/main.fg -> build/<name>
forge pkg run [-- args]   # build, then run
forge pkg test            # every tests/*.fg must exit 0
forge pkg list            # name, version, dependencies
```

Dependencies are vendored (copied), not downloaded, so builds
never need a network or a registry. Import a vendored file with
a path from the package root: `import "vendor/stats/stats.fg";`.

See `examples/ecosystem/word_stats.fg` for a package-style program
that uses the stdlib, file I/O, and CLI args together.

## Formatter — `forge fmt`

```
forge fmt <file.fg>          # rewrite in canonical style, in place
forge fmt <file.fg> --check  # exit 1 if the file would change
```

The formatter parses the file and re-emits it (4-space indent,
`else if` chains kept as chains, right-operand parentheses kept
where they matter for integer division and float rounding). It is
idempotent: formatting formatted code gives the same text.

## Language server — `forge lsp`

```
python3 forge.py lsp
```

A stdio LSP server: `initialize`, full-sync `didOpen`/`didChange`
diagnostics from the real Forge checker, completion for keywords,
builtins, and function/struct names in the open document,
`shutdown`/`exit`. The VS Code grammar and language configuration
are in `editors/vscode/forge/`; point any LSP client at the command
above for diagnostics that can never drift from `forge check`.

## REPL — `forge repl`

```
python3 forge.py repl
forge> 1 + 2
3
forge> let x: int = 40;
forge> x + 2
42
```

`let` definitions are kept and reused; a definition that fails
to check is not kept. Commands: `:help`, `:defs`, `:reset`, `:quit`.

## Standard library

- `stdlib/ml.fg` — dot, mean, relu, sigmoid, matmul
- `stdlib/strings.fg` — repeat_str, word_count, csv_fields,
  lines_of, is_blank (on top of the split/join/substr/trim builtins)
- `stdlib/stats.fg` — sum_float, min_float, max_float, variance,
  stddev, median (median sorts a copy, never the caller's array)

Builtins: print/println, push, fail, len, range, clock_micros,
sqrt/exp/log/pow/abs, read_file/write_file, args, parse_int,
split/join/substr/trim/starts_with/ends_with.

## CI

`.github/workflows/ci.yml` runs `forge test`, a formatter check
over examples and stdlib, and the ecosystem example on every push
and pull request.

## New in the "build everything" pass (26 Oct 2026)

- **Enums + match:** `enum Color { Red, Green, Blue }`, exhaustive
  `match` with a trailing `_` wildcard arm.
- **Concurrency:** `spawn worker(1);` — threads (pthreads) for
  void functions taking 0 or 1 int argument; main joins them at
  the end (and before any return from main).
- **C FFI:** `extern fn puts(s: str) -> int;` — call real C
  functions; str is `const char *`, int is C `int` in the
  declaration, so standard-library functions work.
- **HTTP:** `http_get(url) -> str` — HTTP only, no TLS yet; the
  body is returned, headers are stripped. Tested against a local
  HTTP server.
- **Collections + JSON:** `stdlib/map.fg` (str->int map, put
  returns the updated map) and `stdlib/json.fg` (flat string
  objects only, documented as such).
- **Tests:** `assert(condition, "message")` as a statement builtin.
- **Docs:** `forge doc <file.fg>` — Markdown from // comments
  above structs, enums, and functions.
- **Lockfile:** `forge pkg lock` writes `forge.lock` with sha256
  of every vendored file; `forge pkg verify` detects changes
  (tested: tampering a vendored file is reported as MISMATCH).

## New in the "do it then" pass (26 Oct 2026)

- **Generics:** `fn identity<T>(x: T) -> T`, `struct Option<T>`,
  `struct Result<T, E>`, `struct Pair<T, U>` — monomorphised
  (each concrete use gets its own C function/struct, no runtime
  cost). Generic functions are inferred from call arguments;
  generic structs are inferred from literal fields. Limitations:
  no generic enums yet, no `?` sugar (check `.ok`/`.present`
  explicitly), a generic function cannot be called with an
  abstract type from another generic function, and arrays of
  generic structs are not supported.
- **Option/Result stdlib:** `stdlib/option.fg` (`opt_some`,
  `opt_value_or`; none is a literal with a dummy value, because
  Forge has no null) and `stdlib/result.fg` (`result_value_or`).
- **TLS:** `http_get` now handles `https://` too, with
  certificate verification on (OpenSSL, SNI, default verify
  paths). Tested against a local TLS server with a private CA
  (via `SSL_CERT_FILE`): body "hello https world". A real bug
  found in testing: the HTTP/HTTPS helpers only tried the first
  addrinfo result, so `localhost` (which resolves to ::1 first)
  failed against an IPv4-only server — both helpers now loop
  over all addrinfo results. Linking falls back without `-lssl`
  if the machine lacks libssl (programs that never call
  `http_get` still build).
- **Local registry:** `forge pkg publish` copies a package into
  `$FORGE_REGISTRY` (default `~/.forge_registry`) as
  `<name>/<version>/`, and `forge pkg add name@version` vendors
  it. Tested end to end (quad 7 = 28). This is a local registry,
  not a hosted server.
- **Tiny DB stdlib:** `stdlib/db.fg` — a tab-separated text
  key-value store (str -> str) with serialise/parse, to pair
  with `write_file`/`read_file`. NOT SQL, NOT SQLite, and values
  must not contain tabs/newlines (no escaping yet).
- **big32 backend (landed in the workspace 26 Oct 11:53, verified
  here):** `forge emit-big32` / `forge build --target big32`
  generate RV32IMAC assembly for the big32 v7 CPU (see
  `forge_lang/codegen_rv.py`, `examples/big32/`). Emit and
  assemble to .hex verified (sum.fg -> .hex); the Verilog
  simulation test needs `iverilog`, which is not installed in
  this VM, so it could not be run here.

## New in the "keep going" pass (26 Oct 2026)

- **`?` operator:** `let v: int = get_opt(ok)?;` unwraps an
  Option/Result, or returns early from the current function
  with the None/error value. Works when the function's return
  type is the same Option/Result type, or a Result/Option with
  the same error type and a scalar value type. Tested:
  `opt ok = 43`, `opt none present = false`,
  `calc error = div by zero` (the second divide fails, and the
  error propagates without an explicit if).
- **Generic enums with payloads:** `enum OptionE<T> { Some(T), None }`,
  `enum ResultE<T, E> { Ok(T), Err(E) }`, matched with bindings
  (`Some(v) => { ... }`). Payload enums compile to a C struct
  with a tag and a union, one struct per concrete type.
  No-payload variants of a generic enum are written `None()`
  and get their type from the annotation/return/argument type;
  a variant with no type context is a clear error, not a
  guess. Old non-payload enums (`enum Color { Red, ... }`)
  still work unchanged, and a no-payload variant of a
  non-generic payload enum can be written bare.
  Limitation: a variant takes at most one payload in v1.
- **Table DB stdlib:** `stdlib/table.fg` — a tiny relational
  table (flattened rows, insert/select by column value).
  NOT SQL (no SQL parser yet), and not SQLite.
  Tested: 3 rows, select city=Gorakhpur -> 2 rows,
  first=jayant, second=teju.

## New in the "then do it" pass (26 Oct 2026)

- **SQL parser:** `stdlib/sql.fg` — `sql_query(table, query)`
  with `SELECT name, city FROM t WHERE city = 'Gorakhpur'`,
  `SELECT * FROM t`, and numeric `WHERE age > '20'`.
  Tested: Gorakhpur = 2 (jayant, teju), older = 2, all = 3.
  A real bug found in testing: the parser forgot the table
  name token after FROM, so WHERE was ignored until the
  indices were fixed. NOT full SQL: no JOIN, ORDER BY,
  INSERT/UPDATE, and string `<`/`>` need integer values
  (Forge has no char codes for string ordering).
- **Hosted registry:** `forge_lang/registry_server.py` — a
  simple HTTP server (`forge pkg serve --dir D --port P`,
  no auth, run it on your own machine/trusted network) plus
  `forge pkg publish-remote <url>` and
  `forge pkg add-remote <url> name@version`.
  Tested end to end on localhost: publish hostlib, add-remote
  into another package, septuple 6 = 42.
- **WASM backend:** `forge_lang/codegen_wasm.py` —
  `forge emit-wasm` / `forge build --target wasm` write a
  real .wasm binary directly (no clang/wasm-ld needed),
  run with node (`tools/run_wasm.mjs out.wasm`).
  Subset v1: int (i64), bool (i32), void, functions,
  let/assign, if/else, while, return, calls, recursion.
  Tested: sum 1..10 = 55, fib(10) = 55, both via node.
  Two real bugs found in testing: the i64 comparison opcode
  table was off by one (gt/le/ge were actually gt_u/le_u/ge_u
  neighbours) and integer neg was written as div_u — both
  fixed, and WASM arithmetic wraps (like big32, unlike Forge
  safe mode). NOT supported in v1: float, str, arrays,
  structs, enums, match, spawn, print, file I/O.
- **GC v1 for strings:** copy-on-call for string parameters
  (so a callee owns its parameter), free-on-reassign for
  owned string locals, free-on-return for owned string
  locals, with scope tracking so a return never frees an
  out-of-scope variable, and `alloc_count()`/`free_count()`
  counters. Tested: a 100-iteration reassign loop gives
  allocs = 103, frees = 101, leaving exactly 2 live strings
  (the current value and the greeting) — without this, all
  103 would leak. A real bug found in testing: Assign freed
  the old string before evaluating the new one, so
  `out = out + x` read freed memory — Assign now evaluates
  into a temp first. NOT a full GC yet: arrays, struct
  fields, and array elements are still never freed, and
  string temporaries from concat/helpers are counted only
  through the copy path.

## New in the "do it that also" pass (26 Oct 2026)

- **Parallel kernels:** `parallel_dot(a, b)` and
  `parallel_matmul(a, b, n)` — GPU-style kernels (work split
  into blocks, one pthread per block) that run on CPU threads
  here, because this VM has no GPU, no CUDA, and no OpenCL.
  Verified: dot = 70, matmul = 19 22 43 50, exactly matching
  the serial results. No speedup is claimed on this 2-core
  VM; the kernel shape and correctness are the deliverable,
  and a real GPU backend still needs GPU hardware.
- **Python interop:** `forge build --shared lib.fg -o lib.so`
  compiles a Forge library with no main required, and
  `tools/forge_py.py` calls it from Python via ctypes
  (int/bool/float/str). Verified: add(40, 2) = 42,
  is_even(42) = True, greet("Jayant") = "hello Jayant".
  A real bug found: Forge frees string parameters on return,
  but ctypes passed a Python-owned buffer — the helper now
  mallocs string arguments so Forge can safely free them.
  Arrays/structs are not passed through this helper in v1.
- **Public registry discovery:** `forge pkg list-remote <url>`
  lists every package and version on a registry, so a
  registry you run is discoverable, not just add-by-name.
  Verified: published hostlib@0.1.0, list-remote showed
  "hostlib 0.1.0". This is still a self-hosted server,
  not a centrally hosted service — "public" means anyone
  with your URL can discover and pull from it.
- **GC v2 for arrays:** array structs now carry a refcount
  pointer. Assignment shares, function calls gain a
  reference, struct fields gain a reference, and an array
  is freed only when its last owner goes away. Verified:
  a 100-iteration reassign loop gives arr allocs = 101,
  arr frees = 100 (1 live); a shared array survives its
  original variable's reassign (b = 4 5 after a = [9]);
  a struct-held array survives too (s.arr = 4 5 after
  b = [7]). Two real bugs found: array helpers were
  declared before forge_fail/forge_free_str, so forward
  declarations were added. NOT yet freed: struct variables
  themselves (their fields leak, as before, but they hold
  a reference so shared arrays are never freed under them),
  and array elements inside structs are not counted
  separately. Full suite still passes.

## New in the "do it then" pass (26 Oct 2026)

- **Struct GC:** struct variables now own their fields —
  str fields are deep-copied, array fields gain a reference,
  nested structs recurse — on Let, Assign, Call arguments,
  and Return, and are freed on reassign/return. Verified:
  a 100-iteration struct reassign loop gives str allocs =
  101, str frees = 100, arr allocs = 101, arr frees = 100;
  a shared struct survives its original's reassign
  (q = b 2 3 after p = c). Full suite still passes.
- **Python arrays/structs:** `tools/forge_py.py` now passes
  [int] arrays (as a C struct with malloc'd data/ref, which
  Forge frees on return) and simple structs (ctypes Structure,
  same field layout) to Forge shared libraries. Verified:
  sum_arr([1,2,3,4]) = 10, double_arr([1,2,3]) = [2,4,6],
  point_sum(Point(10,32)) = 42, make_point(3,4) = (3,4).
  Str fields in structs must be malloc'd, as for plain str
  arguments, because Forge frees them on return.
- **CUDA codegen:** `forge emit-cuda` emits a .cu file with
  __global__ dot and matmul kernels, grid/block launches,
  and host code. Verified structurally (kernel signatures,
  <<<grid, block>>> launches, cudaMalloc calls) — NOT run,
  because this VM has no GPU and no nvcc. To run it, copy
  the .cu file to a CUDA GPU machine and compile with nvcc.
- **Centrally hosted static registry:** `tools/make_static_registry.py`
  converts a local registry into a static dir (packages.json
  + packages/<name>/<version>/<file>.fg) that can be pushed
  to GitHub and served by Pages, and `forge pkg list-static`
  / `add-static <base_url>` discover and pull from it with
  no server code running. Verified end to end via a local
  HTTP server simulating Pages: static registry listed
  "hostlib 0.1.0", add-static vendored it into
  vendor/hostlib/. This is centrally hosted by GitHub
  Pages, but read-only for clients — publishing is via git
  push, not via POST, unlike the dynamic server above.

## New in the "finish the remaining 3" pass (26 Oct 2026)

- **Python [float]/[str] arrays + nested structs:** done.
  Verified: sum_float([1.5,2.5,3.0]) = 7.0,
  double_float([1.0,2.5]) = [2.0,5.0],
  join_str(["jayant","teju"]) = "jayant,teju",
  str-array round-trip = ["a","b"],
  outer_sum(Outer{Inner(10,32)}) = 42,
  make_outer(3,4,"hello") = (3,4,"hello").
  Str-array elements are malloc'd in Python and freed by
  Forge on return, exactly like plain str arguments.
- **CUDA execution:** VERIFIED ON A REAL GPU 26 Oct 2026.
  Kaggle GPU notebook `arshhdubeyy/forge-cuda-kernel` v2,
  2x Tesla T4 (15360 MiB each), driver 580.178.04, nvcc 12.8:
  cuda dot = 70.000000, cuda matmul = 19 22 43 50 — exactly
  matching the CPU-thread kernels, the serial code, and the
  `tools/simulate_cuda.py` simulation. The Kaggle token used
  for this run was supplied transiently for this session
  only and was not stored. This VM itself still has no GPU
  or nvcc, so the .cu file cannot run here — the verified
  run happened on Kaggle, and `examples/cuda/` now records
  it with the GPU, driver, and nvcc versions above.
- **Dynamic centrally hosted registry:** the server is now
  production-shaped — POST publishing with an optional Bearer
  token, immutable versions (re-publishing the same version
  returns 409), and a Dockerfile + deploy README in
  `registry/`. Verified end to end: publish without token
  -> 401, publish with token -> ok, re-publish -> 409,
  list-remote -> "hostlib 0.1.0", add-remote -> vendored.
  What is still not provided: a host. Central hosting means
  running that server on a VPS/Render/Fly host you control
  and sharing its URL — this repo gives the server and the
  deploy files, not the host itself.

## What is still not in the ecosystem

No CUDA execution on real GPU hardware (needs a GPU machine
or a GPU token you supply), no Python interop for generic
arrays/structs beyond the types above, and no registry
actually running on a public host (the server above is
ready to deploy, but no host is provisioned here). Those
are the next phases, in that order.
