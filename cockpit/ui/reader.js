/* ============================================================================
   SparkBoard shell + shared reader — vanilla, no build step.
   Exposes a global `SB` used by the per-tool workspace modules (spark/jury/wiki).

   Responsibilities:
     - shell chrome: brand, TOOL SWITCHER (spark/jury/wiki), workspace title,
       sub-view tabs, theme (light/dark/system), language (zh/en)
     - the three-column reader shell + draggable splitters + Zen mode
     - the reusable Reader() reading surface (serif header, prose, AI summary
       card, the polymorphic TOC/backlinks rail, floating overlay scrollbar)
     - keyboard flow (V/C/B/N/M, Space, arrows, font size, ⌘/, Esc) scoped to
       the reader, and the restrained selection-AI action bar + popover
   A tool module calls SB.registerTool(name, {label, sub:[...], render(main,sub)}).
   ============================================================================ */
(function () {
  "use strict";
  var SB = (window.SB = window.SB || {});

  /* ---- tiny helpers ------------------------------------------------------- */
  var $ = (SB.$ = function (s, r) { return (r || document).querySelector(s); });
  var $$ = (SB.$$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); });
  var ESC = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
  var esc = (SB.esc = function (s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return ESC[c]; }); });
  function el(tag, cls, html) { var e = document.createElement(tag); if (cls) e.className = cls; if (html != null) e.innerHTML = html; return e; }
  SB.el = el;

  /* ---- reduced-motion (R28): one source of truth for JS scroll behavior ---- */
  SB.reduceMotion = function () { try { return !!(window.matchMedia && matchMedia("(prefers-reduced-motion:reduce)").matches); } catch (e) { return false; } };
  function smooth() { return SB.reduceMotion() ? "auto" : "smooth"; }
  function scrollInto(node, opts) { if (!node) return; opts = opts || {}; if (SB.reduceMotion() && opts.behavior === "smooth") opts.behavior = "auto"; try { node.scrollIntoView(opts); } catch (e) {} }
  SB.scrollInto = scrollInto;

  /* ---- persisted state ---------------------------------------------------- */
  function load(k, d) { try { var v = localStorage.getItem("sb." + k); return v == null ? d : v; } catch (e) { return d; } }
  function save(k, v) { try { localStorage.setItem("sb." + k, v); } catch (e) {} }

  /* ---- provenance interlock (item 10) ------------------------------------
     A tiny localStorage store the other tools merge into so a paper's lifecycle
     stays linked across tools: Spark links {reviewedFromRun}, Jury reads it for
     'Source: run X →', Wiki for 'Filed from <charge> →'. Defined here (early) so
     it exists the moment any sibling module calls it. */
  SB.prov = {
    get: function (paperKey) {
      try { return JSON.parse(localStorage.getItem("sb.prov." + (paperKey || "")) || "{}") || {}; } catch (e) { return {}; }
    },
    link: function (paperKey, patch) {
      if (!paperKey) return SB.prov.get(paperKey);
      var rec = SB.prov.get(paperKey);
      if (patch) for (var k in patch) if (Object.prototype.hasOwnProperty.call(patch, k)) rec[k] = patch[k];
      try { localStorage.setItem("sb.prov." + paperKey, JSON.stringify(rec)); } catch (e) {}
      return rec;
    },
  };

  // ?tool= / ?theme= / ?lang= force a state for deterministic screenshots (like the base cockpit)
  var Q = new URLSearchParams(location.search);
  var S = (SB.state = {
    tool: Q.get("tool") || load("tool", "spark"),
    theme: Q.get("theme") || load("theme", "system"),
    lang: Q.get("lang") || load("lang", /^zh/i.test(navigator.language || "") ? "zh" : "en"),   // R4: seed from browser; URL/persist override still wins
    fs: parseFloat(load("fs", "17")) || 17,
    zen: false,
    project: Q.get("project") || load("project", ""),   // R2: shared active project id ("" = unbound/default)
    cols: { c0: parseInt(load("c0", "268"), 10), c1: parseInt(load("c1", "340"), 10) },
  });

  /* ---- i18n (shell chrome only) ------------------------------------------- */
  var I18N = (SB.I18N = {
    zh: {
      "tool.spark": "Spark", "tool.jury": "Jury", "tool.wiki": "Wiki",
      "tool.spark.tag": "写论文", "tool.jury.tag": "审论文", "tool.wiki.tag": "建知识库",
      "theme": "主题", "lang": "语言 / Language", "settings": "设置与密钥", "ledger": "运行台账 — 按 i",
      "zen.hint": "ESC 退出 · ⌘/ 快捷键", "kbd": "键盘快捷键", "toc": "本页目录",
      "focus": "专注模式 (Z)", "cmdk.ph": "跳到工具 / 视图,或执行命令…",
      "ai.summary": "AI 摘要", "ai.generate": "生成摘要", "ai.regen": "重新生成",
      "ai.notyet": "尚未生成；仅在你点按后，正文才会发送给模型。",
      "ai.explain": "解释", "ai.translate": "翻译", "ai.ask": "问 AI",
      "ai.explaining": "正在结合全文理解这段文字…", "ai.translating": "正在翻译…", "ai.asking": "正在生成解答…",
      "home": "概览", "home.tag": "跨工具总览", "home.title": "SparkBoard 概览", "home.open": "打开",
      "home.spark": "Spark 运行", "home.jury": "Jury 卷宗", "home.wiki": "Wiki 知识库",
      "home.empty": "此处暂无内容", "home.needs": "待你处理", "home.viewall": "全部 →",
      "home.noread": "读不到这些目录 —— 检查库根目录或访问权限",
      "notes.rail": "批注", "notes.empty": "暂无批注",
      "home.gateblock": "闸门阻断", "home.escalated": "已升级", "home.coverage": "覆盖", "home.inbox": "收件箱 · 待人",
      "proj": "项目", "proj.default": "默认工作区", "proj.pick": "选择项目 / 工作区", "proj.root": "库根目录",
      "needs.tray": "待你处理", "needs.empty": "当前没有待处理项 🎉", "needs.dec": "决策待处置", "needs.wait": "运行等待", "needs.none": "无",
      "needs.sample": "示例数据 —— 非你的真实队列", "needs.pl": "项待你处理", "needs.dossier": "导出档案", "needs.dossier.done": "档案已复制", "skip": "跳到正文",
      "welcome.title": "欢迎来到 SparkBoard", "welcome.body": "Spark = 从灵感草拟论文 · Jury = 让每条审稿意见受审 · Wiki = 你的论文知识库。",
      "welcome.hint": "用上方的工具切换器换工具,按 ⌘K 随处跳转。", "welcome.go": "开始", "welcome.overview": "总览",
      "kh.selection": "解释选中文字", "kh.translate": "翻译选中文字", "kh.ask": "就选中文字问 AI", "kh.highlight": "标注选中文字",
      "hl.rail": "标注", "hl.empty": "暂无标注", "hl.done": "已标注",
      "intro.show": "使用简介", "intro.replay": "重看引导", "help": "帮助", "filter.focus": "聚焦筛选框",
      "cap.workspace": "工作区", "cap.paper": "论文",
      "view.saved": "保存的视图", "view.save": "保存当前视图", "view.saved.done": "已保存视图",
      "view.copylink": "复制本视图链接", "view.copylink.done": "已复制视图链接",
      "act.copy": "复制状态", "act.copied": "已复制状态", "feed.title": "动态", "feed.new": "新",
      "home.allproj": "全部项目", "home.more": "更多", "home.thisproj": "本项目",
      // launcher (一键启动) + cross-tool chain breadcrumb
      "start": "开始", "start.title": "从哪儿开始", "start.hint": "选一条路径 —— 之后随时能切换工具。",
      "start.wiki": "只用 Wiki", "start.wiki.d": "从文献知识库开始",
      "start.spark": "只用 Spark", "start.spark.d": "直接写论文",
      "start.chain": "Wiki → Spark", "start.chain.d": "灵感 → 论文 → 评审",
      "start.explore": "先四处看看",
      "chain.title": "流水线", "chain.dismiss": "关闭流水线提示",
      "chain.step.wiki": "Wiki", "chain.step.spark": "Spark", "chain.step.jury": "Jury",
    },
    en: {
      "tool.spark": "Spark", "tool.jury": "Jury", "tool.wiki": "Wiki",
      "tool.spark.tag": "write", "tool.jury.tag": "review", "tool.wiki.tag": "knowledge",
      "theme": "Theme", "lang": "Language", "settings": "Settings & keys", "ledger": "Run ledger — press i",
      "zen.hint": "ESC to exit · ⌘/ shortcuts", "kbd": "Keyboard shortcuts", "toc": "On this page",
      "focus": "Focus mode (Z)", "cmdk.ph": "Jump to a tool / view, or run a command…",
      "ai.summary": "AI Summary", "ai.generate": "Generate", "ai.regen": "Regenerate",
      "ai.notyet": "Not generated yet — the text is only sent to the model after you click.",
      "ai.explain": "Explain", "ai.translate": "Translate", "ai.ask": "Ask AI",
      "ai.explaining": "Reading this passage in the context of the whole article…", "ai.translating": "Translating…", "ai.asking": "Answering…",
      "home": "Home", "home.tag": "cross-tool overview", "home.title": "SparkBoard overview", "home.open": "Open",
      "home.spark": "Spark runs", "home.jury": "Jury dockets", "home.wiki": "Wiki knowledge base",
      "home.empty": "Nothing here yet", "home.needs": "needs you", "home.viewall": "View all →",
      "home.noread": "Couldn't read these directories — check the library root or permissions",
      "notes.rail": "Notes", "notes.empty": "No notes yet",
      "home.gateblock": "gate-blocking", "home.escalated": "escalated", "home.coverage": "coverage", "home.inbox": "inbox · awaiting",
      "proj": "Project", "proj.default": "Default workspace", "proj.pick": "Select project / workspace", "proj.root": "library root",
      "needs.tray": "Needs you", "needs.empty": "Nothing needs you right now 🎉", "needs.dec": "decisions open", "needs.wait": "runs waiting", "needs.none": "none",
      "needs.sample": "sample — not your real queue", "needs.pl": "need you", "needs.dossier": "Export dossier", "needs.dossier.done": "Dossier copied", "skip": "Skip to content",
      "welcome.title": "Welcome to SparkBoard", "welcome.body": "Spark = draft a paper from a spark idea · Jury = put every reviewer complaint on trial · Wiki = your paper knowledge base.",
      "welcome.hint": "Switch tools with the switcher above, and press ⌘K to jump anywhere.", "welcome.go": "Get started", "welcome.overview": "Overview",
      "kh.selection": "Explain selection", "kh.translate": "Translate selection", "kh.ask": "Ask AI about selection", "kh.highlight": "Highlight selection",
      "hl.rail": "Highlights", "hl.empty": "No highlights yet", "hl.done": "Highlighted",
      "intro.show": "Show intro", "intro.replay": "Replay intro", "help": "Help", "filter.focus": "Focus filter",
      "cap.workspace": "Workspace", "cap.paper": "Paper",
      "view.saved": "Saved views", "view.save": "Save current view", "view.saved.done": "View saved",
      "view.copylink": "Copy link to this view", "view.copylink.done": "View link copied",
      "act.copy": "Copy status", "act.copied": "Status copied", "feed.title": "Activity", "feed.new": "NEW",
      "home.allproj": "All projects", "home.more": "more", "home.thisproj": "This project",
      // launcher (one-click start) + cross-tool chain breadcrumb
      "start": "Start", "start.title": "Where to start?", "start.hint": "Pick a path — you can switch tools anytime.",
      "start.wiki": "Wiki only", "start.wiki.d": "Start from the literature KB",
      "start.spark": "Spark only", "start.spark.d": "Draft a paper directly",
      "start.chain": "Wiki → Spark", "start.chain.d": "Idea → paper → (review)",
      "start.explore": "Just explore",
      "chain.title": "Pipeline", "chain.dismiss": "Dismiss pipeline hint",
      "chain.step.wiki": "Wiki", "chain.step.spark": "Spark", "chain.step.jury": "Jury",
    },
  });
  var t = (SB.t = function (k) { return (I18N[S.lang] && I18N[S.lang][k]) || (I18N.en[k]) || k; });

  /* ---- theme -------------------------------------------------------------- */
  var THEME_ZH = { system: "跟随系统", light: "浅色", dark: "深色" };
  function themeLabel() {
    var m = S.theme;
    return (S.lang === "zh" ? "主题:" + (THEME_ZH[m] || m) : "Theme: " + m.charAt(0).toUpperCase() + m.slice(1));
  }
  function applyTheme() {
    var m = S.theme;
    var root = document.documentElement;
    if (m === "system") root.removeAttribute("data-theme");
    else root.setAttribute("data-theme", m);
    var b = $("#sb-theme"); if (b) { b.dataset.theme = m; b.setAttribute("aria-label", themeLabel()); b.title = themeLabel(); }
  }
  // R4 — one aria-live channel for every content swap (theme, tool/sub switch, run
  // load, toast). Owner tools call SB.onRunSwitch(title) right after a loadRun so the
  // reader swap is announced and reading focus follows it.
  SB.announce = function (msg) { var lv = $("#sb-live"); if (lv) lv.textContent = String(msg == null ? "" : msg); };
  SB.cycleTheme = function () {
    S.theme = S.theme === "system" ? "light" : S.theme === "light" ? "dark" : "system";
    save("theme", S.theme); applyTheme();
    SB.announce(themeLabel());   // announce for screen readers
  };

  /* ---- tool registry + switching ----------------------------------------- */
  var TOOLS = (SB.tools = {}); // name -> {label, accentName, sub:[{id,label}], render, curSub}
  SB.registerTool = function (name, def) { TOOLS[name] = def; def.curSub = def.sub && def.sub[0] && def.sub[0].id; };

  SB.setTool = function (name) {
    if (name !== "home" && !TOOLS[name]) return;         // "home" is a shell pseudo-tool (R4)
    S.tool = name; save("tool", name);
    document.documentElement.setAttribute("data-tool", name);
    $$(".toolsw button").forEach(function (b) { var on = b.dataset.t === name; b.classList.toggle("sel", on); b.setAttribute("aria-selected", on ? "true" : "false"); });
    var brand = $("#sb-brand"); if (brand) brand.classList.toggle("on", name === "home");
    renderWsTitle(); renderSubnav(); renderWorkspace();
    renderChain();                                       // keep the wiki→spark→jury breadcrumb's active segment in sync
    // pendingCharge passthrough (item E): the Manuscript "jump to charge" sets SB.pendingCharge + setTool('jury').
    // If Jury exposes an opener but hadn't yet when the caller ran, consume it here so the charge lands cleanly.
    if (name === "jury" && SB.pendingCharge) {
      try { if (typeof SB.juryOpenCharge === "function") { var _pc = SB.pendingCharge; SB.pendingCharge = null; SB.juryOpenCharge(_pc); } } catch (e) {}
    }
    announceView(); focusView();                         // R4: announce the swap + move reading focus
  };
  SB.setSub = function (id) {
    var tl = TOOLS[S.tool]; if (!tl) return; tl.curSub = id;
    renderSubnav(); renderWorkspace();
    announceView(); focusView();                         // R4
  };

  // R4 — describe the current view for the aria-live channel: "Spark · Reading".
  function announceView() {
    if (S.tool === "home") { SB.announce(t("home.title")); return; }
    var tl = TOOLS[S.tool]; if (!tl) return;
    var toolName = t("tool." + S.tool), sub = null;
    (tl.sub || []).forEach(function (s) { if (s.id === tl.curSub) sub = s; });
    SB.announce(toolName + (sub ? " · " + sub.label : ""));
  }
  // R4 — after a view switch, move focus to the reading surface (its scroll region /
  // h1) so keyboard reading position follows the swap. Never steals focus from an open
  // dialog/overlay. The reader shell also self-focuses on mount (see installReaderKeys);
  // this covers deep-link / run-switch paths that re-render around an existing shell.
  function overlayOpen() { return !!$(".scrim") || !!$(".ai-pop") || !!$("#sb-pal"); }
  function focusView() {
    setTimeout(function () {
      if (overlayOpen()) return;
      var a = document.activeElement;
      if (a && a !== document.body && a.closest && a.closest(".strip, .subnav, .toolsw")) return; // let a just-clicked chrome control keep focus
      var sc = $('.reader-scroll[data-reader]'); if (sc) { try { sc.focus({ preventScroll: true }); } catch (e) { try { sc.focus(); } catch (e2) {} } }
    }, 0);
  }
  // R4 — the hook owner tools (spark loadRun / jury openCharge / wiki open) call after an
  // in-place item swap that does NOT go through setTool/setSub. Announces + refocuses.
  SB.onRunSwitch = function (title) {
    if (S.tool !== "home" && TOOLS[S.tool]) SB.announce(t("tool." + S.tool) + (title ? " · " + title : ""));
    else SB.announce(title || "");
    focusView();
  };

  function renderWsTitle() {
    var host = $("#sb-wstitle"); if (!host) return;
    host.innerHTML = "";
    if (S.tool === "home") {                              // Home has no source switcher
      var hb = el("button", "titlebtn home-tt", esc(t("home.title")));
      hb.setAttribute("aria-current", "page");
      host.appendChild(hb); paintProject(); return;
    }
    var tl = TOOLS[S.tool];
    var paperName = tl && tl.title ? tl.title : t("tool." + S.tool);
    // R28e — document-glyph + "Paper: <name>" caption so this source switcher isn't
    // confused with the adjacent folder-glyph Workspace control.
    // item 3a — wrap the name in .ws-name so CSS can ellipsize it (not clip mid-word); the
    // full name lives in the button title, and the chevron never shrinks.
    // item 13 (honesty) — in sample / couldNotRead mode, append a uniform grey '· 示例 / · Sample'
    // right after the paper name in the top-bar identity. Single source of truth (unaffected by any
    // in-view banner dismissal), so Spark / Jury / Wiki ALL read as sample — not just Jury's breadcrumb.
    var wsSample = needsSample(S.tool)
      ? '<span class="ws-sample" style="color:var(--muted);font-weight:400;margin-left:1px">' + esc(S.lang === "zh" ? "· 示例" : "· Sample") + "</span>"
      : "";
    var b = el("button", "titlebtn", '<svg class="i sm ws-doc"><use href="#i-doc"/></svg><span class="ws-name">' + esc(paperName) + "</span>" + wsSample +
      ' <svg class="i sm ws-chev" style="flex:none"><use href="#i-chev"/></svg>');
    b.setAttribute("aria-haspopup", "dialog");
    b.setAttribute("aria-label", t("cap.paper") + ": " + paperName + (wsSample ? " · " + (S.lang === "zh" ? "示例" : "Sample") : ""));
    b.title = paperName;
    b.onclick = function () { if (tl && tl.onTitle) tl.onTitle(); };
    host.appendChild(b);
    paintProject();
  }
  // item 13 — the sample suffix must track the tool's read state, which resolves asynchronously
  // (a dir's fetch may fail after the top bar first paints). Re-render the title ONLY when the
  // sample state actually flips, so a focused title control isn't needlessly blurred on every poll.
  function syncWsSample() {
    var host = $("#sb-wstitle"); if (!host || S.tool === "home") return;
    if (needsSample(S.tool) !== !!$(".ws-sample", host)) renderWsTitle();
  }
  // R7 — the subnav is a fixed pill with an inner horizontal scroller. An edge fade +
  // a scroll cue appear ONLY when the tabs overflow, and the active tab is scrolled
  // into view on activation so a view is never unreachable behind a silent clip.
  function updateSubnavFade(host, sc) {
    if (!sc) return;
    var over = sc.scrollWidth - sc.clientWidth > 2;
    host.classList.toggle("scrollable", over);
    host.classList.toggle("fade-l", over && sc.scrollLeft > 2);
    host.classList.toggle("fade-r", over && sc.scrollLeft < sc.scrollWidth - sc.clientWidth - 2);
  }
  // R2 — roving ArrowLeft/Right + Home/End over the role=tablist subnav. Attached ONCE
  // to the persistent #sb-subnav host (below in mountShell) so it never leaks per render;
  // it reads the live tool/curSub, cycles SB.setSub, and re-homes focus on the new tab.
  function onSubnavKey(e) {
    if (typing(e) || e.metaKey || e.ctrlKey || e.altKey) return;
    var dir = { ArrowRight: 1, ArrowLeft: -1, Home: "home", End: "end" };
    if (!(e.key in dir)) return;
    var tl = TOOLS[S.tool]; if (S.tool === "home" || !tl || !tl.sub || tl.sub.length < 2) return;
    e.preventDefault();
    var n = tl.sub.length, cur = 0;
    for (var i = 0; i < n; i++) if (tl.sub[i].id === tl.curSub) cur = i;
    var to = dir[e.key] === "home" ? 0 : dir[e.key] === "end" ? n - 1 : (cur + dir[e.key] + n) % n;
    if (tl.sub[to].id !== tl.curSub) SB.setSub(tl.sub[to].id);
    setTimeout(function () { var a = $('#sb-subnav .tab.sel'); if (a) a.focus(); }, 0);
  }
  function renderSubnav() {
    var host = $("#sb-subnav"); if (!host) return;
    host.innerHTML = ""; host.classList.remove("scrollable", "fade-l", "fade-r");
    var tl = TOOLS[S.tool]; if (S.tool === "home" || !tl || !tl.sub) return;
    var sc = el("div", "subnav-scroll");
    var activeBtn = null;
    tl.sub.forEach(function (s) {
      var b = el("button", "tab" + (s.id === tl.curSub ? " sel" : ""), esc(s.label));
      b.setAttribute("role", "tab");
      b.setAttribute("aria-selected", s.id === tl.curSub ? "true" : "false");
      b.tabIndex = s.id === tl.curSub ? 0 : -1;          // R2: roving tabindex over the tablist
      b.onclick = function () { SB.setSub(s.id); };
      if (s.id === tl.curSub) activeBtn = b;
      sc.appendChild(b);
    });
    host.appendChild(sc);
    var upd = function () { updateSubnavFade(host, sc); };
    sc.addEventListener("scroll", upd);
    window.addEventListener("resize", upd);
    SB.onTeardown(function () { window.removeEventListener("resize", upd); });   // per-render listener
    setTimeout(function () { if (activeBtn) scrollInto(activeBtn, { inline: "nearest", block: "nearest" }); upd(); }, 0);
  }
  // Cleanup registry: a workspace (or the reader shell) registers listeners /
  // intervals here, and they are torn down before the next render — so switching
  // tools or sub-views never leaks window-level handlers or polling loops.
  SB._teardowns = [];
  SB.onTeardown = function (fn) { if (typeof fn === "function") SB._teardowns.push(fn); };
  function runTeardowns() {
    var fns = SB._teardowns; SB._teardowns = [];
    for (var i = 0; i < fns.length; i++) { try { fns[i](); } catch (e) {} }
  }

  function renderWorkspace() {
    var main = $("#sb-main"); if (!main) return;
    runTeardowns();                        // clear the previous workspace's listeners/polls
    _readerOpen = _readerHasTr = _readerHasNav = _readerHasStar = false;   // R15: reader-key context resets; installReaderKeys re-sets it if a reader mounts
    main.className = ""; main.innerHTML = "";
    if (S.tool === "home") { renderHome(main); return; }  // R4 cross-tool overview
    var tl = TOOLS[S.tool];
    if (tl && tl.render) tl.render(main, tl.curSub);
  }
  SB.refresh = renderWorkspace;

  /* ---- shell chrome ------------------------------------------------------- */
  SB.mountShell = function (root) {
    root = root || document.body;
    var app = el("div"); app.id = "sb-app"; app.className = "";
    app.innerHTML =
      '<a class="sb-skip" href="#sb-main">' + esc(t("skip")) + '</a>' +   // item 26a — visually-hidden-until-focus skip link
      '<div id="sb-appwrap" style="display:flex;flex-direction:column;height:100%">' +
      '<header class="strip">' +
        '<div class="strip-l">' +
          '<button class="brand" id="sb-brand" title="' + esc(t("home")) + '" aria-label="' + esc(t("home.title")) + '"><svg class="mark" viewBox="0 0 14 14" fill="currentColor" aria-hidden="true">' +
            '<rect x="0" y="2" width="14" height="2.4" rx="1"/><rect x="0" y="5.8" width="9" height="2.4" rx="1"/><rect x="0" y="9.6" width="4" height="2.4" rx="1"/></svg>SparkBoard</button>' +
          '<div class="toolsw" id="sb-toolsw" role="tablist" aria-label="Tool">' +
            toolBtn("spark") + toolBtn("jury") + toolBtn("wiki") +
          '</div>' +
          '<span class="strip-div"></span>' +
          '<button class="projbtn" id="sb-proj" aria-haspopup="listbox" hidden><svg class="i sm proj-ico"><use href="#i-folder"/></svg>' +
            '<span class="proj-lbl"></span><svg class="i sm proj-chev"><use href="#i-chev"/></svg></button>' +
          '<div class="ws-title" id="sb-wstitle"></div>' +
          '<div class="sb-chain" id="sb-chain" hidden></div>' +   // cross-tool wiki→spark→jury breadcrumb (light; only when SB._chain is set)
        '</div>' +
        '<div class="subnav" id="sb-subnav" role="tablist" aria-label="Sub-views"></div>' +
        '<div class="strip-r">' +
          '<span class="lamps" id="sb-lamps"></span>' +
          '<span class="strip-div"></span>' +
          '<button class="iconbtn" id="sb-copylink" title="' + esc(t("view.copylink")) + '" aria-label="' + esc(t("view.copylink")) + '"><svg class="i"><use href="#i-link"/></svg></button>' +
          '<button class="iconbtn" id="sb-zen" title="' + esc(t("focus")) + '" aria-label="' + esc(t("focus")) + '"><svg class="i"><use href="#i-zen"/></svg></button>' +
          '<button class="iconbtn" id="sb-help" title="' + esc(t("help")) + '" aria-label="' + esc(t("help")) + '"><b>?</b></button>' +
          '<button class="iconbtn langbtn" id="sb-lang" title="' + esc(t("lang")) + '"><span class="lg-seg lg-zh">中</span><span class="lg-sep">/</span><span class="lg-seg lg-en">EN</span></button>' +
          '<button class="iconbtn" id="sb-theme" title="' + esc(t("theme")) + '" data-theme="' + esc(S.theme) + '">' +
            '<svg class="i i-sys"><use href="#i-sys"/></svg><svg class="i i-sun" style="display:none"><use href="#i-sun"/></svg><svg class="i i-moon" style="display:none"><use href="#i-moon"/></svg></button>' +
          '<button class="iconbtn" id="sb-settings" title="' + esc(t("settings")) + '"><svg class="i"><use href="#i-gear"/></svg></button>' +
        '</div>' +
      '</header>' +
      '<main id="sb-main"></main>' +
      '<span id="sb-live" class="sr-only" aria-live="polite"></span>' +
      '</div>';
    root.appendChild(app);
    ensureSprite();

    $("#sb-lang").onclick = function () { S.lang = S.lang === "zh" ? "en" : "zh"; save("lang", S.lang); paintLang(); applyTheme(); renderWsTitle(); renderSubnav(); renderWorkspace(); SB.needs.render(); };
    $("#sb-theme").onclick = SB.cycleTheme;
    var zb = $("#sb-zen"); if (zb) zb.onclick = function () { SB.toggleZen(); };
    var cl = $("#sb-copylink"); if (cl) cl.onclick = function () { SB.copyView(); };   // item 7 — copy a canonical link to this view
    var hb = $("#sb-help"); if (hb) hb.onclick = function () { SB.keyHelp(); };
    var brand = $("#sb-brand"); if (brand) brand.onclick = function () { SB.setTool("home"); };   // R4 brand → Home
    var pj = $("#sb-proj"); if (pj) pj.onclick = openProjectPicker;                               // R2 project selector
    $$("#sb-toolsw button").forEach(function (b) { b.onclick = function () { SB.setTool(b.dataset.t); }; });
    var sn = $("#sb-subnav"); if (sn) sn.addEventListener("keydown", onSubnavKey);   // R2: roving tablist (attached once)

    // genuine first run (no ?tool= and no remembered tool) → Home once the library resolves
    _bootFreshTool = !Q.get("tool") && (function () { try { return localStorage.getItem("sb.tool") == null; } catch (e) { return false; } })();

    document.documentElement.setAttribute("data-tool", S.tool);
    if (S.tool === "home" && brand) brand.classList.add("on");
    applyTheme(); paintLang();
    $$(".toolsw button").forEach(function (b) { var on = b.dataset.t === S.tool; b.classList.toggle("sel", on); b.setAttribute("aria-selected", on ? "true" : "false"); });
    renderWsTitle(); renderSubnav(); renderWorkspace();
    renderChain();                          // paint the cross-tool breadcrumb if a chain hint is already set
    installGlobalKeys();
    SB.needs.start();                       // cross-tool "needs me" badges + lamps (also builds PROJECTS)
    // one-click LAUNCHER: explicit deep-link (?start=1) opens it now; otherwise the
    // first-run welcome primer routes into it via its "开始 / Get started" button. Never forced.
    if (Q.get("start") === "1") SB.launcher();
    maybeWelcome();                         // R17 one-time first-run orientation (skips itself if the launcher is open)
    // deep-link / screenshot hook: ?panel=palette|keyhelp|needs|project opens an overlay
    // once its data is ready (harmless when absent; also lets a URL open the palette).
    var _panel = Q.get("panel");
    if (_panel) {
      var tries = 0, iv = setInterval(function () {
        tries++;
        var ready = _panel === "project" ? PROJECTS.length > 0
          : _panel === "needs" ? SB.needs._loaded : true;   // wait for the poll so overlays show real data
        if (!ready && tries < 120) return;
        clearInterval(iv);
        if (_panel === "palette") SB.palette();
        else if (_panel === "keyhelp") SB.keyHelp();
        else if (_panel === "needs") SB.needs.tray();
        else if (_panel === "project") openProjectPicker();
      }, 40);
    }
  };
  function toolBtn(name) {
    // aria-label carries the tool name so the ≤1180px dot-only collapse stays accessible
    return '<button data-t="' + name + '" role="tab" aria-selected="false" aria-label="' + esc(I18N[S.lang]["tool." + name]) + '"><span class="dot" data-letter="' + esc(name.charAt(0).toUpperCase()) + '"></span>' +
      '<span data-i="tool.' + name + '">' + esc(I18N[S.lang]["tool." + name]) + '</span>' +
      '<span class="tsw-badge" data-badge="' + name + '" hidden></span></button>';
  }
  // R28a — dynamic aria-label states the current language + the action (mirrors applyTheme)
  function langLabel() { return S.lang === "zh" ? "语言:中文(点按切换为 English)" : "Language: English (activate to switch to 中文)"; }
  function paintLang() {
    try { document.documentElement.lang = S.lang; } catch (e) {}   // keep :lang(zh) CSS in sync with the toggle (index.html hard-codes zh)
    var b = $("#sb-lang"); if (b) { $(".lg-zh", b).classList.toggle("on", S.lang === "zh"); $(".lg-en", b).classList.toggle("on", S.lang === "en"); b.setAttribute("aria-label", langLabel()); b.title = langLabel(); }
    $$("[data-i]").forEach(function (n) { n.textContent = t(n.getAttribute("data-i")); });
  }

  /* ---- the three-column reader shell ------------------------------------- */
  // opts: { sidebar(el), list(el), reader:{kicker,title,meta,bodyHTML,toc:[{id,label}],backlinks:[{id,label,anno,onClick}]}, rail:'toc'|'dock'|null }
  SB.ReaderShell = function (main, opts) {
    opts = opts || {};
    var shell = el("div", "reader-shell reveal" + (S.zen ? " zen" : ""));
    shell.style.setProperty("--col0", S.cols.c0 + "px");
    shell.style.setProperty("--col1", S.cols.c1 + "px");

    var side = el("div", "col col-side");
    var list = el("div", "col col-list");
    var read = el("div", "col col-read");

    if (opts.sidebar) side.appendChild(opts.sidebar);
    if (opts.list) list.appendChild(opts.list);

    // reader column
    var rd = opts.reader || {};
    var scroll = el("div", "reader-scroll");
    var article = el("article", "reader");
    var head =
      (rd.kicker ? '<div class="kicker">' + esc(rd.kicker) + "</div>" : "") +
      (rd.title ? "<h1>" + esc(rd.title) + "</h1>" : "") +
      (rd.meta ? '<div class="meta">' + normalizeMeta(rd.meta) + "</div>" : "") +   // item 29f: unify separators
      SB.summaryCardHTML() +
      (rd.title ? '<hr class="divider">' : "");
    article.innerHTML = head + (rd.bodyHTML || "");
    scroll.appendChild(article);

    // rail
    var railWrap = null;
    if (opts.rail === "dock") {
      read.style.flexDirection = "row";
      var row = el("div", "read-row");   // flex props in CSS so @media can reflow it to a column
      row.appendChild(scroll);
      railWrap = buildDock(rd, article);
      row.appendChild(railWrap);
      read.appendChild(row);
    } else {
      read.appendChild(scroll);
      if (opts.rail !== null) read.appendChild(buildTocRail(scroll, article));
    }

    attachFloatingScrollbar(scroll);
    attachReadingProgress(scroll, article);   // item 23
    attachFontStepper(scroll);                // item 12 — on-screen A−/A+ text-size handle
    wireSummaryCard(article);
    wireSelectionAI(article);

    shell.appendChild(side);
    shell.appendChild(el("div", "splitter split-0"));
    shell.appendChild(list);
    shell.appendChild(el("div", "splitter split-1"));
    shell.appendChild(read);
    main.appendChild(shell);

    wireSplitters(shell);
    installReaderKeys(scroll, opts);
    scroll.dataset.reader = "1";
    applyFontSize();
    // item 26d — announce the loaded source (after the synchronous view announce, so the
    // specific paper title is the last thing a screen reader hears).
    if (rd.title) setTimeout(function () { if (document.body.contains(scroll)) SB.announce(rd.title); }, 0);
    return { shell: shell, scroll: scroll, article: article };
  };

  function buildTocRail(scroll, article) {
    var rail = el("div", "toc-rail");
    var heads = $$("h2,h3", article);
    if (heads.length < 3) return rail; // stays empty/hidden
    // item 18 — a hover/focus flyout so the ticks aren't an anonymous row of dots. Built in JS
    // (the SHELL-CSS agent owns sparkboard.css) so it stays self-contained; .toc-rail is already
    // position:absolute, so this absolute child anchors to it.
    var fly = el("div", "toc-flyout");
    fly.style.cssText = "position:absolute;right:100%;margin-right:8px;transform:translateY(-50%);white-space:nowrap;pointer-events:none;opacity:0;transition:opacity .12s;background:var(--raise);color:var(--ink);border:1px solid var(--hair-2);border-radius:6px;padding:3px 9px;font-size:11.5px;font-family:var(--sans);box-shadow:0 3px 10px rgba(0,0,0,.14);z-index:8;max-width:220px;overflow:hidden;text-overflow:ellipsis";
    rail.appendChild(fly);
    var focusN = 0;
    function showFly(tickEl, label) { fly.textContent = label; fly.style.top = (tickEl.offsetTop + tickEl.offsetHeight / 2) + "px"; fly.style.opacity = "1"; }
    function hideFly() { if (!focusN) fly.style.opacity = "0"; }
    heads.forEach(function (h, i) {
      if (!h.id) h.id = "h-" + i;
      var b = el("button", "tick"); b.innerHTML = "<i></i>"; b.title = h.textContent;
      b.setAttribute("aria-label", h.textContent);   // item 18 — the section name is now SR-reachable
      b.onclick = function () { h.scrollIntoView({ behavior: smooth(), block: "start" }); };
      b.addEventListener("mouseenter", function () { rail.classList.add("show"); showFly(b, h.textContent); });
      b.addEventListener("mouseleave", hideFly);
      b.addEventListener("focus", function () { focusN++; rail.classList.add("show"); showFly(b, h.textContent); });   // keep the rail up while any tick has focus
      b.addEventListener("blur", function () { focusN = Math.max(0, focusN - 1); if (!focusN) { rail.classList.remove("show"); fly.style.opacity = "0"; } });
      rail.appendChild(b);
    });
    // autohide on scroll + reflect current
    var ticks = $$(".tick", rail);
    scroll.addEventListener("scroll", function () {
      rail.classList.add("show"); clearTimeout(rail._h);
      rail._h = setTimeout(function () { if (!focusN) rail.classList.remove("show"); }, 1100);   // stay visible while a tick holds focus
      var top = scroll.scrollTop + 120, cur = 0;
      heads.forEach(function (h, i) { if (h.offsetTop <= top) cur = i; });
      ticks.forEach(function (tk, i) { tk.classList.toggle("cur", i === cur); });
    });
    return rail;
  }
  // item 14 — infer a backlink's edge KIND from its anno. Wiki's inferred annos lead with the
  // edge-kind code + " · " (see wiki.js edgeKind: ref/seed/attack/probe/feed/synth); an explicit
  // hand-written gloss carries no code, so it buckets as 'other'. Kept generic: any tool whose
  // backlinks don't match falls into one 'other' bucket and renders as a flat list (no grouping).
  var EDGE_LABELS = {
    ref: { zh: "引用", en: "Cited" }, seed: { zh: "播种", en: "Seeded" }, attack: { zh: "攻击面", en: "Attack" },
    probe: { zh: "探针", en: "Probe" }, feed: { zh: "反哺", en: "Feeds" }, synth: { zh: "综合", en: "Synthesis" },
  };
  function edgeKindOf(b) {
    var m = /^([a-z]+)\s·\s/.exec((b && b.anno) || "");
    return m && EDGE_LABELS[m[1]] ? m[1] : "other";
  }
  function edgeKindLabel(code) {
    var e = EDGE_LABELS[code];
    return e ? (S.lang === "zh" ? e.zh : e.en) : (S.lang === "zh" ? "其他" : "Other");
  }
  function buildDock(rd, article) {
    var dock = el("div", "rail-dock");
    // section TOC (top)
    var heads = $$("h2,h3", article);
    var toc = el("div", "rail-sec");
    toc.innerHTML = '<div class="rail-h">' + esc(t("toc")) + "</div>";
    if (heads.length) heads.forEach(function (h, i) {
      if (!h.id) h.id = "h-" + i;
      // item 4 (a11y) — a real <button>, so the section jump is keyboard- and SR-reachable
      var a = el("button", "rail-link", esc(h.textContent));
      a.style.paddingLeft = h.tagName === "H3" ? "18px" : "8px";
      a.onclick = function () { h.scrollIntoView({ behavior: smooth(), block: "start" }); };
      toc.appendChild(a);
    }); else toc.appendChild(el("div", "rail-empty", "—"));
    dock.appendChild(toc);
    // backlinks (bottom) — item 14: grouped by inferred edge kind with per-kind counts
    if (rd.backlinks) {
      var bl = el("div", "rail-sec");
      // item 4 (a11y) — a backlink that carries a real href navigates as a genuine <a>; an
      // onClick-only backlink becomes a <button> so it is keyboard- and SR-reachable. (shared builder)
      function blLink(b) {
        var inner = esc(b.label) + (b.anno ? '<span class="anno">' + esc(b.anno) + "</span>" : "");
        var a = b.href ? el("a", "rail-link", inner) : el("button", "rail-link", inner);
        if (b.href) a.setAttribute("href", b.href);
        if (b.onClick) a.onclick = b.onClick;
        return a;
      }
      if (!rd.backlinks.length) {
        bl.innerHTML = '<div class="rail-h">' + esc(rd.backlinksLabel || "Backlinks") + "</div>";
        bl.appendChild(el("div", "rail-empty", esc(S.lang === "zh" ? "暂无反向链接" : "No inbound links yet")));
      } else {
        // item 14 — bucket by edge kind; a per-kind count summary rides in the header and each kind is
        // a collapsible subsection (the per-link anno is preserved). One-bucket cases (e.g. non-wiki
        // backlinks that carry no kind code) fall back to a flat list so there's no empty chrome.
        var ORDER = ["ref", "seed", "attack", "probe", "feed", "synth", "other"], groups = {};
        rd.backlinks.forEach(function (b) { var k = edgeKindOf(b); (groups[k] = groups[k] || []).push(b); });
        var present = ORDER.filter(function (k) { return groups[k] && groups[k].length; });
        var summary = present.map(function (k) { return edgeKindLabel(k) + " " + groups[k].length; }).join(" · ");
        bl.innerHTML = '<div class="rail-h">' + esc(rd.backlinksLabel || "Backlinks") + "</div>" +
          (present.length > 1 ? '<div class="rail-blsum" style="font-size:11px;color:var(--muted);padding:0 8px 4px">' + esc(summary) + "</div>" : "");
        if (present.length <= 1) {
          rd.backlinks.forEach(function (b) { bl.appendChild(blLink(b)); });
        } else {
          present.forEach(function (k) {
            var sub = el("div", "rail-subsec");
            var head = el("button", "rail-subhead");
            head.style.cssText = "display:flex;align-items:center;gap:6px;width:100%;border:0;background:transparent;color:var(--muted);cursor:pointer;font:inherit;font-size:11px;text-transform:uppercase;letter-spacing:.04em;padding:6px 8px 3px;text-align:left";
            head.setAttribute("aria-expanded", "true");
            head.innerHTML = '<span class="rail-subchev" aria-hidden="true" style="display:inline-block;transition:transform .12s">▾</span><b style="font-weight:600">' + esc(edgeKindLabel(k)) + '</b><span style="opacity:.7">' + groups[k].length + '</span>';
            var body = el("div", "rail-subbody");
            groups[k].forEach(function (b) { body.appendChild(blLink(b)); });
            head.onclick = function () {
              var open = body.style.display !== "none";
              body.style.display = open ? "none" : "";
              head.setAttribute("aria-expanded", open ? "false" : "true");
              var chev = $(".rail-subchev", head); if (chev) chev.style.transform = open ? "rotate(-90deg)" : "";
            };
            sub.appendChild(head); sub.appendChild(body);
            bl.appendChild(sub);
          });
        }
      }
      dock.appendChild(bl);
    }
    if (rd.railExtra) dock.appendChild(rd.railExtra);
    // R21 — persistent highlights: re-apply saved marks, then list them (reuses the rail-section builder)
    var hlKey = paperKey(article);
    reapplyHighlights(article, hlKey);
    var hlSec = buildHlSec(article, hlKey);
    dock.appendChild(hlSec);
    article._hlSec = hlSec; article._hlKey = hlKey;
    // item 30 — pinned Explain/Ask notes live in a sibling section keyed the same way
    var noteSec = buildNotesSec(article, hlKey);
    dock.appendChild(noteSec);
    article._noteSec = noteSec; article._noteKey = hlKey;
    return dock;
  }

  /* ---- floating overlay scrollbar ---------------------------------------- */
  function attachFloatingScrollbar(scroll) {
    var bar = el("div", "fscroll");
    scroll.parentElement.style.position = "relative";
    scroll.parentElement.appendChild(bar);
    var hide;
    function update() {
      var h = scroll.clientHeight, sh = scroll.scrollHeight;
      if (sh <= h + 2) { bar.style.display = "none"; return; }
      bar.style.display = "";
      var track = h - 12, thumb = Math.max(24, track * h / sh);
      var top = 6 + (track - thumb) * (scroll.scrollTop / (sh - h));
      bar.style.height = thumb + "px"; bar.style.top = top + "px";
      bar.classList.add("on"); clearTimeout(hide);
      hide = setTimeout(function () { bar.classList.remove("on", "hot"); }, 700);
    }
    scroll.addEventListener("scroll", update);
    window.addEventListener("resize", update);
    SB.onTeardown(function () { window.removeEventListener("resize", update); });  // don't leak across renders
    scroll.parentElement.addEventListener("mousemove", function (e) {
      var r = scroll.parentElement.getBoundingClientRect();
      if (e.clientX > r.right - 22) { bar.classList.add("hot"); update(); }
    });
    setTimeout(update, 30);
  }

  /* ---- item 10 — script-aware length + reading time. A whitespace split is meaningless for CJK
     (a whole Chinese paragraph collapses to one 'word'), so count CJK by codepoint and the rest by
     whitespace-word, and estimate minutes with per-script rates (~350 字/min CJK, ~220 wpm Latin).
     The dominant script picks the unit label ('字' vs 'words'). Shared by the reading-time readout
     and the summary cap caveat. */
  var CJK_RE = /[㐀-鿿豈-﫿]/g;
  function scriptStats(s) {
    s = String(s == null ? "" : s);
    var cjk = (s.match(CJK_RE) || []).length;
    var latin = (s.replace(CJK_RE, " ").trim().match(/\S+/g) || []).length;
    return { cjk: cjk, latin: latin, mins: cjk / 350 + latin / 220, cjkDominant: cjk >= latin };
  }

  /* ---- item 8 — the AI summary source AND the reading-time count must see the PROSE, not the
     reader chrome (the AI summary card, story-card, status bar, gloss). Spark wraps its reading
     proposal body in `<div class="reader-body">`; read that when present, else fall back to the
     whole article so tools that don't wrap keep working unchanged. */
  function proseNode(article) {
    return (article && article.querySelector && article.querySelector(".reader-body")) || article;
  }

  /* ---- item 23/28 — reading-progress bar (now click/drag to SEEK) + a back-to-top chevron once
     scrolled past a viewport + optional time-left. Reduced-motion aware. */
  function attachReadingProgress(scroll, article) {
    var host = scroll.parentElement; if (!host) return;
    var zh = S.lang === "zh";
    // item 28 — the bar gets a taller (8px) transparent hit area so a 2px line is actually grabbable;
    // the visible fill sits flush at the very top. The font stepper starts at y=8px, so no overlap.
    var bar = el("div", "reader-progress");
    bar.style.cssText = "position:absolute;left:0;top:0;height:8px;width:100%;z-index:6;cursor:pointer";
    bar.setAttribute("role", "slider");
    bar.setAttribute("aria-label", zh ? "阅读进度(点按或拖动跳转)" : "Reading progress (click or drag to seek)");
    bar.setAttribute("aria-orientation", "horizontal");
    bar.setAttribute("aria-valuemin", "0"); bar.setAttribute("aria-valuemax", "100");
    var fill = el("div", "reader-progress-fill");
    fill.style.cssText = "position:absolute;left:0;top:0;height:2px;width:0;background:var(--accent,#C0552A);" + (SB.reduceMotion() ? "" : "transition:width .12s linear");   // honor reduced-motion
    bar.appendChild(fill); host.appendChild(bar);
    // item 28 — seek: map click / drag x → scrollTop (instant, so the position tracks the pointer)
    function seekTo(clientX) {
      var rect = bar.getBoundingClientRect(); if (rect.width <= 0) return;
      var frac = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width));
      var max = scroll.scrollHeight - scroll.clientHeight;
      scroll.scrollTop = frac * (max > 0 ? max : 0);
    }
    bar.addEventListener("mousedown", function (e) {
      e.preventDefault(); seekTo(e.clientX);
      function mv(ev) { seekTo(ev.clientX); }
      function up() { document.removeEventListener("mousemove", mv); document.removeEventListener("mouseup", up); }
      document.addEventListener("mousemove", mv); document.addEventListener("mouseup", up);
    });
    // '~N min left' estimate = remaining reading-time (script-aware, item 10), parked near the top rail
    var stat = article ? scriptStats(proseNode(article).textContent) : { mins: 0 };
    var mins = el("div", "read-mins");
    // item 22 (a11y) — full-opacity var(--muted) at 12px (was opacity:.55 ≈ 2.5:1, failed AA for the small CJK '分钟')
    mins.style.cssText = "position:absolute;right:12px;top:40px;z-index:6;font-size:12px;color:var(--muted);pointer-events:none;font-family:var(--sans)";
    host.appendChild(mins);
    // item 28 — a back-to-top chevron, shown only once scrolled past one viewport; reduced-motion aware
    var topBtn = el("button", "reader-top");
    topBtn.type = "button";
    topBtn.innerHTML = '<svg class="i sm" style="transform:rotate(180deg)"><use href="#i-chev"/></svg>';
    var topLbl = zh ? "回到顶部" : "Back to top";
    topBtn.setAttribute("aria-label", topLbl); topBtn.title = topLbl;
    topBtn.style.cssText = "position:absolute;right:14px;bottom:16px;z-index:8;display:none;align-items:center;justify-content:center;width:34px;height:34px;border-radius:50%;border:1px solid var(--hair-2);background:var(--raise);color:var(--ink);cursor:pointer;box-shadow:0 2px 8px rgba(0,0,0,.16)";
    topBtn.onclick = function () { scroll.scrollTo({ top: 0, behavior: smooth() }); try { scroll.focus({ preventScroll: true }); } catch (e) {} };
    host.appendChild(topBtn);
    function upd() {
      var max = scroll.scrollHeight - scroll.clientHeight;
      var p = max > 2 ? Math.min(1, Math.max(0, scroll.scrollTop / max)) : 1;
      fill.style.width = (p * 100).toFixed(1) + "%";
      bar.setAttribute("aria-valuenow", Math.round(p * 100));
      var left = Math.ceil(stat.mins * (1 - p));
      mins.textContent = (stat.mins > 1.8 && p < 0.985 && left > 0) ? (S.lang === "zh" ? "还剩约 " + left + " 分钟" : "~" + left + " min left") : "";
      topBtn.style.display = scroll.scrollTop > scroll.clientHeight ? "flex" : "none";   // > 1 viewport
    }
    scroll.addEventListener("scroll", upd);
    window.addEventListener("resize", upd);
    SB.onTeardown(function () { window.removeEventListener("resize", upd); });
    setTimeout(upd, 30);
  }
  // item 29f — unify bare " · " separators in a tool-provided reader meta to the styled
  // bullet, leaving already-styled (class="b") or structured (wiki chiprow/fmline) metas alone.
  function normalizeMeta(m) {
    if (!m || typeof m !== "string") return m || "";
    // item 2 — never rewrite a meta that already carries structured markup. Beyond the
    // styled bullet (class="b") and wiki chiprow/fmline, guard ANY string with a title="…"
    // attribute or a class="chip…" element (the jury degraded-reviewer chip): a blind
    // ' · '→<span> replace would fire INSIDE those attributes and dump raw HTML onto the page.
    // chargeMeta emits no visible ' · ' separator, so skipping these is lossless.
    if (m.indexOf('class="b"') >= 0 || m.indexOf("chiprow") >= 0 || m.indexOf("fmline") >= 0 ||
        m.indexOf('title="') >= 0 || m.indexOf('class="chip') >= 0) return m;
    return m.replace(/ · /g, '<span class="b">·</span>');
  }

  /* ---- draggable splitters ----------------------------------------------- */
  function wireSplitters(shell) {
    $$(".splitter", shell).forEach(function (sp, idx) {
      sp.onmousedown = function (e) {
        // item 16 — ≤1080 the responsive grid caps col0/col1 at 224/272 while the drag floors
        // are 240/280, so dragging-narrower was inert dead motion. SHELL-CSS hides .splitter at
        // that width; disable the drag here too so the control is never a silent no-op.
        if (window.matchMedia && window.matchMedia("(max-width:1080px)").matches) return;
        e.preventDefault(); sp.classList.add("drag");
        var startX = e.clientX, c0 = S.cols.c0, c1 = S.cols.c1;
        function mv(ev) {
          var d = ev.clientX - startX;
          if (idx === 0) { S.cols.c0 = Math.max(240, Math.min(340, c0 + d)); shell.style.setProperty("--col0", S.cols.c0 + "px"); }
          else { S.cols.c1 = Math.max(280, Math.min(560, c1 + d)); shell.style.setProperty("--col1", S.cols.c1 + "px"); }
        }
        function up() { document.removeEventListener("mousemove", mv); document.removeEventListener("mouseup", up); sp.classList.remove("drag"); save("c0", S.cols.c0); save("c1", S.cols.c1); }
        document.addEventListener("mousemove", mv); document.addEventListener("mouseup", up);
      };
    });
  }

  /* ---- font size ---------------------------------------------------------- */
  function applyFontSize() { document.documentElement.style.setProperty("--read-fs", S.fs + "px"); }
  SB.font = function (d) {
    S.fs = d === 0 ? 17 : Math.max(13, Math.min(25, S.fs + d)); save("fs", S.fs); applyFontSize();
    var v = $(".font-step-val"); if (v) v.textContent = Math.round(S.fs) + "px";   // item 12 — keep the on-screen stepper in sync with ⌘ +/−/0
  };
  // item 12 — an on-screen text-size handle at the top of the reader column: A− / current px
  // (click to reset) / A+. Buttons call SB.font, which repaints the px readout, so text size
  // has a visible handle instead of being a keyboard-only affordance.
  function buildFontStepper() {
    var wrap = el("div", "font-step");
    wrap.style.cssText = "display:inline-flex;align-items:center;gap:1px;background:var(--raise);border:1px solid var(--hair-2);border-radius:8px;padding:1px;box-shadow:0 1px 3px rgba(0,0,0,.08)";
    var zh = S.lang === "zh";
    function mk(html, label, fn) {
      var b = el("button", "font-step-btn", html);
      b.style.cssText = "border:0;background:transparent;color:var(--ink);cursor:pointer;font:inherit;font-size:13px;line-height:1;padding:4px 8px;border-radius:6px";
      b.setAttribute("aria-label", label); b.title = label;
      b.onclick = function (e) { e.preventDefault(); e.stopPropagation(); fn(); };
      return b;
    }
    wrap.appendChild(mk("A<span style='font-size:9px'>−</span>", zh ? "缩小字号" : "Decrease text size", function () { SB.font(-1); }));
    var val = el("button", "font-step-val", Math.round(S.fs) + "px");
    val.style.cssText = "border:0;background:transparent;color:var(--muted);cursor:pointer;font:inherit;font-size:11px;min-width:36px;text-align:center;border-radius:6px;font-variant-numeric:tabular-nums";
    val.setAttribute("aria-label", zh ? "重置字号" : "Reset text size"); val.title = zh ? "重置字号" : "Reset text size";
    val.onclick = function (e) { e.preventDefault(); e.stopPropagation(); SB.font(0); };
    wrap.appendChild(val);
    wrap.appendChild(mk("A<span style='font-size:13px'>+</span>", zh ? "放大字号" : "Increase text size", function () { SB.font(1); }));
    return wrap;
  }
  // item 12 — a sticky handle pinned to the top-right of the READING area (inside .reader-scroll, so
  // it clears the dock rail and the centered article's right margin), via a zero-height sticky bar so
  // it takes no layout space yet stays visible as the article scrolls.
  function attachFontStepper(scroll) {
    if (!scroll) return;
    var bar = el("div");
    bar.style.cssText = "position:sticky;top:0;z-index:7;display:flex;justify-content:flex-end;align-items:flex-start;height:0;pointer-events:none";
    var st = buildFontStepper();
    st.style.pointerEvents = "auto"; st.style.margin = "8px 10px 0";
    bar.appendChild(st);
    scroll.insertBefore(bar, scroll.firstChild);
  }

  /* ---- Zen mode ----------------------------------------------------------- */
  SB.toggleZen = function () {
    S.zen = !S.zen;
    var sh = $(".reader-shell"); if (sh) sh.classList.toggle("zen", S.zen);
    // item 11a — stamp data-zen on <html> so SHELL-CSS's `:root[data-zen] .strip` can hide the
    // masthead in Zen (it's a sibling of #sb-main, so the .reader-shell.zen scope never reaches it).
    var de = document.documentElement;
    if (S.zen) de.setAttribute("data-zen", "1"); else de.removeAttribute("data-zen");
    if (S.zen) SB.toast(t("zen.hint"));
  };

  /* ---- AI summary card + selection AI (restrained) ----------------------- */
  SB.summaryCardHTML = function () {
    return '<div class="sum-card" data-sum><div class="sum-head">' +
      '<svg class="i sm spark"><use href="#i-spark"/></svg>' +
      '<span class="tt">' + esc(t("ai.summary")) + '</span>' +
      '<span class="pv sum-pv"></span>' +
      '<button class="sum-copy" aria-label="' + esc(copyLabel()) + '" title="' + esc(copyLabel()) + '" hidden><svg class="i sm"><use href="#i-copy"/></svg></button>' +
      '<button class="chev" aria-expanded="false" aria-label="' + esc(S.lang === "zh" ? "展开 / 收起 AI 摘要" : "Toggle AI summary") + '"><svg class="i sm"><use href="#i-chev"/></svg></button>' +
      '</div><div class="sum-body"><div class="sum-empty">' + esc(t("ai.notyet")) +
      ' <button class="btn sm" data-sum-gen style="margin-top:8px">' + esc(t("ai.generate")) + "</button></div></div></div>";
  };
  function wireSummaryCard(article) {
    var card = $("[data-sum]", article); if (!card) return;
    var body = $(".sum-body", card), pv = $(".sum-pv", card), copyBtn = $(".sum-copy", card), chev = $(".chev", card), full = "";
    var CAP = 6000, key = "sb.sum." + paperKey(article);   // item 24 — cache keyed per paper (survives lang toggle + prev/next)
    function toggle() {
      var open = card.classList.toggle("open");
      if (chev) chev.setAttribute("aria-expanded", open ? "true" : "false");   // item 26d
    }
    $(".sum-head", card).onclick = function (e) { if (e.target.closest("[data-sum-gen],[data-sum-regen],.sum-copy")) return; toggle(); };
    card._toggle = toggle;
    wireCopy(copyBtn, function () { return full; });     // R20: copies the generated summary
    // item 24 — when the source overran the cap, disclose it instead of truncating silently.
    // item 10 — script-aware: report the dominant script's count with its own unit ('字' vs 'words'),
    // so a Chinese paper no longer reads as '~1 word'.
    function totalStat() { return scriptStats(proseNode(article).textContent); }
    function capCaveat() {
      var st = totalStat(), n = st.cjkDominant ? st.cjk : st.latin, unit = st.cjkDominant ? "字" : "words";
      return S.lang === "zh" ? ("仅为开头部分的摘要 —— 全文约 " + n + " " + unit) : ("summary of the opening — full paper ~" + n + " " + unit);
    }
    function totalWords() { var st = totalStat(); return st.cjkDominant ? st.cjk : st.latin; }
    function tail(done, capped, words) {
      return (done ? (capped ? '<div class="sum-caveat">' + esc(capCaveat()) + "</div>" : "") +
        '<div class="sum-actions"><button class="btn sm ghost" data-sum-regen>' + esc(t("ai.regen")) + "</button></div>" : "");
    }
    function wireRegen() { var rg = $("[data-sum-regen]", card); if (rg) rg.onclick = function (e) { e.stopPropagation(); generate(); }; }
    function loadCache() { try { return JSON.parse(localStorage.getItem(key) || "null"); } catch (e) { return null; } }
    function saveCache(o) { try { localStorage.setItem(key, JSON.stringify(o)); } catch (e) {} }
    function paint(text, done, capped, words) {
      full = text;
      body.innerHTML = SB.mdLite(text) + tail(done, capped, words);
      pv.textContent = plainMd(text).slice(0, 80);       // R25: strip inline markdown from the collapsed one-line preview
      if (copyBtn) copyBtn.hidden = !text;
      if (done) wireRegen();
    }
    // item 17 — a per-card sequence token: a superseded summary run's late chunks are dropped so a
    // stale callback can't clobber a newer summary. Paired with the transport's dedicated "summary"
    // channel (item 17), which keeps a selection Explain/Ask/Translate from aborting the summary.
    var genSeq = 0;
    function generate() {
      var mySeq = ++genSeq;
      body.innerHTML = '<div class="sum-empty">' + esc(t("ai.summary")) + " …</div>";
      if (copyBtn) copyBtn.hidden = true;
      // item 8 — summarize the PROSE (.reader-body when present), not the surrounding reader chrome.
      var whole = proseNode(article).textContent, capped = whole.length > CAP, words = totalWords();
      SB.ai({ op: "summary", text: whole.slice(0, CAP), channel: "summary" }, function (chunk, done, f) {
        if (mySeq !== genSeq) return;                    // a newer generate() superseded this run — ignore
        paint(f, done, capped, words);
        if (done) saveCache({ text: f, lang: S.lang, ts: Date.now(), capped: capped, words: words });
      });
    }
    // item 24 — restore a cached summary so it survives a language toggle / prev-next (kept
    // collapsed; the one-line preview shows, Regenerate re-runs it in the current language).
    var cached = loadCache();
    if (cached && cached.text) paint(cached.text, true, !!cached.capped, cached.words || totalWords());
    var gen = $("[data-sum-gen]", card);
    if (gen) gen.onclick = function () { generate(); };
  }
  // R10 — a keyboard-origin selection also surfaces the bar. We split mouse vs keyboard
  // so the two don't fight: mouse selection is handled on mouseup; keyboard selection
  // (caret browsing / Shift+arrows) is handled via a debounced selectionchange while no
  // mouse button is down. selectionInside() also gates the bar to the reader's own text.
  var _mdown = false;
  document.addEventListener("mousedown", function () { _mdown = true; });
  document.addEventListener("mouseup", function () { _mdown = false; });
  // item 17 — the working cap for an AI action over a selection. A selection over the cap is
  // NOT "no selection": callers that pass allowLong get it back flagged .long so they can show a
  // disabled bar / honest hint instead of the misleading "select text first" path.
  // item 28 — Explain/Ask accept a longer selection (~1200 chars); Translate stays tight (~400) —
  // a long parallel translation is unwieldy and costly. selectionInside() gates on the larger cap
  // (so the bar still appears up to 1200); the translate action is capped separately by callers.
  var SEL_CAP = 1200, SEL_CAP_TR = 400;
  function selTooLongMsg(cap) { cap = cap || SEL_CAP; return S.lang === "zh" ? ("选择过长 —— 最多约 " + cap + " 字") : ("Selection too long — ~" + cap + " chars max"); }
  function selectionInside(article, allowLong) {
    var sel = window.getSelection(); if (!sel || sel.isCollapsed || !sel.rangeCount) return null;
    var text = sel.toString().trim(); if (!text || text.length < 2) return null;
    var range = sel.getRangeAt(0), node = range.commonAncestorContainer;
    node = node.nodeType === 1 ? node : node.parentNode;
    if (!article || !article.contains(node)) return null;
    var long = text.length > SEL_CAP;
    if (long && !allowLong) return null;   // legacy callers keep the old "too long → null" contract
    return { text: text, rect: range.getBoundingClientRect(), range: range.cloneRange(), long: long };   // R16: clone for scroll re-anchor
  }
  // R5 — translation direction from the selection's script: any CJK ideograph → the text
  // is Chinese, so translate to EN; otherwise translate to 中文. The label states it.
  function translateDir(text) {
    var cjk = /[㐀-鿿豈-﫿぀-ヿ]/.test(text || "");
    return cjk
      ? { target: "en", label: (S.lang === "zh" ? "翻译成英文" : "Translate → EN") }
      : { target: "zh", label: (S.lang === "zh" ? "翻译成中文" : "Translate → 中文") };   // item 13 — localize the non-CJK label
  }
  function showSelectionBar(article) {
    removeBar();
    var s = selectionInside(article, true); if (!s) return;
    var r = s.rect, text = s.text, srange = s.range;
    // item 17 — a present-but-over-cap selection shows a disabled bar with the reason, not nothing
    // (and not the misleading "select text first" path the keyboard route used to hit).
    if (s.long) {
      var lbar = el("div", "ai-actions too-long"); lbar.id = "sb-aibar";
      lbar.setAttribute("role", "status");
      var hint = el("span", "", esc(selTooLongMsg()));
      hint.style.cssText = "font-size:11.5px;opacity:.72;padding:0 8px;white-space:nowrap;font-family:var(--sans)";
      lbar.appendChild(hint);
      document.body.appendChild(lbar);
      lbar.style.left = Math.max(8, Math.min(window.innerWidth - lbar.offsetWidth - 8, r.left + r.width / 2 - lbar.offsetWidth / 2)) + "px";
      lbar.style.top = Math.max(8, r.top - lbar.offsetHeight - 8) + "px";
      return;
    }
    var tdir = translateDir(text);
    var bar = el("div", "ai-actions"); bar.id = "sb-aibar";
    bar.setAttribute("role", "toolbar"); bar.setAttribute("aria-label", t("ai.explain") + " / " + tdir.label + " / " + t("ai.ask") + " / " + t("kh.highlight"));
    [["explain", "#i-note", t("ai.explain")], ["translate", "#i-globe2", tdir.label], ["ask", "#i-ask", t("ai.ask")]].forEach(function (a) {
      var b = el("button", "", '<svg class="i sm"><use href="' + a[1] + '"/></svg>');
      // item 28 — Explain/Ask reach ~1200 chars, but Translate stays capped at ~400; an over-cap
      // selection greys the Translate button (with the reason) instead of silently failing.
      var trCapped = a[0] === "translate" && text.length > SEL_CAP_TR;
      var lbl = trCapped ? a[2] + " — " + selTooLongMsg(SEL_CAP_TR) : a[2];
      b.title = lbl; b.setAttribute("aria-label", lbl);
      if (trCapped) b.disabled = true;
      else b.onclick = function () { openAiPop(a[0], text, r, srange); removeBar(); };
      bar.appendChild(b);
    });
    // R21 — a 4th action: persist a highlight over the selected range
    var hb = el("button", "", '<svg class="i sm"><use href="#i-mark"/></svg>'); hb.title = t("kh.highlight"); hb.setAttribute("aria-label", t("kh.highlight"));
    hb.onclick = function () { highlightSelection(article, srange, text); removeBar(); };
    bar.appendChild(hb);
    document.body.appendChild(bar);
    bar.style.left = Math.max(8, Math.min(window.innerWidth - bar.offsetWidth - 8, r.left + r.width / 2 - bar.offsetWidth / 2)) + "px";
    bar.style.top = Math.max(8, r.top - bar.offsetHeight - 8) + "px";
  }
  function wireSelectionAI(article) {
    article.addEventListener("mouseup", function () { setTimeout(function () { showSelectionBar(article); }, 10); });
    var deb;
    function onSelChange() {
      if (_mdown) return;                       // mouse path owns mouse selections
      clearTimeout(deb); deb = setTimeout(function () { if (document.body.contains(article)) showSelectionBar(article); }, 200);
    }
    document.addEventListener("selectionchange", onSelChange);
    SB.onTeardown(function () { document.removeEventListener("selectionchange", onSelChange); });   // per-render listener
    document.addEventListener("mousedown", function (e) { if (!e.target.closest("#sb-aibar,.ai-pop")) removeBar(); });
  }
  function removeBar() { var b = $("#sb-aibar"); if (b) b.remove(); }
  // reader shortcuts (e/t/a): run an AI op over the current selection (see keyHelp)
  function selectionAI(op, scroll) {
    var article = (scroll && $(".reader", scroll)) || $(".reader");
    var s = selectionInside(article, true); if (!s) { SB.toast(S.lang === "zh" ? "先在正文里选中一段文字" : "Select text in the article first"); return; }
    if (s.long) { SB.toast(selTooLongMsg()); return; }   // item 17 — same honest reason as the mouse bar
    if (op === "translate" && s.text.length > SEL_CAP_TR) { SB.toast(selTooLongMsg(SEL_CAP_TR)); return; }   // item 28 — translate stays tight
    openAiPop(op, s.text, s.rect, s.range); removeBar();
  }
  SB.explainSelection = function (scroll) { selectionAI("explain", scroll); };

  /* ---- R21 persistent highlights (localStorage, keyed per paper) ----------
     A 4th selection action wraps the range in a <mark> and stores {runId,quote,ts}.
     Saved highlights re-apply on mount (best-effort text match), list in the dock
     rail with click-to-scroll, and surface in ⌘K. */
  function currentRunId() { try { return new URL(location.href).searchParams.get("id") || ""; } catch (e) { return ""; } }
  function paperKey(article) {
    var h1 = article && article.querySelector("h1");
    var title = h1 ? h1.textContent.trim() : "";
    return S.tool + "|" + (S.project || "") + "|" + (currentRunId() || title).slice(0, 140);
  }
  function loadHls(key) { try { return JSON.parse(localStorage.getItem("sb.hl." + key) || "[]") || []; } catch (e) { return []; } }
  function saveHls(key, arr) { try { localStorage.setItem("sb.hl." + key, JSON.stringify(arr)); } catch (e) {} }
  function wrapHighlight(range, id) {
    var mk = document.createElement("mark"); mk.className = "sb-hl"; if (id) mk.id = id;
    try { range.surroundContents(mk); return mk; }
    catch (e) { try { mk.appendChild(range.extractContents()); range.insertNode(mk); return mk; } catch (e2) { return null; } }
  }
  function highlightSelection(article, presetRange, presetText) {
    var range, text;
    if (presetRange) { range = presetRange; text = (presetText || presetRange.toString() || "").trim(); }
    else { var sel = window.getSelection(); if (!sel || !sel.rangeCount || sel.isCollapsed) return; text = sel.toString().trim(); range = sel.getRangeAt(0); }
    if (!text) return;
    var key = paperKey(article), arr = loadHls(key), ts = Date.now();
    wrapHighlight(range, "hl-" + ts);
    arr.push({ runId: currentRunId(), quote: text, ts: ts }); saveHls(key, arr);
    try { var s2 = window.getSelection(); s2 && s2.removeAllRanges && s2.removeAllRanges(); } catch (e) {}
    SB.toast(t("hl.done"));
    refreshHlSec(article);
  }
  // re-apply saved highlights on mount (single-text-node matches; multi-node skipped but still listed)
  function reapplyHighlights(article, key) {
    var arr = loadHls(key); if (!arr.length) return;
    arr.forEach(function (rec) {
      if (!rec || !rec.quote || article.querySelector("#hl-" + rec.ts)) return;
      var walker = document.createTreeWalker(article, NodeFilter.SHOW_TEXT, null, false), node;
      while ((node = walker.nextNode())) {
        var idx = node.nodeValue.indexOf(rec.quote);
        if (idx >= 0 && !(node.parentNode && node.parentNode.closest && node.parentNode.closest("mark.sb-hl"))) {
          try { var range = document.createRange(); range.setStart(node, idx); range.setEnd(node, idx + rec.quote.length); wrapHighlight(range, "hl-" + rec.ts); } catch (e) {}
          break;
        }
      }
    });
  }
  function scrollToHl(article, rec) {
    var mk = article.querySelector("#hl-" + rec.ts);
    if (mk) { scrollInto(mk, { behavior: smooth(), block: "center" }); mk.classList.add("hl-flash"); setTimeout(function () { mk.classList.remove("hl-flash"); }, 1200); return; }
    var walker = document.createTreeWalker(article, NodeFilter.SHOW_TEXT, null, false), node;
    while ((node = walker.nextNode())) { if (node.nodeValue.indexOf(rec.quote) >= 0) { var p = node.parentNode; if (p && p.scrollIntoView) scrollInto(p, { behavior: smooth(), block: "center" }); return; } }
  }
  // item 25 — a rail row that pairs the existing jump/open button with a hover/focus × that removes
  // the record (mirrors the saved-views delete affordance). The × sits at the row's right edge and
  // reveals on hover OR keyboard focus, so it's reachable without a mouse.
  function railDeletableRow(mainBtn, delLabel, onDelete) {
    var row = el("div", "rail-row");
    row.style.cssText = "position:relative;display:flex;align-items:stretch";
    mainBtn.style.flex = "1"; mainBtn.style.paddingRight = "26px";
    var del = el("button", "rail-del", "×");
    del.type = "button";
    del.setAttribute("aria-label", delLabel); del.title = delLabel;
    del.style.cssText = "position:absolute;right:3px;top:50%;transform:translateY(-50%);opacity:0;transition:opacity .12s;border:0;background:transparent;color:var(--muted);cursor:pointer;font-size:16px;line-height:1;padding:2px 6px;border-radius:4px";
    function show() { del.style.opacity = "1"; } function hide() { del.style.opacity = ""; }
    row.addEventListener("mouseenter", show); row.addEventListener("mouseleave", hide);
    del.addEventListener("focus", show); del.addEventListener("blur", hide);
    del.onclick = function (e) { e.stopPropagation(); onDelete(); };
    row.appendChild(mainBtn); row.appendChild(del);
    return row;
  }
  // item 25 — remove a highlight: unwrap its <mark> back to plain text, then drop the record + re-render.
  function unwrapHl(article, rec) {
    var mk = article && article.querySelector && article.querySelector("#hl-" + rec.ts);
    if (mk && mk.parentNode) {
      var p = mk.parentNode;
      while (mk.firstChild) p.insertBefore(mk.firstChild, mk);
      p.removeChild(mk);
      try { p.normalize(); } catch (e) {}
    }
  }
  function deleteHl(article, key, rec) {
    var arr = loadHls(key).filter(function (h) { return h.ts !== rec.ts; });
    saveHls(key, arr); unwrapHl(article, rec); refreshHlSec(article);
  }
  // item 11c — concatenate this paper's highlight + note records into paste-ready markdown
  // (paper title heading, quoted highlights, then each note's op + quote + answer). Pure string
  // build; the copy itself reuses wireCopy so clipboard + toast behavior matches everywhere else.
  function highlightsNotesMarkdown(article, key) {
    var hls = loadHls(key), notes = loadNotes(key), L = [];
    var h1 = article && article.querySelector && article.querySelector("h1");
    var title = h1 ? h1.textContent.trim() : "";
    if (title) L.push("# " + title, "");
    if (hls.length) {
      L.push("## " + t("hl.rail"));
      hls.forEach(function (rec) { if (rec && rec.quote) L.push("> " + String(rec.quote).replace(/\s*\n+\s*/g, " ")); });
      L.push("");
    }
    if (notes.length) {
      L.push("## " + t("notes.rail"));
      notes.forEach(function (rec) {
        if (!rec) return;
        L.push("**" + noteOpLabel(rec.op) + "** — " + String(rec.quote || "").replace(/\s*\n+\s*/g, " "));
        if (rec.answer) L.push("", String(rec.answer).trim(), "");
      });
    }
    return L.join("\n").trim();
  }
  // item 11c — a rail-h header that carries an optional trailing copy/export icon. When any
  // highlight OR note exists, the icon dumps the combined markdown (via wireCopy's late-bound getter,
  // so it always exports the current records regardless of which section triggered the re-render).
  function railHeaderWithExport(article, key, labelKey) {
    var head = el("div", "rail-h");
    head.style.display = "flex"; head.style.alignItems = "center"; head.style.justifyContent = "space-between"; head.style.gap = "6px";
    head.appendChild(el("span", null, esc(t(labelKey))));
    if (loadHls(key).length || loadNotes(key).length) {
      var expLbl = S.lang === "zh" ? "复制标注与批注为 Markdown" : "Copy highlights & notes as Markdown";
      var cp = el("button", "rail-hcopy", '<svg class="i sm"><use href="#i-copy"/></svg>');
      cp.type = "button"; cp.setAttribute("aria-label", expLbl); cp.title = expLbl;
      cp.style.cssText = "border:0;background:transparent;color:var(--muted);cursor:pointer;padding:2px;border-radius:4px;display:inline-flex;align-items:center;line-height:0";
      wireCopy(cp, function () { return highlightsNotesMarkdown(article, key); });
      head.appendChild(cp);
    }
    return head;
  }
  function buildHlSec(article, key) {
    var sec = el("div", "rail-sec sb-hl-sec");
    sec.appendChild(railHeaderWithExport(article, key, "hl.rail"));   // item 11c — export icon in the header
    var arr = loadHls(key);
    if (!arr.length) { sec.appendChild(el("div", "rail-empty", esc(t("hl.empty")))); return sec; }
    var delLbl = S.lang === "zh" ? "删除标注" : "Remove highlight";
    arr.slice().reverse().forEach(function (rec) {
      var q = rec.quote || "";
      // item 4 (a11y) — a real <button>, so jumping to a highlight is keyboard/SR-reachable
      var a = el("button", "rail-link", esc(q.length > 64 ? q.slice(0, 64) + "…" : q));
      a.title = q; a.onclick = function () { scrollToHl(article, rec); };
      // item 25 — a hover/focus × removes the highlight (unwrap + splice)
      sec.appendChild(railDeletableRow(a, delLbl, function () { deleteHl(article, key, rec); }));
    });
    return sec;
  }
  function refreshHlSec(article) {
    if (!article || !article._hlSec || !article._hlSec.parentNode) return;
    var fresh = buildHlSec(article, article._hlKey || paperKey(article));
    article._hlSec.parentNode.replaceChild(fresh, article._hlSec);
    article._hlSec = fresh;
  }
  // ⌘K exposure: highlights of the currently-open reader
  function currentReaderArticle() { var sc = $(".reader-scroll[data-reader]"); return sc ? $(".reader", sc) : null; }

  /* ---- item 30 — pinned notes: an Explain/Ask answer saved as an annotation on the
     selected range, stored beside the highlight record per paperKey so it survives a
     navigate. Surfaced in a sibling Notes section of the dock rail (click-to-scroll). */
  function loadNotes(key) { try { return JSON.parse(localStorage.getItem("sb.note." + key) || "[]") || []; } catch (e) { return []; } }
  function saveNotes(key, arr) { try { localStorage.setItem("sb.note." + key, JSON.stringify(arr)); } catch (e) {} }
  function noteOpLabel(op) { return op === "translate" ? t("ai.translate") : op === "ask" ? t("ai.ask") : t("ai.explain"); }
  function deleteNote(article, key, rec) {   // item 25 — drop the note record + re-render the rail section
    var arr = loadNotes(key).filter(function (n) { return n.ts !== rec.ts; });
    saveNotes(key, arr); refreshNotesSec(article); refreshHlSec(article);   // item 11c — keep the Highlights-header export in sync
  }
  function scrollToNote(article, rec) {
    var walker = document.createTreeWalker(article, NodeFilter.SHOW_TEXT, null, false), node;
    while ((node = walker.nextNode())) {
      if (rec.quote && node.nodeValue.indexOf(rec.quote) >= 0) {
        var p = node.parentNode; if (p && p.scrollIntoView) { scrollInto(p, { behavior: smooth(), block: "center" }); if (p.classList) { p.classList.add("hl-flash"); setTimeout(function () { p.classList.remove("hl-flash"); }, 1200); } }
        return;
      }
    }
  }
  // item 25 — a viewport rect to anchor the re-opened note popover: the quote's block if found,
  // else a top-right fallback (the pop clamps + docks on scroll anyway).
  function noteRect(article, rec) {
    var walker = document.createTreeWalker(article, NodeFilter.SHOW_TEXT, null, false), node;
    while ((node = walker.nextNode())) {
      if (rec.quote && node.nodeValue.indexOf(rec.quote) >= 0) {
        var p = node.parentNode;
        if (p && p.getBoundingClientRect) { var r = p.getBoundingClientRect(); if (r.width + r.height > 0) return r; }
        break;
      }
    }
    return { left: Math.max(20, window.innerWidth - 360), top: 90, bottom: 130, width: 320, height: 40, right: window.innerWidth - 40 };
  }
  function buildNotesSec(article, key) {
    var sec = el("div", "rail-sec sb-note-sec");
    sec.innerHTML = '<div class="rail-h">' + esc(t("notes.rail")) + "</div>";
    var arr = loadNotes(key);
    if (!arr.length) { sec.appendChild(el("div", "rail-empty", esc(t("notes.empty")))); return sec; }
    var delLbl = S.lang === "zh" ? "删除批注" : "Remove note";
    arr.slice().reverse().forEach(function (rec) {
      var q = rec.quote || "";
      // op eyebrow + the quoted text
      var a = el("button", "rail-link",
        '<span style="opacity:.6;font-size:10px;text-transform:uppercase;letter-spacing:.04em;margin-right:6px">' + esc(noteOpLabel(rec.op)) + "</span>" +
        esc(q.length > 56 ? q.slice(0, 56) + "…" : q));
      a.title = q;
      // item 25 — clicking a note re-opens its stored answer in the AI popover (read-only), not a
      // truncated 240-char tooltip; scroll to the quote first so the pop anchors near it.
      a.onclick = function () {
        scrollToNote(article, rec);
        openAiPop(rec.op || "explain", rec.quote || "", noteRect(article, rec), null, rec.answer || "");
      };
      sec.appendChild(railDeletableRow(a, delLbl, function () { deleteNote(article, key, rec); }));
    });
    return sec;
  }
  function refreshNotesSec(article) {
    if (!article || !article._noteSec || !article._noteSec.parentNode) return;
    var fresh = buildNotesSec(article, article._noteKey || paperKey(article));
    article._noteSec.parentNode.replaceChild(fresh, article._noteSec);
    article._noteSec = fresh;
  }
  // item 7 — a bounded reading context for Explain/Ask: the enclosing block plus a window of
  // the surrounding article text, capped so we never ship the whole paper. ai.js forwards it verbatim.
  function selectionContext(range, text) {
    try {
      if (!range) return "";
      var node = range.commonAncestorContainer;
      node = node.nodeType === 1 ? node : node.parentNode;
      var block = node && node.closest ? node.closest("p,li,blockquote,figcaption,h1,h2,h3,h4,td,dd") : null;
      var para = block ? String(block.textContent || "").trim() : "";
      var art = currentReaderArticle();
      var whole = art ? String(art.textContent || "") : "";
      var around = "";
      if (whole) {
        var probe = (para || text || "").slice(0, 48);
        var idx = probe ? whole.indexOf(probe) : -1;
        if (idx >= 0) around = whole.slice(Math.max(0, idx - 700), idx + probe.length + 900).trim();
      }
      var ctx = para;
      if (around && around.indexOf(para) < 0) ctx = para ? (para + "\n\n" + around) : around;
      else if (around) ctx = around;
      return ctx.slice(0, 1800);
    } catch (e) { return ""; }
  }
  // item 25 — presetAnswer (optional) re-opens a saved Note's stored answer read-only: the same
  // popover UI, but no model call is made (nothing leaves the page) and Pin is suppressed.
  function openAiPop(op, text, r, presetRange, presetAnswer) {
    $$(".ai-pop").forEach(function (p) { if (p._close) p._close(); else p.remove(); });
    var isPreset = presetAnswer != null;
    var opener = document.activeElement;                          // R16: restore focus on close
    var tdir = op === "translate" ? translateDir(text) : null;    // R5: direction-aware translate
    var pop = el("div", "ai-pop" + (op === "translate" ? " warm" : ""));
    var label = op === "translate" ? tdir.label : op === "ask" ? t("ai.ask") : t("ai.explain");
    var loading = op === "translate" ? t("ai.translating") : op === "ask" ? t("ai.asking") : t("ai.explaining");
    pop.setAttribute("role", "dialog"); pop.setAttribute("aria-live", "polite"); pop.setAttribute("aria-label", label);
    // R20 — a Copy button in the header, disabled until the stream finishes. item 30 — a Pin
    // button next to it saves the answer as an annotation on the selected range.
    var pinLbl = S.lang === "zh" ? "固定为批注" : "Pin as note";
    // item 7 — Ask gets a single-line question field (autofocused, send on Enter); the streaming
    // answer area sits below it and only fills once a question is asked.
    var askRow = (op === "ask" && !isPreset)
      ? '<div class="ap-askrow" style="padding:8px 10px 0"><input class="ap-ask-in" type="text" autocomplete="off" spellcheck="false" placeholder="' +
        esc(S.lang === "zh" ? "输入你的问题,回车提问…" : "Type your question, Enter to ask…") + '" aria-label="' + esc(t("ai.ask")) +
        '" style="width:100%;box-sizing:border-box;height:32px;padding:0 10px;border-radius:8px;border:1px solid var(--hair-2);background:var(--well);color:var(--ink);font:inherit;font-size:13px;outline:none"></div>'
      : "";
    var apbInit = isPreset ? "" : (op === "ask" ? esc(S.lang === "zh" ? "针对选中文字提问,答案会显示在这里。" : "Ask about the selected text; the answer appears here.") : esc(loading));
    pop.innerHTML = '<div class="aph"><svg class="i sm"><use href="#i-spark"/></svg><span class="aph-t">' + esc(label) + '</span>' +
      '<button class="aph-pin" aria-label="' + esc(pinLbl) + '" title="' + esc(pinLbl) + '" disabled' + (isPreset ? ' hidden' : '') + '><svg class="i sm"><use href="#i-pin"/></svg></button>' +
      '<button class="aph-copy" aria-label="' + esc(copyLabel()) + '" title="' + esc(copyLabel()) + '" disabled><svg class="i sm"><use href="#i-copy"/></svg></button>' +
      '<button class="aph-x" aria-label="Close"><svg class="i sm"><use href="#i-close"/></svg></button></div>' +
      askRow +
      // item 11b — the visible answer streams into .apb with aria-live=off so a screen reader is NOT
      // re-read the whole growing text every ~16ms; the settled answer is announced ONCE via the
      // dedicated visually-hidden .ap-live child (see runAi / isPreset).
      "<div class='apb" + ((op === "ask" || isPreset) ? "" : " loading") + "' aria-live='off'>" + apbInit + "</div>" +
      '<div class="ap-live sr-only" aria-live="polite" aria-atomic="true"></div>';
    document.body.appendChild(pop);

    // R16 — the selection range (preset from the still-live selection, else the current one)
    // lets the pop re-anchor as the reader scrolls, and dock once it leaves the viewport. A stored
    // note has no live range (item 25), so it just anchors once at r and docks on scroll.
    var sel = window.getSelection();
    var range = isPreset ? null : (presetRange || ((sel && sel.rangeCount) ? sel.getRangeAt(0).cloneRange() : null));
    function place(rect) {
      pop.classList.remove("docked"); pop.style.right = ""; pop.style.bottom = "";
      pop.style.left = Math.max(20, Math.min(window.innerWidth - pop.offsetWidth - 20, rect.left)) + "px";
      pop.style.top = Math.min(window.innerHeight - pop.offsetHeight - 20, rect.bottom + 8) + "px";
    }
    function dock() { pop.classList.add("docked"); pop.style.left = ""; pop.style.top = ""; pop.style.right = "20px"; pop.style.bottom = "20px"; }
    place(r);
    var sc = $(".reader-scroll[data-reader]");
    function onScroll() {
      var rect = range ? range.getBoundingClientRect() : null;
      var vis = rect && (rect.width + rect.height) > 0 && rect.bottom > 56 && rect.top < window.innerHeight - 16;
      if (vis) place(rect); else dock();                          // follow the selection, else park in a corner
    }
    if (sc) sc.addEventListener("scroll", onScroll);
    window.addEventListener("resize", onScroll);

    var apb = $(".apb", pop), copyBtn = $(".aph-copy", pop), pinBtn = $(".aph-pin", pop), askIn = $(".ap-ask-in", pop), srLive = $(".ap-live", pop), out = "";
    wireCopy(copyBtn, function () { return out; });
    // item 11b — push the settled, plain-text answer into the dedicated live child so a screen reader
    // hears the final answer once, instead of the partial-rewrite garble the streaming .apb would emit.
    function announceAnswer(text) { if (srLive) srLive.textContent = plainMd(text || ""); }
    function focusables() { return $$("button,input", pop).filter(function (n) { return !n.disabled; }); }
    function close() {
      pop.remove();
      if (sc) sc.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
      document.removeEventListener("keydown", onKey, true);
      try { opener && opener.focus && opener.focus(); } catch (e) {}
    }
    function onKey(e) {
      if (!document.body.contains(pop)) { document.removeEventListener("keydown", onKey, true); return; }
      if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); close(); }
      else if (e.key === "Tab") {                                 // minimal focus trap (mirrors keyHelp)
        var f = focusables(); if (!f.length) return;
        var first = f[0], last = f[f.length - 1];
        if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
        else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
        else if (!pop.contains(document.activeElement)) { e.preventDefault(); first.focus(); }
      }
    }
    $(".aph-x", pop).onclick = close;
    pop._close = close;
    document.addEventListener("keydown", onKey, true);

    // item 7 — Explain/Ask carry a bounded context (enclosing paragraph + a window of the article
    // around the selection) so "reading this passage in context of the whole article" is true, not
    // just copy. Translate stays selection-only.
    var ctx = (op === "explain" || op === "ask") ? selectionContext(range, text) : undefined;
    function runAi(question) {
      apb.classList.add("loading"); apb.textContent = loading;
      copyBtn.disabled = true; pinBtn.disabled = true; out = "";
      pop.setAttribute("aria-busy", "true");   // item 11b — hold SR announcements until the stream settles
      if (srLive) srLive.textContent = "";
      SB.ai({ op: op, text: text, question: question, context: ctx, target_lang: tdir ? tdir.target : undefined, channel: "selection" },
        function (chunk, done, full) {
          out = full; apb.classList.remove("loading"); apb.innerHTML = SB.mdLite(full);
          if (done) {
            copyBtn.disabled = !full; pinBtn.disabled = !full;   // item 30 — pin enabled once there's an answer
            pop.setAttribute("aria-busy", "false");              // item 11b — stream settled: allow the one clean announcement
            announceAnswer(full);
          }
        });
    }

    // item 30 — pin the finished answer as an annotation on the selected range (per-paper store)
    if (pinBtn) pinBtn.onclick = function (e) {
      e.stopPropagation();
      var art = currentReaderArticle(); if (!art || !out) return;
      var key = art._noteKey || paperKey(art), arr = loadNotes(key);
      arr.push({ ts: Date.now(), quote: text, op: op, answer: out, runId: currentRunId() });
      saveNotes(key, arr);
      pinBtn.disabled = true; pinBtn.classList.add("pinned");
      SB.toast(S.lang === "zh" ? "已固定为批注" : "Pinned as a note");
      refreshNotesSec(art); refreshHlSec(art);   // item 11c — a new note may enable the Highlights-header export
    };

    if (isPreset) {
      // item 25 — render the stored note answer read-only; no model call, Copy enabled, Pin hidden
      apb.classList.remove("loading"); apb.innerHTML = SB.mdLite(presetAnswer); out = presetAnswer;
      copyBtn.disabled = !presetAnswer;
      announceAnswer(presetAnswer);   // item 11b — a re-opened note reads its stored answer once, cleanly
      var xp = $(".aph-x", pop); if (xp) { try { xp.focus(); } catch (e) {} }
    } else if (op === "ask") {
      // item 7 — wait for the user's question; fire on Enter, keep the streaming area below
      if (askIn) askIn.addEventListener("keydown", function (e) {
        if (e.key === "Enter") { e.preventDefault(); var q = askIn.value.trim(); if (q) runAi(q); }
      });
      var af = askIn || $(".aph-x", pop); if (af) { try { af.focus(); } catch (e) {} }
    } else {
      var x = $(".aph-x", pop); if (x) { try { x.focus(); } catch (e) {} }   // move focus in so Copy/Close are reachable
      runAi();
    }
  }
  // R20 — shared clipboard helper for the AI popover + summary card. getText() is a
  // late-bound getter so the button always copies the latest streamed text.
  function copyLabel() { return S.lang === "zh" ? "复制" : "Copy"; }
  function wireCopy(btn, getText) {
    if (!btn) return;
    btn.onclick = function (e) {
      e.stopPropagation();
      var txt = getText() || ""; if (!txt) return;
      var ok = function () { SB.toast(S.lang === "zh" ? "已复制" : "Copied"); };
      try {
        if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(txt).then(ok, function () { legacyCopy(txt); ok(); });
        else { legacyCopy(txt); ok(); }
      } catch (err) { legacyCopy(txt); ok(); }
    };
  }
  function legacyCopy(txt) {
    try { var ta = el("textarea"); ta.value = txt; ta.style.cssText = "position:fixed;top:-9999px"; document.body.appendChild(ta); ta.select(); document.execCommand("copy"); ta.remove(); } catch (e) {}
  }

  // R25 — collapse inline markdown to a single plain-text line (collapsed summary
  // preview + any short-label fallback), so raw **bold** / # heads never leak as text.
  function plainMd(s) { return String(s == null ? "" : s).replace(/[*_`#>]|^[-•]\s*/gm, "").replace(/\s+/g, " ").trim(); }
  SB.plainMd = plainMd;

  // lightweight markdown -> html for AI output + reader bodies
  SB.mdLite = function (s) {
    return esc(s)
      .replace(/^### (.*)$/gm, "<h3>$1</h3>").replace(/^## (.*)$/gm, "<h2>$1</h2>")
      // item 8 — [text](url) links (safe schemes only; url already escaped by esc())
      .replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, function (m, txt, url) {
        if (!/^(https?:\/\/|mailto:|\/|#)/.test(url)) return m;   // drop javascript: & other unsafe schemes
        var ext = /^(https?:|mailto:)/.test(url);
        return '<a href="' + url + '"' + (ext ? ' target="_blank" rel="noopener noreferrer"' : '') + '>' + txt + "</a>";
      })
      .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
      // item 8 — single-* italics; runs AFTER bold so ** is already consumed
      .replace(/(^|[\s(])\*([^*\s][^*]*?)\*/g, "$1<em>$2</em>")
      .replace(/^- (.*)$/gm, "• $1")
      .replace(/\n\n/g, "<br><br>").replace(/\n/g, "<br>");
  };

  /* ---- AI transport (stubbed here; real /api/ai injected in P3) ----------- */
  // SB.ai({op,text,context,target_lang}, onChunk(chunk,done,full)). Default = mock stream.
  SB.ai = function (req, onChunk) {
    req.ui_lang = req.ui_lang || S.lang;                 // R5: answer language follows the UI (threaded to /api/ai)
    if (SB.aiTransport) return SB.aiTransport(req, onChunk);
    // R5 — the built-in placeholder stream honors ui_lang (and, for translate, target_lang)
    // so the offline demo reads correctly in both languages.
    var MOCK = {
      zh: {
        summary: "**核心贡献**：把「哪里错」与「能改多远」拆成外部权限 + 独立复检两步。\n\n- 外部权威冻结修复范围\n- 每次编辑后做全量复检\n- 从「相信模型自律」变成「可审计的许可流程」",
        explain: "这句话把失败归因从「模型没能力改」转向「许可与判断被塞进同一次调用」——是一次归因转移(attribution-shift)。",
        ask: "它的意思是：把范围冻结的权威与执行编辑的模型分开,鲁莽编辑就从隐形副作用变成可当场否决的对象。",
      },
      en: {
        summary: "**Core contribution**: split *where it's wrong* from *how far it may change* into external permission + an independent recheck.\n\n- an external authority freezes the fix scope\n- a full recheck runs after every edit\n- from “trust the model's restraint” to “an auditable permission flow”",
        explain: "This sentence moves the attribution of failure from “the model can't edit” to “permission and judgment are folded into one call” — an attribution shift.",
        ask: "It means: separate the authority that freezes scope from the model that performs the edit, so a reckless edit turns from an invisible side effect into something you can veto on the spot.",
      },
    };
    // translate resolves to the OPPOSITE of the source script (R5): CJK selection → EN, else → 中文.
    var TRANSLATE = {
      en: "This sentence shifts the attribution of failure from “the model cannot edit” to “permission and judgment are folded into one call.”",
      zh: "这句话把失败的归因从「模型改不动」转移到「许可与判断被塞进同一次调用」。",
    };
    var uiLang = req.ui_lang === "en" ? "en" : "zh";
    var mock = req.op === "translate"
      ? (TRANSLATE[req.target_lang === "en" ? "en" : "zh"])
      : ((MOCK[uiLang] && MOCK[uiLang][req.op]) || "…");
    var i = 0, full = "";
    (function step() {
      if (i >= mock.length) { onChunk("", true, full); return; }
      full = mock.slice(0, Math.min(mock.length, i + 6)); i += 6;
      onChunk(mock.slice(i - 6, i), false, full);
      setTimeout(step, 16);
    })();
  };

  /* ---- keyboard ----------------------------------------------------------- */
  function typing(e) {
    var a = document.activeElement;
    return a && (a.tagName === "INPUT" || a.tagName === "TEXTAREA" || a.isContentEditable);
  }
  function installGlobalKeys() {
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") { var kh = $(".pop.keyhelp"); if (kh && kh._close) kh._close(); if (S.zen) SB.toggleZen(); $$(".ai-pop").forEach(function (p) { if (p._close) p._close(); else p.remove(); }); removeBar(); }
      if ((e.metaKey || e.ctrlKey) && (e.key === "k" || e.key === "K")) { e.preventDefault(); SB.palette(); }
      if ((e.metaKey || e.ctrlKey) && e.key === "/") { e.preventDefault(); SB.keyHelp(); }
      if (!typing(e) && !e.metaKey && !e.ctrlKey && !e.altKey && e.key === "?") { e.preventDefault(); SB.keyHelp(); }   // R10: bare ? opens shortcuts
      if (!typing(e) && !e.metaKey && !e.ctrlKey && !e.altKey && e.key === "/") {   // R26a: bare / focuses the active view's filter
        var fi = curFilterInput(); if (fi) { e.preventDefault(); try { fi.focus(); fi.select && fi.select(); } catch (x) {} }
      }
      // item 12 — the font keys are reader-only: gate them behind _readerOpen so on Jury / Wiki /
      // Home (no reader surface) ⌘ +/−/0 falls through to the browser's native zoom instead of being
      // a silent no-op that swallows it.
      if (_readerOpen) {
        if ((e.metaKey || e.ctrlKey) && (e.key === "=" || e.key === "+")) { e.preventDefault(); SB.font(1); }
        if ((e.metaKey || e.ctrlKey) && e.key === "-") { e.preventDefault(); SB.font(-1); }
        if ((e.metaKey || e.ctrlKey) && e.key === "0") { e.preventDefault(); SB.font(0); }
      }
      // tool quick-switch 1/2/3 when not typing
      if (!typing(e) && !e.metaKey && !e.ctrlKey && (e.key === "1" || e.key === "2" || e.key === "3"))
        SB.setTool(["spark", "jury", "wiki"][+e.key - 1]);
      // item 23 — '[' / ']' step the active tool's sub-views globally (reuses the subnav index
      // math; guarded off Home, single-view tools, and while typing in a field)
      if (!typing(e) && !e.metaKey && !e.ctrlKey && !e.altKey && (e.key === "[" || e.key === "]")) {
        var tlS = TOOLS[S.tool];
        if (S.tool !== "home" && tlS && tlS.sub && tlS.sub.length > 1) {
          e.preventDefault();
          var nS = tlS.sub.length, curS = 0;
          for (var iS = 0; iS < nS; iS++) if (tlS.sub[iS].id === tlS.curSub) curS = iS;
          var toS = (curS + (e.key === "]" ? 1 : -1) + nS) % nS;
          if (tlS.sub[toS].id !== tlS.curSub) SB.setSub(tlS.sub[toS].id);
        }
      }
      // item 8 — Alt+1..9 jumps directly to the Nth sub-view of the active tool (mirrors 1/2/3 for
      // tools). Reuses the subnav index math; guarded off Home / single-view tools / typing. The
      // e.code fallback keeps it working where Alt+digit yields a non-digit e.key (e.g. macOS).
      if (!typing(e) && e.altKey && !e.metaKey && !e.ctrlKey) {
        var digA = /^[1-9]$/.test(e.key) ? e.key : (/^Digit[1-9]$/.test(e.code || "") ? e.code.slice(5) : null);
        if (digA) {
          var tlA = TOOLS[S.tool];
          if (S.tool !== "home" && tlA && tlA.sub && tlA.sub.length > 1) {
            var iA = +digA - 1;
            if (iA < tlA.sub.length) { e.preventDefault(); if (tlA.sub[iA].id !== tlA.curSub) SB.setSub(tlA.sub[iA].id); }
          }
        }
      }
    });
  }
  // R2 — single-press prev/next: navigate immediately, then offer a 2s Undo toast (the
  // inverse move) instead of the old confirm-press timing hazard.
  function navUndo(msg, inverse) {
    if (typeof inverse === "function") SB.toast(msg, { duration: 2000, action: { label: S.lang === "zh" ? "撤销" : "Undo", fn: inverse } });
    else SB.toast(msg, { duration: 2000 });
  }
  function installReaderKeys(scroll, opts) {
    var art = $(".reader", scroll);
    var hasTr = !!(art && $$(".tr", art).length);        // R10: only bind 'C' when parallel-translation blocks exist
    _readerHasTr = hasTr; _readerOpen = true;
    _readerHasNav = !!(opts && (opts.onPrev || opts.onNext));   // R28: advertise B/N only when wired
    _readerHasStar = !!(opts && opts.onStar);                   // R28: advertise M only when wired
    scroll.setAttribute("tabindex", "0");
    scroll.setAttribute("role", "region");
    scroll.setAttribute("aria-label", S.lang === "zh" ? "正文(按 ? 看快捷键)" : "Article (press ? for shortcuts)");
    // R10/R21/R28 — advertise exactly the keys we bind (C only with parallel text; B/N/M only when wired)
    scroll.setAttribute("aria-keyshortcuts", ["V", "E", "T", "A", "H"].concat(hasTr ? ["C"] : [], _readerHasNav ? ["B", "N"] : [], _readerHasStar ? ["M"] : [], ["Z", "Space"]).join(" "));
    scroll.addEventListener("keydown", function (e) {
      if (typing(e) || e.metaKey || e.ctrlKey) return;
      var k = e.key.toLowerCase();
      if (k === "v") { e.preventDefault(); var c = $("[data-sum]", scroll); if (c && c._toggle) c._toggle(); }
      else if (k === "e") { e.preventDefault(); selectionAI("explain", scroll); }     // explain the selection
      else if (k === "t") { e.preventDefault(); selectionAI("translate", scroll); }   // R21: translate the selection
      else if (k === "a" || k === "q") { e.preventDefault(); selectionAI("ask", scroll); }   // R21: ask AI about the selection
      else if (k === "h") { e.preventDefault(); var a3 = $(".reader", scroll), sel3 = window.getSelection(); if (a3 && sel3 && !sel3.isCollapsed && sel3.rangeCount) highlightSelection(a3); else SB.toast(S.lang === "zh" ? "先在正文里选中一段文字" : "Select text in the article first"); }   // R26b: highlight the selection
      else if (k === "c" && hasTr) { e.preventDefault(); var a2 = $(".reader", scroll); if (a2) { a2.classList.toggle("no-tr"); SB.toast(a2.classList.contains("no-tr") ? (S.lang === "zh" ? "已隐藏对照翻译" : "Parallel translation hidden") : (S.lang === "zh" ? "已显示对照翻译" : "Parallel translation shown")); } }
      else if (k === " ") { e.preventDefault(); scroll.scrollBy({ top: scroll.clientHeight * 0.62, behavior: smooth() }); }
      else if (k === "z") { e.preventDefault(); SB.toggleZen(); }
      else if (k === "b" && opts.onPrev) { e.preventDefault(); opts.onPrev(); navUndo(S.lang === "zh" ? "已跳到上一篇" : "Moved to previous", opts.onNext); }
      else if (k === "n" && opts.onNext) { e.preventDefault(); opts.onNext(); navUndo(S.lang === "zh" ? "已跳到下一篇" : "Moved to next", opts.onPrev); }
      else if (k === "m" && opts.onStar) { opts.onStar(); }
    });
    // R2 — auto-focus the reading region on mount so B/N/Space work without a first click
    // (guarded so we never yank focus from an open dialog or a chrome control).
    setTimeout(function () {
      if (overlayOpen()) return;
      var a = document.activeElement;
      if (a && a !== document.body && a.closest && a.closest(".strip, .subnav, .toolsw, input, textarea, [contenteditable]")) return;
      if (document.body.contains(scroll)) { try { scroll.focus({ preventScroll: true }); } catch (e) { try { scroll.focus(); } catch (e2) {} } }
    }, 0);
  }
  // R10/R15/R28: keyHelp + aria-keyshortcuts reflect exactly what the OPEN reader binds.
  var _readerHasTr = false;   // parallel-text 'C'
  var _readerOpen = false;    // a reader surface is mounted (gate all reader keys off a kanban board)
  var _readerHasNav = false;  // onPrev/onNext wired → advertise B / N
  var _readerHasStar = false; // onStar wired → advertise M

  /* ---- toast + key help --------------------------------------------------- */
  var _toastT;
  // R4 — the toast is itself a role=status / aria-live host AND mirrors into #sb-live for
  // reliable SR announcement. R2 — opts.action renders an inline button (e.g. Undo).
  SB.toast = function (msg, opts) {
    opts = opts || {};
    var old = $(".toast"); if (old) old.remove();
    var tst = el("div", "toast", '<svg class="i sm" style="color:var(--accent)"><use href="#i-check"/></svg><span class="toast-msg">' + esc(msg) + "</span>");
    tst.setAttribute("role", "status"); tst.setAttribute("aria-live", "polite");
    if (opts.action && opts.action.label) {
      var ab = el("button", "toast-act", esc(opts.action.label));
      ab.onclick = function () { clearTimeout(_toastT); tst.remove(); try { opts.action.fn && opts.action.fn(); } catch (e) {} };
      tst.appendChild(ab);
    }
    document.body.appendChild(tst);
    SB.announce(msg);
    clearTimeout(_toastT);
    _toastT = setTimeout(function () { tst.remove(); }, opts.duration || 2200);
  };
  SB.keyHelp = function () {
    var existing = $(".pop.keyhelp"); if (existing && existing._close) { existing._close(); return; }   // toggle off
    var zh = S.lang === "zh";
    // R10/R15/R21/R28 — advertise only live shortcuts. Reader keys are listed ONLY when a
    // reader surface is open (never over a kanban board where they do nothing); B/N/M only
    // when wired; 'C' only with parallel text. The ACTIVE workspace appends its own keymap.
    var rows = [];
    if (_readerOpen) {
      rows.push(["V", t("ai.summary")], ["E", t("kh.selection")], ["T", t("kh.translate")], ["A / Q", t("kh.ask")], ["H", t("kh.highlight")], ["Space", zh ? "向下翻页" : "Page down"]);
      if (_readerHasTr) rows.push(["C", zh ? "对照翻译" : "Translate"]);
      if (_readerHasNav) rows.push(["B / N", zh ? "上一篇 / 下一篇" : "Prev / Next"]);
      if (_readerHasStar) rows.push(["M", zh ? "收藏" : "Star"]);
      rows.push(["Z", "Zen"], ["⌘ + / − / 0", zh ? "字号" : "Font size"]);   // item 12 — font keys are reader-only, listed only with a reader open
    }
    rows.push(["/", t("filter.focus")], ["[ / ]", zh ? "上一视图 / 下一视图" : "Prev / Next view"], ["⌥ 1…N", zh ? "跳到第 N 个视图" : "Jump to Nth view"], ["1 / 2 / 3", "Spark / Jury / Wiki"], ["⌘ K", zh ? "命令面板" : "Command palette"], ["?", t("kbd")]);
    // R15 — fold in the active workspace's own keymap (jury docket keys, and any future tool)
    try { var wk = SB.workspaceKeys && SB.workspaceKeys[S.tool] && SB.workspaceKeys[S.tool](); if (wk && wk.length) rows = rows.concat(wk); } catch (e) {}
    $$(".pop.keyhelp,.scrim").forEach(function (n) { n.remove(); });
    var opener = document.activeElement;
    var sc = el("div", "scrim"); document.body.appendChild(sc);
    var pop = el("div", "pop keyhelp"); pop.style.cssText = "left:50%;top:50%;transform:translate(-50%,-50%);width:min(440px,92vw);padding:22px";
    pop.setAttribute("role", "dialog"); pop.setAttribute("aria-modal", "true"); pop.setAttribute("aria-labelledby", "sb-kh-h");
    // R17 — the tool overview folded in above the shortcuts
    var over = '<div class="kh-over"><div class="kh-oh">' + esc(t("welcome.overview")) + '</div>' +
      [["spark", S.lang === "zh" ? "从灵感草拟论文" : "draft a paper from a spark idea"],
       ["jury", S.lang === "zh" ? "让每条审稿意见受审" : "put every reviewer complaint on trial"],
       ["wiki", S.lang === "zh" ? "你的论文知识库" : "your paper knowledge base"]].map(function (o) {
        return '<div class="kh-orow"><span class="kh-odot" style="background:' + NEEDS_TINT[o[0]] + '"></span><b>' + esc(NEEDS_NAME[o[0]]) + '</b><span>' + esc(o[1]) + '</span></div>'; }).join("") + '</div>';
    // item 9-shell — a Glossary of the recurring domain terms, one sentence each, localized
    var GLOSS = S.lang === "zh" ? [
      ["tier / 层级", "把断言按证据强度分档——从大胆假设到当前可断言。"],
      ["seal / 封印", "某产物被冻结的定稿状态,之后要改动必须先显式解封。"],
      ["gate / 闸门", "放行前必须清零的阻断条件(如编译报错、重大缺陷)。"],
      ["fence / 栅栏", "圈定研究范围的边界:核心 / 邻接 / 排除。"],
      ["bench / 基准席", "把方法放到统一 baseline 上受检的对照位。"],
      ["charge / 指控", "对论文的一条具体质疑,进 Jury 后逐条受审。"],
      ["disposition / 处置", "对一条指控的裁决:可改 / 驳回 / 交作者定夺。"],
      ["corroborated / 已佐证", "被独立证据或冻结锚点核实过的说法。"],
      ["escalated / 已升级", "超出自动处置、需要人来定夺的事项。"],
    ] : [
      ["tier", "A claim graded by evidence strength, from a bold hypothesis to what's assertable now."],
      ["seal", "A frozen, finalized state of an artifact; later edits must explicitly unseal it."],
      ["gate", "A blocking condition that must reach zero before release (e.g. compile errors, majors)."],
      ["fence", "The scope boundary of the research: core / adjacent / excluded."],
      ["bench", "A shared baseline slot where a method is put under comparable test."],
      ["charge", "One specific complaint against the paper, tried item-by-item in Jury."],
      ["disposition", "The ruling on a charge: valid-fixable / dropped / author-required."],
      ["corroborated", "A claim verified against independent evidence or a frozen anchor."],
      ["escalated", "An item beyond automatic disposition that needs a human to decide."],
    ];
    var gloss = '<div class="kh-gloss"><div class="kh-oh">' + esc(S.lang === "zh" ? "术语表" : "Glossary") + '</div>' +
      GLOSS.map(function (g) { return '<div class="kh-grow"><b>' + esc(g[0]) + "</b><span>" + esc(g[1]) + "</span></div>"; }).join("") + "</div>";
    // item 1 (a11y) — kh-head is a fixed header OUTSIDE the scroll container; the overview,
    // key rows and glossary go inside .kh-body which the SHELL-CSS agent gives overflow-y:auto
    // (with .pop.keyhelp flex-column + max-height), so short viewports scroll instead of clipping.
    // item 19 — the modal holds the tool overview + full glossary, not just shortcuts, so its title
    // is now 'Help'; 'Keyboard shortcuts' is a section heading over the key rows, and a Replay-intro
    // link sits at the top so the one-shot primer is re-showable from here.
    pop.innerHTML = '<div class="kh-head"><h2 id="sb-kh-h">' + esc(t("help")) + '</h2>' +
      '<button class="iconbtn kh-x" aria-label="Close"><svg class="i sm"><use href="#i-close"/></svg></button></div>' +
      '<div class="kh-body">' +
      '<button class="kh-replay" style="display:inline-flex;align-items:center;gap:6px;border:1px solid var(--hair-2);background:var(--raise);color:var(--ink);border-radius:8px;padding:5px 10px;font:inherit;font-size:12px;cursor:pointer;margin-bottom:12px">↻ ' + esc(t("intro.replay")) + '</button>' +
      over +
      '<div class="kh-oh">' + esc(t("kbd")) + '</div>' +
      rows.map(function (r) { return '<div class="kh-row"><span class="kh-k">' + esc(r[1]) + "</span>" + r[0].split(" ").map(function (k) { return "<kbd>" + esc(k) + "</kbd>"; }).join(" ") + "</div>"; }).join("") + gloss + '</div>';
    document.body.appendChild(pop);
    function close() { pop.remove(); sc.remove(); document.removeEventListener("keydown", onKey, true); try { opener && opener.focus(); } catch (e) {} }
    function onKey(e) {
      if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); close(); }
      else if (e.key === "Tab") {                        // minimal focus trap
        var f = $$("button,[href],[tabindex]:not([tabindex='-1'])", pop).filter(function (n) { return !n.disabled; });
        if (!f.length) return;
        var first = f[0], last = f[f.length - 1];
        if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
        else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
      }
    }
    sc.onclick = close; $(".kh-x", pop).onclick = close;
    var _rep = $(".kh-replay", pop); if (_rep) _rep.onclick = function () { close(); SB.showWelcome(); };   // item 19 — replay the primer
    document.addEventListener("keydown", onKey, true);
    pop._close = close;
    var x = $(".kh-x", pop); if (x) x.focus();
  };

  /* ---- cross-tool "needs me" (R3): tab count badges + right-cluster lamps -
     A cheap poll of the three adapters for the library DEFAULT dirs. Each tool's
     badge = its needs-me integer (0 -> hidden); a lamp per non-zero tool gives the
     same glance on the right, click-to-switch. Shell-level + a guarded singleton
     (it must outlive per-workspace renders), so it is NOT torn down via onTeardown. */
  var NEEDS_TINT = { spark: "#C0552A", jury: "#4B4FA6", wiki: "#5F7355" };
  var NEEDS_NAME = { spark: "Spark", jury: "Jury", wiki: "Wiki" };
  var JURY_ACTIVE = { "raised": 1, "in-trial": 1, "re-trial": 1, "valid-fixable": 1 };
  // counts = the badge/lamp integers; detail = the real items behind them, reused by
  // Home (R4) and the "needs you" tray (R23). dirs = the active project's resolved dirs.
  SB.needs = { counts: { spark: 0, jury: 0, wiki: 0 }, detail: { spark: {}, jury: {}, wiki: {} }, dirs: {}, _timer: null, _loaded: false };
  function needsJson(url) {
    return fetch(url).then(function (r) { return r.ok ? r.json() : null; }).catch(function () { return null; });
  }
  // ---- per-tool fetchers: each resolves { count, detail } for one dir ("" = unbound) --
  function fetchSparkNeeds(dir) {
    var pRuns = needsJson("/api/state").then(function (s) {
      return ((s && s.runs) || []).map(function (r) {
        return { id: r.id, title: r.title || r.id, stage: r.stage || "", status: r.status || "",
          started: r.started || "", waiting: r.status === "waiting", needs: !!r.needs_reply }; });   // R12: started → per-row recency
    });
    var pDec = dir ? needsJson("/api/spark/governance?path=" + encodeURIComponent(dir)).then(function (g) {
      return g && g.decisions && g.decisions.counts ? (g.decisions.counts.open || 0) : 0; }) : Promise.resolve(0);
    return Promise.all([pRuns, pDec]).then(function (r) {
      var runs = r[0], dec = r[1];
      var waiting = runs.filter(function (x) { return x.waiting || x.needs; }).length;
      return { count: waiting + dec, detail: { runs: runs, decisions: dec, waiting: waiting } };
    });
  }
  function fetchJuryNeeds(dir) {
    if (!dir) return Promise.resolve({ count: 0, detail: { items: [], blocking: 0, escalated: 0 } });
    return needsJson("/api/jury/ledger?path=" + encodeURIComponent(dir)).then(function (l) {
      if (!l) return { count: 0, detail: { items: [], blocking: 0, escalated: 0 } };
      var block = {}; (l.gate_blocking_majors || []).forEach(function (id) { block[id] = 1; });
      var escal = {}, byId = {};
      (l.issues || []).forEach(function (i) { byId[i.id] = i; if (i.escalated && JURY_ACTIVE[i.status]) escal[i.id] = 1; });
      var ids = {}; Object.keys(block).forEach(function (k) { ids[k] = 1; }); Object.keys(escal).forEach(function (k) { ids[k] = 1; });
      var items = Object.keys(ids).map(function (id) {
        var i = byId[id] || {};
        return { id: id, summary: i.summary || i.section || id, significance: i.significance || "",
          kind: i.kind || "", gateBlocking: !!block[id], escalated: !!escal[id] }; });
      return { count: items.length, detail: { items: items, blocking: Object.keys(block).length, escalated: Object.keys(escal).length } };
    });
  }
  function fetchWikiNeeds(dir) {
    if (!dir) return Promise.resolve({ count: 0, detail: { inbox: 0, corpus: 0, coverage: null } });
    var pIn = needsJson("/api/wiki/inbox?path=" + encodeURIComponent(dir)).then(function (ib) {
      if (!ib || !ib.rows) return { rows: [], waiting: 0 };
      var w = ib.rows.filter(function (row) { return Object.keys(row).some(function (k) { return String(row[k]).indexOf("待人") >= 0; }); });
      return { rows: ib.rows, waiting: w.length };
    });
    var pCov = needsJson("/api/wiki/coverage?path=" + encodeURIComponent(dir)).then(function (cv) {
      return (cv && cv.saturation) ? { zones: cv.saturation.length } : null; });
    return Promise.all([pIn, pCov]).then(function (r) {
      return { count: r[0].waiting, detail: { inbox: r[0].waiting, corpus: r[0].rows.length, coverage: r[1] } }; });
  }
  function needsFetch() {
    needsJson("/api/library").then(function (lib) {
      if (!lib) return;
      SB._lib = lib; buildProjects(lib);                 // keep the project list + selector fresh
      var dirs = resolveProjectDirs(lib.defaults || {}, S.project); SB.needs.dirs = dirs;
      Promise.all([fetchSparkNeeds(dirs.spark), fetchJuryNeeds(dirs.jury), fetchWikiNeeds(dirs.wiki)]).then(function (r) {
        SB.needs.counts = { spark: r[0].count, jury: r[1].count, wiki: r[2].count };
        SB.needs.detail = { spark: r[0].detail, jury: r[1].detail, wiki: r[2].detail };
        SB.needs._loaded = true;
        SB.needs.render();
        if (SB._homeRefresh) { try { SB._homeRefresh(); } catch (e) {} }   // live-refresh Home if open
        if (SB._wsNeedsRefresh) { try { SB._wsNeedsRefresh(); } catch (e) {} }   // re-render the active workspace's needs-derived chrome once jury/wiki counts land (e.g. Spark runs verdict, which else stays green from a pre-fetch 0)
      });
    });
  }
  SB.needs.refetch = needsFetch;
  function lampTip(nm) {
    var d = SB.needs.detail[nm] || {}, zh = S.lang === "zh", parts = [];
    if (nm === "spark") { if (d.decisions) parts.push(d.decisions + " " + t("needs.dec")); if (d.waiting) parts.push(d.waiting + " " + t("needs.wait")); }
    else if (nm === "jury") { if (d.blocking) parts.push(d.blocking + " " + t("home.gateblock")); if (d.escalated) parts.push(d.escalated + " " + t("home.escalated")); }
    else if (nm === "wiki") { if (d.inbox) parts.push(d.inbox + " " + t("home.inbox")); }
    return NEEDS_NAME[nm] + " · " + (parts.length ? parts.join(zh ? " · " : " · ") : (SB.needs.counts[nm] || 0) + (zh ? " 项待你处理" : " need you"));
  }
  // item 13 — is this tool's needs data degraded (a dir was set but every read failed)?
  // A muted badge on sample/couldNotRead data stops a fake queue from reading as your real one.
  function needsSample(nm) {
    try { var rs = SB.data && SB.data.readState ? SB.data.readState(nm) : null; return !!(rs && rs.couldNotRead); } catch (e) { return false; }
  }
  SB.needs.render = function () {
    var c = SB.needs.counts;
    ["spark", "jury", "wiki"].forEach(function (nm) {
      var b = $('.tsw-badge[data-badge="' + nm + '"]'); if (!b) return;
      var n = c[nm] || 0, muted = needsSample(nm);
      // item 13 — the tab button's aria-label carries the count so the badge isn't SR-silent
      var btn = $('.toolsw button[data-t="' + nm + '"]'), tname = (I18N[S.lang] && I18N[S.lang]["tool." + nm]) || nm;
      if (n > 0) {
        b.textContent = n > 99 ? "99+" : String(n); b.hidden = false;
        b.classList.toggle("muted", muted);
        b.title = muted ? t("needs.sample") : lampTip(nm);       // item 13 — explain what the number is
        if (btn) btn.setAttribute("aria-label", muted ? (tname + " · " + t("needs.sample")) : lampTip(nm));
      } else {
        b.hidden = true; b.textContent = ""; b.classList.remove("muted"); b.removeAttribute("title");
        if (btn) btn.setAttribute("aria-label", tname);
      }
    });
    var host = $("#sb-lamps"); if (!host) return;
    host.innerHTML = "";
    ["spark", "jury", "wiki"].forEach(function (nm) {
      var n = c[nm] || 0; if (n <= 0) return;
      var lamp = el("span", "lamp tool");
      lamp.style.background = NEEDS_TINT[nm];
      lamp.title = lampTip(nm);                          // R23: broken-down tooltip
      lamp.setAttribute("role", "button"); lamp.setAttribute("aria-label", lamp.title);
      lamp.tabIndex = 0;                                 // R19: keyboard-reachable (paired with a ≥24px hit area + focus ring in CSS)
      lamp.onclick = function () { SB.needs.tray(nm); };  // R23: open the drill-in tray
      lamp.onkeydown = function (e) { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); SB.needs.tray(nm); } };
      host.appendChild(lamp);
    });
    syncWsSample();   // item 13 — keep the top-bar '· 示例 / · Sample' suffix in step with the badge muting
  };
  // R23 — the "needs you" tray: real items grouped by tool, each row deep-links
  SB.needs.tray = function (focusTool) {
    $$("#sb-needtray,#sb-needtray-scrim").forEach(function (n) { n.remove(); });
    var sc = el("div", "scrim"); sc.id = "sb-needtray-scrim";
    var pop = el("div", "pop needtray"); pop.id = "sb-needtray";
    pop.setAttribute("role", "dialog"); pop.setAttribute("aria-modal", "true"); pop.setAttribute("aria-label", t("needs.tray"));
    var body = '<div class="nt-head"><b>' + esc(t("needs.tray")) + '</b>' +
      '<button class="iconbtn nt-export" title="' + esc(t("needs.dossier")) + '" aria-label="' + esc(t("needs.dossier")) + '"><svg class="i sm"><use href="#i-copy"/></svg></button>' +
      '<button class="iconbtn nt-x" aria-label="Close"><svg class="i sm"><use href="#i-close"/></svg></button></div>';
    var any = false;
    ["spark", "jury", "wiki"].forEach(function (nm) {
      var d = SB.needs.detail[nm] || {}, rows = [];
      if (nm === "spark") {
        (d.runs || []).filter(function (r) { return r.waiting || r.needs; }).forEach(function (r) {
          rows.push({ id: r.id, sub: "runs", lbl: r.title, meta: (r.stage ? r.stage + " · " : "") + (r.status || "") }); });
        if (d.decisions) rows.push({ id: null, sub: "governance", lbl: d.decisions + " " + t("needs.dec"), meta: t("home.needs") });
      } else if (nm === "jury") {
        (d.items || []).forEach(function (i) {
          rows.push({ id: i.id, sub: "docket", lbl: i.id + " · " + i.summary,
            meta: [i.gateBlocking ? t("home.gateblock") : "", i.escalated ? t("home.escalated") : ""].filter(Boolean).join(" · ") }); });
      } else if (nm === "wiki") {
        if (d.inbox) rows.push({ id: null, sub: "inbox", lbl: d.inbox + " " + t("home.inbox"), meta: t("home.needs") });
      }
      if (!rows.length) return; any = true;
      body += '<div class="nt-sec"><div class="nt-sh"><span class="nt-dot" style="background:' + NEEDS_TINT[nm] + '"></span>' + esc(NEEDS_NAME[nm]) + '</div>';
      rows.forEach(function (row, ri) {
        body += '<button class="nt-row" data-tool="' + nm + '" data-sub="' + esc(row.sub) + '" data-id="' + esc(row.id || "") + '"' +
          (focusTool === nm && ri === 0 ? ' data-focus="1"' : '') + '><span class="nt-lbl">' + esc(row.lbl) + '</span>' +
          (row.meta ? '<span class="nt-meta">' + esc(row.meta) + '</span>' : '') + '</button>';
      });
      body += '</div>';
    });
    if (!any) body += '<div class="nt-empty">' + esc(t("needs.empty")) + '</div>';
    pop.innerHTML = body;
    document.body.appendChild(sc); document.body.appendChild(pop);
    var opener = document.activeElement;
    function close() { pop.remove(); sc.remove(); document.removeEventListener("keydown", onKey, true); try { opener && opener.focus(); } catch (e) {} }
    function onKey(e) { if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); close(); } }
    sc.onclick = close; $(".nt-x", pop).onclick = close;
    var _ex = $(".nt-export", pop); if (_ex) _ex.onclick = function () { SB.exportDossier(); };   // item 27b
    $$(".nt-row", pop).forEach(function (r) { r.onclick = function () { close(); deepLink(r.dataset.tool, r.dataset.sub, r.dataset.id || null); }; });
    document.addEventListener("keydown", onKey, true);
    var f = $(".nt-row[data-focus]", pop) || $(".nt-row", pop) || $(".nt-x", pop); if (f) f.focus();
  };
  SB.needs.start = function () {
    if (SB.needs._timer) clearInterval(SB.needs._timer);
    needsFetch();
    SB.needs._timer = setInterval(needsFetch, 45000);   // modest poll + cache on the counts
  };

  /* ---- deep-link helper: setTool + setSub (+ best-effort item open) (R4/R23/R29) ---- */
  function deepLink(tool, sub, itemId) {
    if (tool === "home") { SB.setTool("home"); return; }
    SB.setTool(tool);
    if (sub) SB.setSub(sub);
    try {   // owner tools expose these openers when wired; guarded so we never hard-depend
      if (tool === "wiki" && itemId && SB.wikiOpen) SB.wikiOpen(itemId);
      else if (tool === "spark" && itemId && SB.sparkOpenRun) SB.sparkOpenRun(itemId);
      else if (tool === "jury" && itemId && SB.juryOpenCharge) SB.juryOpenCharge(itemId);
    } catch (e) {}
    try {   // stamp a shareable ?tool=&view=&id= (owner tools may honor ?id= on boot; harmless otherwise)
      var u = new URL(location.href);
      u.searchParams.set("tool", tool); if (sub) u.searchParams.set("view", sub);
      if (itemId) u.searchParams.set("id", itemId); else u.searchParams.delete("id");
      history.replaceState(null, "", u);
    } catch (e) {}
  }
  SB.deepLink = deepLink;

  /* ---- item 7 — a canonical, shareable URL for the CURRENT view. Built from live shell
     state (tool / current sub / open item id / project / lang) rather than reading the
     address bar, so it's correct even after an in-place run swap that never re-stamped the
     URL. Transient screenshot/panel params are dropped so the shared link opens the plain view. */
  function currentViewUrl() {
    var u; try { u = new URL(location.href); } catch (e) { return location.href; }
    var p = u.searchParams;
    if (S.tool) p.set("tool", S.tool); else p.delete("tool");
    var tl = TOOLS[S.tool], sub = tl && tl.curSub;
    if (S.tool !== "home" && sub) p.set("view", sub); else p.delete("view");
    var id = currentRunId();
    if (id) p.set("id", id); else p.delete("id");
    if (S.project) p.set("project", S.project); else p.delete("project");
    if (S.lang) p.set("lang", S.lang); else p.delete("lang");
    ["panel", "start", "screenshot", "welcome", "dir"].forEach(function (k) { p.delete(k); });
    return u.toString();
  }
  SB.copyView = function () {
    var url = currentViewUrl();
    var ok = function () { SB.toast(t("view.copylink.done")); };
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) { navigator.clipboard.writeText(url).then(ok, function () { legacyCopy(url); ok(); }); return; }
    } catch (e) {}
    legacyCopy(url); ok();
  };

  /* ---- LAUNCHER (一键启动): a one-click start screen with three entry paths -------
     Surfaced explicitly, never forced on every load: on ?start=1, from the Home
     "开始 / Start" chip, from ⌘K, and one click past the first-run welcome primer.
     Reuses the .scrim/.pop overlay + .card + .btn primitives; i18n zh/en; the three
     cards are native <button>s so focus + Enter/Space are free; Esc dismisses; the
     roving arrows move between cards. Picking a path stamps sb.started so it can't nag. */
  SB.launcher = function () {
    $$("#sb-launch-scrim, .pop.launcher").forEach(function (n) { n.remove(); });
    var zh = S.lang === "zh";
    var ENTRIES = [
      { key: "wiki",  ic: "#i-note",  title: t("start.wiki"),  desc: t("start.wiki.d"),
        run: function () { SB._chain = null; renderChain(); SB.setTool("wiki"); } },
      { key: "spark", ic: "#i-spark", title: t("start.spark"), desc: t("start.spark.d"),
        run: function () { SB._chain = null; SB.setTool("spark"); try { SB.setSub("runs"); } catch (e) {} renderChain(); } },
      { key: "chain", ic: "#i-arrow", title: t("start.chain"), desc: t("start.chain.d"),
        run: function () { SB._chain = "wiki2spark"; SB.setTool("wiki"); renderChain(); } },
    ];
    // item 14 — each card carries its destination's hue as a scoped --accent, so the icon (already
    // color:var(--accent)) and the focus ring read as Wiki / Spark / chain instead of a flat Home gray.
    var ACC = { wiki: "#5F7355", spark: "#C0552A", chain: "#4B4FA6" };
    var sc = el("div", "scrim"); sc.id = "sb-launch-scrim";
    var card = el("div", "pop launcher");
    card.setAttribute("role", "dialog"); card.setAttribute("aria-modal", "true"); card.setAttribute("aria-labelledby", "sb-launch-h");
    card.style.cssText = "left:50%;top:50%;transform:translate(-50%,-50%);width:min(680px,94vw);padding:26px 26px 24px;text-align:center";
    var cardsHTML = ENTRIES.map(function (en, i) {
      return '<button type="button" class="card lx-card" data-lx="' + en.key + '" id="lx-' + en.key + '" tabindex="' + (i === 0 ? "0" : "-1") + '" ' +
        'style="--accent:' + ACC[en.key] + ';display:flex;flex-direction:column;align-items:flex-start;gap:6px;text-align:left;padding:16px 16px 15px;cursor:pointer;min-height:118px;background:var(--well);transition:border-color .12s,background .12s">' +
        '<svg class="i" style="width:22px;height:22px;color:var(--accent)"><use href="' + en.ic + '"/></svg>' +
        '<span style="font-family:var(--serif);font-size:16px;font-weight:600;color:var(--ink)">' + esc(en.title) + '</span>' +
        '<span style="font-size:13px;line-height:1.5;color:var(--muted)">' + esc(en.desc) + '</span></button>';
    }).join("");
    card.innerHTML =
      '<h2 id="sb-launch-h" style="font-family:var(--serif);font-size:21px;font-weight:600;margin-bottom:5px;color:var(--ink)">' + esc(t("start.title")) + '</h2>' +
      '<p style="font-size:13px;color:var(--faint);margin-bottom:18px">' + esc(t("start.hint")) + '</p>' +
      '<div class="lx-grid" style="display:grid;grid-template-columns:' + ((window.innerWidth || 700) < 560 ? '1fr' : 'repeat(3,1fr)') + ';gap:12px">' + cardsHTML + '</div>' +
      // item 14 — a low-key "just look around" escape hatch that closes the launcher without picking a path
      '<button type="button" class="lx-explore" style="margin-top:16px;border:0;background:transparent;color:var(--muted);cursor:pointer;font:inherit;font-size:13px;padding:4px 8px;border-radius:6px;text-decoration:underline;text-underline-offset:3px">' + esc(t("start.explore")) + '</button>';
    document.body.appendChild(sc); document.body.appendChild(card);
    var opener = document.activeElement, cards = $$(".lx-card", card), explore = $(".lx-explore", card), active = 0;
    function close() { card.remove(); sc.remove(); document.removeEventListener("keydown", onKey, true); try { opener && opener.focus(); } catch (e) {} }
    function pick(en) { try { save("started", "1"); } catch (e) {} close(); try { en.run(); } catch (e2) {} }
    function focusAt(i) { active = (i + cards.length) % cards.length; cards.forEach(function (c, j) { c.tabIndex = j === active ? 0 : -1; }); try { cards[active].focus(); } catch (e) {} }
    // item 14 — the modal's tab order: the 3 cards + the explore button, wrapped so focus never leaves
    var tabItems = cards.concat(explore ? [explore] : []);
    function onKey(e) {
      if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); close(); return; }
      if (e.key === "ArrowRight" || e.key === "ArrowDown") { e.preventDefault(); focusAt(active + 1); }
      else if (e.key === "ArrowLeft" || e.key === "ArrowUp") { e.preventDefault(); focusAt(active - 1); }
      else if (e.key === "Home") { e.preventDefault(); focusAt(0); }
      else if (e.key === "End") { e.preventDefault(); focusAt(cards.length - 1); }
      else if (e.key === "Tab") {   // item 14 — trap Tab within the dialog (mirrors keyHelp / settings)
        e.preventDefault();
        if (!tabItems.length) return;
        var cur = tabItems.indexOf(document.activeElement); if (cur < 0) cur = 0;
        var to = (cur + (e.shiftKey ? -1 : 1) + tabItems.length) % tabItems.length;
        var tgt = tabItems[to], ci = cards.indexOf(tgt);
        if (ci >= 0) focusAt(ci); else try { tgt.focus(); } catch (x) {}
      }
    }
    cards.forEach(function (c, i) {
      c.onclick = function () { pick(ENTRIES[i]); };
      c.onmouseenter = function () { c.style.borderColor = "var(--hair-2)"; c.style.background = "var(--raise)"; };
      c.onmouseleave = function () { c.style.borderColor = ""; c.style.background = "var(--well)"; };
    });
    if (explore) explore.onclick = function () { try { save("started", "1"); } catch (e) {} close(); };   // item 14 — just close
    sc.onclick = close;
    document.addEventListener("keydown", onKey, true);
    SB.announce(t("start.title"));
    setTimeout(function () { if (cards[0]) cards[0].focus(); }, 30);
  };

  /* ---- cross-tool chain breadcrumb (light): wiki › spark › jury -------------------
     Only visible when SB._chain is set (by the launcher's "Wiki → Spark" path or by
     SB.sparkLaunch), so the pipeline stays in view mid-flight. Each segment jumps to
     its tool; the active tool's segment is emphasized; a × clears the hint. Not a new
     subsystem — a single strip chip, inline-styled (shell CSS is not ours to edit). */
  var CHAIN_STEPS = [
    { tool: "wiki",  k: "chain.step.wiki" },
    { tool: "spark", k: "chain.step.spark" },
    { tool: "jury",  k: "chain.step.jury" },
  ];
  function renderChain() {
    var host = $("#sb-chain"); if (!host) return;
    if (!SB._chain) { host.hidden = true; host.innerHTML = ""; return; }
    host.hidden = false;
    host.style.cssText = "display:inline-flex;align-items:center;gap:5px;margin-left:8px;padding:2px 5px 2px 8px;" +
      "border:1px solid var(--hair);border-radius:var(--r-pill);background:var(--well);font-size:var(--t-note);white-space:nowrap";   // item 14 — text ≥12px (--t-note)
    host.setAttribute("role", "group"); host.setAttribute("aria-label", t("chain.title"));
    var parts = [];
    CHAIN_STEPS.forEach(function (s, i) {
      if (i) parts.push('<span aria-hidden="true" style="color:var(--faint)">›</span>');
      var on = S.tool === s.tool;
      parts.push('<button type="button" class="sb-chain-seg" data-tool="' + s.tool + '"' + (on ? ' aria-current="step"' : '') +
        // item 14 — a real touch/click target: min-height 24px + ~6px horizontal padding + ≥12px text
        ' style="border:0;background:none;cursor:pointer;font:inherit;font-size:var(--t-note);display:inline-flex;align-items:center;min-height:24px;padding:0 6px;border-radius:5px;font-weight:' + (on ? "640" : "460") +
        ';color:' + (on ? "var(--accent-ink)" : "var(--muted)") + '">' + esc(t(s.k)) + '</button>');
    });
    parts.push('<button type="button" class="sb-chain-x" aria-label="' + esc(t("chain.dismiss")) + '" title="' + esc(t("chain.dismiss")) +
      // item 14 — a 24×24 × hit box (was a ~10px sliver)
      '" style="border:0;background:none;padding:0;cursor:pointer;color:var(--faint);font:inherit;font-size:var(--t-note);line-height:1;display:inline-flex;align-items:center;justify-content:center;min-width:24px;min-height:24px;border-radius:5px">×</button>');
    host.innerHTML = parts.join("");
    $$(".sb-chain-seg", host).forEach(function (b) {
      b.onclick = function () { var tool = b.dataset.tool; SB.setTool(tool); if (tool === "spark") { try { SB.setSub("runs"); } catch (e) {} } };
    });
    var x = $(".sb-chain-x", host); if (x) x.onclick = function () { SB._chain = null; renderChain(); };
  }
  SB.renderChain = renderChain;

  /* ---- SB.sparkLaunch(idea): the shell hook WIKI calls from a scored idea's ------
     "· 直接起跑 / Launch in Spark". Sets the wiki→spark→jury chain hint, then prefills
     Spark's new-run form via the existing SB.sparkDraft path (title/hypothesis/direction
     → the form) and lands on Spark ▸ Runs. HONEST: it does NOT auto-POST /api/runs —
     Spark exposes no shell-callable run-start hook that also wires the runs view, and a
     30–90 min run should not fire without the user pressing the form's Start button. So
     this degrades to prefill-only (exactly the safe fallback) and never claims a run
     started. Guarded end-to-end. */
  SB.sparkLaunch = function (idea) {
    SB._chain = "wiki2spark";
    try {
      if (typeof SB.sparkDraft === "function") { SB.sparkDraft(idea || {}); }   // prefill + setTool('spark') + setSub('runs')
      else { SB.setTool("spark"); try { SB.setSub("runs"); } catch (e) {} }
    } catch (e) {
      try { SB.setTool("spark"); SB.setSub("runs"); } catch (e2) {}
    }
    renderChain();
  };

  /* ---- SB.project (R2): the ONE shared active project the three tools agree on ----
     A project = a library entry (the server-suggested "default workspace", or one of
     the configured roots). Selecting one re-bases each tool's dir under it and mirrors
     that into SB.data (the existing per-tool dir mechanism) so tools follow immediately,
     even before they read SB.project.get() themselves. Persisted like tool/theme/lang. */
  var PROJECTS = [];   // [{ id, label, sub, kind, dirs:{spark,jury,wiki} }]
  var _bootFreshTool = false, _homeAuto = false;   // R4: Home as first-run default when >1 project
  function basename(p) { if (!p) return ""; var s = String(p).replace(/[\\\/]+$/, ""); var m = s.split(/[\\\/]/); return m[m.length - 1] || s; }
  function isUnder(child, parent) {
    if (!child || !parent) return false;
    var a = String(child).replace(/[\\\/]+$/, "").toLowerCase(), b = String(parent).replace(/[\\\/]+$/, "").toLowerCase();
    return a === b || a.indexOf(b + "\\") === 0 || a.indexOf(b + "/") === 0;
  }
  // resolve the per-tool dirs for a project id: unbound → server defaults untouched;
  // a root → keep each tool's default when it lives under the root, else re-base to it.
  function resolveProjectDirs(defaults, pid) {
    defaults = defaults || {};
    if (!pid) return { spark: defaults.spark || "", jury: defaults.jury || "", wiki: defaults.wiki || "" };
    function pick(tool) { var d = defaults[tool]; return d && isUnder(d, pid) ? d : pid; }
    return { spark: pick("spark"), jury: pick("jury"), wiki: pick("wiki") };
  }
  function buildProjects(lib) {
    var d = (lib && lib.defaults) || {}, roots = (lib && lib.roots) || [], out = [];
    out.push({ id: "", label: t("proj.default"), sub: "", kind: "default", dirs: { spark: d.spark || "", jury: d.jury || "", wiki: d.wiki || "" } });
    roots.forEach(function (r) {
      out.push({ id: r, label: basename(r) || r, sub: r, kind: "root", dirs: resolveProjectDirs(d, r) });
    });
    PROJECTS = out;
    paintProject();
    // R4: on a genuine first run with more than one project, land on the Home overview
    if (_bootFreshTool && !_homeAuto && PROJECTS.length > 1) { _homeAuto = true; SB.setTool("home"); }
    return out;
  }
  function activeProject() {
    for (var i = 0; i < PROJECTS.length; i++) if (PROJECTS[i].id === (S.project || "")) return PROJECTS[i];
    return PROJECTS[0] || { id: "", label: t("proj.default"), dirs: {} };
  }
  SB.project = {
    get: function () { return S.project || null; },        // active project id ("" persisted) → null when unbound
    set: function (id) {
      id = id || "";
      S.project = id; save("project", id);
      var ap = activeProject();
      // bridge into the existing per-tool dir mechanism so un-migrated tools follow now
      if (SB.data && SB.data.setDir && ap && ap.dirs) {
        ["spark", "jury", "wiki"].forEach(function (tool) {
          try { localStorage.setItem("sb.dir." + tool, ap.dirs[tool] || ""); } catch (e) {}
        });
      }
      paintProject();
      if (SB._lib) { SB.needs.dirs = resolveProjectDirs((SB._lib.defaults) || {}, id); }
      SB.needs.refetch && SB.needs.refetch();            // refresh badges/lamps/Home for the new project
      renderWsTitle(); renderWorkspace();                 // set() re-renders
    },
    list: function () { return PROJECTS.slice(); },
    dirFor: function (tool) { var ap = activeProject(); return (ap && ap.dirs && ap.dirs[tool]) || ""; },
    active: activeProject,
  };
  function paintProject() {
    var btn = $("#sb-proj"); if (!btn) return;
    var ap = activeProject();
    var lbl = ap && ap.id ? ap.label : t("proj.default");
    btn.querySelector(".proj-lbl").textContent = lbl;
    btn.title = t("proj.pick") + " — " + lbl;
    btn.setAttribute("aria-label", t("cap.workspace") + ": " + lbl);   // R28e: folder-glyph control = Workspace
    btn.hidden = PROJECTS.length <= 1;                    // no chooser when the library has a single entry
  }
  function openProjectPicker() {
    $$("#sb-projpop,#sb-projpop-scrim").forEach(function (n) { n.remove(); });
    var btn = $("#sb-proj"); if (!btn) return;
    var sc = el("div", "scrim"); sc.id = "sb-projpop-scrim"; sc.style.background = "transparent"; sc.style.backdropFilter = "none";
    var pop = el("div", "pop projpop"); pop.id = "sb-projpop"; pop.setAttribute("role", "listbox"); pop.setAttribute("aria-label", t("proj.pick"));
    var cur = S.project || "";
    // R26b — a type-to-filter input above the options; ArrowUp/Down/Home/End rove the list
    var fin = el("input", "pj-filter"); fin.type = "text"; fin.setAttribute("autocomplete", "off"); fin.setAttribute("spellcheck", "false");
    fin.setAttribute("aria-label", t("proj.pick")); fin.placeholder = t("proj.pick");
    fin.style.cssText = "width:100%;box-sizing:border-box;margin:0 0 4px;border:1px solid rgba(128,128,128,.28);background:transparent;color:inherit;font:inherit;font-size:13px;border-radius:8px;padding:6px 8px;outline:none";
    pop.appendChild(fin);
    var listBox = el("div", "pj-list"); pop.appendChild(listBox);
    var active = 0;
    function optHTML(q) {
      q = (q || "").toLowerCase();
      var arr = PROJECTS.filter(function (p) { return !q || String(p.label).toLowerCase().indexOf(q) >= 0 || String(p.sub || "").toLowerCase().indexOf(q) >= 0; });
      return arr.map(function (p, i) {
        var on = p.id === cur, sub = p.kind === "root" ? (t("proj.root") + " · " + p.sub) : "";
        return '<button class="pj-row" role="option" aria-selected="' + (on ? "true" : "false") + '" data-id="' + esc(p.id) + '" id="pj-opt-' + i + '">' +
          '<span class="pj-tick">' + (on ? '<svg class="i sm"><use href="#i-check"/></svg>' : '') + '</span>' +
          '<span class="pj-main"><span class="pj-lbl">' + esc(p.label) + '</span>' +
          (sub ? '<span class="pj-sub">' + esc(sub) + '</span>' : '') + '</span></button>';
      }).join("");
    }
    function mark() {
      var rows = $$(".pj-row", listBox);
      rows.forEach(function (r, i) { var on = i === active; r.classList.toggle("active", on); r.style.background = on ? "rgba(128,128,128,.16)" : ""; });
      if (rows[active]) { rows[active].scrollIntoView({ block: "nearest" }); fin.setAttribute("aria-activedescendant", rows[active].id); }
      else fin.removeAttribute("aria-activedescendant");
    }
    function draw() {
      listBox.innerHTML = optHTML(fin.value) || ('<div class="pj-empty" style="padding:8px;opacity:.6;font-size:13px">' + esc(S.lang === "zh" ? "没有匹配项" : "No matches") + '</div>');
      var rows = $$(".pj-row", listBox);
      active = 0; rows.forEach(function (r, i) { if (r.getAttribute("aria-selected") === "true") active = i; });
      rows.forEach(function (row, i) {
        row.onclick = function () { close(); SB.project.set(row.dataset.id); };
        row.addEventListener("mousemove", function () { if (active !== i) { active = i; mark(); } });
      });
      mark();
    }
    document.body.appendChild(sc); document.body.appendChild(pop);
    var r = btn.getBoundingClientRect();
    pop.style.left = Math.max(8, r.left) + "px"; pop.style.top = (r.bottom + 6) + "px";
    var opener = document.activeElement;
    function close() { pop.remove(); sc.remove(); document.removeEventListener("keydown", onKey, true); try { opener && opener.focus(); } catch (e) {} }
    function onKey(e) {
      var rows = $$(".pj-row", listBox);
      if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); close(); }
      else if (e.key === "ArrowDown") { e.preventDefault(); active = Math.min(rows.length - 1, active + 1); mark(); }
      else if (e.key === "ArrowUp") { e.preventDefault(); active = Math.max(0, active - 1); mark(); }
      else if (e.key === "Home") { e.preventDefault(); active = 0; mark(); }
      else if (e.key === "End") { e.preventDefault(); active = rows.length - 1; mark(); }
      else if (e.key === "Enter") { e.preventDefault(); if (rows[active]) { var id = rows[active].dataset.id; close(); SB.project.set(id); } }
    }
    sc.onclick = close;
    fin.addEventListener("input", draw);
    document.addEventListener("keydown", onKey, true);
    draw();
    setTimeout(function () { try { fin.focus(); } catch (e) {} }, 20);
  }
  SB.projectPicker = openProjectPicker;

  /* ---- R12 copy-status + activity feed; R27 saved views ------------------- */
  function copyNow(txt) {
    var ok = function () { SB.toast(t("act.copied")); };
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) { navigator.clipboard.writeText(txt).then(ok, function () { legacyCopy(txt); ok(); }); return; }
    } catch (e) {}
    legacyCopy(txt); ok();
  }
  // R12b — a shareable markdown snapshot of everything waiting on the user, grouped by tool.
  function statusMarkdown() {
    var d = SB.needs.detail || {}, ap = activeProject(), lines = [];
    lines.push("# " + t("needs.tray") + " · " + ((ap && ap.label) || t("proj.default")));
    var j = d.jury || {};
    if ((j.items || []).length) {
      lines.push("", "## " + NEEDS_NAME.jury);
      (j.items || []).forEach(function (i) {
        var tags = [i.gateBlocking ? t("home.gateblock") : "", i.escalated ? t("home.escalated") : "", i.significance].filter(Boolean).join(" · ");
        lines.push("- **" + i.id + "** " + (i.summary || "") + (tags ? "  (" + tags + ")" : ""));
      });
    }
    var s = d.spark || {}, sw = (s.runs || []).filter(function (r) { return r.waiting || r.needs; });
    if (sw.length || s.decisions) {
      lines.push("", "## " + NEEDS_NAME.spark);
      sw.forEach(function (r) { lines.push("- " + (r.title || r.id) + [r.stage ? " · " + r.stage : "", r.status ? " · " + r.status : ""].join("")); });
      if (s.decisions) lines.push("- " + s.decisions + " " + t("needs.dec"));
    }
    var w = d.wiki || {};
    if (w.inbox) { lines.push("", "## " + NEEDS_NAME.wiki); lines.push("- " + w.inbox + " " + t("home.inbox")); }
    if (lines.length <= 1) lines.push("", "_" + t("needs.empty") + "_");
    try { lines.push("", location.origin + location.pathname + "?panel=needs"); } catch (e) {}
    return lines.join("\n");
  }
  SB.copyStatus = function () { copyNow(statusMarkdown()); };
  // R12a — merge genuinely-dated events into one reverse-chron feed. Only spark runs carry
  // a real timestamp (started); jury/wiki items are undated, so we do NOT fabricate dates for
  // them — the feed stays honest and simply omits what has no date.
  function activityEvents() {
    var out = [], s = (SB.needs.detail && SB.needs.detail.spark) || {};
    (s.runs || []).forEach(function (r) {
      var ts = r.started ? Date.parse(r.started) : NaN; if (isNaN(ts)) return;
      out.push({ ts: ts, tool: "spark", sub: "runs", id: r.id, label: (r.title || r.id) + " · " + sparkVerdict(r).label });
    });
    out.sort(function (a, b) { return b.ts - a.ts; });
    return out;
  }
  function feedSeen() { try { return parseInt(load("feedseen", "0"), 10) || 0; } catch (e) { return 0; } }
  function markFeedSeen() { var ev = activityEvents(); if (ev.length) save("feedseen", String(ev[0].ts)); }
  function fmtDate(ts) { try { var dt = new Date(ts); return dt.getFullYear() + "-" + ("0" + (dt.getMonth() + 1)).slice(-2) + "-" + ("0" + dt.getDate()).slice(-2); } catch (e) { return ""; } }

  // R27 — saved views: {tool, sub, filter, project}. Three built-in seeds show value first.
  var VIEW_SEEDS = [
    { id: "seed-gate", zh: "闸门阻断重大项", en: "Gate-blocking majors", view: { tool: "jury", sub: "docket", filter: "gate" } },
    { id: "seed-author", zh: "待作者定夺", en: "Author-required", view: { tool: "jury", sub: "docket", filter: "author" } },
    { id: "seed-skim", zh: "Wiki 覆盖缺口", en: "Wiki skim-gaps", view: { tool: "wiki", sub: "coverage" } },
  ];
  function loadUserViews() { try { return JSON.parse(load("views", "[]")) || []; } catch (e) { return []; } }
  function saveUserViews(arr) { save("views", JSON.stringify(arr)); }
  function curFilterInput() { return $("#wiki-filter-in") || $(".wiki-filter-in") || $("[data-view-filter]") || $(".col-list input[type='text']"); }
  function captureView() {
    var tl = TOOLS[S.tool], fi = curFilterInput();
    return { tool: S.tool, sub: tl ? tl.curSub : "", filter: fi ? fi.value : "", project: S.project || "" };
  }
  function applyView(v) {
    if (!v) return;
    if (v.project != null && (v.project || "") !== (S.project || "")) SB.project.set(v.project);
    if (v.tool && v.tool !== "home") SB.setTool(v.tool); else if (v.tool === "home") { SB.setTool("home"); return; }
    if (v.sub) SB.setSub(v.sub);
    if (v.filter && v.filter !== "gate" && v.filter !== "author") setTimeout(function () {
      var fi = curFilterInput(); if (fi && "value" in fi) { fi.value = v.filter; try { fi.dispatchEvent(new Event("input", { bubbles: true })); } catch (e) {} }
    }, 40);
  }
  // item 18 — the default name for a freshly-saved view is the current tool ▸ sub label.
  function defaultViewLabel() {
    if (S.tool === "home") return t("home.title");
    var tl = TOOLS[S.tool], tname = (I18N[S.lang] && I18N[S.lang]["tool." + S.tool]) || S.tool, sub = "";
    if (tl && tl.sub) tl.sub.forEach(function (s) { if (s.id === tl.curSub) sub = s.label; });
    return tname + (sub ? " ▸ " + sub : "");
  }
  SB.views = {
    list: function () {
      var seeds = VIEW_SEEDS.map(function (s) { return { id: s.id, label: S.lang === "zh" ? s.zh : s.en, view: s.view, seed: true }; });
      return seeds.concat(loadUserViews());
    },
    apply: function (v) { applyView(v && v.view ? v.view : v); },
    saveCurrent: function (label) {
      var arr = loadUserViews();
      arr.push({ id: "v" + Date.now(), label: label || defaultViewLabel(), view: captureView() });
      saveUserViews(arr); SB.toast(t("view.saved.done"));
    },
    remove: function (id) { saveUserViews(loadUserViews().filter(function (v) { return v.id !== id; })); },   // item 18 — user views only
    defaultLabel: defaultViewLabel,
  };
  // item 18 — 'Save current view' opens a tiny inline name input (prefilled with the tool ▸ sub
  // default) in place of the chip; Enter saves, Esc / blur cancels. Re-renders Home either way.
  function startSaveView(chip, repaint) {
    var wrap = chip.parentNode; if (!wrap) return;
    var inp = el("input", "home-view-nameatt");
    inp.type = "text"; inp.value = SB.views.defaultLabel(); inp.setAttribute("aria-label", t("view.save"));
    inp.style.cssText = "font:inherit;font-size:12px;border:1px solid var(--accent);background:var(--well);color:var(--ink);border-radius:999px;padding:3px 10px;outline:none;width:170px";
    chip.style.display = "none"; wrap.insertBefore(inp, chip);
    var done = false;
    function commit() { if (done) return; done = true; var name = inp.value.trim(); if (name) SB.views.saveCurrent(name); repaint(); }
    function cancel() { if (done) return; done = true; if (inp.parentNode) inp.remove(); chip.style.display = ""; }
    inp.addEventListener("keydown", function (e) {
      if (e.key === "Enter") { e.preventDefault(); commit(); }
      else if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); cancel(); }
    });
    inp.addEventListener("blur", function () { setTimeout(cancel, 120); });
    setTimeout(function () { try { inp.focus(); inp.select(); } catch (e) {} }, 10);
  }

  /* ---- Home (R4): cross-tool overview, reusing the SB.needs aggregator ---------
     One section per tool (Spark runs · Jury dockets · Wiki coverage/inbox). Every
     row deep-links into tool+view(+item). Renders instantly from SB.needs.detail and
     live-refreshes when the poll lands (SB._homeRefresh). */
  // R12 — a Spark run reads its verdict from status (paper ready / halted@stage /
  // errored@stage / waiting), tinted to match; unfinished runs sort up and read 'hot'.
  var SPARK_TERMINAL = { done: 1, error: 1, stopped: 1 };
  function shortStage(s) { return s ? String(s).split(/\s+/)[0] : "—"; }
  function sparkVerdict(r) {
    var zh = S.lang === "zh", stage = shortStage(r.stage);
    if (r.status === "done") return { label: zh ? "论文就绪" : "paper ready", tone: "ok" };
    if (r.status === "error") return { label: (zh ? "出错于 " : "errored · ") + stage, tone: "bad" };
    if (r.status === "stopped") return { label: (zh ? "停在 " : "halted · ") + stage, tone: "stale" };
    if (r.waiting || r.needs) return { label: zh ? "等待你" : "waiting on you", tone: "wait" };
    return { label: (zh ? "进行中 · " : "running · ") + stage, tone: "wait" };
  }
  function sparkRank(r) {   // needs-me & unfinished first; ready last
    if (r.waiting || r.needs) return 0;
    if (r.status === "error" || r.status === "stopped") return 1;
    if (!SPARK_TERMINAL[r.status]) return 2;
    return 3;
  }
  function relTime(iso) {
    if (!iso) return "";
    var t0 = Date.parse(iso); if (isNaN(t0)) return "";
    var s = Math.max(0, (Date.now() - t0) / 1000), zh = S.lang === "zh";
    if (s < 60) return zh ? "刚刚" : "just now";
    var m = Math.floor(s / 60); if (m < 60) return zh ? m + " 分钟前" : m + "m ago";
    var h = Math.floor(m / 60); if (h < 24) return zh ? h + " 小时前" : h + "h ago";
    var dd = Math.floor(h / 24); if (dd < 30) return zh ? dd + " 天前" : dd + "d ago";
    return zh ? Math.floor(dd / 30) + " 个月前" : Math.floor(dd / 30) + "mo ago";
  }
  SB.relTime = relTime;   // item 11 — spark consumes this for its Runs hero + reading feed recency
  var _homeSparkExpanded = false;   // R7: single-project Home caps the run list to 5, then expands
  function homeRowsSpark(expanded) {
    var d = SB.needs.detail.spark || {}, runs = (d.runs || []).slice(), rows = "";
    runs.sort(function (a, b) { return sparkRank(a) - sparkRank(b); });   // needs-me / unfinished first
    if (d.decisions) rows += homeRow("spark", "governance", null, (S.lang === "zh" ? "决策队列" : "Decision queue"), "", true, { tag: { label: d.decisions + " " + t("needs.dec"), tone: "wait" } });
    var shown = expanded ? runs : runs.slice(0, 5);      // R7: needs-first, cap the dead-canvas dump
    shown.forEach(function (r) {
      rows += homeRow("spark", "runs", r.id, r.title, "", r.status !== "done", { tag: sparkVerdict(r), time: relTime(r.started) });
    });
    if (!expanded && runs.length > 5) {
      var more = runs.length - 5;
      rows += '<button class="home-row home-more" data-more="spark"><span class="home-rl">' +
        esc((S.lang === "zh" ? "还有 " + more + " 项" : "+" + more + " more")) + '</span><svg class="i sm home-go"><use href="#i-arrow"/></svg></button>';
    }
    if (!rows) rows = '<div class="home-empty">' + esc(t("home.empty")) + '</div>';
    return rows;
  }
  function homeRowsJury() {
    var d = SB.needs.detail.jury || {}, items = d.items || [], rows = "";
    items.forEach(function (i) {
      var tags = [i.gateBlocking ? t("home.gateblock") : "", i.escalated ? t("home.escalated") : "", i.significance].filter(Boolean).join(" · ");
      rows += homeRow("jury", "docket", i.id, i.id + " · " + i.summary, tags, i.gateBlocking || i.escalated);
    });
    if (!rows) rows = '<div class="home-empty">' + esc(t("home.empty")) + '</div>';
    return rows;
  }
  function homeRowsWiki() {
    var d = SB.needs.detail.wiki || {}, rows = "";
    if (d.inbox) rows += homeRow("wiki", "inbox", null, t("home.inbox"), d.inbox + " " + t("home.needs"), true);
    var cov = d.coverage ? (d.coverage.zones + (S.lang === "zh" ? " 个饱和区" : " saturation zones")) : "—";
    rows += homeRow("wiki", "coverage", null, t("home.coverage"), cov, false);
    if (d.corpus != null) rows += homeRow("wiki", "library", null, (S.lang === "zh" ? "语料" : "Corpus"), d.corpus + (S.lang === "zh" ? " 条" : " notes"), false);
    return rows;
  }
  function homeRow(tool, sub, id, label, meta, hot, extra) {
    extra = extra || {};
    var tag = extra.tag ? '<span class="home-tag ' + esc(extra.tag.tone || "") + '">' + esc(extra.tag.label) + '</span>' : "";
    // item 20 — nowrap so a relTime like '1 天前' never snaps to '1 天' / '前' in the ~300px column.
    // (relTime itself stays plain text — it also feeds esc'd cells and the markdown dossier — so the
    // no-wrap is applied here at the render site rather than baked into its return value.)
    var time = extra.time ? '<span class="home-rt" style="white-space:nowrap">' + esc(extra.time) + '</span>' : "";
    return '<button class="home-row' + (hot ? " hot" : "") + '" data-tool="' + tool + '" data-sub="' + esc(sub) + '" data-id="' + esc(id || "") + '">' +
      '<span class="home-rl">' + esc(label) + '</span>' + tag +
      (meta ? '<span class="home-rm">' + esc(meta) + '</span>' : '') + time +
      '<svg class="i sm home-go"><use href="#i-arrow"/></svg></button>';
  }
  // item 20 — an honest empty state (never a blank canvas): "nothing here" + why (dirs unreadable).
  function homeEmptyHint() {
    return '<div class="home-empty">' + esc(t("home.empty")) +
      '<span style="display:block;margin-top:6px;font-size:12px;opacity:.6">' + esc(t("home.noread")) + '</span></div>';
  }
  function homeSection(nm, title, count, rowsHTML) {
    return '<section class="home-col" style="--accent:' + NEEDS_TINT[nm] + '">' +
      '<header class="home-ch"><span class="home-dot" style="background:' + NEEDS_TINT[nm] + '"></span>' +
      '<h2>' + esc(title) + '</h2>' + (count > 0 ? '<span class="home-badge">' + count + ' ' + esc(t("home.needs")) + '</span>' : '') +
      '<button class="home-all" data-tool="' + nm + '">' + esc(t("home.viewall")) + '</button></header>' +
      '<div class="home-rows">' + rowsHTML + '</div></section>';
  }
  // R7 — Home mode: 'all' (portfolio, one row per paper) vs 'single' (drill-down). Only
  // meaningful with >1 project; persisted like the other view state.
  function homeMode() { return PROJECTS.length > 1 ? (load("homemode", "all") === "single" ? "single" : "all") : "single"; }
  function setHomeMode(m) { save("homemode", m); }
  // R7 — per-project needs, reusing the existing per-dir fetchers (spark runs stay global
  // as that fetcher is global; decisions/jury/wiki are per-dir).
  function fetchProjectNeeds(p) {
    var dirs = p.dirs || {};
    return Promise.all([fetchSparkNeeds(dirs.spark), fetchJuryNeeds(dirs.jury), fetchWikiNeeds(dirs.wiki)]).then(function (r) {
      return { project: p, spark: r[0], jury: r[1], wiki: r[2], total: (r[0].count || 0) + (r[1].count || 0) + (r[2].count || 0) };
    });
  }
  function homeRollupHTML() {
    var c = SB.needs.counts, total = (c.spark || 0) + (c.jury || 0) + (c.wiki || 0);
    return total > 0 ? '<button class="home-needs-pill" data-needs aria-label="' + esc(total + " " + t("home.needs")) + '"><span class="hnp-dot"></span>' + total + ' ' + esc(t("home.needs")) + '</button>' : "";
  }
  // one-click LAUNCHER affordance on the Home hub: opens the three-path start screen.
  function homeStartChipHTML() {
    return '<button class="home-chip home-start" data-start style="margin-left:auto"><svg class="i sm" style="width:13px;height:13px"><use href="#i-spark"/></svg>' + esc(t("start")) + ' ▸</button>';
  }
  function homeModeToggleHTML(mode) {
    if (PROJECTS.length <= 1) return "";
    return '<div class="home-mode" role="group" aria-label="' + esc(t("home.tag")) + '">' +
      '<button class="home-chip home-modebtn' + (mode === "all" ? " on" : "") + '" data-mode="all" aria-pressed="' + (mode === "all" ? "true" : "false") + '">' + esc(t("home.allproj")) + '</button>' +
      '<button class="home-chip home-modebtn' + (mode === "single" ? " on" : "") + '" data-mode="single" aria-pressed="' + (mode === "single" ? "true" : "false") + '">' + esc(t("home.thisproj")) + '</button></div>';
  }
  // item 3 — the portfolio's sort control (readiness desc by default; needs / recent alternatives)
  var _pfSort = "ready";
  function pfSortToggleHTML() {
    var zh = S.lang === "zh";
    var opts = [["ready", zh ? "就绪度" : "Readiness"], ["needs", zh ? "待办" : "Needs"], ["recent", zh ? "最近" : "Recent"]];
    return '<div class="home-mode pf-sort" role="group" aria-label="' + esc(zh ? "排序方式" : "Sort by") + '">' +
      '<span class="home-views-h" style="margin-right:2px">' + esc(zh ? "排序" : "Sort") + '</span>' +
      opts.map(function (o) { return '<button class="home-chip pf-sortbtn' + (_pfSort === o[0] ? " on" : "") + '" data-pfsort="' + o[0] + '" aria-pressed="' + (_pfSort === o[0] ? "true" : "false") + '">' + esc(o[1]) + '</button>'; }).join("") +
      '</div>';
  }
  // item 2 — the spark node reads the LATEST run's real state (never a bare '—' once a run
  // is done), with a recency suffix. Reuses sparkVerdict / relTime above.
  function sparkCellText(sp, zh) {
    var runs = (sp.runs || []).slice();
    if (!runs.length) return { txt: (zh ? "无运行" : "no runs"), hot: false };
    runs.sort(function (a, b) { return (Date.parse(b.started) || 0) - (Date.parse(a.started) || 0); });
    var r = runs[0], v = sparkVerdict(r), rec = relTime(r.started);
    return { txt: v.label + (r.status === "done" ? " ✓" : "") + (rec ? " · " + rec : ""), hot: r.status !== "done" };
  }
  // item 2 — the single most-important next step for a project row, deep-linking the
  // specific blocker (first gate-blocking charge when present).
  // item 3 — a 0-100 readiness score per project row from SB.needs.detail: a passing latest run
  // lifts it, each gate-blocking charge is a heavy drag, author-pending (escalated) a medium one,
  // filed coverage a bonus, an open inbox a small drag.
  function readinessScore(row) {
    var sp = row.spark.detail || {}, jr = row.jury.detail || {}, wk = row.wiki.detail || {};
    var runs = (sp.runs || []).slice().sort(function (a, b) { return (Date.parse(b.started) || 0) - (Date.parse(a.started) || 0); });
    var latest = runs[0], score = 45;
    if (latest && latest.status === "done") score += 35;                                   // + passing latest run
    else if (latest && (latest.status === "error" || latest.status === "stopped")) score -= 10;
    score -= 22 * (jr.blocking || 0);                                                       // − heavy per gate-blocking charge
    score -= 9 * (jr.escalated || 0);                                                       // − medium author-pending
    if (wk.corpus) score += Math.min(15, wk.corpus * 3);                                    // + coverage bonus
    score -= 4 * (wk.inbox || 0);                                                           // − small open inbox
    if (sp.waiting) score -= 12;
    return Math.max(0, Math.min(100, Math.round(score)));
  }
  function scoreTone(s) { return s >= 80 ? "ok" : s >= 50 ? "wait" : "bad"; }
  function latestTs(row) {
    var runs = ((row.spark && row.spark.detail && row.spark.detail.runs) || []), m = 0;
    runs.forEach(function (r) { var t0 = Date.parse(r.started) || 0; if (t0 > m) m = t0; });
    return m;
  }
  // item 3 — sort bucket for the default 'readiness' order: ship-ready (0) and needs-you (1) both
  // float to the top, everything else (2) sinks; ties break by readiness desc.
  function pfBucket(row) { var na = nextAction(row, false); if (na && na.positive) return 0; if ((row.total || 0) > 0) return 1; return 2; }
  function nextAction(row, zh) {
    var sp = row.spark.detail || {}, jr = row.jury.detail || {}, wk = row.wiki.detail || {};
    // item 3 — POSITIVE branch: spark done AND the ledger is bound (a jury dir resolved) with zero
    // gate-blocking / escalated charges AND no waiting run → a sage 'ready to submit' chip, not a chore.
    var spDone = (sp.runs || []).some(function (r) { return r.status === "done"; });
    var bound = !!(row.project && row.project.dirs && row.project.dirs.jury);
    if (spDone && bound && !jr.blocking && !jr.escalated && !sp.waiting) {
      return { tool: "spark", sub: "runs", id: null, positive: true, label: (zh ? "可提交 · 打开 PDF / 投稿护盾 →" : "Ready to submit · Open PDF / shield →") };
    }
    if (jr.blocking) {
      var fb = ((jr.items || []).filter(function (i) { return i.gateBlocking; })[0]) || null;
      return { tool: "jury", sub: "docket", id: fb ? fb.id : null, label: (zh ? "清理 " + jr.blocking + " 项闸门阻断 →" : "Clear " + jr.blocking + " gate-block" + (jr.blocking > 1 ? "s" : "") + " →") };
    }
    if (sp.waiting) return { tool: "spark", sub: "runs", id: null, label: (zh ? "回应 " + sp.waiting + " 个等待中的运行 →" : "Answer " + sp.waiting + " waiting run" + (sp.waiting > 1 ? "s" : "") + " →") };
    if (sp.decisions) return { tool: "spark", sub: "governance", id: null, label: (zh ? "处置 " + sp.decisions + " 项决策 →" : "Resolve " + sp.decisions + " decision" + (sp.decisions > 1 ? "s" : "") + " →") };
    if (jr.escalated) return { tool: "jury", sub: "docket", id: null, label: (zh ? jr.escalated + " 项已升级待办 →" : jr.escalated + " escalated →") };
    if (wk.inbox) return { tool: "wiki", sub: "inbox", id: null, label: (zh ? "整理 " + wk.inbox + " 条收件箱 →" : "Triage " + wk.inbox + " inbox →") };
    return null;
  }
  function pfRowHTML(row) {
    var p = row.project, zh = S.lang === "zh";
    // a pipeline node: dot + kicker (Draft/Review/Filed) + state line, deep-linking the tool
    function node(tool, sub, kick, label, hot, badge) {
      return '<button class="pf-cell' + (hot ? " hot" : "") + '" data-proj="' + esc(p.id) + '" data-tool="' + tool + '"' + (sub ? ' data-sub="' + esc(sub) + '"' : '') +
        ' aria-label="' + esc(NEEDS_NAME[tool] + " · " + kick + " · " + label) + '"><span class="pf-cell-dot" style="background:' + NEEDS_TINT[tool] + '"></span>' +
        '<span class="pf-cell-lbl"><span class="pf-node-k">' + esc(kick) + '</span>' + esc(label) + (badge || "") + '</span></button>';
    }
    var sp = row.spark.detail || {}, jr = row.jury.detail || {}, wk = row.wiki.detail || {};
    var draft = sparkCellText(sp, zh);                                        // node 1 — Draft (spark verdict)
    var jrTxt = (jr.blocking || jr.escalated)                                 // node 2 — Review (jury)
      ? [jr.blocking ? jr.blocking + " " + t("home.gateblock") : "", jr.escalated ? jr.escalated + " " + t("home.escalated") : ""].filter(Boolean).join(" · ")
      : (zh ? "无阻断" : "clear");
    var wkTxt = wk.corpus != null                                            // node 3 — Filed (wiki insights)
      ? (wk.corpus + (zh ? " 条已归档" : " filed")) + (wk.inbox ? (zh ? " · " + wk.inbox + " 待入" : " · " + wk.inbox + " pending") : "")
      : (wk.inbox ? (wk.inbox + " " + t("home.inbox")) : "—");
    var na = nextAction(row, zh), ready = !!(na && na.positive);
    // item 3 — a sage positive chip when ship-ready, else the existing hot 'Next action' chip.
    var cta = na ? '<div class="pf-next-row"><button class="pf-cell pf-next' + (ready ? " pf-next-ready" : " hot") + '"' +
      (ready ? ' style="border:1px solid #4a8f5b"' : '') + ' data-proj="' + esc(p.id) + '" data-tool="' + na.tool + '"' +
      (na.sub ? ' data-sub="' + esc(na.sub) + '"' : '') + (na.id ? ' data-id="' + esc(na.id) + '"' : '') +
      ' aria-label="' + esc((ready ? (zh ? "可提交:" : "Ready to submit: ") : (zh ? "下一步:" : "Next action: ")) + na.label) + '"><span class="pf-next-k"' +
      (ready ? ' style="color:#3f7d4e"' : '') + '>' + esc(ready ? (zh ? "就绪" : "Ready") : (zh ? "下一步" : "Next")) + '</span>' +
      '<span class="pf-cell-lbl">' + esc(na.label) + '</span></button></div>' : "";
    // item 3 — a right-aligned readiness pill on the row header, and a green check on the Filed node
    // + a 'ready' row class when the paper is ship-ready.
    var score = readinessScore(row), scol = ({ ok: "#4a8f5b", wait: "#b07d2a", bad: "#c15a48" })[scoreTone(score)];
    var scorePill = '<span class="pf-score" style="margin-left:auto;font-size:11px;font-variant-numeric:tabular-nums;white-space:nowrap;padding:2px 9px;border-radius:999px;border:1px solid var(--hair-2)" aria-label="' +
      esc((zh ? "就绪度 " : "Readiness ") + score + "/100") + '"><b style="color:' + scol + '">' + score + '</b> <span style="color:var(--muted)">' + esc(zh ? "就绪" : "ready") + '</span></span>';
    var filedBadge = ready ? ' <span style="color:#4a8f5b;font-weight:600" aria-hidden="true">✓</span>' : "";
    return '<div class="pf-row' + (row.total > 0 ? " hot" : "") + (ready ? " ready" : "") + '"><div class="pf-name">' +
      '<button class="pf-open" data-proj="' + esc(p.id) + '">' + esc(p.label) + '</button>' +
      (row.total > 0 ? '<span class="pf-badge">' + row.total + ' ' + esc(t("home.needs")) + '</span>' : '') + scorePill + '</div>' +
      '<div class="pf-cells pf-pipe">' +
        node("spark", "runs", (zh ? "草拟" : "Draft"), draft.txt, draft.hot) +
        node("jury", "docket", (zh ? "复检" : "Review"), jrTxt, (jr.blocking || jr.escalated) > 0) +
        node("wiki", "inbox", (zh ? "归档" : "Filed"), wkTxt, wk.inbox > 0, filedBadge) +
      '</div>' + cta + '</div>';
  }
  // R12a — a reverse-chron activity feed from genuinely-dated events (spark run starts);
  // events newer than the stored last-seen wear a NEW badge.
  function homeFeedHTML() {
    var ev = activityEvents(); if (!ev.length) return "";
    var seen = feedSeen();
    var rows = ev.slice(0, 12).map(function (e) {
      var isNew = e.ts > seen;
      return '<button class="home-feed-row' + (isNew ? " isnew" : "") + '" data-tool="' + e.tool + '" data-sub="' + esc(e.sub) + '" data-id="' + esc(e.id || "") + '">' +
        '<span class="hf-date">' + esc(fmtDate(e.ts)) + '</span>' +
        '<span class="hf-dot" style="background:' + NEEDS_TINT[e.tool] + '"></span>' +
        '<span class="hf-tool">' + esc(NEEDS_NAME[e.tool]) + '</span>' +
        '<span class="hf-lbl">' + esc(e.label) + '</span>' +
        (isNew ? '<span class="hf-new">' + esc(t("feed.new")) + '</span>' : '') + '</button>';
    }).join("");
    return '<section class="home-feed"><header class="home-ch"><h2>' + esc(t("feed.title")) + '</h2></header><div class="home-feed-rows">' + rows + '</div></section>';
  }
  // R27 — saved-views strip: built-in seeds + user views, plus a "save current view" chip
  function homeViewsHTML() {
    var vs = SB.views.list(), delLabel = S.lang === "zh" ? "删除视图" : "Delete view";
    // item 18 — user views (not the 3 seeds) get an inline ✕ delete; each chip is wrapped so the
    // delete button is a SIBLING, not an (invalid) button-inside-button.
    var chips = vs.map(function (v, i) {
      var del = (!v.seed && v.id) ? '<button class="home-view-del" data-viewdel="' + esc(v.id) + '" title="' + esc(delLabel) + '" aria-label="' + esc(delLabel + " ▸ " + v.label) + '" style="border:0;background:transparent;color:var(--muted);cursor:pointer;font:inherit;font-size:11px;padding:0 5px;margin-left:-3px">✕</button>' : "";
      return '<span class="home-view-wrap" style="display:inline-flex;align-items:center">' +
        '<button class="home-chip home-view-chip" data-view="' + i + '">' + esc(v.label) + '</button>' + del + '</span>';
    }).join("");
    return '<div class="home-views" role="group" aria-label="' + esc(t("view.saved")) + '"><span class="home-views-h">' + esc(t("view.saved")) + '</span>' +
      chips + '<button class="home-chip home-view-chip home-view-save" data-viewsave="1">＋ ' + esc(t("view.save")) + '</button></div>';
  }
  /* ---- item 27a — "since last visit" diff banner --------------------------
     Snapshot the gate-blocking charge ids + finished-run ids per project; on the
     next Home visit, diff against the stored snapshot to surface what changed. */
  function needsSnapKey() { return "needssnap." + (S.project || ""); }
  function currentNeedsIds() {
    var d = SB.needs.detail || {};
    return {
      jury: (((d.jury && d.jury.items) || []).filter(function (i) { return i.gateBlocking; }).map(function (i) { return i.id; })),
      doneRuns: (((d.spark && d.spark.runs) || []).filter(function (r) { return r.status === "done"; }).map(function (r) { return r.id; })),
    };
  }
  function loadNeedsSnap() { try { return JSON.parse(load(needsSnapKey(), "null")); } catch (e) { return null; } }
  function storeNeedsSnap() { try { save(needsSnapKey(), JSON.stringify(currentNeedsIds())); } catch (e) {} }
  function needsDiff() {
    var prev = loadNeedsSnap(); if (!prev) return null;                      // first ever visit → no banner
    var cur = currentNeedsIds();
    var newBlocks = cur.jury.filter(function (id) { return (prev.jury || []).indexOf(id) < 0; });
    var finished = cur.doneRuns.filter(function (id) { return (prev.doneRuns || []).indexOf(id) < 0; });
    if (!newBlocks.length && !finished.length) return null;
    return { newBlocks: newBlocks, finished: finished };
  }
  function homeBannerHTML() {
    var diff = needsDiff(); if (!diff) return "";
    var zh = S.lang === "zh", chips = [];
    diff.newBlocks.forEach(function (id) {
      chips.push('<button class="home-banner-chip" data-tool="jury" data-sub="docket" data-id="' + esc(id) + '">' + esc((zh ? "新增闸门阻断 " : "new gate-block ") + id) + '</button>');
    });
    diff.finished.forEach(function (id) {
      var r = (((SB.needs.detail.spark || {}).runs) || []).filter(function (x) { return x.id === id; })[0];
      chips.push('<button class="home-banner-chip" data-tool="spark" data-sub="runs" data-id="' + esc(id) + '">' + esc((zh ? "运行完成 · " : "run finished · ") + (r ? (r.title || id) : id)) + '</button>');
    });
    var parts = [];
    if (diff.newBlocks.length) parts.push(diff.newBlocks.length + " " + (zh ? "个新增闸门阻断" : "new gate-block" + (diff.newBlocks.length > 1 ? "s" : "")));
    if (diff.finished.length) parts.push(diff.finished.length + " " + (zh ? "个运行完成" : "run" + (diff.finished.length > 1 ? "s" : "") + " finished"));
    return '<div class="home-banner" role="status"><span class="home-banner-h">' +
      esc(parts.join(" · ") + (zh ? "(自上次访问以来)" : " since last visit")) + '</span>' + chips.join("") + '</div>';
  }
  // item 27b — a shareable markdown dossier: run verdicts + jury charge table + wiki notes filed.
  SB.exportDossier = function () {
    var d = SB.needs.detail || {}, ap = activeProject(), zh = S.lang === "zh", L = [];
    L.push("# " + (zh ? "论文档案" : "Dossier") + " · " + ((ap && ap.label) || t("proj.default")));
    var runs = (d.spark && d.spark.runs) || [];
    if (runs.length) {
      L.push("", "## " + NEEDS_NAME.spark + " — " + (zh ? "运行结论" : "run verdicts"));
      runs.forEach(function (r) { L.push("- " + (r.title || r.id) + ": " + sparkVerdict(r).label + (r.started ? " (" + relTime(r.started) + ")" : "")); });
    }
    var items = (d.jury && d.jury.items) || [];
    if (items.length) {
      L.push("", "## " + NEEDS_NAME.jury + " — " + (zh ? "指控表" : "charge table"));
      L.push("| id | " + (zh ? "性质" : "verdict") + " | " + (zh ? "理由" : "reason") + " | " + (zh ? "阻断" : "blocking") + " |", "| --- | --- | --- | --- |");
      items.forEach(function (i) {
        var verdict = [i.kind, i.significance].filter(Boolean).join(" ") || "—";
        var reason = String(i.summary || "").replace(/\|/g, "/");
        var blk = i.gateBlocking ? (zh ? "是" : "yes") : (i.escalated ? (zh ? "升级" : "escalated") : (zh ? "否" : "no"));
        L.push("| " + i.id + " | " + verdict + " | " + reason + " | " + blk + " |");
      });
    }
    var w = d.wiki || {};
    L.push("", "## " + NEEDS_NAME.wiki + " — " + (zh ? "已归档笔记" : "notes filed"),
      "- " + (zh ? "语料" : "corpus") + ": " + (w.corpus != null ? w.corpus : 0) + (zh ? " 条" : " notes") + (w.inbox ? " · " + w.inbox + " " + t("home.inbox") : ""));
    copyNow(L.join("\n")); SB.toast(t("needs.dossier.done"));
  };

  function renderHome(main) {
    var pane = el("div", "home-pane");
    main.appendChild(pane);
    var _bannerHTML = null;   // item 27a: computed once (on the first loaded paint) so it survives poll repaints
    var _pfArr = null;        // item 3: cache the last portfolio fetch so a sort toggle re-sorts without a refetch flash
    function bannerOnce() { if (_bannerHTML === null && SB.needs._loaded) { _bannerHTML = homeBannerHTML(); storeNeedsSnap(); } return _bannerHTML || ""; }
    function wireBanner() { $$(".home-banner-chip", pane).forEach(function (b) { b.onclick = function () { deepLink(b.dataset.tool, b.dataset.sub, b.dataset.id || null); }; }); }
    function wireHead() {
      var np = $("[data-needs]", pane); if (np) np.onclick = function () { SB.needs.tray(); };   // R12: rollup → needs tray
      var st = $("[data-start]", pane); if (st) st.onclick = function () { SB.launcher(); };       // one-click launcher affordance
      $$(".home-modebtn", pane).forEach(function (b) { b.onclick = function () { setHomeMode(b.dataset.mode); _homeSparkExpanded = false; paint(); }; });
    }
    function paintSingle() {
      var c = SB.needs.counts, chips = PROJECTS.map(function (p) {
        var on = (p.id || "") === (S.project || "");
        return '<button class="home-chip' + (on ? " on" : "") + '" data-proj="' + esc(p.id) + '">' + esc(p.label) + '</button>';
      }).join("");
      pane.innerHTML =
        '<div class="pane-wide">' +
        '<div class="home-head"><h1>' + esc(t("home.title")) + '</h1>' + homeRollupHTML() + homeModeToggleHTML("single") +
        (PROJECTS.length > 1 ? '<div class="home-projs" role="group" aria-label="' + esc(t("proj.pick")) + '">' + chips + '</div>' : '') +
        homeStartChipHTML() +
        '</div>' + bannerOnce() + homeViewsHTML() +
        '<div class="home-grid reveal">' +
        homeSection("spark", t("home.spark"), c.spark, homeRowsSpark(_homeSparkExpanded)) +
        homeSection("jury", t("home.jury"), c.jury, homeRowsJury()) +
        homeSection("wiki", t("home.wiki"), c.wiki, homeRowsWiki()) +
        '</div>' + homeFeedHTML() + '</div>';
      $$(".home-row", pane).forEach(function (r) {
        if (r.dataset.more) { r.onclick = function (e) { e.stopPropagation(); _homeSparkExpanded = true; paint(); }; return; }   // R7 expander
        r.onclick = function () { deepLink(r.dataset.tool, r.dataset.sub, r.dataset.id || null); };
      });
      $$(".home-feed-row", pane).forEach(function (r) { r.onclick = function () { deepLink(r.dataset.tool, r.dataset.sub, r.dataset.id || null); }; });
      $$(".home-all", pane).forEach(function (b) { b.onclick = function () { deepLink(b.dataset.tool, null, null); }; });
      $$(".home-chip", pane).forEach(function (b) { if (!("proj" in b.dataset)) return; b.onclick = function () { SB.project.set(b.dataset.proj); }; });   // only real project chips
      var _views = SB.views.list();   // R27: saved-views strip
      $$(".home-view-chip", pane).forEach(function (b) {
        if (b.dataset.viewsave) { b.onclick = function () { startSaveView(b, paint); }; return; }   // item 18 — inline name input
        b.onclick = function () { var v = _views[+b.dataset.view]; if (v) SB.views.apply(v); };
      });
      $$(".home-view-del", pane).forEach(function (b) { b.onclick = function (e) { e.stopPropagation(); SB.views.remove(b.dataset.viewdel); paint(); }; });   // item 18 — delete a user view
      wireHead(); wireBanner();
      markFeedSeen();   // R12a: badges reflect the pre-render last-seen; stamp now so next visit clears them
    }
    // item 3 — sort + render the portfolio from an already-fetched array (reused on sort-toggle so
    // re-sorting doesn't re-hit the network or flash 'Gathering…').
    function renderPf(host, arr) {
      arr = arr.slice();
      arr.sort(function (a, b) {
        if (_pfSort === "needs") return (b.total - a.total) || (readinessScore(b) - readinessScore(a));   // most-needs-you first
        if (_pfSort === "recent") return latestTs(b) - latestTs(a);                                       // most-recent run first
        // 'ready' (default) — ship-ready & needs-you both float up (bucket), then readiness desc, then needs desc
        return (pfBucket(a) - pfBucket(b)) || (readinessScore(b) - readinessScore(a)) || (b.total - a.total);
      });
      // item 20 — a project is "populated" only when real data sits behind it; an all-empty portfolio
      // (dirs unreadable / no runs anywhere) resolves to an honest empty+hint, not a wall of dashes.
      var populated = arr.filter(function (r) {
        var s = r.spark.detail || {}, j = r.jury.detail || {}, w = r.wiki.detail || {};
        return (r.total || 0) > 0 || (s.runs || []).length || (j.items || []).length || (w.corpus || 0) > 0;
      });
      if (!populated.length) { host.innerHTML = homeEmptyHint(); return; }
      host.innerHTML = arr.map(pfRowHTML).join("");
      $$(".pf-cell", host).forEach(function (cell) {
        cell.onclick = function () { SB.project.set(cell.dataset.proj); deepLink(cell.dataset.tool, cell.dataset.sub || null, cell.dataset.id || null); };   // item 2: CTA carries a specific blocker id
      });
      $$(".pf-open", host).forEach(function (b) { b.onclick = function () { setHomeMode("single"); SB.project.set(b.dataset.proj); }; });   // drill-in: single mode picks up on the fresh render
    }
    function paintPortfolio() {
      pane.innerHTML =
        '<div class="pane-wide">' +
        '<div class="home-head"><h1>' + esc(t("home.title")) + '</h1>' + homeRollupHTML() + homeModeToggleHTML("all") + pfSortToggleHTML() + homeStartChipHTML() + '</div>' + bannerOnce() +
        '<div class="home-portfolio reveal"><div class="home-empty">' + esc(S.lang === "zh" ? "正在汇总各项目…" : "Gathering across projects…") + '</div></div>' +
        '</div>';
      wireHead(); wireBanner();
      $$(".pf-sortbtn", pane).forEach(function (b) { b.onclick = function () {   // item 3 — sort toggle (re-sorts the cache in place)
        _pfSort = b.dataset.pfsort;
        $$(".pf-sortbtn", pane).forEach(function (x) { var on = x.dataset.pfsort === _pfSort; x.classList.toggle("on", on); x.setAttribute("aria-pressed", on ? "true" : "false"); });
        var h = $(".home-portfolio", pane); if (h && _pfArr) renderPf(h, _pfArr); else paint();
      }; });
      var host = $(".home-portfolio", pane);
      var list = PROJECTS.filter(function (p) { return p.id; }); if (!list.length) list = PROJECTS.slice();
      Promise.all(list.map(fetchProjectNeeds)).then(function (arr) {
        if (!document.body.contains(host)) return;
        _pfArr = arr; renderPf(host, arr);
      }).catch(function () {
        if (!document.body.contains(host)) return;
        host.innerHTML = homeEmptyHint();   // item 20 — a failed fetch degrades, never leaves 'Gathering…' hanging
      });
    }
    function paint() { if (homeMode() === "all" && PROJECTS.length > 1) paintPortfolio(); else paintSingle(); }
    paint();
    SB._homeRefresh = function () { if (document.body.contains(pane)) paint(); };   // live refresh on poll
    SB.onTeardown(function () { SB._homeRefresh = null; });                          // per-render: don't leak
    if (SB.needs.refetch) SB.needs.refetch();                                        // ensure fresh on entry
  }

  /* ---- first-run orientation (R17): one-time dismissible welcome, keyed sb.seen -- */
  function maybeWelcome() {
    if (Q.get("welcome") === "0") return;
    if ($("#sb-launch-scrim")) return;   // launcher already up (?start=1) — don't stack a second overlay
    // item 7 — ONLY a dedicated ?screenshot=1 flag suppresses the primer (deterministic screenshots).
    // The navigation params ?tool/?view/?theme/?lang are EXACTLY how a deep link / shared link arrives,
    // so their presence must NOT self-suppress it — a real first-week student following a shared link
    // still needs the primer while sb.seen is unset. (?welcome=1 still force-shows it.)
    var scripted = Q.get("screenshot") === "1";
    if (Q.get("welcome") !== "1" && (scripted || load("seen", "") === "1")) return;
    showWelcome();
  }
  // R28d — the one-shot primer is re-showable from ⌘K ("Show intro") / this function.
  SB.showWelcome = showWelcome;
  function showWelcome() {
    $$("#sb-welcome-scrim, .pop.welcome").forEach(function (n) { n.remove(); });
    var sc = el("div", "scrim"); sc.id = "sb-welcome-scrim";
    var card = el("div", "pop welcome");
    card.setAttribute("role", "dialog"); card.setAttribute("aria-modal", "true"); card.setAttribute("aria-labelledby", "sb-welcome-h");
    card.innerHTML =
      '<div class="wc-mark"><svg class="mark" viewBox="0 0 14 14" fill="currentColor" aria-hidden="true"><rect x="0" y="2" width="14" height="2.4" rx="1"/><rect x="0" y="5.8" width="9" height="2.4" rx="1"/><rect x="0" y="9.6" width="4" height="2.4" rx="1"/></svg></div>' +
      '<h2 id="sb-welcome-h">' + esc(t("welcome.title")) + '</h2>' +
      '<p class="wc-body">' + esc(t("welcome.body")) + '</p>' +
      '<p class="wc-hint">' + esc(t("welcome.hint")) + '</p>' +
      '<div class="wc-actions"><button class="btn primary wc-go">' + esc(t("welcome.go")) + '</button></div>';
    document.body.appendChild(sc); document.body.appendChild(card);
    var opener = document.activeElement;
    function close() { save("seen", "1"); card.remove(); sc.remove(); document.removeEventListener("keydown", onKey, true); try { opener && opener.focus(); } catch (e) {} }
    function onKey(e) { if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); close(); } }
    // "开始 / Get started" flows straight into the one-click launcher (first-run entry).
    sc.onclick = close; $(".wc-go", card).onclick = function () { close(); SB.launcher(); };
    document.addEventListener("keydown", onKey, true);
    setTimeout(function () { var g = $(".wc-go", card); if (g) g.focus(); }, 30);
  }

  /* ---- command palette (⌘K / Ctrl-K) (R3/R6) -----------------------------
     Bounded, self-contained. Folds tool + sub-view navigation, a small command set,
     AND any items registered by the tool modules (runs / charges / notes / papers)
     via SB.registerPaletteSource. Each source returns [{id,label,sub?,type?,run()}];
     type+context render as the row subtitle, subsequence match is over the label. */
  SB._paletteSources = [];
  SB.registerPaletteSource = function (fn) { if (typeof fn === "function" && SB._paletteSources.indexOf(fn) < 0) SB._paletteSources.push(fn); };
  function paletteItems() {
    var out = [];
    out.push({ label: t("home.title"), hint: "⌂", run: function () { SB.setTool("home"); } });
    out.push({ label: t("start.title"), hint: "▸", type: (S.lang === "zh" ? "开始" : "start"), run: function () { SB.launcher(); } });   // one-click launcher
    // item 14 — context ACTIONS on the open run/charge: thin wrappers over the surface's own
    // buttons (present only while that surface is mounted), so ⌘K acts, not just jumps.
    [["#sp-pdf", "打开 PDF", "Open PDF", "⎋"], ["#sp-jury", "送去评审", "Send to Jury", "→"], ["#sp-shield", "跳到投稿护盾", "Jump to shield", "▣"]].forEach(function (a) {
      if (!$(a[0])) return;
      out.push({ label: (S.lang === "zh" ? a[1] : a[2]), hint: a[3], type: (S.lang === "zh" ? "操作" : "action"),
        run: function () { var n = $(a[0]); if (n) n.click(); } });
    });
    out.push({ label: t("needs.tray"), hint: "!", run: function () { SB.needs.tray(); } });        // item 14 — open the Needs-you tray
    out.push({ label: t("needs.dossier"), hint: "⧉", run: function () { SB.exportDossier(); } });   // item 27b — export a dossier
    ["spark", "jury", "wiki"].forEach(function (nm, ti) {
      var tl = TOOLS[nm]; if (!tl) return;
      var tname = (I18N[S.lang] && I18N[S.lang]["tool." + nm]) || nm;
      // item 8 — surface the real key binding: 1/2/3 switches tools; ⌥N jumps to the active tool's Nth view.
      out.push({ label: (S.lang === "zh" ? "切换到 " : "Switch to ") + tname, hint: nm, dot: NEEDS_TINT[nm], kbd: String(ti + 1),
        run: function () { SB.setTool(nm); } });
      (tl.sub || []).forEach(function (s, si) {
        out.push({ label: tname + " ▸ " + s.label, hint: nm, dot: NEEDS_TINT[nm], kbd: (nm === S.tool && si < 9) ? "⌥" + (si + 1) : "",
          run: function () { SB.setTool(nm); SB.setSub(s.id); } });
      });
    });
    // R9 — switch the active project from ⌘K (skipped when the library has a single entry)
    var projs = SB.project.list(), curPid = S.project || "";
    if (projs.length > 1) {
      projs.forEach(function (p) {
        var on = (p.id || "") === curPid;
        out.push({ label: (S.lang === "zh" ? "切换项目 ▸ " : "Switch project ▸ ") + p.label,
          sub: p.kind === "root" ? p.sub : t("proj.default"), hint: on ? "✓" : "",
          run: function () { SB.project.set(p.id); } });
      });
    }
    out.push({ label: (S.lang === "zh" ? "切换主题(浅 / 深 / 系统)" : "Toggle theme"), hint: "◐", run: function () { SB.cycleTheme(); } });
    out.push({ label: (S.lang === "zh" ? "切换语言 中 / EN" : "Toggle language 中 / EN"), hint: "文", run: function () { var b = $("#sb-lang"); if (b && b.onclick) b.onclick(); } });
    out.push({ label: t("settings"), hint: "⚙", run: function () { var b = $("#sb-settings"); if (b) b.click(); } });
    out.push({ label: t("kbd"), hint: "?", run: function () { SB.keyHelp(); } });
    out.push({ label: t("intro.show"), hint: "★", run: function () { SB.showWelcome(); } });     // R28d
    out.push({ label: t("act.copy"), hint: "⧉", run: function () { SB.copyStatus(); } });          // R12b
    out.push({ label: t("view.copylink"), hint: "↗", run: function () { SB.copyView(); } });        // item 7 — copy link to this view
    // R27 — saved views: 3 built-in seeds + user views, plus "save current view"
    SB.views.list().forEach(function (v) {
      out.push({ label: (S.lang === "zh" ? "视图:" : "View: ") + v.label, hint: v.seed ? "◆" : "◇", sub: t("view.saved"),
        run: function () { SB.views.apply(v); } });
    });
    out.push({ label: t("view.save"), hint: "＋", run: function () { SB.views.saveCurrent(); } });
    // item 18 — delete a saved view from ⌘K (USER views only, never the 3 seeds)
    SB.views.list().forEach(function (v) {
      if (v.seed || !v.id) return;
      out.push({ label: (S.lang === "zh" ? "删除视图 ▸ " : "Delete view ▸ ") + v.label, hint: "✕", sub: t("view.saved"),
        run: function () { SB.views.remove(v.id); SB.toast(S.lang === "zh" ? "已删除视图" : "View deleted"); } });
    });
    // R21 — jump to a highlight in the currently-open reader
    var _hlArt = currentReaderArticle();
    if (_hlArt) {
      var _hlKey = paperKey(_hlArt);
      loadHls(_hlKey).slice().reverse().forEach(function (rec) {
        var q = rec.quote || ""; if (!q) return;
        out.push({ label: (S.lang === "zh" ? "标注:" : "Highlight: ") + (q.length > 60 ? q.slice(0, 60) + "…" : q), hint: "▍", type: t("hl.rail"),
          run: function () { scrollToHl(_hlArt, rec); } });
      });
    }
    // R3: fold in the tool-registered corpus (jump to a paper / run / charge / note)
    // item 14 — a source item MAY carry `project`; when >1 root, label out-of-project rows.
    var _multiRoot = SB.project.list().length > 1, _curPid = S.project || "", _projLbl = {};
    if (_multiRoot) SB.project.list().forEach(function (p) { _projLbl[p.id || ""] = p.label; });
    SB._paletteSources.forEach(function (src) {
      var arr; try { arr = src() || []; } catch (e) { arr = []; }
      if (!arr || !arr.length) return;
      arr.forEach(function (it) {
        if (!it || !it.label || typeof it.run !== "function") return;
        var sub = it.sub || "";
        if (_multiRoot && it.project != null && (it.project || "") !== _curPid) {
          var pl = _projLbl[it.project || ""] || it.project; sub = sub ? (pl + " · " + sub) : pl;
        }
        out.push({ label: it.label, sub: sub, type: it.type || "", dot: it.dot || (it.type ? NEEDS_TINT[it.type] : null), run: it.run });
      });
    });
    return out;
  }
  function subseqScore(text, q) {
    var ti = 0, first = -1, last = -1, gaps = 0;
    for (var qi = 0; qi < q.length; qi++) {
      var f = text.indexOf(q[qi], ti);
      if (f < 0) return -1;
      if (first < 0) first = f;
      if (last >= 0) gaps += f - last - 1;
      last = f; ti = f + 1;
    }
    return first * 3 + gaps;
  }
  // R26c — a small MRU of palette labels (recents on empty query + a fuzzy-rank bonus)
  function palMru() { try { return JSON.parse(load("palmru", "[]")) || []; } catch (e) { return []; } }
  function palMruPush(label) { if (!label) return; var a = palMru().filter(function (x) { return x !== label; }); a.unshift(label); if (a.length > 8) a = a.slice(0, 8); save("palmru", JSON.stringify(a)); }
  function palMruRank() { var m = palMru(), r = {}; m.forEach(function (l, i) { r[l] = i; }); return r; }
  function recentsFirst(list) {
    var rank = palMruRank(), inMru = [], rest = [];
    list.forEach(function (it) { if (rank[it.label] != null) inMru.push(it); else rest.push(it); });
    inMru.sort(function (a, b) { return rank[a.label] - rank[b.label]; });
    return inMru.concat(rest);
  }
  function fuzzyRank(items, q) {
    q = (q || "").trim().toLowerCase();
    if (!q) return recentsFirst(items);                    // R26c: empty query surfaces recents first
    var rank = palMruRank(), scored = [];
    items.forEach(function (it) {
      // subsequence match over the label (primary), with sub/type/hint as a recall superset
      var lbl = String(it.label).toLowerCase();
      var s = subseqScore(lbl, q);
      if (s < 0) { var extra = subseqScore((lbl + " " + (it.sub || "") + " " + (it.type || "") + " " + (it.hint || "")).toLowerCase(), q); if (extra >= 0) s = extra + 1000; }
      if (s >= 0) { if (rank[it.label] != null) s -= 40; scored.push({ it: it, s: s }); }   // R26c: MRU bonus
    });
    scored.sort(function (a, b) { return a.s - b.s; });
    return scored.map(function (x) { return x.it; });
  }
  SB.palette = function () {
    var open = $("#sb-pal");
    if (open) { var inp = $(".pal-input", open); if (inp) inp.focus(); return; }
    var items = paletteItems();
    var opener = document.activeElement;
    var scrim = el("div", "scrim"); scrim.id = "sb-pal-scrim";
    var pal = el("div", "palette"); pal.id = "sb-pal";
    pal.setAttribute("role", "dialog"); pal.setAttribute("aria-modal", "true"); pal.setAttribute("aria-label", t("cmdk.ph"));
    var zh = S.lang === "zh";
    pal.innerHTML =
      '<div class="pal-in"><svg class="i sm"><use href="#i-search"/></svg>' +
      '<input class="pal-input" type="text" role="combobox" aria-expanded="true" aria-controls="sb-pal-list" aria-autocomplete="list" autocomplete="off" spellcheck="false" placeholder="' + esc(t("cmdk.ph")) + '"></div>' +
      '<div class="pal-list" id="sb-pal-list" role="listbox"></div>' +
      // item 18 — a persistent footer that surfaces the (previously undiscoverable) ⌥↵ keep-open action
      '<div class="pal-foot" style="display:flex;gap:14px;padding:7px 12px;border-top:1px solid var(--hair-2);font-size:11px;color:var(--muted);font-family:var(--sans)">' +
        '<span><kbd>↵</kbd> ' + esc(zh ? "执行" : "run") + '</span>' +
        '<span><kbd>⌥↵</kbd> ' + esc(zh ? "执行并保持打开" : "run & keep open") + '</span>' +
        '<span><kbd>esc</kbd> ' + esc(zh ? "关闭" : "close") + '</span>' +
      '</div>' +
      '<span class="sr-only" id="sb-pal-live" aria-live="polite"></span>';
    document.body.appendChild(scrim); document.body.appendChild(pal);
    var input = $(".pal-input", pal), listEl = $(".pal-list", pal), live = $("#sb-pal-live", pal);
    var filtered = recentsFirst(items), sel = 0;           // R26c: open on recents
    function draw() {
      listEl.innerHTML = "";
      if (!filtered.length) { listEl.appendChild(el("div", "pal-empty", S.lang === "zh" ? "没有匹配项" : "No matches")); input.removeAttribute("aria-activedescendant"); if (live) live.textContent = S.lang === "zh" ? "没有匹配项" : "No matches"; return; }
      filtered.forEach(function (it, i) {
        var subtitle = it.sub ? (it.type ? it.type + " · " + it.sub : it.sub) : (it.type || "");
        var row = el("div", "pal-row" + (i === sel ? " sel" : "") + (subtitle ? " has-sub" : ""),
          (it.dot ? '<span class="pal-dot" style="background:' + it.dot + '"></span>' : "") +
          '<span class="pal-main"><span class="pal-lbl">' + esc(it.label) + "</span>" +
          (subtitle ? '<span class="pal-sub">' + esc(subtitle) + "</span>" : "") + "</span>" +
          (it.hint ? '<span class="pal-hint">' + esc(it.hint) + "</span>" : "") +
          // item 8 — a right-aligned <kbd> showing the real key binding where known (1/2/3, ⌥N)
          (it.kbd ? '<kbd class="pal-kbd" style="margin-left:6px;font-family:var(--sans);font-size:10px;border:1px solid var(--hair-2);border-radius:4px;padding:1px 5px;color:var(--muted);white-space:nowrap">' + esc(it.kbd) + "</kbd>" : ""));
        row.id = "sb-pal-opt-" + i; row.setAttribute("role", "option"); row.setAttribute("aria-selected", i === sel ? "true" : "false");
        row.addEventListener("mousemove", function () { if (sel !== i) { sel = i; mark(); } });
        row.onclick = function (ev) { runIt(it, ev.altKey); };   // item 18 — honor ⌥-click (run & keep open) on mouse too
        listEl.appendChild(row);
      });
      mark();
      if (live) live.textContent = (S.lang === "zh" ? filtered.length + " 项匹配" : filtered.length + " matches");
    }
    function mark() {
      var rows = $$(".pal-row", listEl);
      rows.forEach(function (r, i) { var on = i === sel; r.classList.toggle("sel", on); r.setAttribute("aria-selected", on ? "true" : "false"); });
      if (rows[sel]) { rows[sel].scrollIntoView({ block: "nearest" }); input.setAttribute("aria-activedescendant", rows[sel].id); }
    }
    function runIt(it, keepOpen) { palMruPush(it && it.label); if (!keepOpen) close(); if (it && it.run) { try { it.run(); } catch (e) {} } }
    function close() { pal.remove(); scrim.remove(); document.removeEventListener("keydown", onKey, true); try { opener && opener.focus(); } catch (e) {} }
    function onKey(e) {
      if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); close(); }
      else if (e.key === "ArrowDown") { e.preventDefault(); sel = Math.min(filtered.length - 1, sel + 1); mark(); }
      else if (e.key === "ArrowUp") { e.preventDefault(); sel = Math.max(0, sel - 1); mark(); }
      else if (e.key === "Enter") { e.preventDefault(); if (filtered[sel]) runIt(filtered[sel], e.altKey); }   // R26c: Alt+Enter runs without closing
    }
    scrim.onclick = close;
    input.addEventListener("input", function () { filtered = fuzzyRank(items, input.value); sel = 0; draw(); });
    document.addEventListener("keydown", onKey, true);
    draw();
    setTimeout(function () { input.focus(); }, 20);
  };

  /* ---- svg sprite (icons used by the shell) ------------------------------ */
  // Icon sprite. Built via insertAdjacentHTML (NOT createElement+innerHTML): the
  // HTML parser only puts children in the SVG namespace inside an <svg> foreign
  // element, and `<use href="#id">` silently paints nothing against an HTML-
  // namespaced <g>. Each glyph is a <symbol viewBox> so `.i` / `.i.sm` scale it
  // instead of clipping at a fixed 16px. `SB.addIcon(id, innerSVG)` lets a
  // workspace register its own glyph on the shared sprite.
  var GLYPH = {
    "i-chev": '<g fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><path d="M4 6.25L8 10.25l4-4"/></g>',
    "i-gear": '<g fill="none" stroke="currentColor" stroke-width="1.5"><path d="M2 4.5h6M11 4.5h3M2 11.5h3M8 11.5h6"/><path d="M9.5 2.5v4M6.5 9.5v4"/></g>',
    "i-sun": '<g fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="8" cy="8" r="3"/><path d="M8 1.5v2M8 12.5v2M1.5 8h2M12.5 8h2M3.4 3.4l1.3 1.3M11.3 11.3l1.3 1.3M12.6 3.4l-1.3 1.3M4.7 11.3l-1.3 1.3"/></g>',
    "i-moon": '<g fill="none" stroke="currentColor" stroke-width="1.5"><path d="M13 10.4A5.6 5.6 0 0 1 5.6 3 5.6 5.6 0 1 0 13 10.4z"/></g>',
    "i-sys": '<g fill="none" stroke="currentColor" stroke-width="1.5"><rect x="2.75" y="2.75" width="10.5" height="10.5" rx="1.5"/><path d="M8 2.75v10.5"/></g>',
    "i-spark": '<g fill="currentColor"><path d="M8 1.5l1.4 4.1L13.5 7 9.4 8.4 8 12.5 6.6 8.4 2.5 7l4.1-1.4z"/></g>',
    "i-note": '<g fill="none" stroke="currentColor" stroke-width="1.5"><rect x="3" y="2.5" width="10" height="11" rx="1.5"/><path d="M5.5 6h5M5.5 8.5h5M5.5 11h3"/></g>',
    "i-globe2": '<g fill="none" stroke="currentColor" stroke-width="1.4"><circle cx="8" cy="8" r="5.5"/><path d="M2.5 8h11M8 2.5c2 2 2 9 0 11M8 2.5c-2 2-2 9 0 11"/></g>',
    "i-ask": '<g fill="none" stroke="currentColor" stroke-width="1.5"><path d="M6 6a2 2 0 1 1 2.6 1.9c-.6.2-.9.6-.9 1.3v.3"/><circle cx="8" cy="11.5" r=".6" fill="currentColor" stroke="none"/></g>',
    "i-check": '<g fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round"><path d="M3 8.25l3.5 3.5L13 5"/></g>',
    "i-close": '<g fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><path d="M4 4l8 8M12 4l-8 8"/></g>',
    "i-zen": '<g fill="none" stroke="currentColor" stroke-width="1.5"><rect x="2.5" y="3" width="11" height="10" rx="1.5"/><path d="M6 3v10M10 3v10"/></g>',
    "i-search": '<g fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="7" cy="7" r="4.2"/><path d="M10.2 10.2l3.3 3.3" stroke-linecap="round"/></g>',
    "i-folder": '<g fill="none" stroke="currentColor" stroke-width="1.4"><path d="M2 4.5a1 1 0 0 1 1-1h3l1.4 1.5H13a1 1 0 0 1 1 1V12a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1z"/></g>',
    "i-arrow": '<g fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M3.5 8h9M9 4.5L12.5 8 9 11.5"/></g>',
    "i-info": '<g fill="none" stroke="currentColor" stroke-width="1.4"><circle cx="8" cy="8" r="6"/><path d="M8 7.2v3.6" stroke-linecap="round"/><circle cx="8" cy="5.2" r=".7" fill="currentColor" stroke="none"/></g>',
    "i-copy": '<g fill="none" stroke="currentColor" stroke-width="1.4"><rect x="5.5" y="5.5" width="8" height="8" rx="1.5"/><path d="M10.5 5.5V3.5a1 1 0 0 0-1-1h-6a1 1 0 0 0-1 1v6a1 1 0 0 0 1 1h2"/></g>',
    "i-mark": '<g fill="none" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"><path d="M4 2.5h6l1 1v9l-2-1.4-2 1.4-2-1.4-2 1.4v-9z"/><path d="M6 5.5h4M6 8h3" stroke-linecap="round"/></g>',
    "i-pin": '<g fill="none" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round" stroke-linecap="round"><path d="M9.6 1.9l4.5 4.5-1.6.5-2.2 2.2.2 2.6-3.3-3.3-3 3.4 2.9-3.5L3.3 8l2.6.2 2.2-2.2z"/></g>',
    "i-doc": '<g fill="none" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"><path d="M4 2.5h4.5L12 6v7.5H4z"/><path d="M8.3 2.6V6h3.4" /><path d="M6 8.5h4M6 10.8h4" stroke-linecap="round"/></g>',
    "i-link": '<g fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"><path d="M6.6 9.4l2.8-2.8"/><path d="M8.4 4.9l1-1a2.4 2.4 0 0 1 3.4 3.4l-1.6 1.6a2.4 2.4 0 0 1-3.4 0"/><path d="M7.6 11.1l-1 1a2.4 2.4 0 0 1-3.4-3.4l1.6-1.6a2.4 2.4 0 0 1 3.4 0"/></g>',
  };
  SB.addIcon = function (id, inner) {
    if (document.getElementById(id)) return;
    var s = $("#sb-sprite");
    if (s) s.insertAdjacentHTML("beforeend", '<symbol id="' + id + '" viewBox="0 0 16 16">' + inner + "</symbol>");
    else GLYPH[id] = inner;   // sprite not built yet — fold it in
  };
  function ensureSprite() {
    if ($("#sb-sprite")) return;
    var syms = Object.keys(GLYPH).map(function (id) {
      return '<symbol id="' + id + '" viewBox="0 0 16 16">' + GLYPH[id] + "</symbol>";
    }).join("");
    document.body.insertAdjacentHTML("beforeend",
      '<svg id="sb-sprite" width="0" height="0" aria-hidden="true" style="position:absolute">' + syms + "</svg>");
  }
})();
