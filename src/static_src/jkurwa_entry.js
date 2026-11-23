/**
 * jkurwa_entry.js — entry point bundled by build.js → jkurwa.bundle.js
 *
 * Assigns window.jkurwaLib = { jk, algo } directly instead of relying on
 * esbuild globalName re-export mechanism (which breaks with named re-exports).
 */
import { Buffer } from "buffer";

// Patch Buffer onto Uint8Array prototype so that any Uint8Array created by
// asn1.js or jkurwa internals gets Buffer methods (readUInt32BE etc).
// This is needed because the buffer polyfill subclasses Uint8Array but code
// may receive plain Uint8Arrays and call Buffer methods on them.
if (typeof globalThis.Buffer === "undefined" || globalThis.Buffer !== Buffer) {
  globalThis.Buffer = Buffer;
}
// Patch missing Buffer methods onto plain Uint8Array instances created before
// or outside the Buffer class (belt-and-braces for readUInt32BE etc).
const _proto = Uint8Array.prototype;
const _bproto = Buffer.prototype;
const _methods = [
  "readUInt8","readUInt16BE","readUInt16LE","readUInt32BE","readUInt32LE",
  "readInt8","readInt16BE","readInt16LE","readInt32BE","readInt32LE",
  "writeUInt8","writeUInt16BE","writeUInt16LE","writeUInt32BE","writeUInt32LE",
  "writeInt8","writeInt16BE","writeInt16LE","writeInt32BE","writeInt32LE",
  "slice","copy","fill","equals","compare","toString","toJSON",
  "readDoubleBE","readDoubleLE","readFloatBE","readFloatLE",
];
for (const m of _methods) {
  if (_bproto[m] && !_proto[m]) {
    _proto[m] = _bproto[m];
  }
}

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

// Assign directly — don't rely on esbuild globalName for named re-exports.
window.jkurwaLib = { jk, algo };
