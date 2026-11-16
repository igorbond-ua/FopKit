(function () {
  "use strict";

  const data = JSON.parse(document.getElementById("dialog-data").textContent);
  const year = document.body.dataset.year;

  function openDialog(dialog) {
    if (!dialog.open) dialog.showModal();
  }

  function cell(text, className) {
    const td = document.createElement("td");
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

  const editDialog = document.getElementById("edit-dialog");
  const editForm = document.getElementById("edit-form");

  function openEdit(entryId, returnMonth) {
    const entry = data.entries[String(entryId)];
    if (!entry) return;
    editForm.action = "/income/" + entry.id + "/";
    editForm.elements.received_on.value = entry.date;
    editForm.elements.amount.value = entry.amountInput;
    editForm.elements.return_year.value = year;
    editForm.elements.return_month.value = returnMonth || "";
    editForm.querySelectorAll("input[name=currency]").forEach(function (radio) {
      radio.checked = radio.value === entry.currency;
    });
    openDialog(editDialog);
  }

  const monthDialog = document.getElementById("month-dialog");
  const monthRows = document.getElementById("month-dialog-rows");

  function openMonth(month) {
    const ids = data.months[String(month)] || [];
    document.getElementById("month-dialog-title").textContent =
      "Операції: " + data.monthNames[month - 1] + " " + year;
    monthRows.replaceChildren();
    if (ids.length === 0) {
      const row = document.createElement("tr");
      const empty = cell("Операцій у цьому місяці немає", "empty");
      empty.colSpan = monthDialog.querySelectorAll("thead th").length;
      row.appendChild(empty);
      monthRows.appendChild(row);
    }
    ids.forEach(function (id) {
      const entry = data.entries[String(id)];
      const row = document.createElement("tr");
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
    openDialog(monthDialog);
  }

  document.querySelectorAll("td[data-month]").forEach(function (td) {
    activateOnKey(td, function () { openMonth(Number(td.dataset.month)); });
  });

  document.querySelectorAll("tr[data-entry-id]").forEach(function (row) {
    activateOnKey(row, function () { openEdit(row.dataset.entryId, ""); });
  });

  const confirmDialog = document.getElementById("confirm-dialog");
  const confirmForm = document.getElementById("confirm-form");
  const confirmText = document.getElementById("confirm-dialog-text");

  document.getElementById("delete-income").addEventListener("click", function () {
    confirmForm.action = editForm.action + "delete/";
    confirmForm.elements.return_month.value = editForm.elements.return_month.value;
    confirmText.textContent = "Видалити прибуток?";
    openDialog(confirmDialog);
  });

  document.querySelectorAll("td[data-toggle-url]").forEach(function (td) {
    activateOnKey(td, function () {
      confirmForm.action = td.dataset.toggleUrl;
      confirmForm.elements.return_month.value = "";
      confirmText.textContent = td.dataset.paid === "1"
        ? "Зняти помітку \"виконано\"?"
        : "Помітити як зроблене?";
      openDialog(confirmDialog);
    });
  });

  document.querySelectorAll("[data-open-dialog]").forEach(function (button) {
    if (button.tagName !== "BUTTON") return;
    button.addEventListener("click", function () {
      openDialog(document.getElementById(button.dataset.openDialog));
    });
  });

  document.querySelectorAll("[data-close-dialog]").forEach(function (button) {
    button.addEventListener("click", function () {
      button.closest("dialog").close();
    });
  });

  document.querySelectorAll("[data-autosubmit]").forEach(function (input) {
    input.addEventListener("change", function () { input.form.submit(); });
  });

  function fitRecent() {
    const monthly = document.getElementById("monthly-panel");
    const recent = document.getElementById("recent-panel");
    const desk = document.querySelector(".desk");
    if (!monthly || !recent || !desk) return;
    const rows = Array.from(recent.querySelectorAll("tbody tr[data-entry-id]"));
    rows.forEach(function (row) { row.hidden = false; });
    const stacked = getComputedStyle(desk).gridTemplateColumns.trim().split(/\s+/).length < 2;
    if (stacked) {
      rows.slice(10).forEach(function (row) { row.hidden = true; });
      return;
    }
    const limit = monthly.getBoundingClientRect().bottom + 0.5;
    for (let i = rows.length - 1; i > 0 && recent.getBoundingClientRect().bottom > limit; i--) {
      rows[i].hidden = true;
    }
  }

  fitRecent();
  window.addEventListener("resize", fitRecent);

  const openMonthParam = Number(document.body.dataset.openMonth);
  if (openMonthParam >= 1 && openMonthParam <= 12) openMonth(openMonthParam);
  if (document.body.dataset.openDialog === "cabinet") {
    openDialog(document.getElementById("cabinet-dialog"));
  }
})();
