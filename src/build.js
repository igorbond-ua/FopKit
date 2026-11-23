/**
 * build.js — builds jkurwa.bundle.js for browser use.
 * Run: npm run build  (from src/)
 * Output: ledger/static/ledger/jkurwa.bundle.js (~350 KB minified)
 */
const esbuild = require("esbuild");
const path = require("path");

esbuild
  .build({
    entryPoints: [path.join(__dirname, "static_src", "jkurwa_entry.js")],
    bundle: true,
    platform: "browser",
    format: "iife",
    globalName: "jkurwaLib",
    // node:crypto  → tiny shim (only .rng() is used, for random number generation)
    // node:fs      → empty stub (we never pass privPath in browser code)
    alias: {
      "node:crypto": path.join(__dirname, "static_src", "node_crypto_shim.js"),
      "fs": path.join(__dirname, "static_src", "fs_shim.js"),
    },
    outfile: path.join(
      __dirname,
      "ledger",
      "static",
      "ledger",
      "jkurwa.bundle.js"
    ),
    minify: true,
    logLevel: "info",
  })
  .catch(() => process.exit(1));
