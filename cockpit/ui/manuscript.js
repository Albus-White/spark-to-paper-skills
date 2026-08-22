/* ============================================================================
   SparkBoard · SPARK sub-view: 稿件 / Manuscript — cockpit/ui/manuscript.js

   A native Overleaf-like surface for the tex package a run produces — done
   natively because third-party Overleaf OAuth is a hard constraint. Exposes ONE
   global, SB.sparkManuscript(main); spark.js dispatches to it for sub==='manuscript'
   and the shell adds the <script>. This file OWNS nothing in the tool registry.

   Three tabs over a left tex file tree:
     · 源码 Source  — a monospace, line-numbered editor; an explicit Save button
                      POSTs /api/file/write (writes a <name>.bak first). Honest
                      未改动/已改动 state; Save disabled on sample / couldNotRead.
     · 预览 PDF     — the compiled main.pdf in an <iframe>; honest empty state.
     · 修订 Changes — a GitHub-PR-style edit history from /api/spark/edits: a
                      summary line, then per-edit cards with red −/green + diffs
                      and a 'jump to charge →' deep-link into Jury.

   Endpoints consumed (all guarded, all with a built-in SAMPLE fallback so the
   view is beautiful before the backend lands / when no dir is opened):
     GET  /api/spark/manuscript  → {main, pdf, files:[{name,rel,url,order}], bib}
     GET  /api/spark/edits       → {edits:[{seq,issue_id,section,passage_id,round,
                                    close_criterion,before,after,ts,applied}], source_dir}
     GET  /api/file?path=…       → raw tex/bib (per-file url)
     POST /api/file/write {path,content} → {ok,bytes,bak}   (the only mutation)

   Vanilla ES5-ish (var + function-expr), no build, no deps. Reuses the shared
   SB primitives + the sparkboard/spark CSS tokens & classes.
   ============================================================================ */
