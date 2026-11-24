/**
 * app.js — shared logic for all pages that extend page_base.html.
 * Handles: cabinet dialog, KEP section, data-open-dialog, data-close-dialog.
 *
 * Dashboard-specific logic (month/entry dialogs) lives in dashboard.js.
 * Settlements logic lives in settlements.js.
 * KEP IndexedDB + signing live in kep.js (loaded before this file).
 */
(function () {
  "use strict";

  // ── User ID ─────────────────────────────────────────────────────────
  // The base template sets data-user-id on <body> so JS can key IndexedDB.
  var userId = document.body.dataset.userId || "";

  // ── Generic dialog helpers ──────────────────────────────────────────

  function openDialog(dialog) {
    if (dialog && !dialog.open) dialog.showModal();
  }

  document.querySelectorAll("[data-open-dialog]").forEach(function (button) {
    if (button.tagName !== "BUTTON") return;
    button.addEventListener("click", function () {
      openDialog(document.getElementById(button.dataset.openDialog));
    });
  });

  document.querySelectorAll("[data-close-dialog]").forEach(function (button) {
    button.addEventListener("click", function () {
      var dlg = button.closest("dialog");
      if (dlg) dlg.close();
    });
  });

  // ── Cabinet dialog: auto-open if requested ──────────────────────────
  var reopenCabinet = sessionStorage.getItem("fopkit-reopen-cabinet") === "1";
  sessionStorage.removeItem("fopkit-reopen-cabinet");
  if (document.body.dataset.openDialog === "cabinet" || reopenCabinet) {
    openDialog(document.getElementById("cabinet-dialog"));
  }

  // ── Cabinet dialog: refresh from the tax cabinet ─────────────────────
  var dpsSyncBtn = document.getElementById("dps-sync-btn");
  if (dpsSyncBtn && window.kepStore && !dpsSyncBtn.dataset.bound) {
    dpsSyncBtn.dataset.bound = "1";
    dpsSyncBtn.addEventListener("click", function () {
      kepStore.signAndPost(dpsSyncBtn.dataset.syncUrl).then(function (data) {
        if (!data) return;
        sessionStorage.setItem("fopkit-reopen-cabinet", "1");
        window.location.reload();
      }).catch(function (err) {
        if (err && err.message === "NO_KEY") {
          var status = document.querySelector(".dps-status");
          if (status) status.textContent = "Щоб оновити дані з податкової, спершу додайте ключ КЕП нижче.";
        }
      });
    });
  }

  // ── KEP section ──────────────────────────────────────────────────────
  if (window.kepStore && userId) {
    kepStore.initSection(userId);
    kepStore.initDialogs();
  }

  // ── Auto-submit selects (year pickers, etc.) ─────────────────────────
  // Note: each page script also wires its own [data-autosubmit] if needed.
  document.querySelectorAll("[data-autosubmit]").forEach(function (input) {
    // Avoid double-binding if a page script already did it
    if (input.dataset.autosubmitBound) return;
    input.dataset.autosubmitBound = "1";
    input.addEventListener("change", function () { input.form.submit(); });
  });

}());
