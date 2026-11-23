/**
 * Shim for node:crypto used by jkurwa.
 * jkurwa only calls crypto.rng(buffer) for random-number generation.
 * We replace it with the browser's native getRandomValues.
 */
export default {
  rng: function (buf) {
    return globalThis.crypto.getRandomValues(buf);
  },
};
