/* Andarz local UI (D-0141, rebranded D-0143). Served from /static/app.js under script-src 'self'.
   Progressive enhancement only: every page works without this file. It never builds
   markup from data and never evaluates strings; it only toggles classes, sets
   textContent and fills form fields (tests/test_ui.py asserts the forbidden APIs are
   absent from this file). */
(function () {
  "use strict";
  var root = document.documentElement;
  /* D-0143: the theme key is "andarz-theme"; a choice saved under the old key still applies. */
  try {
    var saved = window.localStorage.getItem("andarz-theme") || window.localStorage.getItem("marfin-theme");
    if (saved === "dark" || saved === "light") { root.setAttribute("data-theme", saved); }
  } catch (e) { /* storage blocked: follow the system theme */ }

  /* D-0143(7): storage helpers -- every access in try/catch (storage may be blocked) */
  function tget(k) { try { return window.localStorage.getItem(k); } catch (e) { return null; } }
  function tset(k, v) { try { window.localStorage.setItem(k, v); } catch (e) { /* blocked: the tour just restarts */ } }

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
        try { window.localStorage.setItem("andarz-theme", next); } catch (e) { /* ignore */ }
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

    /* D-0143(7): first-run tour -- skippable, resumable, re-launchable from the menu */
    var tour = document.querySelector("[data-tour]");
    if (tour) {
      var steps = tour.querySelectorAll(".tour-step");
      var pos = tour.querySelector("[data-tour-pos]");
      var nextBtn = tour.querySelector("[data-tour-next]");
      var nextText = nextBtn ? nextBtn.textContent : "";
      var cur = parseInt(tget("andarz-tour-step") || "0", 10);
      if (!(cur >= 0 && cur < steps.length)) { cur = 0; }
      var showTour = function (i) {
        cur = Math.max(0, Math.min(steps.length - 1, i));
        Array.prototype.forEach.call(steps, function (s, j) { s.classList.toggle("on", j === cur); });
        if (pos) { pos.textContent = String(cur + 1); }
        if (nextBtn) { nextBtn.textContent = cur === steps.length - 1 ? nextBtn.getAttribute("data-last") : nextText; }
        tset("andarz-tour-step", String(cur));
        tour.classList.remove("is-hidden");
      };
      var hideTour = function (done) {
        tour.classList.add("is-hidden");
        if (done) { tset("andarz-tour-done", "1"); }
      };
      var startTour = function () { tset("andarz-tour-done", "0"); showTour(0); tour.focus(); };
      each("[data-tour-next]", function (b) {
        b.addEventListener("click", function () { if (cur >= steps.length - 1) { hideTour(true); } else { showTour(cur + 1); } });
      });
      each("[data-tour-prev]", function (b) { b.addEventListener("click", function () { showTour(cur - 1); }); });
      each("[data-tour-skip]", function (b) { b.addEventListener("click", function () { hideTour(true); }); });
      each("[data-tour-start]", function (b) {
        b.classList.remove("is-hidden");
        b.addEventListener("click", startTour);
      });
      document.addEventListener("keydown", function (e) {
        if (e.key === "Escape" && !tour.classList.contains("is-hidden")) { hideTour(false); }
      });
      if (/[?&]tour=1(&|$)/.test(window.location.search)) { startTour(); }
      else if (steps.length && tget("andarz-tour-done") !== "1") { showTour(cur); }
    }

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
