// Run a Forge-compiled .wasm file with node and print main()'s result.
// Usage: node tools/run_wasm.mjs out.wasm [function-name]
// Default function: main. i64 results print as decimal strings.
import { readFileSync } from "node:fs";

const path = process.argv[2];
const fnName = process.argv[3] || "main";
if (!path) {
  console.error("usage: node tools/run_wasm.mjs out.wasm [function-name]");
  process.exit(1);
}
const bytes = readFileSync(path);
const { instance } = await WebAssembly.instantiate(bytes, {});
const fn = instance.exports[fnName];
if (typeof fn !== "function") {
  console.error(`no exported function '${fnName}'`);
  process.exit(1);
}
const result = fn();
console.log(typeof result === "bigint" ? result.toString() : result);
