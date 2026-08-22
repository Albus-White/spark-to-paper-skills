/* ============================================================================
   SB.data — the shared bridge from the workspace modules to the server adapters
   (/api/{spark,jury,wiki}/<view>). Each workspace has a "current target" directory
   (a spark run root / a manuscript with .paper-review/ / a compiled wiki project);
   the modules fetch their real on-disk data for that dir and fall back to their
   built-in sample when nothing is opened, so the app is beautiful out of the box
   and truthful the moment you point it at real work.

   Target selection order: an explicit ?dir= (for a tool, deterministic screenshots
   + deep links) → the remembered choice (localStorage) → a server-suggested default
   (from /api/library) → none (sample fallback).
   ============================================================================ */
(function () {
  "use strict";
  var SB = window.SB;
  if (!SB) return;

  var Q = new URLSearchParams(location.search);
  var suggested = {};                    // tool -> dir, filled from /api/library once

  // R1 — per-tool read trace. Lets a module tell two very different failures apart:
  //   "couldn't read <dir> at all" (a real dir was set but EVERY adapter errored/404'd)
  //   vs "read fine, this field just has no data" (adapter answered 200 with {} / found:false).
  // Only the first is a broken directory worth a dismissible warning; the second is an
  // honest per-field sample fallback. The trace resets whenever the tool's dir changes.
  var readTrace = {};                    // tool -> { dir, ok, fail, dismissed }
  function traceOf(tool) {
    var d = ""; try { d = data.dir(tool); } catch (e) {}
    var t = readTrace[tool];
    if (!t || t.dir !== d) t = readTrace[tool] = { dir: d, ok: 0, fail: 0, dismissed: false };
    return t;
  }

  var data = (SB.data = {
    // the directory a tool is currently reading (may be "")
    dir: function (tool) {
      var q = Q.get("dir") && (Q.get("tool") || SB.state.tool) === tool ? Q.get("dir") : null;
      var q2 = Q.get("dir_" + tool);
      try {
        return q || q2 || localStorage.getItem("sb.dir." + tool) || suggested[tool] || "";
      } catch (e) { return q || q2 || suggested[tool] || ""; }
    },
    setDir: function (tool, d) {
      try { localStorage.setItem("sb.dir." + tool, d || ""); } catch (e) {}
      if (SB.state.tool === tool && SB.refresh) SB.refresh();
    },
    hasDir: function (tool) { return !!data.dir(tool); },

    // fetch a view's JSON for the tool's current dir; rejects if no dir / http error
    get: function (tool, view, params) {
      var d = data.dir(tool);
      if (!d) return Promise.reject(new Error("no directory opened"));
      var tr = traceOf(tool);
      var qs = "path=" + encodeURIComponent(d);
      params = params || {};
      for (var k in params) if (params[k] != null) qs += "&" + k + "=" + encodeURIComponent(params[k]);
      return fetch("/api/" + tool + "/" + view + "?" + qs).then(function (r) {
        if (!r.ok) return r.json().then(function (e) { throw new Error(e.error || (view + " " + r.status)); },
                                        function () { throw new Error(view + " " + r.status); });
        return r.json();
      // record whether the dir was readable at all (a 200 — even {} — counts as "read ok").
      }).then(function (j) { tr.ok++; return j; }, function (err) { tr.fail++; throw err; });
    },

    // R1 — read state for the current dir: couldNotRead is true only when a real dir is
    // set and every adapter that was tried errored (none answered 200). `dismissed` lets
    // the warning be closed until the dir changes.
    readState: function (tool) {
      var d = ""; try { d = data.dir(tool); } catch (e) {}
      var t = readTrace[tool];
      if (!t || t.dir !== d) return { dir: d, ok: 0, fail: 0, dismissed: false, couldNotRead: false };
      return { dir: d, ok: t.ok, fail: t.fail, dismissed: t.dismissed,
               couldNotRead: !!d && t.ok === 0 && t.fail > 0 };
    },
    dismissRead: function (tool) { traceOf(tool).dismissed = true; },

    // convenience: get(...) but resolve to `fallback` instead of rejecting, so a
    // view can write `SB.data.getOr('wiki','notes',SAMPLE).then(render)`.
    getOr: function (tool, view, fallback, params) {
      return data.get(tool, view, params).catch(function () { return fallback; });
    },

    // the server's configured library roots + a suggested default dir per tool
    library: function () {
      return fetch("/api/library").then(function (r) { return r.ok ? r.json() : { roots: [], defaults: {} }; })
        .then(function (d) { suggested = d.defaults || {}; return d; })
        .catch(function () { return { roots: [], defaults: {} }; });
    },
  });

  // bootstrap suggested defaults once (non-blocking; modules render sample until it lands)
  data.library().then(function () { if (SB.refresh) SB.refresh(); });
})();
