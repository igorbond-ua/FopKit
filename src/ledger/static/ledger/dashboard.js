/**
 * dashboard.js — logic specific to the Облік (dashboard) page.
 * Requires: app.js (loaded first via page_base.html).
 */
(function () {
  "use strict";

  var data = JSON.parse(document.getElementById("dialog-data").textContent);
  var year = document.body.dataset.year;

  function cell(text, className) {
    var td = document.createElement("td");
    td.textContent = text;
    if (className) td.className = className;
    return td;
  }

  function activateOnKey(element, handler) {
    element.addEventListener("click", handler);
    element.addEventListener("keydown", function (event) {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        handler(event);
      }
    });
  }

  var editDialog = document.getElementById("edit-dialog");
  var editForm   = document.getElementById("edit-form");

  function openEdit(entryId, returnMonth) {
    var entry = data.entries[String(entryId)];
    if (!entry) return;
    editForm.action = "/income/" + entry.id + "/";
    editForm.elements.received_on.value = entry.date;
    editForm.elements.amount.value = entry.amountInput;
    editForm.elements.return_year.value = year;
    editForm.elements.return_month.value = returnMonth || "";
    editForm.querySelectorAll("input[name=currency]").forEach(function (radio) {
      radio.checked = radio.value === entry.currency;
    });
    if (editDialog && !editDialog.open) editDialog.showModal();
  }

  var monthDialog = document.getElementById("month-dialog");
  var monthRows   = document.getElementById("month-dialog-rows");

  function openMonth(month) {
    var ids = data.months[String(month)] || [];
    document.getElementById("month-dialog-title").textContent =
      "Операції: " + data.monthNames[month - 1] + " " + year;
    monthRows.replaceChildren();
    if (ids.length === 0) {
      var row = document.createElement("tr");
      var empty = cell("Операцій у цьому місяці немає", "empty");
      empty.colSpan = monthDialog.querySelectorAll("thead th").length;
      row.appendChild(empty);
      monthRows.appendChild(row);
    }
    ids.forEach(function (id) {
      var entry = data.entries[String(id)];
      var row = document.createElement("tr");
      row.className = "clickable";
      row.tabIndex = 0;
      row.title = "Редагувати";
      row.appendChild(cell(entry.dateLabel));
      row.appendChild(cell(entry.uah, "num"));
      row.appendChild(cell(entry.currencyLabel));
      row.appendChild(cell(entry.amount, entry.amount === "—" ? "num empty" : "num"));
      row.appendChild(cell(entry.rate, entry.rate === "—" ? "num empty" : "num"));
      row.appendChild(cell(entry.singleTax, "num"));
      row.appendChild(cell(entry.militaryLevy, "num"));
      activateOnKey(row, function () { openEdit(id, month); });
      monthRows.appendChild(row);
    });
    if (monthDialog && !monthDialog.open) monthDialog.showModal();
  }

  document.querySelectorAll("td[data-month]").forEach(function (td) {
    activateOnKey(td, function () { openMonth(Number(td.dataset.month)); });
  });

  document.querySelectorAll("tr[data-entry-id]").forEach(function (row) {
    activateOnKey(row, function () { openEdit(row.dataset.entryId, ""); });
  });

  var confirmDialog = document.getElementById("confirm-dialog");
  var confirmForm   = document.getElementById("confirm-form");
  var confirmText   = document.getElementById("confirm-dialog-text");

  document.getElementById("delete-income").addEventListener("click", function () {
    confirmForm.action = editForm.action + "delete/";
    confirmForm.elements.return_month.value = editForm.elements.return_month.value;
    confirmText.textContent = "Видалити прибуток?";
    if (confirmDialog && !confirmDialog.open) confirmDialog.showModal();
  });

  document.querySelectorAll("td[data-toggle-url]").forEach(function (td) {
    activateOnKey(td, function () {
      confirmForm.action = td.dataset.toggleUrl;
      confirmForm.elements.return_month.value = "";
      confirmText.textContent = td.dataset.paid === "1"
        ? "Зняти помітку \"виконано\"?"
        : "Помітити як зроблене?";
      if (confirmDialog && !confirmDialog.open) confirmDialog.showModal();
    });
  });

  function fitRecent() {
    var monthly = document.getElementById("monthly-panel");
    var recent  = document.getElementById("recent-panel");
    var desk    = document.querySelector(".desk");
    if (!monthly || !recent || !desk) return;
    var rows = Array.from(recent.querySelectorAll("tbody tr[data-entry-id]"));
    rows.forEach(function (row) { row.hidden = false; });
    var stacked = getComputedStyle(desk).gridTemplateColumns.trim().split(/\s+/).length < 2;
    if (stacked) {
      rows.slice(10).forEach(function (row) { row.hidden = true; });
      return;
    }
    var limit = monthly.getBoundingClientRect().bottom + 0.5;
    for (var i = rows.length - 1; i > 0 && recent.getBoundingClientRect().bottom > limit; i--) {
      rows[i].hidden = true;
    }
  }

  fitRecent();
  window.addEventListener("resize", fitRecent);

  var openMonthParam = Number(document.body.dataset.openMonth);
  if (openMonthParam >= 1 && openMonthParam <= 12) openMonth(openMonthParam);

}());
