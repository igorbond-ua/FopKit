(function () {
  "use strict";

  // The script can be evaluated twice (a second copy shows up as "VM… settlements.js").
  // Each sync logs in to the cabinet, and a second login revokes the first token,
  // so bind the handlers only once. The flag lives on the DOM, which both copies share.
  if (document.body.dataset.settlementsBound) return;
  document.body.dataset.settlementsBound = "1";

  // Values read from data-* attributes on <body> (set by the settlements template).
  // This avoids inline <script> tags which would be blocked by our CSP.
  var syncUrl  = document.body.dataset.syncUrl  || "";
  var year     = Number(document.body.dataset.year) || 0;
  var rnokpp   = document.body.dataset.rnokpp   || "";
  var csrf     = document.body.dataset.csrf     || "";
  var userId   = document.body.dataset.userId   || "";

  // ── Account card switching ──────────────────────────────────────────

  document.querySelectorAll(".account-card").forEach(function (card) {
    card.addEventListener("click", function () {
      var url = card.dataset.url;
      if (url) window.location.href = url;
    });
    card.addEventListener("keydown", function (e) {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); card.click(); }
    });
    card.tabIndex = 0;
  });

  // ── Sync flow ───────────────────────────────────────────────────────

  var syncBtn     = document.getElementById("sync-btn");
  var syncDlg     = document.getElementById("sync-password-dialog");
  var syncSignBtn = document.getElementById("sync-sign-btn");
  var syncCancel  = document.getElementById("sync-cancel");
  var syncPwd     = document.getElementById("sync-password");
  var syncErr     = document.getElementById("sync-error");
  var noKeyMsg    = document.getElementById("settlements-no-key-msg");

  function showSyncError(msg) {
    if (syncErr) { syncErr.textContent = msg; syncErr.hidden = false; }
  }
  function clearSyncError() {
    if (syncErr) { syncErr.hidden = true; syncErr.textContent = ""; }
  }

  function setSignBtnBusy(busy) {
    if (syncSignBtn) {
      syncSignBtn.disabled = busy;
      syncSignBtn.textContent = busy ? "Підписую…" : "Підписати і синхронізувати";
    }
  }

  if (syncBtn && syncDlg) {
    syncBtn.addEventListener("click", function () {
      // Check if key exists before showing dialog
      if (!window.kepStore) { showSyncError("KEP store not available."); return; }
      kepStore.getKeyRecord(userId).then(function (record) {
        if (!record) {
          // Show hint to add key
          if (noKeyMsg) noKeyMsg.hidden = false;
          return;
        }
        clearSyncError();
        if (syncPwd) syncPwd.value = "";
        syncDlg.showModal();
        setTimeout(function () { if (syncPwd) syncPwd.focus(); }, 50);
      });
    });

    if (syncCancel) syncCancel.addEventListener("click", function () { syncDlg.close(); });

    if (syncSignBtn) {
      syncSignBtn.addEventListener("click", function () {
        clearSyncError();
        var password = syncPwd ? syncPwd.value : "";
        if (!password) { showSyncError("Введіть пароль ключа."); return; }

        if (!rnokpp) {
          showSyncError("Заповніть РНОКПП у профілі перед синхронізацією.");
          return;
        }

        setSignBtnBusy(true);

        var timestamp = Date.now();
        kepStore.signRnokpp(userId, password, rnokpp, timestamp)
          .then(function (result) {
            return fetch(syncUrl, {
              method: "POST",
              headers: {
                "Content-Type": "application/json",
                "X-CSRFToken": csrf,
              },
              body: JSON.stringify({ username: result.username, password: result.password, year: year }),
            });
          })
          .then(function (resp) {
            return resp.json().then(function (data) {
              return { ok: resp.ok, data: data };
            }, function () {
              return { ok: false, data: { error: "Помилка сервера FopKit (HTTP " + resp.status + ")." } };
            });
          })
          .then(function (result) {
            setSignBtnBusy(false);
            if (result.ok) {
              syncDlg.close();
              window.location.href = result.data.redirect || window.location.href;
            } else {
              showSyncError(result.data.error || "Помилка синхронізації.");
            }
          })
          .catch(function (err) {
            setSignBtnBusy(false);
            var msg = err.message || String(err);
            if (msg === "LIBRARY_NOT_LOADED") {
              showSyncError("Бібліотека підпису ще не підключена. Дивіться kep.js → INTEGRATION POINT.");
            } else if (msg === "NO_KEY") {
              showSyncError("Ключ КЕП не знайдено. Додайте його в Кабінеті.");
            } else if (msg === "WRONG_PASSWORD") {
              showSyncError("Невірний пароль ключа.");
              if (syncPwd) syncPwd.focus();
            } else {
              showSyncError("Помилка підпису: " + msg);
            }
          });
      });
    }
  }

  // ── Auto-submit year selector ───────────────────────────────────────

  document.querySelectorAll("[data-autosubmit]").forEach(function (input) {
    input.addEventListener("change", function () { input.form.submit(); });
  });

}());
