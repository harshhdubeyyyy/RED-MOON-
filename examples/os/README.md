# JalOS — a complete teaching OS in Jal Pari

One file, `jalos.fg` (~1300 lines), implementing every subsystem a
modern OS has, at the architecture level:

| Subsystem | What JalOS does |
|---|---|
| Bootloader + kernel + init | Banner, RAM test, rootfs mount, daemon startup, login |
| Process management | Fixed process table, spawn, kill, ps/top |
| Scheduler | Priority scheduling in one-step quanta, tick log |
| Memory management | First-fit free-list allocator over 1024 simulated words, split + coalesce, `malloc`/`free`/`mem` |
| Filesystem | Hierarchical VFS (inodes by index), mkdir/write/cat/cp/mv/rm/ls, `/proc` pseudo-filesystem |
| Permissions + users | root/guest, file owners, owner-or-root checks, `su`, `useradd`, `/etc/passwd` |
| Devices | Console, loopback network device, disk (the VFS) |
| Networking | `ping` (loopback, simulated), `ifconfig`, `httpget` (real HTTP through the host stack) |
| Package manager | `pkg list/search/info/install/remove` — install really fetches the package source over HTTPS from the repo |
| Services + logging | cron (heartbeat every 5 ticks), syslog (`/var/log/syslog`), `logger`, `services` |
| Shell | ~30 commands, script files, single-command mode, `history`, `env`, `uptime`, `df`, `shutdown`, `ai`, `audit` |

## Run it

```
python3 forge.py run examples/os/jalos.fg            # built-in demo tour
python3 forge.py run examples/os/jalos.fg script.txt # run a script file
python3 forge.py run examples/os/jalos.fg ps         # a single command
```

The demo tour is offline and deterministic, and it is wired into
`tests/run_tests.py` as an exact-output test.

## Honest limits

- **Not bootable.** Jal Pari has no pointers, inline assembly,
  interrupts, or freestanding mode, so this runs on top of a host
  OS. A bootable Jal Pari kernel would need a freestanding backend
  first — the big32 RISC-V CPU in this workspace is the plausible
  target for that someday, not today.
- **No GUI.** No graphics builtins exist, so the desktop is the
  text shell. A TUI window manager over ANSI escapes is possible
  later; it is not here.
- **No passwords worth trusting.** Passwords are compared as plain
  strings (no hashing builtin exists) — the user model demonstrates
  permissions, it does not secure anything real.
- **HTTPS needs direct internet.** `pkg install` and `httpget` over
  HTTPS fail behind HTTP proxies: the language's HTTP client does
  not speak proxy CONNECT yet, so a proxied sandbox breaks the TLS
  handshake. Plain HTTP works everywhere. Proxy support in the
  HTTP client is the next language feature this OS wants.
- **No persistence.** The VFS lives in memory; shutdown loses it.
  Saving the filesystem image to a host file is a planned step.
