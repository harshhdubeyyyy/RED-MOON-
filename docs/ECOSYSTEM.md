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

## What is still not in the ecosystem

No registry (packages are vendored by path), no HTTP/TLS or
database stdlib, no generics/`Option`/`Result`, no concurrency,
no GPU kernels, and no package lockfile yet — the package manager
records dependencies in `forge.toml`, but does not yet pin exact
versions. Those are the next phases, in that order.
