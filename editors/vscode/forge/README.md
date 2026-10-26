# The Jal Pari Language for VS Code

Syntax highlighting for `.fg` files (this folder). Diagnostics
and completion from the Forge language server.

## Language server

Point your LSP client (for example `vscode-languageclient`, or any
editor that can launch a stdio LSP server) at:

```
python3 /path/to/forge-v2/forge.py lsp
```

The server publishes diagnostics from the real Forge checker on
`didOpen`/`didChange`, and completes keywords, builtins, and
function/struct names from the open document.

This extension folder is intentionally client-free: it ships the
grammar and language configuration, and the server is the Forge
compiler itself, so diagnostics can never drift from `forge check`.
