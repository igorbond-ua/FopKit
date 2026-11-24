/**
 * jkurwa_entry.js — entry point bundled by build.js → jkurwa.bundle.js
 *
 * Assigns window.jkurwaLib = { jk, algo } directly instead of relying on
 * esbuild globalName re-export mechanism (which breaks with named re-exports).
 */
import { Buffer } from "buffer";

globalThis.Buffer = Buffer;

import * as jk from "jkurwa";
import gost89 from "gost89";
import dstu7564 from "dstu7564";

const gostHash = gost89.compat.algos().hash;

function kupynaHash(data) {
  return dstu7564.computeHash(32, data);
}

const algo = {
  hash: gostHash,
  hashes: {
    Gost34311: gostHash,
    Dstu4145le: gostHash,
    Dstu4145leWithDstu7564: kupynaHash,
    Dstu7564: kupynaHash,
    "Dstu7564-256": kupynaHash,
  },
};

// Use globalThis so the bundle works in both window and Web Worker contexts.
globalThis.jkurwaLib = { jk, algo };
