/**
 * jkurwa_entry.js — entry point bundled by build.js → jkurwa.bundle.js
 *
 * Bundles together:
 *   - jkurwa    — ДСТУ 4145-2002 crypto (EC signing, CAdES-BES construction)
 *   - gost89    — GOST 34.311-95 hash (used by pre-2019 CA certificates)
 *   - dstu7564  — ДСТУ 7564 Kupyna-256 hash (used by post-2019 CA certificates)
 *
 * Both hash families are registered so the Box auto-picks the right one based
 * on the signer certificate OID.
 *
 * Exposed as: window.jkurwaLib  (IIFE global via esbuild globalName)
 *   .jk    — the full jkurwa module (Box, Certificate, Priv, …)
 *   .algo  — pre-built algo object for Box({ algo })
 */
import * as jk from "jkurwa";
import gost89 from "gost89";
import dstu7564 from "dstu7564";

const gostHash = gost89.compat.algos().hash;

function kupynaHash(data) {
  return dstu7564.computeHash(32, data);
}

const algo = {
  // Default hash used when the cert OID does not map to a known family:
  hash: gostHash,
  hashes: {
    // GOST 34.311 (pre-2019 CAs)
    Gost34311: gostHash,
    Dstu4145le: gostHash,
    // Kupyna / ДСТУ 7564 (post-2019 CAs)
    Dstu4145leWithDstu7564: kupynaHash,
    Dstu7564: kupynaHash,
    "Dstu7564-256": kupynaHash,
  },
};

export { jk, algo };
