# Platforms — The Jal Pari Language

What runs where, what blocks the rest, and what would unblock it.
Verified 26 Oct 2026 on a Linux VM (x86_64, gcc, OpenSSL headers
present). Nothing here claims a binary that was not built.

## Linux (x86_64) — verified

The supported platform. `forge.py run/build` compiles generated C
with `cc` (`-std=gnu11 -pthread`, `-lm -lssl -lcrypto`, falling
back to `-lm` if the SSL libraries are missing). Install is
verified on a clean HOME and a clean pip venv (1.0.0).

## The C compiler is selectable: `JALPARI_CC`

`forge.py run`, `forge.py build`, and the shared-library build all
use `JALPARI_CC` when it is set, and `cc` otherwise. The default
is unchanged, so this is an addition, not a behavior change:

```
JALPARI_CC=/usr/bin/gcc python3 forge.py run examples/fib.fg
JALPARI_CC=x86_64-w64-mingw32-gcc-posix python3 forge.py build prog.fg -o prog.exe
```

Setting it to a cross compiler does NOT by itself produce a
working binary for another OS — the generated C (below) must
also compile for that OS. The override exists so the toolchain
choice is not hardcoded when that day comes.

## Windows (MinGW-w64) — NOT buildable yet, blockers verified

Attempted 26 Oct 2026: generated C for a fib program (no threads,
no HTTP in the program itself) cross-compiled with both MinGW
variants installed from apt (`gcc-mingw-w64-x86-64` 13.2.0,
`-posix` and `-win32`). Both fail identically at the first
header:

```
fibtest.c:7:10: fatal error: sys/socket.h: No such file or directory
```

Why: the codegen HEADER (forge_lang/codegen.py) unconditionally
emits POSIX socket headers (`sys/socket.h`, `netdb.h`,
`netinet/in.h`, `arpa/inet.h`), `unistd.h`, and OpenSSL headers
into EVERY program, because the HTTP/HTTPS helper functions are
part of the runtime. Stripping those includes from a scratch copy
shows the next layer of errors: `struct addrinfo`, `getaddrinfo`,
`AF_UNSPEC`, `SOCK_STREAM`, `SSL_CTX`, `SSL`, `X509_V_OK` — the
helpers use the POSIX socket API and OpenSSL throughout
(`socket/connect/send/recv/bind/close`, `SSL_connect/SSL_read/
SSL_write`), and `close()` on sockets.

What a Windows port needs, in order:

1. A `#ifdef _WIN32` branch in the generated runtime: winsock
   headers (`winsock2.h`, `ws2tcpip.h`) instead of the POSIX
   ones, `WSAStartup`/`WSACleanup`, `closesocket` instead of
   `close` on sockets, and link `-lws2_32`.
2. OpenSSL for MinGW (a mingw build of OpenSSL), or HTTPS made
   conditional so plain-HTTP and non-network programs build
   without it.
3. The `-posix` MinGW variant (it provides `pthread.h` via
   winpthreads; the `-win32` variant does not).

Until then, do not claim a Windows binary. The `JALPARI_CC`
override plus the mingw-posix compiler gets as far as the
socket headers and stops there — that is the verified state.

## macOS — NOT verified here, path documented

No macOS machine, SDK, or Apple clang is available in this VM,
and `zig` (the usual Linux-to-macOS cross toolchain) is not
installed, so no macOS binary was built or tested. By analysis:

- The POSIX headers in the generated C all exist on macOS
  (pthread, sockets, unistd), so the socket code is not the
  blocker it is on Windows.
- The blocker is OpenSSL: macOS ships no OpenSSL headers by
  default. A native macOS build needs Homebrew OpenSSL
  (`brew install openssl`, with its include/lib paths visible
  to the compiler), or the same conditional-HTTPS work as
  Windows item 2 above.
- A native build ON a Mac (Xcode command-line tools + Homebrew
  OpenSSL + `JALPARI_CC` if a specific clang is wanted) is the
  plausible first macOS binary. Cross-compiling macOS binaries
  from Linux needs an Apple SDK or zig, neither of which is
  present here.

## Notes for distributed binaries

- Fast mode uses `-march=native`: a binary built in fast mode
  may not run on a different CPU. Ship release binaries built
  in safe mode (or with an explicit portable `-march`), not
  fast mode.
- WASM and big32 backends do not use the C compiler at all, so
  they are unaffected by all of the above. The playground
  (Pyodide + WASM) is already OS-independent.
- The Python toolchain itself (`forge.py`, `pip install`) is
  platform-neutral; only the native C backend has OS-specific
  requirements.
