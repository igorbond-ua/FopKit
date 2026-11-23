/**
 * Shim for the 'fs' module used by jkurwa.
 * jkurwa calls fs.readFileSync only when privPath/certPath options are passed.
 * In browser code we always pass keyBuffers directly, so this never fires.
 */
export default {
  readFileSync: function () {
    throw new Error("fs.readFileSync is not available in the browser. Pass keyBuffers instead of privPath.");
  },
};
