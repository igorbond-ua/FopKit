/**
 * Shim for node:crypto used by jkurwa.
 * jkurwa only calls crypto.rng(buffer) for random-number generation.
 * We replace it with the browser's native getRandomValues.
 */
export default {
  /**
   * Replacement for Node.js crypto.rng(n).
   * jkurwa calls it as: crypto.rng(xb.length) — i.e. with a NUMBER, not a Buffer.
   * It expects a filled Uint8Array of that length back.
   */
  rng: function (nOrBuf) {
    if (typeof nOrBuf === "number") {
      // Called with a byte count → allocate and fill
      const buf = new Uint8Array(nOrBuf);
      globalThis.crypto.getRandomValues(buf);
      return buf;
    }
    // Called with an existing Buffer/Uint8Array → fill in place
    const view = new Uint8Array(nOrBuf.buffer, nOrBuf.byteOffset, nOrBuf.byteLength);
    globalThis.crypto.getRandomValues(view);
    return nOrBuf;
  },
};
