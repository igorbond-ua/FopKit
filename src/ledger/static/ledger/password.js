/**
 * password.js — "show password" eye button for every password field on the page.
 */
(function () {
  "use strict";

  var SVG = "http://www.w3.org/2000/svg";
  var EYE = "M1 12s4-7 11-7 11 7 11 7-4 7-11 7S1 12 1 12z M12 9a3 3 0 1 0 0 6a3 3 0 1 0 0-6z";
  var SLASH = "M3 3l18 18";

  function icon(hidden) {
    var svg = document.createElementNS(SVG, "svg");
    svg.setAttribute("viewBox", "0 0 24 24");
    svg.setAttribute("aria-hidden", "true");
    var paths = hidden ? [EYE] : [EYE, SLASH];
    paths.forEach(function (d) {
      var path = document.createElementNS(SVG, "path");
      path.setAttribute("d", d);
      svg.appendChild(path);
    });
    return svg;
  }

  function addToggle(input) {
    if (input.dataset.passwordToggle) return;
    input.dataset.passwordToggle = "1";

    var wrap = document.createElement("span");
    wrap.className = "password-wrap";
    input.parentNode.insertBefore(wrap, input);
    wrap.appendChild(input);

    var button = document.createElement("button");
    button.type = "button";
    button.className = "password-toggle";
    wrap.appendChild(button);

    function render() {
      var shown = input.type === "text";
      button.replaceChildren(icon(!shown));
      button.setAttribute("aria-label", shown ? "Сховати пароль" : "Показати пароль");
      button.setAttribute("aria-pressed", shown ? "true" : "false");
      button.title = button.getAttribute("aria-label");
    }

    button.addEventListener("click", function () {
      input.type = input.type === "password" ? "text" : "password";
      render();
      input.focus();
    });

    // A revealed password must not stay visible when its dialog or page is reused.
    var dialog = input.closest("dialog");
    if (dialog) {
      dialog.addEventListener("close", function () { input.type = "password"; render(); });
    }
    if (input.form) {
      input.form.addEventListener("submit", function () { input.type = "password"; });
    }
    render();
  }

  document.querySelectorAll('input[type="password"]').forEach(addToggle);
}());
