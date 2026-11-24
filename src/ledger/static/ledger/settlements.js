(function () {
  "use strict";

  // The script can be evaluated twice (a second copy shows up as "VM… settlements.js").
  // Each sync logs in to the cabinet, and a second login revokes the first token,
  // so bind the handlers only once. The flag lives on the DOM, which both copies share.
  if (document.body.dataset.settlementsBound) return;
  document.body.dataset.settlementsBound = "1";

  var syncUrl = document.body.dataset.syncUrl || "";
  var year    = Number(document.body.dataset.year) || 0;

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

  var syncBtn  = document.getElementById("sync-btn");
  var noKeyMsg = document.getElementById("settlements-no-key-msg");

  if (syncBtn && window.kepStore) {
    syncBtn.addEventListener("click", function () {
      kepStore.signAndPost(syncUrl, { year: year }).then(function (data) {
        if (data) window.location.href = data.redirect || window.location.href;
      }).catch(function (err) {
        if (err && err.message === "NO_KEY" && noKeyMsg) noKeyMsg.hidden = false;
      });
    });
  }

  // ── Auto-submit year selector ───────────────────────────────────────

  document.querySelectorAll("[data-autosubmit]").forEach(function (input) {
    if (input.dataset.autosubmitBound) return;
    input.dataset.autosubmitBound = "1";
    input.addEventListener("change", function () { input.form.submit(); });
  });

}());