(function () {
  "use strict";
  var SB = window.SB;
  if (!SB) { if (window.console) console.error("manuscript.js requires reader.js (window.SB)"); return; }

  /* ---- tiny helpers (fall back if a sibling primitive is missing) --------- */
  var ESCMAP = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
  var esc = SB.esc || function (s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return ESCMAP[c]; }); };
  var el = SB.el || function (tag, cls, html) { var e = document.createElement(tag); if (cls) e.className = cls; if (html != null) e.innerHTML = html; return e; };
  function lang() { return SB.state && SB.state.lang === "en" ? "en" : "zh"; }
  function tx(zh, en) { return lang() === "zh" ? zh : en; }
  function toast(msg) { try { if (SB.toast) SB.toast(msg); } catch (e) {} }
  function dirOf() { try { return (SB.data && SB.data.dir) ? SB.data.dir("spark") : ""; } catch (e) { return ""; } }
  function dirOpen() { return !!dirOf(); }
  function baseName(p) { return String(p || "").replace(/[\\/]+$/, "").split(/[\\/]/).pop(); }

  /* ---- icon sprite (prefixed ms- so it never collides with sp-/i- sprites) */
  function ensureSprite() {
    if (document.getElementById("ms-sprite")) return;
    var svg = el("svg"); svg.id = "ms-sprite"; svg.setAttribute("aria-hidden", "true");
    svg.setAttribute("width", "0"); svg.setAttribute("height", "0"); svg.style.position = "absolute";
    svg.innerHTML =
      "<defs>" +
      '<g id="ms-doc" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"><path d="M4 2.2h5l3 3v8.6H4z"/><path d="M9 2.2v3h3"/><path d="M6 8.5h4M6 10.7h4"/></g>' +
      '<g id="ms-bib" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"><path d="M3.2 3.2h6.4v9.6l-3.2-1.9-3.2 1.9z"/><path d="M10.4 4.2h2.4v8.6l-1.2-.8"/></g>' +
      '<g id="ms-pdf" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"><rect x="3" y="2.4" width="10" height="11.2" rx="1.3"/><path d="M5.4 6.2h5.2M5.4 8.4h5.2M5.4 10.6h3.2"/></g>' +
      '<g id="ms-hash" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"><path d="M5.6 2.6 4.2 13.4M11.8 2.6 10.4 13.4M2.6 5.6h10.4M2.2 10.4h10.4"/></g>' +
      '<g id="ms-save" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"><path d="M3 3.4A1.4 1.4 0 0 1 4.4 2h6l2.6 2.6v7A1.4 1.4 0 0 1 11.6 13H4.4A1.4 1.4 0 0 1 3 11.6z"/><path d="M5.4 2v3.4h4.2V2M5.4 13v-3.6h5.2V13"/></g>' +
      '<g id="ms-warn" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"><path d="M8 2.6 14 12.5H2z"/><path d="M8 6.4v3.1" stroke-linecap="round"/><circle cx="8" cy="11.2" r=".7" fill="currentColor" stroke="none"/></g>' +
      '<g id="ms-check" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M3.2 8.4 6.4 11.4 12.8 4.8"/></g>' +
      '<g id="ms-arrow" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M3 8h9.4"/><path d="M9 4.6 12.6 8 9 11.4"/></g>' +
      '<g id="ms-chev" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M6 3.5 10.5 8 6 12.5"/></g>' +
      '<g id="ms-x" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><path d="M4 4 12 12M12 4 4 12"/></g>' +
      "</defs>";
    document.body.appendChild(svg);
  }
  function ic(id, cls) { return '<svg class="i ' + (cls || "") + '"><use href="#' + id + '"/></svg>'; }
  function chevIcon(dir) { return '<svg class="i sm' + (dir === "left" ? " ms-flip" : "") + '"><use href="#ms-chev"/></svg>'; }

  /* =========================================================================
     BUILT-IN SAMPLE — a tiny but faithful manuscript so the view renders out of
     the box (flagged 示例数据). Field names mirror the documented endpoint shapes.
     ========================================================================= */
  var SAMPLE_MANU = {
    main: "main.tex",
    pdf: null,   // no compiled PDF ships with the sample → honest empty state
    files: [
      { name: "main.tex", rel: "main.tex", order: 0, content:
        "\\documentclass{article}\n" +
        "\\usepackage{neurips_2025}\n" +
        "\\usepackage{graphicx}\n\n" +
        "\\title{Spark-to-Paper: Composable Agent Skills for\n" +
        "        Integrity-Gated Paper Generation}\n\n" +
        "\\begin{document}\n" +
        "\\maketitle\n\n" +
        "\\input{sections/introduction}\n" +
        "\\input{sections/approach}\n\n" +
        "\\bibliographystyle{plainnat}\n" +
        "\\bibliography{refs}\n" +
        "\\end{document}\n" },
      { name: "introduction.tex", rel: "sections/introduction.tex", order: 1, content:
        "\\section{Introduction}\n\n" +
        "Large language models can draft fluent prose, yet turning a research\n" +
        "spark into a submittable manuscript is still not one trustworthy,\n" +
        "low-friction workflow. Integrity failures --- hallucinated citations,\n" +
        "fabricated numbers --- are too often treated as stylistic risk rather\n" +
        "than build-breaking errors.\n\n" +
        "We present a zero-infrastructure, end-to-end suite realized purely as\n" +
        "composable agent skills with files-on-disk stage contracts.\n" },
      { name: "approach.tex", rel: "sections/approach.tex", order: 2, content:
        "\\section{System Design}\n\n" +
        "We let the model own all judgement while it holds the whole paper in\n" +
        "context, and let small deterministic scripts backstop only the\n" +
        "irreducible parts: lint, assemble, plot, vectorize. A single content\n" +
        "router sets one \\texttt{results\\_mode} that flips the suite between two\n" +
        "integrity regimes with opposite rules for numbers and tense.\n" }
    ],
    bib: { name: "refs.bib", rel: "refs.bib", order: 99, content:
      "@article{wang2025spark,\n" +
      "  title   = {Spark-to-Paper: Composable Agent Skills},\n" +
      "  author  = {Wang, Yiran and others},\n" +
      "  journal = {Preprint},\n" +
      "  year    = {2025}\n" +
      "}\n" }
  };

  // Sample PR-style edits — issue_ids mirror Jury's own sample docket (I-01…) so the
  // 'jump to charge' deep-link plausibly lands on a real charge in that workspace.
  var SAMPLE_EDITS = {
    source_dir: ".paper-review/ (示例)",
    edits: [
      { seq: 1, issue_id: "I-01", section: "§8 Implementation", passage_id: "p-s8-concurrency", round: 1, applied: true,
        close_criterion: "Prose and Table 4 state one identical concurrency number; no other site disagrees.",
        before: "the orchestrator runs up to 8 reviewer agents concurrently",
        after: "the orchestrator runs up to 16 reviewer agents concurrently",
        ts: "2026-08-18T09:12:00Z" },
      { seq: 2, issue_id: "I-02", section: "§7.2 / Eq. 5", passage_id: "p-s72-simthreshold", round: 1, applied: true,
        close_criterion: "Prose threshold equals the equation's value at every occurrence.",
        before: "duplicate weaknesses are merged when simThreshold = 0.7",
        after: "duplicate weaknesses are merged when simThreshold = 0.8",
        ts: "2026-08-18T09:15:00Z" },
      { seq: 3, issue_id: "I-09", section: "§1 Introduction", passage_id: "p-s1-claim", round: 2, applied: false,
        close_criterion: "Remove the unsupported quantitative claim or cite its measurement.",
        before: "achieving 94% router agreement, confirming the approach in practice",
        after: "an illustrative target; Section 9 specifies the measurement methodology",
        ts: "2026-08-18T11:40:00Z" }
    ]
  };

  /* =========================================================================
     MODULE STATE — survives re-renders so tab/file selection + unsaved drafts
     persist. Reset when the opened directory changes (a different run).
     ========================================================================= */
  var ST = { tab: "source", tabExplicit: false, sel: null, orig: {}, draft: {}, fileErr: {},
             saved: {}, treeCollapsed: false, dataKey: undefined };
  var CTX = null;     // last painted context {main,man,files,isSample,cnr,edits,editsSample}
  var TOKEN = 0;      // stale-render guard for async fetches
  var pendingFocus = null;   // (item7) explicit focus target to restore across a draw()
  var _findOpen = null;      // (item3) opener for the live source find bar, re-bound each mountSource
  var wrapOn = false;        // (item21) soft-wrap preference, persisted
  try { wrapOn = (window.localStorage && localStorage.getItem("sb.ms.wrap") === "1"); } catch (e) {}

  function resetForDir(dir) {
    if (ST.dataKey === dir) return;
    // treeCollapsed + wrapOn are per-session / persisted preferences — not per-dir state.
    ST.dataKey = dir; ST.sel = null; ST.orig = {}; ST.draft = {}; ST.fileErr = {};
    ST.saved = {}; ST.tabExplicit = false;
  }

  /* ---- normalize the file tree from the manuscript payload ---------------- */
  function normalizeFiles(man) {
    var out = [];
    var files = (man && man.files) || [];
    for (var i = 0; i < files.length; i++) {
      var f = files[i]; if (!f) continue;
      out.push({ name: f.name || baseName(f.rel) || ("file" + i), rel: f.rel || f.name || ("file" + i),
                 url: f.url || null, order: f.order == null ? i : f.order, content: f.content, kind: "tex" });
    }
    // bib may arrive as a {name,rel,url} object or a bare url string — but the server
    // sometimes ALSO lists refs.bib inside files[]; skip the separate bib then (no dupe row).
    var haveBib = false;
    for (var k = 0; k < out.length; k++) { if (/refs\.bib$/i.test(out[k].rel || out[k].name || "")) { haveBib = true; out[k].kind = "bib"; break; } }
    if (man && man.bib && !haveBib) {
      var b = man.bib;
      if (typeof b === "string") out.push({ name: "refs.bib", rel: "refs.bib", url: b, order: 99, kind: "bib" });
      else out.push({ name: b.name || baseName(b.rel) || "refs.bib", rel: b.rel || b.name || "refs.bib",
                      url: b.url || null, order: b.order == null ? 99 : b.order, content: b.content, kind: "bib" });
    }
    out.sort(function (a, b) { return a.order - b.order; });
    // tag the main file so the tree can badge it
    var mainRel = man && man.main;
    for (var k = 0; k < out.length; k++) if (out[k].rel === mainRel || out[k].name === mainRel) out[k].isMain = true;
    return out;
  }

  function selFile() {
    if (!CTX) return null;
    var files = CTX.files;
    for (var i = 0; i < files.length; i++) if (files[i].rel === ST.sel) return files[i];
    return files[0] || null;
  }
  function isSampleFile() { return !!(CTX && CTX.isSample); }

  // the on-disk path for the write endpoint: prefer the exact ?path= the backend
  // encoded into the file url (already jailed); fall back to dir + rel.
  function pathOfFile(f) {
    if (f && f.url) {
      try {
        var q = f.url.split("?")[1] || "";
        var p = new URLSearchParams(q).get("path");
        if (p) return p;
      } catch (e) {}
    }
    var dir = dirOf();
    if (!dir) return f && (f.rel || f.name) || "";
    return String(dir).replace(/[\\/]+$/, "") + "/" + (f && (f.rel || f.name) || "");
  }

  /* =========================================================================
     ENTRY — SB.sparkManuscript(main): fetch both endpoints (guarded, sample
     fallback), then paint. main is already sized by spark.js's fitMain.
     ========================================================================= */
  SB.sparkManuscript = function (main) {
    ensureSprite();
    ensureGlobalKeys();      // (item10) ⌘S / ⌘⇧S while the source tab is live
    ensureBeforeUnload();    // (item10) warn on unload while any draft is dirty
    resetForDir(dirOf());
    var token = ++TOKEN;
    main.innerHTML = "";
    main.appendChild(skeleton());

    var gm = (SB.data && SB.data.getOr) ? SB.data.getOr("spark", "manuscript", null) : Promise.resolve(null);
    var ge = (SB.data && SB.data.getOr) ? SB.data.getOr("spark", "edits", null) : Promise.resolve(null);
    Promise.all([gm, ge]).then(function (r) {
      if (token !== TOKEN) return;   // switched away before data landed
      paint(main, r[0], r[1]);
    });
  };

  function skeleton() {
    var s = el("div", "ms-root ms-skel");
    s.innerHTML = '<div class="ms-head"><div class="ms-sk-line w40"></div></div>' +
      '<div class="ms-grid"><div class="ms-tree"><div class="ms-sk-line"></div><div class="ms-sk-line"></div><div class="ms-sk-line w60"></div></div>' +
      '<div class="ms-panel"><div class="ms-sk-block"></div></div></div>';
    return s;
  }

  /* ---- read-state → couldNotRead (a real dir set, every adapter errored) --- */
  function couldNotRead() {
    try {
      var rs = (SB.data && SB.data.readState) ? SB.data.readState("spark") : null;
      return !!(rs && rs.couldNotRead && !rs.dismissed);
    } catch (e) { return false; }
  }

  function paint(main, rawMan, rawEd) {
    var realMan = (rawMan && rawMan.files && rawMan.files.length) ? rawMan : null;
    var man = realMan || SAMPLE_MANU;
    var isSample = !realMan;
    var files = normalizeFiles(man);

    // keep / default the selected file
    var have = false;
    for (var i = 0; i < files.length; i++) if (files[i].rel === ST.sel) { have = true; break; }
    if (!have) { var m = null; for (var j = 0; j < files.length; j++) if (files[j].isMain) { m = files[j]; break; } ST.sel = (m || files[0] || {}).rel || null; }

    var realEd = (rawEd && rawEd.edits && rawEd.edits.length != null && Array.isArray(rawEd.edits)) ? rawEd : null;
    var editsData = realEd || SAMPLE_EDITS;

    CTX = { main: main, man: man, files: files, isSample: isSample, cnr: couldNotRead(),
            edits: editsData.edits || [], editsSample: !realEd, sourceDir: editsData.source_dir || "" };
    // LINEAR public run: a real dir is open, the edits endpoint answered, but there is
    // no edit journal at all (source_dir null/absent + zero edits) → say so honestly,
    // never fall through to the sample-flavoured "no edits yet" ledger copy.
    CTX.editsNoJournal = !!(realEd && rawEd.source_dir == null && CTX.edits.length === 0 && !isSample);

    // (item15) smart default tab — until the user picks one for this run, land on the
    // most useful surface: recorded edits → Changes, else a compiled PDF → PDF, else Source.
    if (!ST.tabExplicit) {
      ST.tab = (CTX.edits && CTX.edits.length) ? "changes"
             : (CTX.man && CTX.man.pdf) ? "pdf" : "source";
    }
    draw();
  }

  /* =========================================================================
     DRAW — rebuild the whole surface from CTX. Cheap; per-file content is cached
     in ST so tab/file switches never re-hit the network. Keystrokes do NOT redraw
     (they patch the dirty chip + gutter in place).
     ========================================================================= */
  function draw() {
    if (!CTX) return;
    var main = CTX.main;

    // (item7) remember which keyboard-focused control we're rebuilding under, so the
    // rebuild doesn't drop focus to <body>. An explicit pendingFocus (e.g. the collapse
    // chevron) wins; otherwise infer the active tab / treeitem before we wipe the DOM.
    var focusKind = pendingFocus; pendingFocus = null;
    if (!focusKind) {
      var ae = document.activeElement;
      if (ae && main.contains(ae)) {
        if (ae.closest && ae.closest(".ms-tab")) focusKind = "tab";
        else if (ae.closest && ae.closest(".ms-tnode")) focusKind = "tree";
      }
    }

    main.innerHTML = "";
    var root = el("div", "ms-root");

    root.appendChild(headBar());
    var banner = bannerNode();
    if (banner) root.appendChild(banner);

    var grid = el("div", "ms-grid" + (ST.treeCollapsed ? " tree-collapsed" : ""));
    grid.appendChild(treeNode());
    grid.appendChild(panelNode());
    root.appendChild(grid);
    main.appendChild(root);

    wireBanner(root);
    wireTree(root);
    wireTabs(root);
    if (ST.tab === "source") mountSource(root);
    else if (ST.tab === "pdf") mountPdf(root);
    updateGlobalDirty();
    restoreFocus(root, focusKind);
  }
  function restoreFocus(root, kind) {
    if (!kind) return;
    var t = kind === "tab" ? root.querySelector(".ms-tab.sel")
          : kind === "tree" ? root.querySelector(".ms-tnode.sel")
          : root.querySelector(kind);
    if (t && t.focus) { try { t.focus(); } catch (e) {} }
  }

  /* ---- header + provenance chip ------------------------------------------- */
  function provChip() {
    var d = dirOf();
    if (!CTX.isSample && d) return '<span class="src-hint live" title="' + esc(d) + '">' + ic("ms-hash", "sm") + tx("来自 ", "from ") + esc(baseName(d)) + "</span>";
    return '<span class="src-hint sample">' + tx("示例数据", "Sample") + "</span>";
  }
  function headBar() {
    var h = el("div", "ms-head");
    var n = CTX.files.length;
    var sub = n + tx(" 个文件", " file" + (n === 1 ? "" : "s")) +
      (CTX.man && CTX.man.main ? " · " + esc(CTX.man.main) : "");
    h.innerHTML = '<div class="ms-head-l"><h2>' + tx("稿件", "Manuscript") + "</h2>" +
      '<span class="ms-sub">' + sub + "</span>" + provChip() + "</div>";
    return h;
  }

  function bannerNode() {
    // loud amber banner only when a real dir is open but this view is sample /
    // unreadable; a fresh no-dir session just carries the quiet header chip.
    if (!dirOpen()) return null;
    if (!CTX.cnr && !CTX.isSample) return null;
    var b = el("div", "sample-banner" + (CTX.cnr ? " cnr" : ""));
    b.setAttribute("role", "status");
    var head, sub;
    if (CTX.cnr) {
      head = tx("读不到这个目录", "Couldn't read this directory");
      sub = tx("无法读取 ", "couldn't read ") + esc(dirOf() || tx("(未指定目录)", "(no directory)")) + tx(" —— 下方为示例。", " — showing sample.");
    } else {
      head = tx("本次运行暂无稿件数据", "No manuscript for this run");
      sub = tx("下方为示例,不代表本次运行", "showing sample, not this run");
    }
    b.innerHTML = '<span class="sb-ic">' + ic("ms-warn") + "</span>" +
      '<div class="sb-tx"><b>' + head + "</b><span>" + sub + "</span></div>" +
      (CTX.cnr ? '<button class="btn sm ghost" data-ms-dismiss>' + tx("知道了", "Dismiss") + "</button>" : "");
    return b;
  }
  function wireBanner(scope) {
    var b = scope.querySelector("[data-ms-dismiss]"); if (!b) return;
    b.onclick = function () {
      try { if (SB.data && SB.data.dismissRead) SB.data.dismissRead("spark"); } catch (e) {}
      var bn = b.closest ? b.closest(".sample-banner") : null; if (bn) bn.remove();
    };
  }

  /* ---- left tex file tree (roving-focus treeitems) ------------------------ */
  function treeNode() {
    if (ST.treeCollapsed) return miniTreeNode();
    var aside = el("div", "ms-tree");
    aside.setAttribute("role", "tree");
    aside.setAttribute("aria-label", tx("文件树", "File tree"));
    var chev = '<button type="button" class="btn sm ghost ms-collapse" data-collapse="1" ' +
      'aria-label="' + tx("收起文件树", "Collapse file tree") + '" title="' + tx("收起文件树", "Collapse file tree") + '">' + chevIcon("left") + "</button>";
    var h = '<div class="ms-tree-h"><span>' + tx("文件", "Files") + "</span>" + chev + "</div>";
    var rows = CTX.files.map(function (f, i) {
      var sel = f.rel === ST.sel;
      var icon = f.kind === "bib" ? "ms-bib" : "ms-doc";
      return '<div class="ms-tnode' + (sel ? " sel" : "") + '" role="treeitem" data-rel="' + esc(f.rel) + '" ' +
        'aria-selected="' + (sel ? "true" : "false") + '" tabindex="' + (sel ? "0" : "-1") + '" ' +
        'title="' + esc(f.rel) + '">' +
        '<span class="ms-tic">' + ic(icon, "sm") + "</span>" +
        '<span class="ms-tname">' + esc(f.name) + "</span>" +
        (f.isMain ? '<span class="ms-tbadge">main</span>' : "") +
        '<span class="ms-tdot" aria-hidden="true"></span></div>';
    }).join("");
    aside.innerHTML = h + rows;
    return aside;
  }
  // (item21) collapsed rail: a thin icon-only switcher + an expand chevron.
  function miniTreeNode() {
    var aside = el("div", "ms-tree mini");
    aside.setAttribute("role", "tree");
    aside.setAttribute("aria-label", tx("文件树(已收起)", "File tree (collapsed)"));
    var chev = '<button type="button" class="btn sm ghost ms-collapse" data-collapse="0" ' +
      'aria-label="' + tx("展开文件树", "Expand file tree") + '" title="' + tx("展开文件树", "Expand file tree") + '">' + chevIcon("right") + "</button>";
    var rows = CTX.files.map(function (f) {
      var sel = f.rel === ST.sel;
      var icon = f.kind === "bib" ? "ms-bib" : "ms-doc";
      return '<button type="button" class="ms-mininode' + (sel ? " sel" : "") + '" data-rel="' + esc(f.rel) + '" ' +
        'title="' + esc(f.rel) + '" aria-label="' + esc(f.name) + '"' + (sel ? ' aria-current="true"' : "") + '>' +
        ic(icon, "sm") + '<span class="ms-tdot" aria-hidden="true"></span></button>';
    }).join("");
    aside.innerHTML = '<div class="ms-railtop">' + chev + "</div>" + rows;
    return aside;
  }
  function wireTree(scope) {
    // collapse / expand chevrons (present in both full + mini rails)
    Array.prototype.slice.call(scope.querySelectorAll("[data-collapse]")).forEach(function (b) {
      b.addEventListener("click", function () {
        ST.treeCollapsed = b.getAttribute("data-collapse") === "1";
        pendingFocus = ".ms-collapse"; draw();
      });
    });
    // collapsed rail switcher buttons
    Array.prototype.slice.call(scope.querySelectorAll(".ms-mininode")).forEach(function (n) {
      n.addEventListener("click", function () { selectFile(n.getAttribute("data-rel")); });
    });
    var nodes = Array.prototype.slice.call(scope.querySelectorAll(".ms-tnode"));
    function focusAt(idx) {
      if (idx < 0) idx = nodes.length - 1; if (idx >= nodes.length) idx = 0;
      nodes.forEach(function (m) { m.setAttribute("tabindex", "-1"); });
      nodes[idx].setAttribute("tabindex", "0"); nodes[idx].focus();
    }
    nodes.forEach(function (n, i) {
      n.addEventListener("click", function () { selectFile(n.getAttribute("data-rel")); });
      n.addEventListener("keydown", function (e) {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); selectFile(n.getAttribute("data-rel")); }
        else if (e.key === "ArrowDown") { e.preventDefault(); focusAt(i + 1); }
        else if (e.key === "ArrowUp") { e.preventDefault(); focusAt(i - 1); }
        else if (e.key === "Home") { e.preventDefault(); focusAt(0); }
        else if (e.key === "End") { e.preventDefault(); focusAt(nodes.length - 1); }
      });
    });
  }
  function selectFile(rel) {
    ST.tabExplicit = true;
    if (rel === ST.sel) { if (ST.tab !== "source") { ST.tab = "source"; draw(); } return; }
    ST.sel = rel; ST.tab = "source"; draw();
  }

  /* ---- center panel: tablist + the active tab's body ---------------------- */
  var TABS = [
    { id: "source", zh: "源码", en: "Source" },
    { id: "pdf", zh: "预览 PDF", en: "PDF" },
    { id: "changes", zh: "修订", en: "Changes" }
  ];
  function panelNode() {
    var panel = el("div", "ms-panel");
    var tabs = '<div class="ms-tabs" role="tablist" aria-label="' + tx("稿件视图", "Manuscript views") + '">' +
      TABS.map(function (tb) {
        var sel = tb.id === ST.tab;
        return '<button class="ms-tab' + (sel ? " sel" : "") + '" role="tab" id="ms-tab-' + tb.id + '" ' +
          'aria-selected="' + (sel ? "true" : "false") + '" aria-controls="ms-panel-body" ' +
          'tabindex="' + (sel ? "0" : "-1") + '" data-tab="' + tb.id + '">' + tx(tb.zh, tb.en) + "</button>";
      }).join("") + "</div>";
    var body = el("div", "ms-tabbody" + (ST.tab === "source" ? " is-source" : ""));
    body.id = "ms-panel-body"; body.setAttribute("role", "tabpanel");
    body.setAttribute("aria-labelledby", "ms-tab-" + ST.tab);
    if (ST.tab === "pdf") body.innerHTML = pdfHTML();
    else if (ST.tab === "changes") body.appendChild(changesNode());
    else body.innerHTML = sourceShellHTML();
    panel.innerHTML = tabs;
    panel.appendChild(body);
    return panel;
  }
  function wireTabs(scope) {
    var tabs = Array.prototype.slice.call(scope.querySelectorAll(".ms-tab"));
    function activate(idx) {
      if (idx < 0) idx = tabs.length - 1; if (idx >= tabs.length) idx = 0;
      ST.tab = tabs[idx].getAttribute("data-tab"); ST.tabExplicit = true; draw();
    }
    tabs.forEach(function (tb, i) {
      tb.addEventListener("click", function () { if (tb.getAttribute("data-tab") !== ST.tab) { ST.tab = tb.getAttribute("data-tab"); ST.tabExplicit = true; draw(); } });
      tb.addEventListener("keydown", function (e) {
        if (e.key === "ArrowRight") { e.preventDefault(); activate(i + 1); }
        else if (e.key === "ArrowLeft") { e.preventDefault(); activate(i - 1); }
        else if (e.key === "Home") { e.preventDefault(); activate(0); }
        else if (e.key === "End") { e.preventDefault(); activate(tabs.length - 1); }
      });
    });
  }

  /* =========================================================================
     TAB 1 — SOURCE: monospace, line-numbered editor + explicit Save
     ========================================================================= */
  function sourceShellHTML() {
    var f = selFile();
    if (!f) return '<div class="ms-empty">' + ic("ms-doc") + "<p>" + tx("没有可编辑的文件", "No file to edit") + "</p></div>";
    var stateChip = '<span class="ms-state" aria-live="polite"></span>';
    var unsaved = '<span class="ms-unsaved" aria-live="polite" hidden></span>';
    var wrap = '<button type="button" class="btn sm ghost ms-wrap' + (wrapOn ? " on" : "") + '" aria-pressed="' + (wrapOn ? "true" : "false") + '" ' +
      'title="' + tx("自动换行", "Soft wrap") + '">' + tx("换行", "Wrap") + "</button>";
    var saveAll = '<button type="button" class="btn sm ghost ms-saveall" disabled title="' + tx("保存所有未保存的改动 (⌘⇧S)", "Save all unsaved changes (⌘⇧S)") + '">' + ic("ms-save", "sm") + tx("全部保存", "Save all") + "</button>";
    var save = '<button class="btn sm primary ms-save" disabled title="' + tx("保存 (⌘S)", "Save (⌘S)") + '">' + ic("ms-save", "sm") + tx("保存", "Save") + "</button>";
    var find = '<div class="ms-find" data-ms-find hidden role="search" aria-label="' + tx("在文件中查找", "Find in file") + '">' +
      '<input type="text" class="ms-find-in" spellcheck="false" autocomplete="off" ' +
        'aria-label="' + tx("查找", "Find") + '" placeholder="' + tx("查找…", "Find…") + '">' +
      '<span class="ms-find-count" aria-live="polite"></span>' +
      '<button type="button" class="ms-find-btn" data-find-prev aria-label="' + tx("上一个", "Previous") + '" title="' + tx("上一个 · ⇧Enter", "Previous · ⇧Enter") + '">' + ic("ms-chev", "sm ms-cup") + "</button>" +
      '<button type="button" class="ms-find-btn" data-find-next aria-label="' + tx("下一个", "Next") + '" title="' + tx("下一个 · Enter", "Next · Enter") + '">' + ic("ms-chev", "sm ms-cdown") + "</button>" +
      '<button type="button" class="ms-find-btn" data-find-close aria-label="' + tx("关闭查找", "Close find") + '" title="' + tx("关闭 · Esc", "Close · Esc") + '">' + ic("ms-x", "sm") + "</button>" +
      "</div>";
    var hint = '<div class="ms-hint" aria-hidden="true">' +
      tx("Tab 缩进 · Esc 后 Tab 退出 · ⌘S 保存 · ⌘F 查找", "Tab indent · Esc then Tab to exit · ⌘S save · ⌘F find") + "</div>";
    return '<div class="ms-source">' +
      '<div class="ms-editorbar">' +
        '<span class="ms-fname">' + ic(f.kind === "bib" ? "ms-bib" : "ms-doc", "sm") + esc(f.name) + "</span>" +
        stateChip + '<span class="ms-bar-sp"></span>' + unsaved + wrap + saveAll + save +
      "</div>" +
      '<div class="ms-editor">' + find +
        '<div class="ms-gutter" aria-hidden="true">1</div>' +
        '<textarea class="ms-ta' + (wrapOn ? " wrap" : "") + '" wrap="' + (wrapOn ? "soft" : "off") + '" spellcheck="false" autocomplete="off" autocapitalize="off" ' +
          'aria-keyshortcuts="Control+S Control+Shift+S Control+F Tab Escape" ' +
          'aria-label="' + esc(f.name) + '">' + tx("载入中…", "Loading…") + "</textarea>" +
      "</div>" + hint +
    "</div>";
  }
  function mountSource(scope) {
    var f = selFile(); if (!f) return;
    var ta = scope.querySelector(".ms-ta"), g = scope.querySelector(".ms-gutter"),
        save = scope.querySelector(".ms-save"), saveAll = scope.querySelector(".ms-saveall"),
        wrapBtn = scope.querySelector(".ms-wrap"), editor = scope.querySelector(".ms-editor");
    if (!ta) return;
    var myTok = TOKEN, rel = f.rel;

    function fillFrom(text) {
      ta.value = text == null ? "" : text;
      syncGutter(); refreshDirty();
    }
    function ready() {
      if (myTok !== TOKEN || rel !== ST.sel) return;   // selection changed under us
      if (ST.fileErr[rel]) {
        editor.innerHTML = '<div class="ms-empty ms-fileerr">' + ic("ms-warn") + "<p>" + tx("读不到这个文件", "Couldn't read this file") + "</p>" +
          '<span class="ms-empty-note">' + esc(f.rel) + "</span></div>";
        refreshDirty();
        return;
      }
      fillFrom(ST.draft[rel] != null ? ST.draft[rel] : ST.orig[rel]);
      ta.readOnly = !!isSampleFile();
      ta.addEventListener("input", function () { ST.draft[rel] = ta.value; syncGutter(); refreshDirty(); });
      ta.addEventListener("scroll", function () { if (g) g.scrollTop = ta.scrollTop; });
      // (item10) editable-file keys: Tab/⇧Tab indent, with an Esc-then-Tab focus escape.
      if (!ta.readOnly) {
        var escToTab = false;
        ta.addEventListener("keydown", function (e) {
          if (e.key === "Escape") { escToTab = true; return; }    // arm the focus escape
          if (e.key === "Tab") {
            if (escToTab) { escToTab = false; return; }            // let focus move out
            e.preventDefault();
            indentSelection(ta, e.shiftKey);
            ST.draft[rel] = ta.value; syncGutter(); refreshDirty();
            return;
          }
          if (e.key !== "Shift") escToTab = false;
        });
      }
    }
    ensureLoaded(f, ready);
    if (save) save.addEventListener("click", function () { saveFile(f); });
    if (saveAll) saveAll.addEventListener("click", function () { saveAll_(); });

    // (item21) soft-wrap toggle — flips wrap off↔soft in place (no redraw), persisted,
    // and re-syncs the gutter so line numbers still track the visible scroll.
    if (wrapBtn) {
      wrapBtn.addEventListener("click", function () {
        wrapOn = !wrapOn;
        try { if (window.localStorage) localStorage.setItem("sb.ms.wrap", wrapOn ? "1" : "0"); } catch (e) {}
        if (wrapOn) { ta.classList.add("wrap"); ta.setAttribute("wrap", "soft"); }
        else { ta.classList.remove("wrap"); ta.setAttribute("wrap", "off"); }
        wrapBtn.classList.toggle("on", wrapOn);
        wrapBtn.setAttribute("aria-pressed", wrapOn ? "true" : "false");
        syncGutter(); ta.focus();
      });
    }

    wireFind(scope, ta);   // (item3) ⌘/Ctrl+F find bar over this textarea

    function syncGutter() {
      if (!g) return;
      var lines = ta.value.split("\n").length;
      var s = ""; for (var i = 1; i <= lines; i++) s += i + (i < lines ? "\n" : "");
      g.textContent = s; g.scrollTop = ta.scrollTop;
    }
  }
  // (item3) ⌘/Ctrl+F find bar: incremental case-insensitive substring match on ta.value,
  // Enter/⇧Enter cycles next/prev (selection + scrollIntoView), Esc closes back to the editor.
  function wireFind(scope, ta) {
    var bar = scope.querySelector("[data-ms-find]");
    if (!bar || !ta) { _findOpen = null; return; }
    var input = bar.querySelector(".ms-find-in"), count = bar.querySelector(".ms-find-count");
    var matches = [], cur = -1, term = "";
    function recompute() {
      term = input.value || ""; matches = [];
      if (term) {
        var lower = String(ta.value).toLowerCase(), needle = term.toLowerCase();
        var idx = lower.indexOf(needle), stepBy = Math.max(1, needle.length);
        while (idx !== -1) { matches.push(idx); idx = lower.indexOf(needle, idx + stepBy); }
      }
      cur = matches.length ? 0 : -1;
      paint(); if (cur >= 0) select(cur);
    }
    function paint() {
      if (count) count.textContent = term ? ((matches.length ? cur + 1 : 0) + "/" + matches.length) : "";
      bar.classList.toggle("no-match", !!term && matches.length === 0);
    }
    function select(i) {
      if (i < 0 || i >= matches.length) return;
      var at = matches[i];
      try { ta.setSelectionRange(at, at + term.length); } catch (e) {}
      scrollTaToOffset(ta, at);
    }
    function step(delta) {
      if (!matches.length) return;
      cur = (cur + delta + matches.length) % matches.length; paint(); select(cur);
    }
    function open() {
      bar.hidden = false;
      var selText = ""; try { selText = String(ta.value).slice(ta.selectionStart, ta.selectionEnd); } catch (e) {}
      if (selText && selText.indexOf("\n") === -1) input.value = selText;
      input.focus(); input.select(); recompute();
    }
    function close() { bar.hidden = true; matches = []; cur = -1; try { ta.focus(); } catch (e) {} }
    input.addEventListener("input", recompute);
    input.addEventListener("keydown", function (e) {
      if (e.key === "Enter") { e.preventDefault(); step(e.shiftKey ? -1 : 1); }
      else if (e.key === "Escape") { e.preventDefault(); close(); }
    });
    var pv = bar.querySelector("[data-find-prev]"), nx = bar.querySelector("[data-find-next]"), cl = bar.querySelector("[data-find-close]");
    if (pv) pv.addEventListener("click", function () { input.focus(); step(-1); });
    if (nx) nx.addEventListener("click", function () { input.focus(); step(1); });
    if (cl) cl.addEventListener("click", close);
    _findOpen = open;
  }
  // approximate scroll: bring the logical line of char-offset `at` into view (line-based;
  // exact with soft-wrap off, best-effort when wrapped). The gutter re-syncs via ta's scroll event.
  function scrollTaToOffset(ta, at) {
    try {
      var line = String(ta.value).slice(0, at).split("\n").length - 1;
      var lh = parseFloat(getComputedStyle(ta).lineHeight) || 20;
      var target = line * lh, view = ta.clientHeight || 0;
      if (target < ta.scrollTop || target > ta.scrollTop + view - lh) {
        ta.scrollTop = Math.max(0, target - Math.max(0, (view - lh) / 2));
      }
    } catch (e) {}
  }
  // insert 2 spaces at the caret (Tab) / outdent up to 2 leading spaces per spanned line (⇧Tab).
  function indentSelection(ta, outdent) {
    var start = ta.selectionStart, end = ta.selectionEnd, val = ta.value, IND = "  ";
    if (start === end && !outdent) {
      ta.value = val.slice(0, start) + IND + val.slice(start);
      ta.selectionStart = ta.selectionEnd = start + IND.length;
      return;
    }
    var ls = val.lastIndexOf("\n", start - 1) + 1;
    var le = val.indexOf("\n", end); if (le === -1) le = val.length;
    var lines = val.slice(ls, le).split("\n");
    var delta = 0, firstAdj = 0;
    for (var i = 0; i < lines.length; i++) {
      if (outdent) {
        var m = /^( {1,2}|\t)/.exec(lines[i]);
        if (m) { lines[i] = lines[i].slice(m[0].length); delta -= m[0].length; if (i === 0) firstAdj = -m[0].length; }
      } else { lines[i] = IND + lines[i]; delta += IND.length; if (i === 0) firstAdj = IND.length; }
    }
    ta.value = val.slice(0, ls) + lines.join("\n") + val.slice(le);
    ta.selectionStart = Math.max(ls, start + firstAdj);
    ta.selectionEnd = end + delta;
  }
  // load a file's content once → ST.orig/ST.draft; sample files carry inline content.
  function ensureLoaded(f, cb) {
    var rel = f.rel;
    if (ST.orig[rel] != null || ST.fileErr[rel]) { cb(); return; }
    if (f.content != null) { ST.orig[rel] = f.content; if (ST.draft[rel] == null) ST.draft[rel] = f.content; cb(); return; }
    if (!f.url) { ST.fileErr[rel] = true; cb(); return; }
    fetch(f.url).then(function (r) { if (!r.ok) throw new Error("read " + r.status); return r.text(); })
      .then(function (t) { ST.orig[rel] = t; if (ST.draft[rel] == null) ST.draft[rel] = t; cb(); },
            function () { ST.fileErr[rel] = true; cb(); });
  }
  function refreshDirty() {
    if (!CTX) return;
    var f = selFile(); if (!f) return;
    var main = CTX.main;
    var chip = main.querySelector(".ms-state"), save = main.querySelector(".ms-save");
    var sample = isSampleFile(), err = !!ST.fileErr[f.rel];
    var dirty = !sample && !err && (ST.draft[f.rel] !== ST.orig[f.rel]);
    if (chip) {
      if (sample) chip.innerHTML = '<span class="ms-st ms-st-sample">' + tx("示例 · 只读", "sample · read-only") + "</span>";
      else if (err) chip.innerHTML = '<span class="ms-st ms-st-bad">' + tx("读取失败", "read failed") + "</span>";
      else if (dirty) chip.innerHTML = '<span class="ms-st ms-st-dirty"><span class="ms-dot"></span>' + tx("已改动 · 未保存", "changed · unsaved") + "</span>";
      else chip.innerHTML = '<span class="ms-st ms-st-clean">' + ic("ms-check", "sm") + tx("未改动", "no changes") + "</span>";
    }
    if (save) save.disabled = sample || err || !dirty;
    updateGlobalDirty();
  }
  // (item10) every rel whose draft diverges from what's on disk (loaded, real, non-error).
  function dirtyRels() {
    var out = [];
    if (!CTX || CTX.isSample) return out;
    var files = CTX.files;
    for (var i = 0; i < files.length; i++) {
      var r = files[i].rel;
      if (ST.fileErr[r]) continue;
      if (ST.orig[r] != null && ST.draft[r] != null && ST.draft[r] !== ST.orig[r]) out.push(r);
    }
    return out;
  }
  // (item10) reflect the whole dirty set: tree dots, the 'N unsaved' cell, the Save-All button.
  function updateGlobalDirty() {
    if (!CTX) return;
    var main = CTX.main, dirty = dirtyRels(), set = {}, i;
    for (i = 0; i < dirty.length; i++) set[dirty[i]] = 1;
    var n = dirty.length;
    var marks = main.querySelectorAll(".ms-tree [data-rel]");
    for (i = 0; i < marks.length; i++) {
      if (set[marks[i].getAttribute("data-rel")]) marks[i].classList.add("is-dirty");
      else marks[i].classList.remove("is-dirty");
    }
    var uc = main.querySelector(".ms-unsaved");
    if (uc) {
      if (n > 0) { uc.textContent = n + tx(" 个未保存", " unsaved"); uc.hidden = false; }
      else { uc.textContent = ""; uc.hidden = true; }
    }
    var sa = main.querySelector(".ms-saveall");
    if (sa && !sa.classList.contains("busy")) sa.disabled = n === 0;
  }
  // (item10) shared writer → resolves with the server JSON, marks orig + saved-this-session.
  function writeFile(f) {
    var path = pathOfFile(f), content = ST.draft[f.rel];
    return fetch("/api/file/write", { method: "POST", headers: { "Content-Type": "application/json" },
                                      body: JSON.stringify({ path: path, content: content }) })
      .then(function (r) { return r.json().then(function (j) { if (!r.ok) throw new Error(j.error || ("write " + r.status)); return j; },
                                                function () { throw new Error("write " + r.status); }); })
      .then(function (j) { ST.orig[f.rel] = content; ST.saved[f.rel] = 1; return j; });
  }
  function noopSaveToast(f) {
    if (isSampleFile()) toast(tx("示例数据 · 只读,不保存", "Sample · read-only, nothing saved"));
    else if (f && ST.fileErr[f.rel]) toast(tx("读取失败 · 无法保存", "Read failed · cannot save"));
    else toast(tx("无改动 · 无需保存", "No changes to save"));
  }
  function saveFile(f) {
    if (!f) return;
    if (isSampleFile() || ST.fileErr[f.rel] || ST.draft[f.rel] === ST.orig[f.rel]) { noopSaveToast(f); return; }
    var main = CTX.main, save = main.querySelector(".ms-save");
    if (save) { save.disabled = true; save.classList.add("busy"); }
    writeFile(f).then(function (j) {
      var bak = (j && j.bak) ? baseName(j.bak) : (f.name + ".bak");
      toast(tx("已写入磁盘 · " + bak + " 已备份", "Wrote to disk · " + bak + " backed up"));
      if (save) save.classList.remove("busy");
      refreshDirty();
    }, function (err) {
      if (save) save.classList.remove("busy");
      toast(tx("写入失败:", "Write failed: ") + (err && err.message || err));
      refreshDirty();
    });
  }
  // (item10) Save-All (⌘⇧S) — sequential POST of every dirty file; honest summary toast.
  function saveAll_() {
    var dirty = dirtyRels();
    if (!dirty.length) { toast(tx("无改动 · 无需保存", "No changes to save")); return; }
    var byRel = {}; CTX.files.forEach(function (f) { byRel[f.rel] = f; });
    var sa = CTX.main.querySelector(".ms-saveall");
    if (sa) { sa.disabled = true; sa.classList.add("busy"); }
    var ok = 0, fail = 0, i = 0;
    (function next() {
      if (i >= dirty.length) {
        if (sa) sa.classList.remove("busy");
        toast(fail ? tx("已保存 " + ok + " · 失败 " + fail, "Saved " + ok + " · " + fail + " failed")
                   : tx("已全部保存 · " + ok + " 个文件", "Saved all · " + ok + " file" + (ok === 1 ? "" : "s")));
        refreshDirty();
        return;
      }
      var f = byRel[dirty[i++]];
      if (!f) { next(); return; }
      writeFile(f).then(function () { ok++; next(); }, function () { fail++; next(); });
    })();
  }

  /* =========================================================================
     TAB 2 — PDF: the compiled main.pdf, or an honest empty state
     ========================================================================= */
  function pdfHTML() {
    var url = CTX.man && CTX.man.pdf;
    if (url) {
      // (item21) passive staleness note — count files saved this session OR still dirty.
      var stale = {}, r;
      for (r in ST.saved) if (ST.saved.hasOwnProperty(r)) stale[r] = 1;
      dirtyRels().forEach(function (rr) { stale[rr] = 1; });
      var n = 0; for (r in stale) if (stale.hasOwnProperty(r)) n++;
      var note = n > 0
        ? '<div class="ms-pdfstale" role="status">' + ic("ms-warn", "sm") + "<span>" +
            tx("PDF 生成于 " + n + " 处改动之前 —— 重新编译以刷新", "PDF predates " + n + " edit" + (n === 1 ? "" : "s") + " — recompile to refresh") + "</span></div>"
        : "";
      // (item1) skeleton over the iframe (cleared on load) + an honest error overlay (shown
      // on iframe error or a load timeout) so a present-but-broken/slow PDF never renders a void.
      var loading = '<div class="ms-pdfover ms-empty ms-pdfload" data-ms-pdfload role="status" aria-live="polite">' +
        ic("ms-pdf") + "<p>" + tx("加载编译好的 PDF…", "Loading compiled PDF…") + "</p></div>";
      var errover = '<div class="ms-pdfover ms-empty ms-fileerr ms-pdferr" data-ms-pdferr hidden>' +
        ic("ms-warn") + "<p>" + tx("无法加载 PDF", "Couldn't load PDF") + "</p>" +
        '<span class="ms-empty-note">' + tx("可能已移动或需重新编译", "it may have moved or need a recompile") + "</span></div>";
      return '<div class="ms-pdfwrap">' + note +
        '<div class="ms-pdfstage">' +
          '<iframe class="ms-pdf" data-ms-pdf src="' + esc(url) + '" title="' + tx("编译好的 PDF", "Compiled PDF") + '"></iframe>' +
          loading + errover +
        "</div></div>";
    }
    var note = CTX.isSample ? tx("示例数据不含已编译 PDF。", "The sample carries no compiled PDF.")
                            : tx("本次运行还没有 main.pdf —— 编译后即可预览。", "No main.pdf for this run yet — it appears here once compiled.");
    return '<div class="ms-empty">' + ic("ms-pdf") + "<p>" + tx("没有可预览的 PDF", "No PDF to preview") + "</p>" +
      '<span class="ms-empty-note">' + note + "</span></div>";
  }
  // (item1) wire the PDF iframe: clear the loading skeleton on load; swap to the honest empty
  // state on iframe error or a load timeout. Token-guarded so a late timeout after a tab switch no-ops.
  function mountPdf(scope) {
    var iframe = scope.querySelector("[data-ms-pdf]");
    if (!iframe) return;
    var load = scope.querySelector("[data-ms-pdfload]"), err = scope.querySelector("[data-ms-pdferr]");
    var myTok = TOKEN, done = false, timer = null;
    function settle() { if (timer) { clearTimeout(timer); timer = null; } }
    function ok() { if (myTok !== TOKEN || done) return; done = true; settle(); if (load) load.hidden = true; }
    function fail() {
      if (myTok !== TOKEN || done) return; done = true; settle();
      if (load) load.hidden = true;
      if (err) err.hidden = false;
      iframe.style.display = "none";
    }
    iframe.addEventListener("load", ok);
    iframe.addEventListener("error", fail);
    timer = setTimeout(fail, 15000);
  }

  /* =========================================================================
     TAB 3 — CHANGES: a GitHub-PR-style edit history (better-than-Overleaf log)
     ========================================================================= */
  function changesNode() {
    var wrap = el("div", "ms-scroll");
    var edits = (CTX.edits || []).slice().sort(function (a, b) { return (a.seq || 0) - (b.seq || 0); });
    var secs = {}, rounds = {}, applied = 0;
    edits.forEach(function (e) { if (e.section) secs[e.section] = 1; if (e.round != null) rounds[e.round] = 1; if (e.applied) applied++; });
    var nS = Object.keys(secs).length, nR = Object.keys(rounds).length, pending = edits.length - applied;

    var summary = '<div class="ms-prhead">' +
      '<div class="ms-prtitle">' + ic("ms-arrow", "sm") + tx("修订记录", "Revision history") + "</div>" +
      '<div class="ms-prsum">' +
        '<span class="ms-prstat"><b>' + edits.length + "</b> " + tx("处修订", "edit" + (edits.length === 1 ? "" : "s")) + "</span>" +
        '<span class="ms-prstat"><b>' + nS + "</b> " + tx("个章节", "section" + (nS === 1 ? "" : "s")) + "</span>" +
        '<span class="ms-prstat"><b>' + nR + "</b> " + tx("轮", "round" + (nR === 1 ? "" : "s")) + "</span>" +
        '<span class="ms-prstat ms-prpend' + (pending > 0 ? " warn" : "") + '"><b>' + pending + "</b> " + tx("待应用", "pending") + " · <b>" + applied + "</b> " + tx("已应用", "applied") + "</span>" +
      "</div>" +
      (CTX.editsSample ? '<span class="src-hint sample">' + tx("示例数据", "Sample") + "</span>"
                       : '<span class="src-hint live" title="' + esc(CTX.sourceDir) + '">' + ic("ms-hash", "sm") + tx("来自 ", "from ") + esc(baseName(CTX.sourceDir) || CTX.sourceDir) + "</span>") +
      "</div>";

    if (!edits.length) {
      if (CTX.editsNoJournal) {
        wrap.innerHTML = summary + '<div class="ms-empty"><p>' + tx("本次运行没有编辑日志", "No edit journal for this run") + "</p></div>";
        return wrap;
      }
      wrap.innerHTML = summary + '<div class="ms-empty"><p>' + tx("本次运行还没有记录在案的修订。", "No recorded edits for this run yet.") + "</p>" +
        '<span class="ms-empty-note">' + tx("修订来自绑定的 Jury 评审台账(.paper-review/)。", "Edits come from the bound Jury ledger (.paper-review/).") + "</span></div>";
      return wrap;
    }
    wrap.innerHTML = summary + '<div class="ms-edits">' + edits.map(function (e, i) { return editCardHTML(e, i); }).join("") + "</div>";
    // wire the deep-links + apply buttons after DOM is in the fragment
    setTimeout(function () {
      Array.prototype.slice.call(wrap.querySelectorAll(".ms-jump")).forEach(function (btn) {
        btn.addEventListener("click", function () { jumpToCharge(btn.getAttribute("data-charge")); });
      });
      Array.prototype.slice.call(wrap.querySelectorAll(".ms-apply")).forEach(function (btn) {
        btn.addEventListener("click", function () { applyEdit(edits[+btn.getAttribute("data-idx")]); });
      });
    }, 0);
    return wrap;
  }
  function editCardHTML(e, idx) {
    var applied = e.applied
      ? '<span class="chip ok">' + ic("ms-check", "sm") + tx("已应用", "applied") + "</span>"
      : '<span class="chip wait">' + tx("待应用", "pending") + "</span>";
    // (item18) Apply-to-source: a persistent bordered ghost, disabled once applied or on
    // sample / read-only data (the global .btn:disabled styles the disabled state).
    var applyDisabled = !!e.applied || !!(CTX && CTX.isSample);
    var applyTitle = e.applied ? tx("这条修订已应用到源码", "this edit is already in the source")
                   : (CTX && CTX.isSample) ? tx("示例数据 · 不可应用到源码", "sample data · can't apply to source")
                   : tx("把这条修订套用到源码草稿", "apply this edit to the source draft");
    var head = '<div class="ms-edit-head">' +
      '<span class="chip mono">' + esc(e.issue_id || "—") + "</span>" +
      '<span class="ms-esec">' + esc(e.section || "—") + "</span>" +
      (e.round != null ? '<span class="chip">' + tx("第 ", "round ") + esc(e.round) + tx(" 轮", "") + "</span>" : "") +
      applied +
      '<button type="button" class="btn sm ghost ms-apply" data-idx="' + idx + '"' + (applyDisabled ? " disabled" : "") + ' title="' + applyTitle + '">' + ic("ms-check", "sm") + tx("应用到源码", "Apply to source") + "</button>" +
      (e.issue_id ? '<button class="btn sm ghost ms-jump" data-charge="' + esc(e.issue_id) + '" title="' + tx("在 Jury 打开这条指控", "open this charge in Jury") + '">' + tx("跳到指控", "jump to charge") + " " + ic("ms-arrow", "sm") + "</button>" : "") +
      "</div>";
    var crit = e.close_criterion ? '<div class="ms-ecrit"><span class="ms-ecrit-k">' + tx("关闭条件", "close criterion") + "</span>" + esc(e.close_criterion) + "</div>" : "";
    var foot = '<div class="ms-edit-foot">' +
      (e.seq != null ? "#" + esc(e.seq) : "") +
      (e.passage_id ? '<span class="ms-epass" title="passage_id">' + esc(e.passage_id) + "</span>" : "") +
      (e.ts ? '<span class="ms-ets">' + esc(fmtTs(e.ts)) + "</span>" : "") + "</div>";
    return '<div class="ms-edit">' + head + crit + diffHTML(e.before, e.after) + foot + "</div>";
  }
  // red − / green + line-colored diff (github-PR look). Multi-line before/after aware.
  function diffHTML(before, after) {
    var out = '<div class="ms-diff">';
    out += splitLines(before).map(function (l) { return diffRow("del", "−", l); }).join("");
    out += splitLines(after).map(function (l) { return diffRow("add", "+", l); }).join("");
    return out + "</div>";
  }
  function splitLines(s) { if (s == null || s === "") return [""]; return String(s).split("\n"); }
  function diffRow(kind, sign, text) {
    return '<div class="ms-dl ' + kind + '"><span class="ms-dsign">' + sign + "</span>" +
      '<span class="ms-dtext">' + esc(text) + "</span></div>";
  }
  function fmtTs(v) {
    var d = new Date(v); if (isNaN(d.getTime())) return String(v);
    function p(n) { return (n < 10 ? "0" : "") + n; }
    return d.getFullYear() + "-" + p(d.getMonth() + 1) + "-" + p(d.getDate()) + " " + p(d.getHours()) + ":" + p(d.getMinutes());
  }

  /* ---- apply an edit's before→after into the live source draft (item11) ---- */
  function ensureAllLoaded(cb) {
    var files = (CTX && CTX.files) || [], i = 0;
    (function next() { if (i >= files.length) { cb(); return; } ensureLoaded(files[i++], next); })();
  }
  function findContaining(text) {
    if (text == null || text === "") return null;
    var files = CTX.files;
    for (var i = 0; i < files.length; i++) {
      var r = files[i].rel, body = ST.draft[r] != null ? ST.draft[r] : ST.orig[r];
      if (body != null && body.indexOf(text) !== -1) return files[i];
    }
    return null;
  }
  // soft anchor: match a file whose basename shows up in the edit's section string.
  function anchorFileFor(e) {
    if (!e || !e.section) return null;
    var sec = String(e.section).toLowerCase(), files = CTX.files;
    for (var i = 0; i < files.length; i++) {
      var base = String(files[i].name || "").replace(/\.[a-z]+$/i, "").toLowerCase();
      if (base && base.length >= 3 && sec.indexOf(base) !== -1) return files[i];
    }
    return null;
  }
  function applyEdit(e) {
    if (!e) return;
    if (isSampleFile()) { toast(tx("示例数据 · 不可应用到源码", "Sample data · can't apply to source")); return; }
    var before = e.before, after = e.after == null ? "" : e.after;
    if (before == null || before === "") { toast(tx("这条修订没有可定位的原文", "This edit has no locatable source text")); return; }
    ensureAllLoaded(function () {
      var target = findContaining(before);
      if (!target) {
        // guard: before-text not found — maybe already applied, else offer open-at-anchor.
        var done = findContaining(after);
        if (done) { ST.sel = done.rel; ST.tab = "source"; ST.tabExplicit = true; draw(); toast(tx("这条修订似乎已在源码中", "This edit already appears in the source")); return; }
        var anc = anchorFileFor(e);
        if (anc) { ST.sel = anc.rel; ST.tab = "source"; ST.tabExplicit = true; draw(); toast(tx("未找到原文 · 已打开 " + anc.name + " 供手动核对", "Source text not found · opened " + anc.name + " to check by hand")); }
        else toast(tx("未找到原文 · 可能已改动或跨多个文件", "Source text not found · it may have changed or span files"));
        return;
      }
      var rel = target.rel, body = ST.draft[rel] != null ? ST.draft[rel] : ST.orig[rel];
      var at = body.indexOf(before);
      ST.draft[rel] = body.slice(0, at) + after + body.slice(at + before.length);
      ST.sel = rel; ST.tab = "source"; ST.tabExplicit = true; draw();
      focusRange(at, after.length);   // (item3d) land ON the applied range, not line 1
      toast(tx("已应用到 " + target.name + " · 记得保存", "Applied to " + target.name + " · remember to Save"));
    });
  }
  // (item3d) after a redraw, focus the textarea, select [at, at+len], scroll it into view,
  // and flash the editor so the eye lands on the edited passage.
  function focusRange(at, len) {
    var ta = CTX && CTX.main && CTX.main.querySelector(".ms-ta");
    if (!ta) return;
    try {
      ta.focus();
      ta.setSelectionRange(at, at + (len || 0));
      scrollTaToOffset(ta, at);
      var ed = ta.closest ? ta.closest(".ms-editor") : null;
      if (ed) {
        ed.classList.remove("ms-flash"); void ed.offsetWidth; ed.classList.add("ms-flash");
        setTimeout(function () { ed.classList.remove("ms-flash"); }, 900);
      }
    } catch (e) {}
  }

  /* ---- deep-link into Jury (guarded; no runtime hook is guaranteed) -------- */
  function jumpToCharge(id) {
    if (!id) return;
    // honor a runtime hook if a future Jury build exposes one; otherwise leave a
    // marker it may read, switch tools, and stay honest about what happened.
    // (item2) juryOpenCharge now navigates + returns a boolean; false → charge not found.
    try {
      if (typeof SB.juryOpenCharge === "function") {
        if (SB.juryOpenCharge(id) === false) toast(tx("已切到 Jury · 未找到指控 " + id, "Switched to Jury · charge " + id + " not found"));
        return;
      }
    } catch (e) {}
    try { SB.pendingCharge = id; } catch (e) {}
    if (SB.setTool) {
      SB.setTool("jury");
      toast(tx("已切到 Jury · 指控 " + id, "Switched to Jury · charge " + id));
    } else {
      toast(tx("指控 " + id, "Charge " + id));
    }
  }

  /* =========================================================================
     ONCE-ONLY GLOBAL WIRING — installed on first mount, guarded so they no-op
     unless the manuscript source tab is actually live.
     ========================================================================= */
  var _keyBound = false;
  function ensureGlobalKeys() {
    if (_keyBound) return; _keyBound = true;
    // capture-phase so ⌘S works from anywhere in the source view (textarea, buttons…).
    document.addEventListener("keydown", function (e) {
      if (!CTX || ST.tab !== "source") return;
      if (!CTX.main || !document.body.contains(CTX.main) || !CTX.main.querySelector(".ms-ta")) return;
      var mod = e.metaKey || e.ctrlKey;
      if (mod && (e.key === "s" || e.key === "S")) {
        e.preventDefault();
        if (e.shiftKey) saveAll_();
        else { var f = selFile(); if (f) saveFile(f); }
      } else if (mod && !e.shiftKey && (e.key === "f" || e.key === "F")) {
        e.preventDefault();               // (item3) ⌘/Ctrl+F opens the source find bar
        if (_findOpen) _findOpen();
      }
    }, true);
  }
  var _unloadBound = false;
  function ensureBeforeUnload() {
    if (_unloadBound) return; _unloadBound = true;
    window.addEventListener("beforeunload", function (e) {
      try { if (dirtyRels().length) { e.preventDefault(); e.returnValue = ""; return ""; } } catch (err) {}
    });
  }

  // (item23) fold each open tex/bib file into the ⌘K palette (guarded on dirOpen +
  // a real file list; re-read live on each palette open). Selecting jumps into the
  // manuscript sub-view with that file open.
  if (SB.registerPaletteSource) {
    SB.registerPaletteSource(function () {
      if (!dirOpen() || !CTX || CTX.isSample || !CTX.files) return [];
      return CTX.files.map(function (f) {
        return { id: "ms-" + f.rel, label: tx("稿件 ▸ ", "Manuscript ▸ ") + f.name,
                 type: tx("稿件文件", "manuscript file"),
                 run: function () { SB.setTool("spark"); if (SB.setSub) SB.setSub("manuscript"); selectFile(f.rel); } };
      });
    });
  }
})();
