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
  if (document.body.dataset.openDialog === "cabinet") {
    openDialog(document.getElementById("cabinet-dialog"));
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
