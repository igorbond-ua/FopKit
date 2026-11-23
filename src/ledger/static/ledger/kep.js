/**
 * kep.js — KEP key management (IndexedDB) and signing.
 *
 * The key file (Key-6.dat, .jks, .pfx) is stored encrypted in IndexedDB.
 * The signing function is a stub that must be completed once a JS crypto
 * library is chosen and tested with a real key.
 *
 * INTEGRATION POINT (signRnokpp):
 *   Replace the stub body with a call to the chosen library.
 *   Candidates:
 *     - jkurwa (https://github.com/dstucrypt/jkurwa) — pure JS, ДСТУ 4145
 *     - ІІТ eusign.js (https://iit.com.ua) — needs browser extension for hw tokens,
 *       but file keys work without it via their JS-only build
 *   The function must return a Base64-encoded CAdES signature of `rnokpp`
 *   with the signer certificate and a time-stamp (required by cabinet.tax.gov.ua).
 */

(function (global) {
  "use strict";

  const DB_NAME = "fopkit";
  const STORE = "kep_keys";
  const DB_VERSION = 1;

  // ── IndexedDB helpers ──────────────────────────────────────────────────

  function openDB() {
    return new Promise(function (resolve, reject) {
      var req = indexedDB.open(DB_NAME, DB_VERSION);
      req.onupgradeneeded = function (event) {
        var db = event.target.result;
        if (!db.objectStoreNames.contains(STORE)) {
          db.createObjectStore(STORE, { keyPath: "user_id" });
        }
      };
      req.onsuccess = function (event) { resolve(event.target.result); };
      req.onerror   = function (event) { reject(event.target.error); };
    });
  }

  function dbGet(user_id) {
    return openDB().then(function (db) {
      return new Promise(function (resolve, reject) {
        var tx = db.transaction(STORE, "readonly");
        var req = tx.objectStore(STORE).get(user_id);
        req.onsuccess = function (event) { resolve(event.target.result || null); };
        req.onerror   = function (event) { reject(event.target.error); };
      });
    });
  }

  function dbPut(record) {
    return openDB().then(function (db) {
      return new Promise(function (resolve, reject) {
        var tx = db.transaction(STORE, "readwrite");
        var req = tx.objectStore(STORE).put(record);
        req.onsuccess = function () { resolve(); };
        req.onerror   = function (event) { reject(event.target.error); };
      });
    });
  }

  function dbDelete(user_id) {
    return openDB().then(function (db) {
      return new Promise(function (resolve, reject) {
        var tx = db.transaction(STORE, "readwrite");
        var req = tx.objectStore(STORE).delete(user_id);
        req.onsuccess = function () { resolve(); };
        req.onerror   = function (event) { reject(event.target.error); };
      });
    });
  }

  // ── Public API ─────────────────────────────────────────────────────────

  /**
   * Returns the stored key record for `user_id`, or null if not stored.
   * Record shape: { user_id, key_bytes, cert_bytes, owner_name, tax_number,
   *                 valid_from, valid_until, issuer }
   */
  function getKeyRecord(user_id) {
    return dbGet(user_id);
  }

  /**
   * Save key files to IndexedDB.
   * `meta` = { owner_name, tax_number, valid_from, valid_until, issuer }
   */
  function saveKey(user_id, keyBytes, certBytes, meta) {
    return dbPut({
      user_id: user_id,
      key_bytes: keyBytes,
      cert_bytes: certBytes || null,
      owner_name: meta.owner_name || "",
      tax_number: meta.tax_number || "",
      valid_from: meta.valid_from || null,
      valid_until: meta.valid_until || null,
      issuer: meta.issuer || "",
    });
  }

  /** Delete the stored key for `user_id`. */
  function deleteKey(user_id) {
    return dbDelete(user_id);
  }

  // ── jkurwa helpers ────────────────────────────────────────────────────
  // jkurwa.bundle.js is loaded before this file and exposes window.jkurwaLib.
  // { jk, algo } = window.jkurwaLib

  function getLib() {
    if (!window.jkurwaLib) throw new Error("LIBRARY_NOT_LOADED");
    return window.jkurwaLib;
  }

  function bufferFromStore(val) {
    // jkurwa requires proper Buffer instances (not plain Uint8Array).
    // globalThis.Buffer is set by our jkurwa_entry.js bundle.
    var Buf = globalThis.Buffer;
    if (!Buf) throw new Error("LIBRARY_NOT_LOADED");
    if (val instanceof ArrayBuffer) return Buf.from(new Uint8Array(val));
    if (val instanceof Uint8Array) return Buf.from(val);
    if (typeof val === "string") return Buf.from(val, "binary");
    return val;
  }

  /**
   * Load key bytes into a Box, return the first signing cert's metadata.
   * Returns: Promise<{ owner_name, tax_number, valid_from, valid_until, issuer }>
   * Throws: Error("WRONG_PASSWORD") | Error("LIBRARY_NOT_LOADED") | Error(message)
   */
  function _buildBox(keyBytes, certBytes, password) {
    var lib = getLib();
    var box = new lib.jk.Box({ algo: lib.algo });
    var keyBuf = bufferFromStore(keyBytes);

    // Load private key
    box.load({ keyBuffers: [keyBuf], password: password || "" });

    // JKS files pack certs as separate trusted entries in the same file —
    // loading the same buffer as certBuffers extracts them and links to the key.
    box.load({ certBuffers: [keyBuf] });

    // Load accompanying certificate if provided separately (Key-6.dat case)
    if (certBytes) {
      box.load({ certBuffers: [bufferFromStore(certBytes)] });
    }

    return box;
  }

  function loadKeyMeta(keyBytes, certBytes, password) {
    return Promise.resolve().then(function () {
      var box = _buildBox(keyBytes, certBytes, password);

      // Find the first key that has an associated certificate
      var keyPair = box.keys.filter(function (k) { return k.cert; })[0];
      if (!keyPair) {
        // Fallback: check if any certs were loaded even without a key pair
        // (should not happen in normal JKS, but guard anyway)
        throw new Error("Не знайдено сертифікат у ключовому файлі. Спробуйте вказати окремий файл сертифіката (.cer).");
      }

      var cert = keyPair.cert;
      var subj = cert.subject || {};
      var issuer = cert.issuer || {};
      var validity = cert.validity || {};

      return {
        owner_name: subj.commonName || subj.organizationName || "",
        tax_number: subj.serialNumber || subj.dnQualifier || "",
        valid_from: validity.notBefore ? new Date(validity.notBefore).toISOString() : null,
        valid_until: validity.notAfter  ? new Date(validity.notAfter).toISOString()  : null,
        issuer: issuer.commonName || issuer.organizationName || "",
      };
    }).catch(function (err) {
      var msg = (err && err.message) || String(err);
      if (/password|пароль|decrypt|mac|hmac|wrong/i.test(msg)) {
        throw new Error("WRONG_PASSWORD");
      }
      throw err;
    });
  }

  /**
   * Sign `rnokpp` (string) with the stored key.
   * Returns: Promise<string>  — Base64-encoded DER of a CAdES-BES SignedData
   * Throws: Error("WRONG_PASSWORD") | Error("NO_KEY") | Error("LIBRARY_NOT_LOADED")
   *
   * cabinet.tax.gov.ua expects: Base64( CMS SignedData ) as the Authorization header value.
   * The container must include the signer certificate (CAdES-BES).
   * A timestamp (TSP) is NOT required by the cabinet API — tsp: false keeps it offline.
   */
  function signRnokpp(user_id, password, rnokpp) {
    return getKeyRecord(user_id).then(function (record) {
      if (!record) throw new Error("NO_KEY");

      getLib(); // ensure library is loaded
      var box = _buildBox(record.key_bytes, record.cert_bytes || null, password);

      var data = new TextEncoder().encode(rnokpp);

      // box.pipe returns a Buffer (Uint8Array-compatible) containing the DER-encoded CMS blob
      return box.pipe(
        data,
        [{ op: "sign", time: new Date() }],
        { tsp: false, includeChain: false }
      );
    }).then(function (signedBuffer) {
      // Convert to Base64
      var bytes = new Uint8Array(signedBuffer);
      var binary = "";
      for (var i = 0; i < bytes.byteLength; i++) {
        binary += String.fromCharCode(bytes[i]);
      }
      return btoa(binary);
    }).catch(function (err) {
      var msg = (err && err.message) || String(err);
      if (msg === "NO_KEY" || msg === "LIBRARY_NOT_LOADED") throw err;
      if (/password|пароль|decrypt|mac|hmac|wrong/i.test(msg)) {
        throw new Error("WRONG_PASSWORD");
      }
      throw err;
    });
  }

  // ── Cabinet dialog: KEP section UI ────────────────────────────────────

  var currentUserId = null;

  function formatDate(val) {
    if (!val) return "—";
    try {
      return new Date(val).toLocaleDateString("uk-UA", { day: "2-digit", month: "2-digit", year: "numeric" });
    } catch (e) { return String(val); }
  }

  function isExpiringSoon(validUntil) {
    if (!validUntil) return false;
    var diff = new Date(validUntil) - Date.now();
    return diff < 30 * 24 * 60 * 60 * 1000; // 30 days
  }

  function renderKepSection(record) {
    var noKey  = document.getElementById("kep-no-key");
    var hasKey = document.getElementById("kep-has-key");
    var loading = document.getElementById("kep-loading");
    if (!noKey) return;
    loading.hidden = true;
    if (!record) {
      noKey.hidden = false;
      hasKey.hidden = true;
      return;
    }
    noKey.hidden = true;
    hasKey.hidden = false;
    var info = document.getElementById("kep-info");
    var expiring = isExpiringSoon(record.valid_until);
    var expired  = record.valid_until && new Date(record.valid_until) < new Date();
    var warnClass = (expired || expiring) ? " warn" : "";
    var untilLabel = expired ? "⚠ Строк дії минув" : (expiring ? "⚠ Скоро закінчується" : "Дійсний до");
    info.innerHTML =
      '<div class="kep-info-row"><strong>' + (record.owner_name || "—") + '</strong></div>' +
      (record.tax_number ? '<div class="kep-info-row">РНОКПП: <strong>' + record.tax_number + '</strong></div>' : '') +
      '<div class="kep-info-row' + warnClass + '">' + untilLabel + ': <strong>' + formatDate(record.valid_until) + '</strong></div>' +
      (record.issuer ? '<div class="kep-info-row" style="font-size:11px;color:#8aa0b4">' + record.issuer + '</div>' : '');
  }

  function initKepSection(userId) {
    currentUserId = userId;
    getKeyRecord(userId).then(renderKepSection).catch(function () {
      renderKepSection(null);
    });
  }

  // ── Add-key dialog ─────────────────────────────────────────────────────

  function initAddKeyDialog() {
    var addBtn    = document.getElementById("kep-add-btn");
    var cancelBtn = document.getElementById("kep-add-cancel");
    var loadBtn   = document.getElementById("kep-load-btn");
    var saveBtn   = document.getElementById("kep-save-btn");
    var keyFile   = document.getElementById("kep-key-file");
    var certField = document.getElementById("kep-cert-field");
    var certFile  = document.getElementById("kep-cert-file");
    var pwdInput  = document.getElementById("kep-password");
    var preview   = document.getElementById("kep-preview");
    var errEl     = document.getElementById("kep-add-error");
    var addDialog = document.getElementById("add-key-dialog");
    var cabDialog = document.getElementById("cabinet-dialog");
    if (!addBtn || !addDialog) return;

    var loadedMeta = null;
    var loadedKeyBytes = null;
    var loadedCertBytes = null;

    function resetAddDialog() {
      loadedMeta = null; loadedKeyBytes = null; loadedCertBytes = null;
      if (keyFile) keyFile.value = "";
      if (certFile) certFile.value = "";
      if (pwdInput) pwdInput.value = "";
      if (preview) preview.hidden = true;
      if (errEl) errEl.hidden = true;
      if (loadBtn) loadBtn.hidden = false;
      if (saveBtn) saveBtn.hidden = true;
      if (certField) certField.hidden = true;
    }

    addBtn.addEventListener("click", function () {
      resetAddDialog();
      addDialog.showModal();
    });

    if (cancelBtn) {
      cancelBtn.addEventListener("click", function () {
        addDialog.close();
        if (cabDialog) cabDialog.showModal();
      });
    }

    if (keyFile) {
      keyFile.addEventListener("change", function () {
        var name = (keyFile.files[0] || {}).name || "";
        // Key-6.dat does not embed a certificate — show cert field
        if (certField) certField.hidden = !/key-6/i.test(name) && !/\.dat$/i.test(name);
      });
    }

    if (loadBtn) {
      loadBtn.addEventListener("click", function () {
        errEl.hidden = true;
        var file = keyFile && keyFile.files[0];
        if (!file) { showErr("Оберіть файл ключа."); return; }
        var password = pwdInput ? pwdInput.value : "";

        var readers = [readFile(file)];
        var cFile = certFile && certFile.files[0];
        if (cFile) readers.push(readFile(cFile));
        else readers.push(Promise.resolve(null));

        Promise.all(readers).then(function (results) {
          loadedKeyBytes  = results[0];
          loadedCertBytes = results[1];
          return loadKeyMeta(loadedKeyBytes, loadedCertBytes, password);
        }).then(function (meta) {
          loadedMeta = meta;
          if (preview) {
            preview.hidden = false;
            preview.innerHTML =
              "<strong>" + (meta.owner_name || "—") + "</strong>" +
              (meta.tax_number ? " · РНОКПП " + meta.tax_number : "") +
              (meta.valid_until ? " · до " + formatDate(meta.valid_until) : "") +
              (meta._stub ? "<br><small style='color:#5c7084'>⚠ Метадані без верифікації — бібліотека підпису не підключена</small>" : "");
          }
          loadBtn.hidden = true;
          saveBtn.hidden = false;
        }).catch(function (err) {
          showErr("Не вдалося відкрити ключ: " + (err.message || err));
        });
      });
    }

    if (saveBtn) {
      saveBtn.addEventListener("click", function () {
        if (!loadedMeta || !loadedKeyBytes) return;
        saveKey(currentUserId, loadedKeyBytes, loadedCertBytes, loadedMeta).then(function () {
          addDialog.close();
          renderKepSection({ ...loadedMeta });
          if (cabDialog) cabDialog.showModal();
          resetAddDialog();
        }).catch(function (err) {
          showErr("Не вдалося зберегти ключ: " + (err.message || err));
        });
      });
    }

    function showErr(msg) {
      if (errEl) { errEl.textContent = msg; errEl.hidden = false; }
    }
  }

  // ── Delete-key dialog ───────────────────────────────────────────────────

  function initDeleteKeyDialog() {
    var deleteBtn   = document.getElementById("kep-delete-btn");
    var confirmBtn  = document.getElementById("kep-confirm-delete-btn");
    var confirmDlg  = document.getElementById("confirm-delete-key-dialog");
    var cabDialog   = document.getElementById("cabinet-dialog");
    if (!deleteBtn || !confirmDlg) return;

    deleteBtn.addEventListener("click", function () {
      confirmDlg.showModal();
    });

    if (confirmBtn) {
      confirmBtn.addEventListener("click", function () {
        deleteKey(currentUserId).then(function () {
          confirmDlg.close();
          renderKepSection(null);
          if (cabDialog) cabDialog.showModal();
        });
      });
    }
  }

  // ── File reader helper ──────────────────────────────────────────────────

  function readFile(file) {
    return new Promise(function (resolve, reject) {
      var reader = new FileReader();
      reader.onload  = function (e) { resolve(e.target.result); };
      reader.onerror = function (e) { reject(e.target.error); };
      reader.readAsArrayBuffer(file);
    });
  }

  // ── Exports ─────────────────────────────────────────────────────────────

  global.kepStore = {
    getKeyRecord: getKeyRecord,
    saveKey:      saveKey,
    deleteKey:    deleteKey,
    loadKeyMeta:  loadKeyMeta,
    signRnokpp:   signRnokpp,
    initSection:  initKepSection,
    initDialogs:  function () {
      initAddKeyDialog();
      initDeleteKeyDialog();
    },
  };

}(window));
