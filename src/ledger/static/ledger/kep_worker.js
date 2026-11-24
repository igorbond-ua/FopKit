/**
 * kep_worker.js — Web Worker for KEP signing.
 *
 * Runs in a background thread so the browser UI never freezes
 * during the CPU-heavy DSTU 4145 / GOST cryptographic operations.
 *
 * Protocol:
 *   Main → Worker: { type: "sign", keyBytes: ArrayBuffer, certBytes: ArrayBuffer|null,
 *                    password: string, rnokpp: string, timestamp: number,
 *                    tspUrl: string, csrf: string }
 *   Worker → Main: { type: "result", username: string, password: string }
 *                | { type: "error",  code: string, message: string }
 */

// jkurwa.bundle.js is loaded first (URL passed via initial message).
// It sets globalThis.jkurwaLib and globalThis.Buffer.
var bundleLoaded = false;

self.onmessage = function (e) {
  var msg = e.data;

  if (msg.type === "init") {
    // Load the bundle inside the worker via importScripts.
    try {
      importScripts(msg.bundleUrl);
      bundleLoaded = true;
      self.postMessage({ type: "ready" });
    } catch (err) {
      self.postMessage({ type: "error", code: "LIBRARY_NOT_LOADED", message: String(err) });
    }
    return;
  }

  if (msg.type === "sign") {
    if (!bundleLoaded) {
      self.postMessage({ type: "error", code: "LIBRARY_NOT_LOADED", message: "Bundle not loaded." });
      return;
    }
    _sign(msg).then(function (result) {
      self.postMessage({ type: "result", username: result.username, password: result.password });
    }).catch(function (err) {
      // jkurwa rejects with null when the TSP server gives no usable answer.
      var message = err ? (err.message || String(err)) : "Не вдалося отримати позначку часу від АЦСК.";
      var code = "SIGN_ERROR";
      if (/password|пароль|decrypt|mac|hmac|wrong/i.test(message)) code = "WRONG_PASSWORD";
      self.postMessage({ type: "error", code: code, message: message });
    });
    return;
  }
};

// Catch unhandled rejections inside the worker
self.onunhandledrejection = function (e) {
  self.postMessage({ type: "error", code: "UNHANDLED", message: String(e.reason) });
};

function _sign(msg) {
  var lib = globalThis.jkurwaLib;
  if (!lib) return Promise.reject(new Error("LIBRARY_NOT_LOADED"));

  var Buf = globalThis.Buffer;

  // jkurwa's TSP client calls query(method, url, headers, body, cb) and
  // expects cb(responseBuffer) or cb(null) on failure.
  function tspQuery(method, url, headers, body, cb) {
    var bytes = new Uint8Array(body);
    var bin = "";
    for (var i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
    fetch(msg.tspUrl, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-CSRFToken": msg.csrf },
      body: JSON.stringify({ url: url, data: btoa(bin) }),
    }).then(function (r) {
      return r.ok ? r.json() : null;
    }).then(function (json) {
      if (!json || !json.data) { cb(null); return; }
      var raw = atob(json.data);
      var out = new Uint8Array(raw.length);
      for (var i = 0; i < raw.length; i++) out[i] = raw.charCodeAt(i);
      cb(Buf.from(out));
    }).catch(function () { cb(null); });
  }

  var box = new lib.jk.Box({ algo: lib.algo, query: tspQuery });

  var keyBuf = Buf.from(new Uint8Array(msg.keyBytes));
  box.load({ keyBuffers: [keyBuf], password: msg.password || "" });

  if (msg.certBytes) {
    box.load({ certBuffers: [Buf.from(new Uint8Array(msg.certBytes))] });
  }

  // The cabinet's file-key login signs only the РНОКПП (attached data,
  // signer certificate included); without a content time-stamp the token
  // endpoint answers "Не визначена помилка". The username is
  // "{РНОКПП}-{РНОКПП}-{idCabinet}", idCabinet being any millisecond timestamp.
  var username = msg.rnokpp + "-" + msg.rnokpp + "-" + msg.timestamp;
  var data = Buf.from(new TextEncoder().encode(msg.rnokpp));

  return box.pipe(data, [{ op: "sign", time: new Date(), tsp: "content" }], {}).then(function (signedBuffer) {
    var bytes = new Uint8Array(signedBuffer);
    var binary = "";
    for (var i = 0; i < bytes.length; i++) {
      binary += String.fromCharCode(bytes[i]);
    }
    return { username: username, password: btoa(binary) };
  });
}
