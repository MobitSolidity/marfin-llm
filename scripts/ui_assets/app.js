/* marfin-llm local UI (D-0141). Served from /static/app.js under script-src 'self'.
   Progressive enhancement only: every page works without this file. It never builds
   markup from data and never evaluates strings; it only toggles classes, sets
   textContent and fills form fields (tests/test_ui.py asserts the forbidden APIs are
   absent from this file). */
(function () {
  "use strict";
  var root = document.documentElement;
  try {
    var saved = window.localStorage.getItem("marfin-theme");
    if (saved === "dark" || saved === "light") { root.setAttribute("data-theme", saved); }
  } catch (e) { /* storage blocked: follow the system theme */ }

  function each(sel, fn, scope) {
    Array.prototype.forEach.call((scope || document).querySelectorAll(sel), fn);
  }

  /* Persian-aware search: unify Arabic and Persian yeh/kaf, drop ZWNJ, fold digits. */
  function norm(text) {
    var s = String(text || "").toLowerCase();
    s = s.replace(/\u064A/g, "\u06CC").replace(/\u0643/g, "\u06A9").replace(/\u200C/g, " ");
    s = s.replace(/[\u06F0-\u06F9]/g, function (d) { return String(d.charCodeAt(0) - 0x06F0); });
    s = s.replace(/[\u0660-\u0669]/g, function (d) { return String(d.charCodeAt(0) - 0x0660); });
    return s;
  }

  document.addEventListener("DOMContentLoaded", function () {
    /* theme toggle */
    each("[data-theme-toggle]", function (btn) {
      btn.addEventListener("click", function () {
        var cur = root.getAttribute("data-theme") ||
          (window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
        var next = cur === "dark" ? "light" : "dark";
        root.setAttribute("data-theme", next);
        try { window.localStorage.setItem("marfin-theme", next); } catch (e) { /* ignore */ }
      });
    });

    /* calculator search + category chips */
    var search = document.getElementById("tool-search");
    var active = "all";
    var empty = document.getElementById("tool-empty");
    function applyFilter() {
      var q = norm(search ? search.value : "").trim();
      var shown = 0;
      each(".tool-card", function (card) {
        var okCat = active === "all" || card.getAttribute("data-cat") === active;
        var okQ = !q || norm(card.getAttribute("data-search")).indexOf(q) !== -1;
        var vis = okCat && okQ;
        card.classList.toggle("is-hidden", !vis);
        if (vis) { shown += 1; }
      });
      each("section.cat", function (sec) {
        sec.classList.toggle("is-hidden", sec.querySelectorAll(".tool-card:not(.is-hidden)").length === 0);
      });
      if (empty) { empty.classList.toggle("is-hidden", shown !== 0); }
      var counter = document.getElementById("tool-count");
      if (counter) { counter.textContent = String(shown); }
    }
    if (search) {
      search.classList.remove("is-hidden");
      search.addEventListener("input", applyFilter);
    }
    each("[data-cat-chip]", function (chip) {
      chip.classList.remove("is-hidden");
      chip.addEventListener("click", function () {
        active = chip.getAttribute("data-cat-chip");
        each("[data-cat-chip]", function (c) { c.classList.toggle("on", c === chip); });
        applyFilter();
      });
    });

    /* "/" focuses the search box */
    document.addEventListener("keydown", function (e) {
      var tag = (document.activeElement && document.activeElement.tagName) || "";
      if (e.key === "/" && search && !/INPUT|TEXTAREA|SELECT/.test(tag)) {
        e.preventDefault();
        search.focus();
      }
    });

    /* example chips fill a textarea */
    each("[data-fill]", function (btn) {
      btn.addEventListener("click", function () {
        var target = document.querySelector(btn.getAttribute("data-target"));
        if (target) { target.value = btn.getAttribute("data-fill"); target.focus(); }
      });
    });

    /* Ctrl+Enter submits a textarea's form */
    each("textarea", function (ta) {
      ta.addEventListener("keydown", function (e) {
        if ((e.ctrlKey || e.metaKey) && e.key === "Enter" && ta.form) {
          e.preventDefault();
          if (ta.form.requestSubmit) { ta.form.requestSubmit(); } else { ta.form.submit(); }
        }
      });
    });

    /* long-running forms show progress and cannot be double-submitted */
    each("form[data-busy]", function (form) {
      form.addEventListener("submit", function () {
        var btn = form.querySelector("button:not([type=button])");
        if (btn) {
          btn.disabled = true;
          btn.classList.add("is-busy");
          btn.textContent = form.getAttribute("data-busy");
        }
      });
    });

    /* destructive actions ask once more */
    each("form[data-confirm]", function (form) {
      form.addEventListener("submit", function (e) {
        if (!window.confirm(form.getAttribute("data-confirm"))) { e.preventDefault(); }
      });
    });

    /* copy a result */
    each("[data-copy]", function (btn) {
      btn.classList.remove("is-hidden");
      btn.addEventListener("click", function () {
        var el = document.querySelector(btn.getAttribute("data-copy"));
        if (!el || !navigator.clipboard) { return; }
        navigator.clipboard.writeText(el.textContent.trim()).then(function () {
          var old = btn.textContent;
          btn.textContent = "\u06A9\u067E\u06CC \u0634\u062F";
          window.setTimeout(function () { btn.textContent = old; }, 1400);
        });
      });
    });
  });
})();
