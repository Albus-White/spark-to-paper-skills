/* ============================================================================
   Settings overlay (shared) — edits the same .env the cockpit already uses, via
   /api/settings. The one group that matters for the reader is "Reading assistant"
   (the DeepSeek/OpenAI key powering summary/explain/translate/ask); the pipeline
   groups (figure/vision/embed/overleaf/remote) ride along so a Spark run can be
   configured from the same place.

   Attaches by event delegation so it works no matter when the shell chrome (the
   gear button #sb-settings) is built — it never touches reader.js.
   ============================================================================ */
(function () {
  "use strict";
  var SB = window.SB;
  if (!SB) return;
  var esc = SB.esc, el = SB.el;

  document.addEventListener("click", function (e) {
    if (e.target.closest && e.target.closest("#sb-settings")) SB.openSettings();
  });

  // minimal input chrome — kept here so sparkboard.css stays the shared shell
  var css = document.createElement("style");
  css.textContent =
    ".sb-set{left:50%;top:50%;transform:translate(-50%,-50%);width:min(700px,94vw);max-height:86vh;display:flex;flex-direction:column}" +
    ".sb-set .ss-head{display:flex;align-items:center;gap:10px;padding:18px 22px 12px;border-bottom:1px solid var(--hair)}" +
    ".sb-set .ss-head h2{font-family:var(--serif);font-size:21px}" +
    ".sb-set .ss-head .env{margin-left:auto;font-family:var(--mono);font-size:11px;color:var(--faint)}" +
    ".sb-set .ss-body{overflow:auto;padding:18px 22px 22px;display:flex;flex-direction:column;gap:16px;scrollbar-width:thin}" +
    ".sb-set .grp .why{font-size:12.5px;color:var(--muted);line-height:1.45;margin:2px 0 12px}" +
    ".sb-set .fld{display:grid;grid-template-columns:180px 1fr;gap:10px;align-items:center;margin-bottom:8px}" +
    ".sb-set .fld label{font-family:var(--mono);font-size:11.5px;color:var(--muted);overflow:hidden;text-overflow:ellipsis}" +
    ".sb-set input{width:100%;height:32px;padding:0 11px;border-radius:8px;border:1px solid var(--hair-2);background:var(--well);color:var(--ink);font:inherit;font-size:13px}" +
    ".sb-set input:focus{outline:none;border-color:color-mix(in oklab,var(--accent) 55%,var(--hair-2))}" +
    // item 9 (a11y) — the plain :focus tint was likely <3:1; keyboard focus gets a real ring
    ".sb-set input:focus-visible{outline:2px solid var(--focus-ring);outline-offset:2px;border-color:color-mix(in oklab,var(--accent) 55%,var(--hair-2))}" +
    ".sb-set .grp-foot{display:flex;align-items:center;gap:10px;margin-top:6px}" +
    ".sb-set .status{font-size:12px}.sb-set .status.ok{color:var(--ok)}.sb-set .status.bad{color:var(--bad)}" +
    ".sb-set .ss-foot{display:flex;align-items:center;gap:10px;padding:14px 22px;border-top:1px solid var(--hair)}";
  document.head.appendChild(css);

  var _opener = null;   // item 9 — the control that opened Settings; focus returns to it on close
  function close() {
    var p = document.querySelector(".sb-set"); if (p) p.remove();
    var s = document.querySelector(".scrim.ss-scrim"); if (s) s.remove();
    document.removeEventListener("keydown", onKey, true);
    try { _opener && _opener.focus && _opener.focus(); } catch (e) {} _opener = null;
  }
  // item 9 (a11y) — Escape closes; Tab is trapped inside the dialog (mirrors keyHelp), wrapping
  // first↔last over the live focusable set (Save/Close/Test buttons + the .env inputs).
  function onKey(e) {
    if (e.key === "Escape") { close(); return; }
    if (e.key !== "Tab") return;
    var pop = document.querySelector(".sb-set"); if (!pop) return;
    var f = [].slice.call(pop.querySelectorAll("button,[href],input,select,textarea,[tabindex]:not([tabindex='-1'])"))
      .filter(function (n) { return !n.disabled && n.offsetParent !== null; });
    if (!f.length) return;
    var first = f[0], last = f[f.length - 1];
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    else if (!pop.contains(document.activeElement)) { e.preventDefault(); first.focus(); }
  }

  SB.openSettings = function () {
    var opener = document.activeElement;   // item 9 — remember it before close() clears state
    close();
    _opener = opener;
    var sc = el("div", "scrim ss-scrim"); sc.onclick = close; document.body.appendChild(sc);
    var pop = el("div", "pop sb-set");
    pop.setAttribute("role", "dialog"); pop.setAttribute("aria-modal", "true");
    pop.innerHTML =
      '<div class="ss-head"><svg class="i"><use href="#i-gear"/></svg>' +
      "<h2>" + esc(SB.state.lang === "en" ? "Settings & keys" : "设置与密钥") + "</h2>" +
      '<span class="env" id="ss-env"></span></div>' +
      '<div class="ss-body" id="ss-body">' + esc(SB.state.lang === "en" ? "loading…" : "加载中…") + "</div>" +
      '<div class="ss-foot"><button class="btn primary" id="ss-save">' + esc(SB.state.lang === "en" ? "Save" : "保存") +
      '</button><button class="btn ghost" id="ss-close">' + esc(SB.state.lang === "en" ? "Close" : "关闭") + "</button>" +
      '<span class="status" id="ss-msg" style="margin-left:auto"></span></div>';
    document.body.appendChild(pop);
    document.addEventListener("keydown", onKey, true);   // item 9 — capture, matched by close()'s remove
    pop.querySelector("#ss-close").onclick = close;
    pop.querySelector("#ss-save").onclick = save;
    // item 9 — move focus into the dialog on open (the close button; render() hands off to the
    // first field once the form loads)
    setTimeout(function () { var f = pop.querySelector("#ss-close") || pop.querySelector("button"); if (f) try { f.focus(); } catch (e) {} }, 20);

    fetch("/api/settings").then(function (r) { return r.json(); }).then(function (d) { render(d); }).catch(function () {
      document.getElementById("ss-body").textContent =
        SB.state.lang === "en" ? "Settings server did not answer /api/settings." : "服务器没有响应 /api/settings。";
    });
  };

  function render(d, isReload) {
    var env = document.getElementById("ss-env"); if (env) env.textContent = d.env_path || "";
    // reading-ai first — it is the reader's own model
    var groups = (d.groups || []).slice().sort(function (a, b) {
      return (a.key === "reading-ai" ? -1 : 0) - (b.key === "reading-ai" ? -1 : 0);
    });
    var body = document.getElementById("ss-body"); body.innerHTML = "";
    groups.forEach(function (g) {
      var card = el("div", "card grp"); card.dataset.group = g.key;
      var rows = g.vars.map(function (v) {
        var ph = v.secret ? (v.set ? "•••••••• （已保存 · leave blank to keep）" : "") : "";
        var val = v.secret ? "" : (v.value || "");
        return '<div class="fld"><label title="' + esc(v.name) + '">' + esc(v.name) + "</label>" +
          '<input data-name="' + esc(v.name) + '" type="' + (v.secret ? "password" : "text") +
          '" value="' + esc(val) + '" placeholder="' + esc(ph) + '" autocomplete="off" spellcheck="false"></div>';
      }).join("");
      card.innerHTML =
        '<div class="card-h"><span class="kick">' + esc(g.key) + '</span><h3>' + esc(g.title) + "</h3></div>" +
        '<div class="why">' + esc(g.why) + "</div>" + rows +
        '<div class="grp-foot"><button class="btn sm" data-test="' + esc(g.key) + '">' +
        esc(SB.state.lang === "en" ? "Test connection" : "测试连接") + '</button><span class="status" data-st="' + esc(g.key) + '"></span></div>';
      body.appendChild(card);
    });
    body.querySelectorAll("[data-test]").forEach(function (b) {
      b.onclick = function () {
        var key = b.dataset.test, st = body.querySelector('[data-st="' + key + '"]');
        st.className = "status"; st.textContent = SB.state.lang === "en" ? "testing…" : "测试中…";
        fetch("/api/settings/test", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ group: key }) })
          .then(function (r) { return r.json(); }).then(function (r) {
            st.className = "status " + (r.ok ? "ok" : "bad"); st.textContent = r.detail || (r.ok ? "ok" : "failed");
          }).catch(function () { st.className = "status bad"; st.textContent = "error"; });
      };
    });
    // item 9 — on the first load, hand initial focus from the close button to the first field;
    // don't steal focus on the post-save re-render.
    if (!isReload) {
      var pop = document.querySelector(".sb-set"), fi = body.querySelector("input");
      if (pop && fi) {
        var a = document.activeElement;
        if (!a || a === document.body || a.id === "ss-close" || a.id === "ss-save" || !pop.contains(a)) { try { fi.focus(); } catch (e) {} }
      }
    }
  }

  function save() {
    var vars = {};
    document.querySelectorAll(".sb-set input[data-name]").forEach(function (i) {
      var v = i.value.trim();
      if (v) vars[i.dataset.name] = v;             // blank = leave the stored value alone
    });
    var msg = document.getElementById("ss-msg");
    if (!Object.keys(vars).length) { msg.className = "status"; msg.textContent = SB.state.lang === "en" ? "nothing to save" : "没有改动"; return; }
    msg.className = "status"; msg.textContent = SB.state.lang === "en" ? "saving…" : "保存中…";
    fetch("/api/settings", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ vars: vars }) })
      .then(function (r) { return r.json(); }).then(function (r) {
        if (r.error) { msg.className = "status bad"; msg.textContent = r.error; return; }
        msg.className = "status ok"; msg.textContent = SB.state.lang === "en" ? "saved" : "已保存";
        render(r, true);   // item 9 — reload without yanking focus from the Save button
      }).catch(function () { msg.className = "status bad"; msg.textContent = "error"; });
  }
})();
