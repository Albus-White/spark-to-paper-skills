/* ============================================================================
   SparkBoard · JURY workspace — the pre-submission adversarial "courtroom".

   Registers SB.registerTool('jury', …) with five sub-views:
     docket      the VERDICT BOARD (kanban) + a charge opened as a reader article
     revisions   the REVISION INBOX (drafted_patch diffs) + journal.jsonl history
     panel       reviewer PERSONA cards + coverage HEATMAP + per-charge TRIAL view
     shield      the SUBMISSION SHIELD (compile banner + desk-reject + convergence)
     example     the WORKED EXAMPLE (the real dogfood run: 152→55→26/10/19)

   The LEDGER row IS the unit of the whole workspace — one row = one "charge in the
   courtroom". This module renders that ledger three ways (board / feed / inbox) plus
   the per-stage artifacts (trials, coverage, journal, spine, compile, compliance).

   All sample data below MIRRORS the real .paper-review/* fixture field names
   (ledger-schema.md / map 04) so the panels are faithful, not decorative. Content
   (quotes, sections, LaTeX) is verbatim and NEVER routed through i18n — only chrome
   labels are translated.
   ============================================================================ */
(function () {
  "use strict";
  var SB = window.SB;
  if (!SB) { console.error("[jury] reader.js (window.SB) must load first"); return; }
  var el = SB.el, esc = SB.esc, t = SB.t;

  /* ---- i18n: extend the shell dictionary with jury chrome keys ------------- *
   * Only labels/buttons/lane names live here. The paper's own text stays verbatim. */
  var JZH = {
    "j.tab.docket": "判决台", "j.tab.revisions": "修订箱", "j.tab.panel": "评审团",
    "j.tab.shield": "投稿护盾", "j.tab.example": "实证样例",
    "j.board": "判决台", "j.board.sub": "每条评审意见都要过庭 —— 三种判决:判定可修 / 待作者 / 驳回",
    "j.lane.raised": "已提出", "j.lane.in-trial": "庭审中", "j.lane.valid-fixable": "判定可修",
    "j.lane.closed": "已结案", "j.lane.author-required": "待作者", "j.lane.dropped": "已驳回",
    "j.lane.queued": "已入队", "j.lane.withdrawn": "已撤并",
    "j.corrob": "多方印证", "j.esc": "升级 12 人", "j.conf": "置信",
    "j.notried": "尚未庭审", "j.back": "返回判决台", "j.charges": "全部指控",
    "j.verdict": "判决", "j.evidence": "所依原文(逐字)", "j.close": "结案标准",
    "j.refs": "相关处", "j.prov": "来源与流程", "j.trial.link": "查看庭审记录（评审团）",
    "j.section.jump": "跳到论文对应位置",
    "j.kicker.charge": "指控",
    "j.rev.title": "修订箱", "j.rev.sub": "带草拟补丁的行 —— 接受即落盘、驳回即留痕",
    "j.rev.pending": "待裁定的补丁", "j.rev.hist": "本轮已应用（journal.jsonl）",
    "j.accept": "接受", "j.reject": "驳回", "j.undo": "撤销", "j.applied": "已应用",
    "j.rejected": "已驳回", "j.reverted": "已撤销", "j.frozen": "触及冻结锚点",
    "j.panel.title": "评审团", "j.panel.reviewers": "%d 位领域评审", "j.panel.coverage": "覆盖热力图",
    "j.panel.trials": "逐条庭审", "j.unverified": "未验证 · 已降级", "j.defense": "钢人辩护",
    "j.grounds": "依据", "j.jurors": "位陪审员理由", "j.jury.size": "陪审团",
    "j.shield.title": "投稿护盾", "j.shield.compile": "编译状态", "j.shield.desk": "桌拒合规清单",
    "j.shield.conv": "收敛度", "j.compile.clean": "编译通过", "j.compile.err": "编译报错",
    "j.compile.notrun": "未跑编译", "j.pages": "页", "j.warns": "版式警告", "j.errors": "错误",
    "j.notrun.note": "compiled: null 如实报告为「未跑编译」—— 绝不伪装成通过。",
    "j.converged": "已收敛", "j.notconverged": "未收敛",
    "j.ex.title": "实证样例", "j.ex.sub": "一份真实 21 页初稿,注入 11 个缺陷,跑一轮 AUTO",
    "j.ex.orig": "初稿", "j.ex.rev": "修订稿", "j.ex.defects": "个已知缺陷",
    "j.chain": "接力自 Spark 的成稿", "j.chain.sub": "把 Spark 产出的 main.tex 直接送审 —— 无需转换",
    "j.chain.act": "评审这份初稿", "j.vote.ok": "有效", "j.vote.no": "无效", "j.vote.lim": "证据不足",
    "j.source": "送审稿", "j.mode": "模式",
    "j.src.reading": "读取", "j.src.sample": "示例数据",
    // KPI strip — eyebrows (R5), plain-language tooltips + sublabels (R4)
    "j.stat.charges": "指控", "j.stat.gate": "阻断投稿的重大项", "j.stat.corrob": "多方印证 ≥2",
    "j.stat.esc": "升级至 12 人", "j.stat.route": "待作者 · 已驳回",
    "j.stat.gate.must": "必须降到 0 才能投稿", "j.stat.gate.clear": "可以投稿",
    "j.tip.charges": "判决台上本轮的每一条评审意见(全部指控)。",
    "j.tip.gate": "重大且尚未了结的指控数 —— 只要还大于 0 就不能投稿。点击只看这些指控。",
    "j.tip.corrob": "被 ≥2 位评审各自独立提出的指控 —— 信号更强。",
    "j.tip.esc": "5 人小陪审团未达法定多数、被送到 12 人大陪审团重审的指控。",
    "j.tip.route": "已交回作者定夺 + 已按无效驳回的指控;它们在判决台右侧、屏幕外的车道里。点击跳过去。",
    "j.filter.on": "已筛选:阻断投稿的重大项(major 且未了结)", "j.filter.clear": "清除筛选",
    // legend (R11)
    "j.legend": "图例", "j.legend.chips": "指控上的标记", "j.legend.lanes": "判决台车道",
    "j.gl.major": "阻断投稿的严重度", "j.gl.minor": "不阻断投稿",
    "j.gl.mech": "表层 / 机械错误", "j.gl.subst": "涉及含义的问题",
    "j.gl.vfix": "判定成立、可安全自动修", "j.gl.authreq": "判定成立,但需作者定夺",
    "j.gl.drop": "判定不成立、驳回", "j.gl.escal": "未达多数,升级重审",
    "j.gl.corrob": "≥2 位 reviewer 各自独立提出", "j.gl.esc12": "送 12 人大陪审团重审",
    "j.gl.frozen": "改动会触及冻结的锚点句",
    "j.lm.raised": "已提出,待路由到庭审", "j.lm.in-trial": "陪审团正在表决",
    "j.lm.valid-fixable": "判定可修,补丁待落盘", "j.lm.closed": "已改并核验",
    "j.lm.author-required": "已交回作者定夺", "j.lm.dropped": "判定不成立",
    "j.lm.queued": "触及锚点 / 改动含义,待人工回看", "j.lm.withdrawn": "并入其他指控",
    // revision routing (R7) + explicit override
    "j.route.author": "交作者定夺", "j.route.queue": "保持入队", "j.routed": "已路由",
    "j.override": "覆盖并应用…", "j.overridden": "覆盖",
    // R24 — localized enum chip labels (display only; the raw value/class is unchanged)
    "j.en.major": "重大", "j.en.minor": "次要",
    "j.en.mechanical": "机械", "j.en.substantive": "实质",
    "j.en.valid-fixable": "判定可修", "j.en.author-required": "待作者",
    "j.en.invalid-drop": "驳回", "j.en.escalate": "升级",
    // R18 — always-visible gloss caption (jargon legible without hover)
    "j.legend.cap": "重大 = 阻断投稿 · conf = reviewer 置信度(1–5) · 多方印证 ×2 = ≥2 位评审各自独立提出",
    "j.legend.more": "展开下方图例看全部标记与车道",
    // R13 — off-screen lane overflow cue (R7: fixed short label; the lane list stays in the tooltip)
    "j.board.more": "更多车道 →",
    "j.board.more.tip": "滚到屏幕外右侧的车道(待作者 / 已驳回 / 已入队)",
    // R6 — empty docket state
    "j.empty.title": "本轮还没有评审记录",
    "j.empty.sub": "把一份初稿送审,判决台就会列出每一条评审意见,并逐条过庭判决。",
    "j.empty.cta": "评审这份初稿",
    "j.empty.hint": "想先看看长什么样?打开「实证样例」。",
    // R14 — jump lands on the verbatim evidence in place
    "j.jump.done": "已定位到所依原文",
    // R21 — coverage summary line
    "j.cov.summary": "覆盖证据统计", "j.cov.thorough": "充分", "j.cov.light": "偏浅", "j.cov.skipped": "跳过",
    "j.cov.noflag": "无 skim 标记", "j.cov.unflagged": "未标注 = 无正面覆盖证据",
    // R15 — one-line go/no-go readiness verdict on the docket
    "j.ready.eyebrow": "能投稿吗", "j.ready.clear": "可提交",
    "j.ready.blocked": "尚不可提交", "j.ready.sample": "无法判定 —— 当前为样例数据",
    "j.ready.clear.sub": "无阻断投稿的重大项,且本轮已收敛",
    // R6 — vote colour key on the docket + R2 keyboard hint
    "j.vote.key": "陪审团票:", "j.kbd.hint": "键盘:j / k 上下 · h / l 换车道 · a 待作者 · r 驳回 · f 判定可修 · x 多选 · ⇧A 选车道 · ⇧* 选全台 · Enter 打开",
    // R9 — newcomer gloss under the convergence card
    "j.conv.gloss": "「genuinely new」= 本轮新增、此前不存在的问题(已按 passage 去重、排除沿用项);某轮不再产生这类问题,即盖「已收敛」印。",
    // R18 — coverage cell → docket section filter
    "j.cov.filtered": "已筛选:", "j.cov.filtered.suf": " 的指控", "j.cov.blocked": "卡住",
    // R1 — couldNotRead honesty banner (broken dir → sample, not this manuscript)
    "j.cnr.head": "读不到这个目录", "j.cnr.sub": " —— 下方为示例,不代表本稿。", "j.cnr.pre": "无法读取 ",
    "j.cnr.dismiss": "知道了", "j.tally.tip": "陪审团投票:有效 · 无效 · 证据不足",
    // R2(round4) — distinct AMBER readiness state: auto-blockers clear, author calls pending
    "j.ready.author": "自动阻断已清",
    // R20b(round4) — tally shown but no per-juror trial record on file
    "j.tally.only": "仅计票 · 未记录逐条理由",
    "j.jurors.label": "陪审员理由", "j.excerpt": "摘录",
    // R8(round4) — Jury → Wiki handoff (files a not-yet-persisted inbox item)
    "j.wiki.file": "归档到 Wiki", "j.wiki.file.note": "在 Wiki 收件箱新建待处理项 · 尚未落盘",
    "j.wiki.notready": "Wiki 未就绪",
    // R22(round4) — sample-run title (drops the internal 'dogfood' slang)
    // R25(round6) — was under-translated "示例"; match EN "sample run"
    "j.title.sample": "示例运行",
    // R28b(round4) — evidence-anchor verbatim proof badge
    "j.ev.verbatim": "与原文逐字一致", "j.ev.notlocated": "未定位",
    // R5 — jump relabel when the anchor can't be precisely resolved
    "j.section.open": "在阅读器中打开该章节",
    // R5(6) — degraded reviewer surfaced at the charge
    "j.unv.title": "降级 / 未验证评审", "j.degraded.only": "仅由降级评审提出",
    // R5(7) — bulk disposition bar + undo
    "j.bulk.selected": "已选", "j.bulk.author": "交作者", "j.bulk.drop": "驳回",
    "j.bulk.fixable": "判定可修", "j.bulk.clear": "清除选择", "j.bulk.undo": "撤销",
    // R5(10) — charge provenance: which Spark run produced this manuscript
    "j.prov.src": "来源:运行",
    // R5(20) — contested lens + dropped-without-trial audit
    "j.contested": "有争议", "j.stat.contested": "有争议",
    "j.tip.contested": "高置信评审(≥4)提出、却被驳回或交作者 / 入队的指控 —— 点击只看这些。",
    "j.contested.tip": "高置信评审(≥4)提出,却被驳回或交作者 / 入队 —— 值得复核。",
    "j.contested.on": "已筛选:有争议的指控(高置信却被驳回或延后)",
    "j.drop.audit": "驳回但无庭审记录",
    "j.drop.audit.sub": "以下指控被驳回,却没有逐条庭审记录 —— 附计票与理由,便于复核每一次驳回。",
    "j.drop.reason": "驳回理由", "j.drop.open": "查看该指控",
    // R5(21) — verbatim badge discloses WHICH source matched
    "j.ev.anchor": "与冻结锚点一致", "j.ev.patchrec": "与草拟补丁记录一致",
    "j.ev.selfonly": "仅与本条补丁原文一致(非独立佐证)",
    // R5(25) — compile head: warnings are not a clean pass
    "j.compile.warn": "编译带警告",
    // R6(round6) — jury additions: plain-language subtitles, coverage-gap caveat, round budget
    "j.panel.sub": "评审员、按章覆盖情况与逐条庭审",
    "j.shield.sub": "编译、桌拒合规与收敛度检查",
    "j.cov.gap": "覆盖缺口 —— 本指控所依的章节在覆盖审查中被跳过,判决请谨慎采信。",
    "j.conv.terminal": "若到上限仍未收敛,余下阻断投稿的重大项将转交作者定夺。",
    // R7(round7) — projected readiness preview (dispositions not yet written) + coverage a11y + jury gloss
    "j.ready.proj": "处置后降为 %d · 待写入",
    "j.cov.opens": "打开",
    "j.cov.blank": "无 skim 标记 · 无正面覆盖证据(未确认已读)",
    "j.jury.gloss": "陪审团 = 独立于评审员 %r 的表决团:基础 %n 人,未达法定多数则升级至 12 人大陪审团重审。",
    "j.jury.esc": "陪审团 5 → 12(升级重审)", "j.jury.framings": "%n 种框架(非陪审员)",
    // R12(round10) — de-leaked stat labels + reverted-row restore + on-card coverage-gap chip
    "j.bibentries": "文献条目", "j.genuinelynew": "本轮新增",
    "j.redo": "恢复", "j.redo.tip": "撤销这次撤销,恢复此已应用的编辑", "j.restored": "已恢复",
    "j.cov.gapchip": "覆盖缺口",
  };
  var JEN = {
    "j.tab.docket": "Docket", "j.tab.revisions": "Revisions", "j.tab.panel": "Panel",
    "j.tab.shield": "Shield", "j.tab.example": "Worked example",
    "j.board": "Verdict board", "j.board.sub": "Every reviewer complaint is put on trial — three verdicts: valid-fixable / author-required / invalid-drop",
    "j.lane.raised": "Raised", "j.lane.in-trial": "In-Trial", "j.lane.valid-fixable": "Valid · Fixable",
    "j.lane.closed": "Closed", "j.lane.author-required": "Author-Required", "j.lane.dropped": "Dropped",
    "j.lane.queued": "Queued", "j.lane.withdrawn": "Withdrawn",
    "j.corrob": "corroborated", "j.esc": "escalated · 12", "j.conf": "conf",
    "j.notried": "not tried yet", "j.back": "Verdict board", "j.charges": "All charges",
    "j.verdict": "Verdict", "j.evidence": "Evidence anchor (verbatim)", "j.close": "Close criterion",
    "j.refs": "References", "j.prov": "Provenance & flow", "j.trial.link": "See the trial record (Panel)",
    "j.section.jump": "Jump to this location in the paper",
    "j.kicker.charge": "Charge",
    "j.rev.title": "Revision inbox", "j.rev.sub": "Rows carrying a drafted patch — Accept lands it, Reject logs it",
    "j.rev.pending": "Patches awaiting a ruling", "j.rev.hist": "Applied this round (journal.jsonl)",
    "j.accept": "Accept", "j.reject": "Reject", "j.undo": "Undo", "j.applied": "Applied",
    "j.rejected": "Rejected", "j.reverted": "Reverted", "j.frozen": "touches frozen anchor",
    "j.panel.title": "Reviewer panel", "j.panel.reviewers": "%d domain reviewers", "j.panel.coverage": "Coverage heatmap",
    "j.panel.trials": "Per-charge trials", "j.unverified": "unverified · degraded", "j.defense": "Steelman defense",
    "j.grounds": "grounds", "j.jurors": "juror reasons", "j.jury.size": "jury",
    "j.shield.title": "Submission shield", "j.shield.compile": "Compile status", "j.shield.desk": "Desk-reject compliance",
    "j.shield.conv": "Convergence", "j.compile.clean": "Compiles clean", "j.compile.err": "Build errors",
    "j.compile.notrun": "Compile not run", "j.pages": "pages", "j.warns": "layout warnings", "j.errors": "errors",
    "j.notrun.note": "compiled: null is reported honestly as “compile not run” — never a fake pass.",
    "j.converged": "Converged", "j.notconverged": "Not converged",
    "j.ex.title": "Worked example", "j.ex.sub": "A real 21-page draft with 11 injected defects, one AUTO round",
    "j.ex.orig": "Original draft", "j.ex.rev": "Revised draft", "j.ex.defects": "known defects",
    "j.chain": "Chains from a Spark paper", "j.chain.sub": "Point Jury at a Spark-produced main.tex — it drops straight in, no conversion",
    "j.chain.act": "Review this draft", "j.vote.ok": "valid", "j.vote.no": "invalid", "j.vote.lim": "context-limited",
    "j.source": "under review", "j.mode": "mode",
    "j.src.reading": "reading", "j.src.sample": "Sample",
    // KPI strip — eyebrows (R5), plain-language tooltips + sublabels (R4)
    "j.stat.charges": "charges", "j.stat.gate": "gate-blocking majors", "j.stat.corrob": "corroborated ≥2",
    "j.stat.esc": "escalated to 12", "j.stat.route": "author-required · dropped",
    "j.stat.gate.must": "must reach 0 to submit", "j.stat.gate.clear": "clear to submit",
    "j.tip.charges": "Every reviewer complaint on the docket this round.",
    "j.tip.gate": "Open, major charges still blocking submission — while this is above 0 you cannot submit. Click to filter the docket to just these.",
    "j.tip.corrob": "Charges raised independently by ≥2 reviewers — a stronger signal.",
    "j.tip.esc": "Charges the 5-juror panel couldn't reach quorum on, sent to the 12-juror tier.",
    "j.tip.route": "Charges handed back to the author plus those dropped as invalid; they sit in off-screen lanes to the right. Click to jump there.",
    "j.filter.on": "Filtered to gate-blocking majors (major and still open)", "j.filter.clear": "Clear filter",
    // legend (R11)
    "j.legend": "Legend", "j.legend.chips": "Marks on each charge", "j.legend.lanes": "Board lanes",
    "j.gl.major": "gate-blocking severity", "j.gl.minor": "does not block submission",
    "j.gl.mech": "surface / mechanical error", "j.gl.subst": "meaning-level issue",
    "j.gl.vfix": "valid — safe to auto-fix", "j.gl.authreq": "valid, but needs the author",
    "j.gl.drop": "judged invalid — dropped", "j.gl.escal": "no quorum — escalated",
    "j.gl.corrob": "raised independently by ≥2 reviewers", "j.gl.esc12": "sent to the 12-juror tier",
    "j.gl.frozen": "edit here touches a frozen anchor sentence",
    "j.lm.raised": "raised, awaiting routing to trial", "j.lm.in-trial": "the jury is voting",
    "j.lm.valid-fixable": "valid, patch pending", "j.lm.closed": "fixed and verified",
    "j.lm.author-required": "handed back to the author", "j.lm.dropped": "judged invalid",
    "j.lm.queued": "anchor / meaning — queued for a human", "j.lm.withdrawn": "merged into another charge",
    // revision routing (R7) + explicit override
    "j.route.author": "Send to author", "j.route.queue": "Keep queued", "j.routed": "Routed",
    "j.override": "Override & apply…", "j.overridden": "override",
    // R24 — enum labels: EN is the raw enum, so identity (helper falls back to the value)
    // R18 — always-visible gloss caption (jargon legible without hover)
    "j.legend.cap": "major = blocks submission · conf = reviewer confidence (1–5) · corroborated ×2 = raised independently by ≥2 reviewers",
    "j.legend.more": "open the legend below for every mark and lane",
    // R13 — off-screen lane overflow cue (R7: fixed short label; the lane list stays in the tooltip)
    "j.board.more": "More lanes →",
    "j.board.more.tip": "Scroll to the off-screen lanes on the right (Author-Required / Dropped / Queued)",
    // R6 — empty docket state
    "j.empty.title": "No review on the docket yet",
    "j.empty.sub": "Send a draft to Jury and the board fills with every reviewer complaint, each one put on trial.",
    "j.empty.cta": "Review this draft",
    "j.empty.hint": "Want to see what it looks like? Open the Worked example.",
    // R14 — jump lands on the verbatim evidence in place
    "j.jump.done": "Jumped to the evidence in the manuscript text",
    // R21 — coverage summary line
    "j.cov.summary": "coverage evidence", "j.cov.thorough": "thorough", "j.cov.light": "light", "j.cov.skipped": "skipped",
    "j.cov.noflag": "no skim flag", "j.cov.unflagged": "unflagged = no positive coverage evidence",
    // R15 — one-line go/no-go readiness verdict on the docket
    "j.ready.eyebrow": "Submittable?", "j.ready.clear": "Clear to submit",
    "j.ready.blocked": "Not ready to submit", "j.ready.sample": "Can't assess — showing sample data",
    "j.ready.clear.sub": "no gate-blocking majors, round converged",
    // R6 — vote colour key on the docket + R2 keyboard hint
    "j.vote.key": "Jury vote:", "j.kbd.hint": "Keys: j / k up-down · h / l lanes · a author · r drop · f fixable · x select · ⇧A select lane · ⇧* select board · Enter open",
    // R9 — newcomer gloss under the convergence card
    "j.conv.gloss": "“genuinely new” = issues raised this round that didn't already exist (deduped against carried-over); a round that adds none emits the converged stamp.",
    // R18 — coverage cell → docket section filter
    "j.cov.filtered": "Filtered to charges in ", "j.cov.filtered.suf": "", "j.cov.blocked": "blocked",
    // R1 — couldNotRead honesty banner (broken dir → sample, not this manuscript)
    "j.cnr.head": "Couldn't read this directory", "j.cnr.sub": " — showing sample, not this manuscript.", "j.cnr.pre": "couldn't read ",
    "j.cnr.dismiss": "Dismiss", "j.tally.tip": "Jury vote: valid · invalid · context-limited",
    // R2(round4) — distinct AMBER readiness state: auto-blockers clear, author calls pending
    "j.ready.author": "Auto-blockers clear",
    // R20b(round4) — tally shown but no per-juror trial record on file
    "j.tally.only": "tally only — per-juror reasoning not recorded",
    "j.jurors.label": "juror reasons", "j.excerpt": "excerpt",
    // R8(round4) — Jury → Wiki handoff (files a not-yet-persisted inbox item)
    "j.wiki.file": "File to Wiki", "j.wiki.file.note": "New pending item in the Wiki inbox · not yet persisted",
    "j.wiki.notready": "Wiki not ready",
    // R22(round4) — sample-run title (drops the internal 'dogfood' slang)
    "j.title.sample": "sample run",
    // R28b(round4) — evidence-anchor verbatim proof badge
    "j.ev.verbatim": "verbatim match in source", "j.ev.notlocated": "not located",
    // R5 — jump relabel when the anchor can't be precisely resolved
    "j.section.open": "Open this section in the reader",
    // R5(6) — degraded reviewer surfaced at the charge
    "j.unv.title": "degraded / unverified reviewer", "j.degraded.only": "raised only by a degraded reviewer",
    // R5(7) — bulk disposition bar + undo
    "j.bulk.selected": "selected", "j.bulk.author": "author", "j.bulk.drop": "drop",
    "j.bulk.fixable": "fixable", "j.bulk.clear": "clear", "j.bulk.undo": "Undo",
    // R5(10) — charge provenance: which Spark run produced this manuscript
    "j.prov.src": "Source: run",
    // R5(20) — contested lens + dropped-without-trial audit
    "j.contested": "contested", "j.stat.contested": "contested",
    "j.tip.contested": "Charges a confident reviewer (≥4) raised that were dropped or deferred — click to filter to just these.",
    "j.contested.tip": "Raised by a confident reviewer (≥4) yet dropped or deferred — worth a second look.",
    "j.contested.on": "Filtered to contested charges (confident yet dropped or deferred)",
    "j.drop.audit": "Dropped without a recorded trial",
    "j.drop.audit.sub": "These charges were dropped without a per-juror trial record — tally and notes are shown so every dismissal stays auditable.",
    "j.drop.reason": "Reason dropped", "j.drop.open": "Open charge",
    // R5(21) — verbatim badge discloses WHICH source matched
    "j.ev.anchor": "matches frozen anchor", "j.ev.patchrec": "matches drafted patch record",
    "j.ev.selfonly": "matches only this charge's own patch text (not independent evidence)",
    // R5(25) — compile head: warnings are not a clean pass
    "j.compile.warn": "Compiles with warnings",
    // R6(round6) — jury additions: plain-language subtitles, coverage-gap caveat, round budget
    "j.panel.sub": "Reviewers, per-section coverage, and per-charge trials",
    "j.shield.sub": "Compile, desk-reject compliance, and convergence",
    "j.cov.gap": "Coverage gap — the section this charge rests on was skipped in coverage; weigh the verdict accordingly.",
    "j.conv.terminal": "If the round doesn't converge by the cap, remaining gate-blocking majors route to author-required.",
    // R7(round7) — projected readiness preview (dispositions not yet written) + coverage a11y + jury gloss
    "j.ready.proj": "%d after dispositions · preview, not written",
    "j.cov.opens": "opens",
    "j.cov.blank": "no skim flag · no positive coverage evidence (unread — not confirmed)",
    "j.jury.gloss": "Jury = a panel independent of reviewers %r: a base %n-juror panel; on no quorum it escalates to a 12-juror tier.",
    "j.jury.esc": "jury 5 → 12 (escalated)", "j.jury.framings": "%n framings (not jurors)",
    // R12(round10) — de-leaked stat labels + reverted-row restore + on-card coverage-gap chip
    "j.bibentries": "bib entries", "j.genuinelynew": "genuinely new",
    "j.redo": "Restore", "j.redo.tip": "Undo the revert — restore this applied edit", "j.restored": "Restored",
    "j.cov.gapchip": "coverage gap",
  };
  if (SB.I18N) { Object.assign(SB.I18N.zh, JZH); Object.assign(SB.I18N.en, JEN); }

  /* ---- extra glyphs (injected once; work in BOTH the demo and the real shell) */
  function ensureJurySprite() {
    if (document.getElementById("j-sprite")) return;
    // Build the sprite through the HTML parser (insertAdjacentHTML) so the <svg>
    // enters FOREIGN-CONTENT mode and the <symbol>/<path> defs land in the real SVG
    // namespace. document.createElement("svg") (what el() does) makes an HTML-
    // namespaced element whose <symbol> children never paint via <use> — the trap
    // the shell's own createElement-based sprite hits, leaving its icons blank.
    // Icons are <symbol viewBox="0 0 16 16"> so a <use> scales to the host <svg> at
    // any size (a bare <g> without a viewBox renders at fixed 16px pinned top-left,
    // clipping at .i.sm=13px). We define our OWN check/close so the module never
    // depends on the shell glyphs. Fill icons set fill on the path (beats .i{fill:none}).
    var sprite =
      '<svg id="j-sprite" width="0" height="0" aria-hidden="true" style="position:absolute">' +
      '<defs>' +
      '<symbol id="jx-check" viewBox="0 0 16 16"><path d="M3 8.25l3.5 3.5L13 5" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"/></symbol>' +
      '<symbol id="jx-close" viewBox="0 0 16 16"><path d="M4 4l8 8M12 4l-8 8" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></symbol>' +
      '<symbol id="jx-back" viewBox="0 0 16 16"><path d="M9.5 3.5L5 8l4.5 4.5" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/></symbol>' +
      '<symbol id="jx-scale" viewBox="0 0 16 16"><path d="M8 2.6v10.8M4 13.4h8M3 6l-1.7 3.4a2 2 0 0 0 3.4 0zM13 6l-1.7 3.4a2 2 0 0 0 3.4 0zM3 6h10M8 3.4l-5 2.6M8 3.4l5 2.6" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></symbol>' +
      '<symbol id="jx-shield" viewBox="0 0 16 16"><path d="M8 1.8l5 1.8v4.2c0 3-2.1 5-5 6.4-2.9-1.4-5-3.4-5-6.4V3.6L8 1.8z" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/></symbol>' +
      '<symbol id="jx-undo" viewBox="0 0 16 16"><path d="M4 6.5H9.5a3.2 3.2 0 0 1 0 6.4H6M4 6.5l2.4-2.4M4 6.5l2.4 2.4" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></symbol>' +
      '<symbol id="jx-doc" viewBox="0 0 16 16"><path d="M4 1.8h5l3 3v9.4H4V1.8zM9 1.8V5h3" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/></symbol>' +
      '<symbol id="jx-warn" viewBox="0 0 16 16"><path d="M8 2.4l6 10.6H2L8 2.4z" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/><path d="M8 6.6v3.1" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/><circle cx="8" cy="11.5" r=".72" fill="currentColor" stroke="none"/></symbol>' +
      '<symbol id="jx-quote" viewBox="0 0 16 16"><path d="M3 4h3.4v3.4c0 1.9-1 3.2-3 3.9L2.6 10c1.1-.4 1.7-1 1.8-1.9H3V4zm6 0h3.4v3.4c0 1.9-1 3.2-3 3.9L8.6 10c1.1-.4 1.7-1 1.8-1.9H9V4z" fill="currentColor" stroke="none"/></symbol>' +
      '<symbol id="jx-gavel" viewBox="0 0 16 16"><path d="M3 13.4h6M9.2 3.4l3.4 3.4M7.4 5.2l3.4 3.4M4.6 8l2.8-2.8M9.2 5.6L11 3.8M5 12l4-4" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/></symbol>' +
      '<symbol id="jx-flame" viewBox="0 0 16 16"><path d="M8 1.6c.6 2.2-1.9 3-1.9 5.1 0 .9.5 1.6 1 2-.2-1.4.7-2.2 1.2-2.7.9 1 1.9 2 1.9 3.4A3.2 3.2 0 1 1 4.8 9c0-2.8 3.2-3.6 3.2-7.4z" fill="currentColor" stroke="none"/></symbol>' +
      '</defs></svg>';
    document.body.insertAdjacentHTML("beforeend", sprite);
  }

  /* ========================================================================== *
     INLINE SAMPLE DATA — mirrors <manuscript>/.paper-review/* (ledger-schema.md)
     This is the FALLBACK: the app is gorgeous out-of-the-box from SAMPLE, then
     truthful the moment SB.data points it at a reviewed manuscript (see LIVE DATA).
     ========================================================================== */
  var SAMPLE = {
    meta: { manuscript: "paper/main.tex", venue_family: "ml", created_round: 1,
            assignment_unverified: ["R3"], display_mode: "collapse", mode: "auto",
            run_id: "jury-2026-08-14-dogfood" },

    // 23 charges — one per ledger row. Full field set per ledger-schema.md.
    ledger: [
      { id:"I-01", passage_id:"p-s8-concurrency", significance:"major", kind:"mechanical",
        section:"§8 / Table 4 / ¶2", evidence_anchor:"the orchestrator runs up to 8 reviewer agents concurrently",
        summary:"Self-contradiction: prose says 8 concurrent reviewers, Table 4 says 16.",
        references:"§8 Implementation; Table 4 (throughput)",
        close_criterion:"Prose and Table 4 state one identical concurrency number; no other site disagrees.",
        status:"closed", verdict:"valid-fixable", reason_code:null,
        tally:{valid:5,invalid:0,context_limited:0}, escalated:false, reviewer_confidence:4,
        raised_by:["R1","R2"], raised_by_count:2, round_raised:1, round_closed:1,
        drafted_patch:{before:"the orchestrator runs up to 8 reviewer agents concurrently",after:"the orchestrator runs up to 16 reviewer agents concurrently"},
        journal_ref:"J-0001", notes:"F1. Unified to 16 to match Table 4 (draft intent)." },
      { id:"I-02", passage_id:"p-s72-simthreshold", significance:"major", kind:"mechanical",
        section:"§7.2 / eq 5 / ¶1", evidence_anchor:"duplicate weaknesses are merged when simThreshold = 0.7",
        summary:"Clerk merge threshold: prose simThreshold=0.7 contradicts adjacent equation (0.8).",
        references:"§7.2 Clerk merge; Eq. 5",
        close_criterion:"Prose threshold equals the equation's value at every occurrence.",
        status:"closed", verdict:"valid-fixable", reason_code:null,
        tally:{valid:5,invalid:0,context_limited:0}, escalated:false, reviewer_confidence:4,
        raised_by:["R1"], raised_by_count:1, round_raised:1, round_closed:1,
        drafted_patch:{before:"duplicate weaknesses are merged when simThreshold = 0.7",after:"duplicate weaknesses are merged when simThreshold = 0.8"},
        journal_ref:"J-0002", notes:"F2. Unified to 0.8 to match Eq. 5." },
      { id:"I-03", passage_id:"p-s5-jurysize", significance:"major", kind:"mechanical",
        section:"§5 / ¶3", evidence_anchor:"the escalated tier convenes a jury of jurySize = 10",
        summary:"Escalation jury size written as 10; every other site says 12.",
        references:"§5 Escalation; §5.2; §9",
        close_criterion:"Escalation jury size is 12 wherever the escalated tier is described.",
        status:"closed", verdict:"valid-fixable", reason_code:null,
        tally:{valid:5,invalid:0,context_limited:0}, escalated:false, reviewer_confidence:5,
        raised_by:["R2","R3"], raised_by_count:2, round_raised:1, round_closed:1,
        drafted_patch:{before:"the escalated tier convenes a jury of jurySize = 10",after:"the escalated tier convenes a jury of jurySize = 12"},
        journal_ref:"J-0003", notes:"F3. Corrected to 12." },
      { id:"I-04", passage_id:"p-s2-isolation", significance:"major", kind:"substantive",
        section:"§2 / Invariant 1", evidence_anchor:"each juror is given the cumulative ledger before voting",
        summary:"Isolation invariant flipped: text says jurors see the cumulative ledger, contradicting the core design.",
        references:"§2 Invariants; §5 Trial mechanics",
        close_criterion:"Invariant 1 states jurors are isolated and never see the ledger; no downstream text contradicts it.",
        status:"closed", verdict:"valid-fixable", reason_code:null,
        tally:{valid:5,invalid:0,context_limited:0}, escalated:false, reviewer_confidence:5,
        raised_by:["R1","R2","R3"], raised_by_count:3, round_raised:1, round_closed:1,
        drafted_patch:{before:"each juror is given the cumulative ledger before voting",after:"each juror is isolated and never sees the ledger before voting"},
        journal_ref:"J-0004", notes:"F4. Restored the isolation invariant (meaning consistent with §5)." },
      { id:"I-05", passage_id:"p-s1-c5-clerk", significance:"minor", kind:"mechanical",
        section:"§1 / Contribution C5", evidence_anchor:"C5: the registrar reconciles carried open questions across rounds",
        summary:"Term 'registrar' used once for the component called 'clerk' everywhere else.",
        references:"§1 C5; §7.2; §10",
        close_criterion:"The component is named 'clerk' consistently; 'registrar' does not appear.",
        status:"closed", verdict:"valid-fixable", reason_code:null,
        tally:{valid:4,invalid:0,context_limited:1}, escalated:false, reviewer_confidence:3,
        raised_by:["R2"], raised_by_count:1, round_raised:1, round_closed:1,
        drafted_patch:{before:"C5: the registrar reconciles carried open questions across rounds",after:"C5: the clerk reconciles carried open questions across rounds"},
        journal_ref:"J-0005", notes:"F5. Renamed registrar → clerk (folded into Minor digest by collapse render)." },
      { id:"I-06", passage_id:"p-s4-dangling-cite", significance:"major", kind:"mechanical",
        section:"§4 / ¶1", evidence_anchor:"the program chair assigns reviewers \\cite{wang2025programchair}",
        summary:"Dangling citation: \\cite{wang2025programchair} has no bib entry; breaks a clean build.",
        references:"§4; refs.bib",
        close_criterion:"No undefined citation keys remain; build is warning-free.",
        status:"closed", verdict:"valid-fixable", reason_code:null,
        tally:{valid:5,invalid:0,context_limited:0}, escalated:false, reviewer_confidence:4,
        raised_by:["R1"], raised_by_count:1, round_raised:1, round_closed:1,
        drafted_patch:{before:"the program chair assigns reviewers \\cite{wang2025programchair}",after:"the program chair assigns reviewers"},
        journal_ref:"J-0006", notes:"F6. Deleted the dangling citation; bib key never existed." },
      { id:"I-07", passage_id:"p-abs-router-agree", significance:"major", kind:"substantive",
        section:"Abstract / ¶1", evidence_anchor:"achieving 94% router agreement, confirming the approach in practice",
        summary:"Abstract asserts a 94% router-agreement result with no supporting experiment (fabricated over-claim).",
        references:"Abstract; §9 (no matching experiment)",
        close_criterion:"The abstract makes no empirical claim unsupported by a reported experiment; any target is marked illustrative.",
        status:"closed", verdict:"valid-fixable", reason_code:null,
        tally:{valid:5,invalid:0,context_limited:0}, escalated:false, reviewer_confidence:5,
        raised_by:["R1","R2","R3"], raised_by_count:3, round_raised:1, round_closed:1,
        drafted_patch:{before:"achieving 94% router agreement, confirming the approach in practice",after:"an illustrative target; Section 9 specifies the measurement methodology"},
        journal_ref:"J-0007", notes:"A1. Fabricated number softened to an illustrative target (over-claim neutralized)." },
      { id:"I-08", passage_id:"p-s3-three-rounds", significance:"major", kind:"substantive",
        section:"§3 / ¶4", evidence_anchor:"the reconciliation reaches this fixed point within three rounds",
        summary:"Convergence claim 'within three rounds' has no supporting data (fabricated specificity).",
        references:"§3 Convergence; §10 (no round-count study)",
        close_criterion:"Any convergence-speed statement is qualitative unless a measured round count is reported.",
        status:"closed", verdict:"valid-fixable", reason_code:null,
        tally:{valid:4,invalid:1,context_limited:0}, escalated:false, reviewer_confidence:4,
        raised_by:["R2"], raised_by_count:1, round_raised:1, round_closed:1,
        drafted_patch:{before:"the reconciliation reaches this fixed point within three rounds",after:"the reconciliation reaches this fixed point in a small number of rounds"},
        journal_ref:"J-0008", notes:"A3. Dropped the unsupported 'three'; softened to 'a small number of rounds'." },
      { id:"I-09", passage_id:"p-s4-fewer-agents", significance:"major", kind:"substantive",
        section:"§4 / ¶3", evidence_anchor:"in our runs the courtroom uses an order of magnitude fewer agents at strictly higher precision",
        summary:"Fabricated head-to-head result ('order of magnitude fewer agents … strictly higher precision') with no experiment in the paper.",
        references:"§4; §9 (no such comparison reported)",
        close_criterion:"The comparison is removed or backed by a reported experiment; no 'in our runs' claim survives without data.",
        status:"author-required", verdict:"author-required", reason_code:"needs-human-input",
        tally:{valid:5,invalid:0,context_limited:0}, escalated:false, reviewer_confidence:5,
        raised_by:["R1","R3"], raised_by_count:2, round_raised:1, round_closed:null,
        drafted_patch:{before:"in our runs the courtroom uses an order of magnitude fewer agents at strictly higher precision",after:"the courtroom is designed to use fewer agents; Section 9 specifies how precision would be measured"},
        journal_ref:null, notes:"A2. Verdict valid, but softening vs. deletion changes the paper's claim scope; handed to the author. Draft patch proposed, NOT applied." },
      { id:"I-10", passage_id:"p-s1-c3-fivetier", significance:"major", kind:"substantive",
        section:"§1 / C3 vs §5.2 title / §5.4 caption / §9", evidence_anchor:"C3: a two-sided escalating trial adjudicates each charge",
        summary:"Polish reworded C3 to 'two-sided escalating trial', but §5.2 title, §5.4 caption, and §9 still say 'five-tier'.",
        references:"§1 C3; §5.2; §5.4; §9",
        close_criterion:"One consistent name for the trial mechanism appears in C3, section titles, and captions.",
        status:"author-required", verdict:"author-required", reason_code:"claim-meaning-change",
        tally:{valid:4,invalid:0,context_limited:1}, escalated:false, reviewer_confidence:4,
        raised_by:["R2"], raised_by_count:1, round_raised:1, round_closed:null,
        drafted_patch:{before:"C3: a two-sided escalating trial adjudicates each charge",after:"C3: a five-tier trial adjudicates each charge"},
        journal_ref:null, notes:"Engine-introduced during review (not an injected defect). Reverting to 'five-tier' is the safe fix but touches a contribution sentence; deferred to author." },
      { id:"I-11", passage_id:"p-s4-no-quota", significance:"major", kind:"substantive",
        section:"§4 / ¶2", evidence_anchor:"there is no per-section reviewer assignment and no per-section coverage quota",
        summary:"Reviewer flags the absence of per-section coverage quotas as a soundness gap.",
        references:"§4 Assignment; §6 Anti-skim", close_criterion:null,
        status:"dropped", verdict:"invalid-drop", reason_code:null,
        tally:{valid:1,invalid:4,context_limited:0}, escalated:false, reviewer_confidence:3,
        raised_by:["R3"], raised_by_count:1, round_raised:1, round_closed:1,
        drafted_patch:null, journal_ref:null,
        notes:"B1 (bait). Defensible: the paper states this is a deliberate design choice justified by the holistic-reviewer + coverage-auditor anti-skim path. Left untouched; zero false positive." },
      { id:"I-12", passage_id:"p-s7-same-ledger", significance:"major", kind:"substantive",
        section:"§7 / ¶4", evidence_anchor:"the completion gate is evaluated over the same ledger state the engine's own steps write",
        summary:"Reviewer alleges the completion gate is circular (evaluated over state the engine writes).",
        references:"§7 Gate; §2 Invariants", close_criterion:null,
        status:"dropped", verdict:"invalid-drop", reason_code:null,
        tally:{valid:2,invalid:9,context_limited:1}, escalated:true, reviewer_confidence:3,
        raised_by:["R1","R3"], raised_by_count:2, round_raised:1, round_closed:1,
        drafted_patch:null, journal_ref:null,
        notes:"B2 (bait). Escalated to 12 for the disagreement, then dropped: the gate reads a monotone invariant, not a value the same step mutates. Defensible; left untouched." },
      { id:"I-13", passage_id:"p-s9-missing-baseline", significance:"minor", kind:"substantive",
        section:"§9 / ¶1", evidence_anchor:"we compare against a single-reviewer baseline",
        summary:"Reviewer wants an additional multi-agent-debate baseline.",
        references:"§9 Evaluation", close_criterion:null,
        status:"dropped", verdict:"invalid-drop", reason_code:null,
        tally:{valid:1,invalid:3,context_limited:1}, escalated:false, reviewer_confidence:2,
        raised_by:["R3"], raised_by_count:1, round_raised:1, round_closed:1,
        drafted_patch:null, journal_ref:null,
        notes:"Dropped: out-of-scope for a bounded-revision methods paper; the requested baseline addresses a different claim. Reason logged." },
      { id:"I-14", passage_id:"p-s6-cap-style", significance:"minor", kind:"mechanical",
        section:"§6 / ¶2", evidence_anchor:"the Ledger records every applied edit",
        summary:"Inconsistent capitalization of 'Ledger' vs 'ledger'.",
        references:"§6; throughout", close_criterion:null,
        status:"dropped", verdict:"invalid-drop", reason_code:null,
        tally:{valid:1,invalid:4,context_limited:0}, escalated:false, reviewer_confidence:2,
        raised_by:["R2"], raised_by_count:1, round_raised:1, round_closed:1,
        drafted_patch:null, journal_ref:null,
        notes:"Dropped: severity-overstated; house style capitalizes the artifact 'Ledger' deliberately. Not a defect." },
      { id:"I-15", passage_id:"p-abs-central-claim", significance:"major", kind:"substantive",
        section:"Abstract / ¶2", evidence_anchor:"Due-process review yields a 4.4x lower unsafe-edit rate than agreeable revision",
        summary:"Reviewer wants '4.4x' rephrased; a fix here would restate the paper's headline claim sentence.",
        references:"Abstract; §9 ESVR",
        close_criterion:"Abstract's ESVR statement matches the reported number and the frozen claim wording.",
        status:"queued", verdict:"valid-fixable", reason_code:"anchor-touching",
        tally:{valid:4,invalid:1,context_limited:0}, escalated:false, reviewer_confidence:4,
        raised_by:["R1"], raised_by_count:1, round_raised:1, round_closed:null,
        drafted_patch:{before:"Due-process review yields a 4.4x lower unsafe-edit rate than agreeable revision",after:"Due-process review yields a substantially lower unsafe-edit rate (4.4x, ESVR 0.025 vs 0.110) than agreeable revision"},
        journal_ref:null, notes:"Auto queued: the edit touches frozen spine anchor A1; deferred to human review rather than drifting the headline claim." },
      { id:"I-16", passage_id:"p-s1-c1-scope", significance:"major", kind:"substantive",
        section:"§1 / Contribution C1", evidence_anchor:"C1: a due-process review engine for bounded LaTeX revision",
        summary:"Reviewer suggests widening C1 to 'any document format'; would change the contribution's scope.",
        references:"§1 C1; §8 Intake",
        close_criterion:"C1 states the scope the experiments actually validate; no broadened claim without support.",
        status:"queued", verdict:"valid-fixable", reason_code:"claim-meaning-change",
        tally:{valid:3,invalid:1,context_limited:1}, escalated:false, reviewer_confidence:3,
        raised_by:["R2"], raised_by_count:1, round_raised:1, round_closed:null,
        drafted_patch:null, journal_ref:null,
        notes:"Auto queued (claim-meaning-change): broadening C1 beyond LaTeX/MD/docx is a claim expansion; needs author sign-off." },
      { id:"I-17", passage_id:"p-s10-typo-flow", significance:"minor", kind:"mechanical",
        section:"§10 / ¶1", evidence_anchor:"the clerk emits a converged stamp when a round adds nothing new",
        summary:"Minor wording: 'adds nothing new' is slightly redundant; polish suggestion.",
        references:"§10 Convergence", close_criterion:"Sentence reads cleanly; meaning unchanged.",
        status:"queued", verdict:null, reason_code:"polish-review",
        tally:null, escalated:false, reviewer_confidence:2,
        raised_by:["R2"], raised_by_count:1, round_raised:1, round_closed:null,
        drafted_patch:{before:"the clerk emits a converged stamp when a round adds nothing new",after:"the clerk emits a converged stamp when a round adds nothing"},
        journal_ref:null, notes:"Polish item queued for a human glance (polish-review); cosmetic only." },
      { id:"I-18", passage_id:"p-s9-seed-var", significance:"major", kind:"substantive",
        section:"§9 / Table 5", evidence_anchor:"F1 question quality reaches 0.656",
        summary:"Table 5 reports F1=0.656 with no variance / seed information.",
        references:"§9 Table 5; §9.1 Protocol", close_criterion:null,
        status:"raised", verdict:null, reason_code:null,
        tally:null, escalated:false, reviewer_confidence:4,
        raised_by:["R1","R3"], raised_by_count:2, round_raised:1, round_closed:null,
        drafted_patch:null, journal_ref:null,
        notes:"Freshly merged this round; awaiting routing to trial (substantive-major)." },
      { id:"I-19", passage_id:"p-s5-fig3-label", significance:"minor", kind:"mechanical",
        section:"§5 / Figure 3", evidence_anchor:"Figure 3: the five-tier trial pipeline",
        summary:"Figure 3 panel labels (a)-(c) are referenced in text as (a)-(d).",
        references:"§5; Figure 3 caption", close_criterion:null,
        status:"raised", verdict:null, reason_code:null,
        tally:null, escalated:false, reviewer_confidence:3,
        raised_by:["R2"], raised_by_count:1, round_raised:1, round_closed:null,
        drafted_patch:null, journal_ref:null, notes:"Fresh mechanical-minor; will route to polish." },
      { id:"I-20", passage_id:"p-s3-fixedpoint-proof", significance:"major", kind:"substantive",
        section:"§3 / Prop. 1", evidence_anchor:"Proposition 1: the reconciliation operator has a unique fixed point",
        summary:"Uniqueness claim in Prop. 1 may not hold without a stated contraction/monotonicity condition.",
        references:"§3 Prop. 1; Appendix A proof", close_criterion:null,
        status:"in-trial", verdict:"escalate", reason_code:null,
        tally:{valid:3,invalid:2,context_limited:2}, escalated:true, reviewer_confidence:5,
        raised_by:["R1","R3"], raised_by_count:2, round_raised:1, round_closed:null,
        drafted_patch:null, journal_ref:null,
        notes:"5-juror tier failed quorum (no side >60% of surviving votes); escalated to the 12-juror tier, re-run pending." },
      { id:"I-21", passage_id:"p-s6-quote-verify", significance:"major", kind:"substantive",
        section:"§6 / ¶3", evidence_anchor:"a hallucinated quote is detected because it fails a deterministic string match",
        summary:"The 'cannot quote = did not read' mechanism is asserted but never tied to a measured false-negative rate.",
        references:"§6 Anti-skim; §9",
        close_criterion:"The claim is scoped to what is measured, or a pointer to the quote-verify evaluation is added.",
        status:"valid-fixable", verdict:"valid-fixable", reason_code:null,
        tally:{valid:5,invalid:0,context_limited:0}, escalated:false, reviewer_confidence:4,
        raised_by:["R1"], raised_by_count:1, round_raised:1, round_closed:null,
        drafted_patch:{before:"a hallucinated quote is detected because it fails a deterministic string match",after:"a hallucinated quote fails a deterministic string match (Section 9 reports the verification pass rate)"},
        journal_ref:null, notes:"Verdict valid-fixable; drafter pending. Non-anchor edit, will route through edit-audit." },
      { id:"I-22", passage_id:"p-s72-clerk-nit", significance:"minor", kind:"mechanical",
        section:"§7.2 / ¶2", evidence_anchor:"the clerk dedups this-round issues and carries open questions foward",
        summary:"Typo: 'foward' → 'forward'.",
        references:"§7.2", close_criterion:"Spelling corrected; no meaning change.",
        status:"valid-fixable", verdict:"valid-fixable", reason_code:"polish-review",
        tally:{valid:5,invalid:0,context_limited:0}, escalated:false, reviewer_confidence:3,
        raised_by:["R2"], raised_by_count:1, round_raised:1, round_closed:null,
        drafted_patch:{before:"the clerk dedups this-round issues and carries open questions foward",after:"the clerk dedups this-round issues and carries open questions forward"},
        journal_ref:null, notes:"Polish path: trivial close_criterion set; drafter pending." },
      { id:"I-23", passage_id:"p-s8-concurrency", significance:"minor", kind:"mechanical",
        section:"§8 / ¶4", evidence_anchor:"concurrency is capped at eight workers",
        summary:"Second site restating the 8-vs-16 concurrency contradiction (duplicate of I-01).",
        references:"§8", close_criterion:null,
        status:"withdrawn", verdict:null, reason_code:null,
        tally:null, escalated:false, reviewer_confidence:3,
        raised_by:["R3"], raised_by_count:1, round_raised:1, round_closed:1,
        drafted_patch:null, journal_ref:null,
        notes:"Withdrawn by the clerk: merged into I-01 (same passage_id p-s8-concurrency)." },
    ],

    // assign-reviewers.workflow.js output — the panel
    reviewers: [
      { reviewer_id:"R1", domain:"LLM agents / multi-agent orchestration", overall_confidence:5, unverified:false,
        persona_prompt:"Senior reviewer alert to unsupported central claims in agentic systems: whether an orchestration design is actually validated by the reported runs, whether agent-count / latency claims are measured or asserted, and whether cross-agent isolation guarantees hold as stated. You separate fatal flaws from fixable nits, quote exactly, and never invent problems to look thorough." },
      { reviewer_id:"R2", domain:"Program analysis / automated verification & safety gates", overall_confidence:4, unverified:false,
        persona_prompt:"Reviewer from software verification, alert to soundness of build gates, circularity in invariants, and whether a 'deterministic guard' actually decides what it claims. You check that thresholds, fixed-point/uniqueness arguments, and completion gates are well-defined and non-circular, and that numbers in prose match tables and equations." },
      { reviewer_id:"R3", domain:"generic gatekeeper (degraded) + ML venue reviewer", overall_confidence:3, unverified:true,
        persona_prompt:"GENERIC fallback lens (empirical/benchmark): baseline fairness and vintage, metric correctness, variance/seeds, ablation coverage, cherry-picking, and claims-vs-evidence rigor. Applied because the assigned subfield 'peer-review meta-science' could not be confirmed on-topic by the verifier." },
    ],

    // coverage-auditor.workflow.js flags — skimmed (reviewer × section) pairs
    coverage_flags: [
      { reviewer_id:"R1", section:"§8 Implementation", status:"light", reason:"R1 filed no in-section quote for §8; the concurrency contradiction (I-01) was caught by R2 only until a cap-1 re-invoke." },
      { reviewer_id:"R3", section:"§3 Convergence / Prop. 1", status:"skipped", reason:"R3 coverage report had no verbatim quote from §3; re-invoked in targets mode." },
      { reviewer_id:"R3", section:"Appendix A (proof)", status:"skipped", reason:"Proof appendix not quoted by any reviewer; flagged for a targeted read before the fixed-point charge (I-20) could be tried." },
      { reviewer_id:"R2", section:"§9 Evaluation", status:"thorough", reason:"No skim flag; kept for the (reviewer × section) heatmap as a fully-covered cell." },
    ],

    // trial.workflow.js scorecards — verdict + jury per substantive-major charge
    trials: [
      { charge_id:"T-04", issue_id:"I-04", significance:"major", kind:"substantive", section:"§2 / Invariant 1",
        summary:"Isolation invariant flipped: text says jurors see the cumulative ledger.",
        evidence_anchor:"each juror is given the cumulative ledger before voting", verdict:"valid-fixable",
        close_criterion:"Invariant 1 states jurors are isolated and never see the ledger; no downstream text contradicts it.",
        rationale:"Quorum reached; 5/5 jurors valid. The sentence directly contradicts §5's isolated-voting mechanic and Invariant 1's own heading, so it is an internal contradiction, not a defensible framing.",
        tally:{valid:5,invalid:0,context_limited:0}, jury_size:5, escalated:false,
        defense:{ defense:"The sentence could be read as describing the clerk's post-vote reconciliation, which does see the ledger.", grounds:"severity-overstated" },
        votes:[
          {vote:"valid", reason:"Invariant 1's title says 'isolation'; the body sentence asserts the opposite. Textbook internal contradiction."},
          {vote:"valid", reason:"§5.1 states jurors vote 'without ledger sight'; §2 must agree."},
          {vote:"valid", reason:"Most-hostile framing still finds no reading where a juror both is isolated and is given the cumulative ledger."},
          {vote:"valid", reason:"Most-charitable framing (clerk, not juror) fails: the subject of the sentence is 'each juror'."},
          {vote:"valid", reason:"Fixable by restoring the isolation wording; does not touch a frozen result."} ] },
      { charge_id:"T-12", issue_id:"I-12", significance:"major", kind:"substantive", section:"§7 / ¶4",
        summary:"Completion gate alleged circular (evaluated over state the engine writes).",
        evidence_anchor:"the completion gate is evaluated over the same ledger state the engine's own steps write", verdict:"invalid-drop",
        close_criterion:null,
        rationale:"5-tier tier split 3 invalid / 1 valid / 1 context-limited (no side >60% of surviving votes at the 0.8 quorum); escalated to 12. The 12-juror tier reached 9 invalid / 2 valid / 1 context-limited: the gate reads a monotone 'no active gate-blocking major' invariant, which no single engine step both writes and then reads to certify itself.",
        tally:{valid:2,invalid:9,context_limited:1}, jury_size:12, escalated:true,
        defense:{ defense:"The gate is not circular: it evaluates a monotone invariant (count of active gate-blocking majors), not a value a step mutates to pass itself; the ledger writer and the gate reader are decorrelated steps.", grounds:"addressed-in-text" },
        votes:[
          {vote:"invalid", reason:"Reading state you also write is only circular if the writer can set the pass condition; here the condition is a count no single step can zero out for itself."},
          {vote:"invalid", reason:"§2 Invariant 3 already pins the gate to activeCounts(); defensible design choice, not a flaw."},
          {vote:"valid", reason:"The prose is loose enough to invite the circularity reading; could be sharpened."},
          {vote:"context_limited", reason:"Would need the appendix to confirm the write/read decorrelation."} ] },
      { charge_id:"T-09", issue_id:"I-09", significance:"major", kind:"substantive", section:"§4 / ¶3",
        summary:"Fabricated head-to-head result with no experiment ('order of magnitude fewer agents … strictly higher precision').",
        evidence_anchor:"in our runs the courtroom uses an order of magnitude fewer agents at strictly higher precision", verdict:"author-required",
        close_criterion:"The comparison is removed or backed by a reported experiment; no 'in our runs' claim survives without data.",
        rationale:"Jury unanimous that the sentence asserts an empirical result absent from §9. Judge routes to author-required rather than valid-fixable: choosing between deletion and softening changes the paper's claimed contribution scope and needs author-private knowledge of whether the run exists.",
        tally:{valid:5,invalid:0,context_limited:0}, jury_size:5, escalated:false,
        defense:{ defense:"The claim may summarize a run the authors have but did not table.", grounds:"out-of-scope" },
        votes:[
          {vote:"valid", reason:"'in our runs' promises data; §9 reports none matching this comparison."},
          {vote:"valid", reason:"'strictly higher precision' is a falsifiable claim with no number and no baseline named."},
          {vote:"valid", reason:"Even the charitable framing (a real-but-untabled run) still means the text overstates what the paper shows."},
          {vote:"valid", reason:"Cannot be auto-softened safely: deletion vs. hedge is an author decision."},
          {vote:"valid", reason:"Route to author-required; drafter may PROPOSE a hedge but must not apply it."} ] },
      { charge_id:"T-20", issue_id:"I-20", significance:"major", kind:"substantive", section:"§3 / Prop. 1",
        summary:"Uniqueness of the reconciliation fixed point may not hold without a stated contraction/monotonicity condition.",
        evidence_anchor:"Proposition 1: the reconciliation operator has a unique fixed point", verdict:"escalate",
        close_criterion:null,
        rationale:"5-tier tier: 3 valid / 2 invalid / 2 context-limited over a jury of 7 framings (surviving votes fail the >60% one-side rule). Quorum not met; charge escalated to the 12-juror tier, re-run pending. Status stays in-trial.",
        tally:{valid:3,invalid:2,context_limited:2}, jury_size:7, escalated:true,
        defense:{ defense:"Appendix A proves monotonicity of the reconciliation operator on the finite ledger lattice, which gives a least fixed point; 'unique' may be a wording slip for 'least'.", grounds:"would-drift-anchor" },
        votes:[
          {vote:"valid", reason:"Uniqueness needs contraction or a stated order; monotonicity alone gives least/greatest, not unique."},
          {vote:"invalid", reason:"On a finite lattice with the stated join, the least fixed point suffices for the convergence claim; 'unique' is harmless."},
          {vote:"context_limited", reason:"Cannot adjudicate without reading Appendix A's operator definition, which was skipped in coverage."},
          {vote:"valid", reason:"If it is a wording slip, fixing it edits a Proposition statement — a frozen-spine-adjacent claim; needs the escalated tier."} ] },
    ],

    // clerk.workflow.js — round-boundary / convergence report
    clerk: { round:1, new:2, closed:8, author_required:2, queued:3, dropped:4, withdrawn:1,
      genuinely_new:["I-18","I-19"], genuinely_new_count:2, new_closures_count:8, new_author_required_count:2,
      converged:false,
      // R5-jury(round10): paired reason so the zh shell never shows the English narrative verbatim.
      // `reason` is kept as a fallback for a LIVE adapter that emits only one language.
      reason:"Round 1 added 2 genuinely-new issues and left 2 author-required + 3 queued open; not converged. A round that adds nothing new will emit the converged stamp.",
      reason_en:"Round 1 added 2 genuinely-new issues and left 2 author-required + 3 queued open; not converged. A round that adds nothing new will emit the converged stamp.",
      reason_zh:"第 1 轮新增 2 个此前不存在的问题,并留下 2 项待作者 + 3 项已入队未了结;未收敛。某一轮不再产生新问题,即盖上「已收敛」印。" },

    // journal.jsonl — every applied edit as an atomic reversible unit
    journal: [
      { seq:1, jid:"J-0001", issue_id:"I-01", passage_id:"p-s8-concurrency", round:1, close_criterion:"Prose and Table 4 state one identical concurrency number; no other site disagrees.", before:"the orchestrator runs up to 8 reviewer agents concurrently", after:"the orchestrator runs up to 16 reviewer agents concurrently", ts:"2026-08-14T09:12:03Z", applied:true },
      { seq:2, jid:"J-0002", issue_id:"I-02", passage_id:"p-s72-simthreshold", round:1, close_criterion:"Prose threshold equals the equation's value at every occurrence.", before:"duplicate weaknesses are merged when simThreshold = 0.7", after:"duplicate weaknesses are merged when simThreshold = 0.8", ts:"2026-08-14T09:12:41Z", applied:true },
      { seq:3, jid:"J-0003", issue_id:"I-03", passage_id:"p-s5-jurysize", round:1, close_criterion:"Escalation jury size is 12 wherever the escalated tier is described.", before:"the escalated tier convenes a jury of jurySize = 10", after:"the escalated tier convenes a jury of jurySize = 12", ts:"2026-08-14T09:13:20Z", applied:true },
      { seq:4, jid:"J-0004", issue_id:"I-04", passage_id:"p-s2-isolation", round:1, close_criterion:"Invariant 1 states jurors are isolated and never see the ledger; no downstream text contradicts it.", before:"each juror is given the cumulative ledger before voting", after:"each juror is isolated and never sees the ledger before voting", ts:"2026-08-14T09:14:05Z", applied:true },
      { seq:5, jid:"J-0005", issue_id:"I-05", passage_id:"p-s1-c5-clerk", round:1, close_criterion:"The component is named 'clerk' consistently; 'registrar' does not appear.", before:"C5: the registrar reconciles carried open questions across rounds", after:"C5: the clerk reconciles carried open questions across rounds", ts:"2026-08-14T09:14:39Z", applied:true },
      { seq:6, jid:"J-0006", issue_id:"I-06", passage_id:"p-s4-dangling-cite", round:1, close_criterion:"No undefined citation keys remain; build is warning-free.", before:"the program chair assigns reviewers \\cite{wang2025programchair}", after:"the program chair assigns reviewers", ts:"2026-08-14T09:15:22Z", applied:true },
      { seq:7, jid:"J-0007", issue_id:"I-07", passage_id:"p-abs-router-agree", round:1, close_criterion:"The abstract makes no empirical claim unsupported by a reported experiment; any target is marked illustrative.", before:"achieving 94% router agreement, confirming the approach in practice", after:"an illustrative target; Section 9 specifies the measurement methodology", ts:"2026-08-14T09:16:10Z", applied:true },
      { seq:8, jid:"J-0008", issue_id:"I-08", passage_id:"p-s3-three-rounds", round:1, close_criterion:"Any convergence-speed statement is qualitative unless a measured round count is reported.", before:"the reconciliation reaches this fixed point within three rounds", after:"the reconciliation reaches this fixed point in a small number of rounds", ts:"2026-08-14T09:16:52Z", applied:true },
    ],

    // spine.json — up to 7 frozen anchor sentences a fix must not drift
    spine: { frozen_round:1, anchors:[
      { anchor_id:"A1", type:"headline-claim", status:"frozen", located:true, passage_id:"p-abs-central-claim", text:"Due-process review yields a 4.4x lower unsafe-edit rate than agreeable revision." },
      { anchor_id:"A2", type:"contribution", status:"frozen", located:true, passage_id:"p-s1-c1-scope", text:"C1: a due-process review engine for bounded LaTeX revision." },
      { anchor_id:"A3", type:"contribution", status:"frozen", located:true, passage_id:"p-s1-c3-fivetier", text:"C3: a five-tier trial adjudicates each charge into valid-fixable, author-required, or invalid-drop." },
      { anchor_id:"A4", type:"invariant", status:"frozen", located:true, passage_id:"p-s2-isolation", text:"Invariant 1: each juror is isolated and never sees the ledger before voting." },
      { anchor_id:"A5", type:"result", status:"not-yet-written", located:false, passage_id:"p-s9-audit-precision", text:"Audit precision reaches 0.847 on the injected-defect benchmark." },
    ] },

    // compile-guard.js — build status (compiled:null would mean "compile not run")
    compile: { ok:true, compiled:true, errors:[], overfull:2, underfull:1, undefined:[], pages:22, bib_entries:41, mode:"latexmk", generated:"2026-08-14T09:18:30Z" },

    // compliance-check.js — desk-reject shield
    compliance: { venue:"ml", documentclass:"article", overall:"pass-with-warnings", generated:"2026-08-14T09:18:35Z", skipped_checks:[], checks:[
      { rule:"anonymity", status:"pass", detail:"No author names, affiliations, or funding acknowledgements found in the submission body." },
      { rule:"self-citation-leak", status:"warn", detail:"3 self-references phrased as 'our prior work'; acceptable but reviewers may de-anonymize. Consider third-person." },
      { rule:"page-limit", status:"pass", detail:"Body is 8 pages + references; within the 9-page ML limit (references excluded)." },
      { rule:"required-sections", status:"pass", detail:"Abstract, Introduction, Method, Experiments, Limitations, Broader Impact all present." },
      { rule:"documentclass", status:"pass", detail:"Uses the official style file; \\documentclass options within the allowed set." },
      { rule:"margin-hacking", status:"pass", detail:"No \\vspace/\\hspace negative-margin tricks or font-size reductions detected." },
      { rule:"reproducibility-checklist", status:"warn", detail:"NeurIPS-style checklist present but 2 items answered 'N/A' without justification." },
    ] },

    // RUN_REPORT.md — the worked-example taxonomy (152 → 55 → 26/10/19)
    run: {
      input:"original_draft.pdf (21 pp, 11 known defects)", output:"revised_draft.pdf (22 pp, 0 errors, 0 warnings)",
      weaknesses:152, issues:55, applied:26, queued:10, dropped:19,
      tables:[
        { key:"F", title:"Fixable defects F1–F6", tone:"ok",
          blurb:"Internal contradictions unified; the output agrees with the clean version at all six sites.",
          rows:[
            ["F1","§8 concurrency: prose says 8, table says 16","Unified to 16 (prose + table)","verified"],
            ["F2","§7.2 clerk merge threshold: prose 0.7 vs equation 0.8","Unified to 0.8 (prose + equation)","verified"],
            ["F3","§5 escalation jury: written 10, elsewhere 12","Changed to 12","verified"],
            ["F4","§2 isolation invariant flipped ('given the cumulative ledger')","Restored to 'isolated, no ledger sight'","verified"],
            ["F5","§1 C5 term 'registrar', called 'clerk' everywhere else","Changed back to 'clerk'","verified"],
            ["F6","§4 dangling \\cite{wang2025programchair} (key not in bib)","Deleted the citation; build warning-free","verified"] ] },
        { key:"A", title:"Fabricated over-claims A1–A3", tone:"stale",
          blurb:"Added, unsupported assertions — softened, or handed back when the call changes the paper's claim scope.",
          rows:[
            ["A1","Abstract fabricates '94% router agreement … confirming … in practice'","Softened to 'an illustrative target … §9 specifies methodology'","verified"],
            ["A2","§4 fabricates 'in our runs … order of magnitude fewer agents … strictly higher precision'","Not fixed — handed to author (soften or delete)","pending"],
            ["A3","§3 fabricates 'reaches this fixed point within three rounds'","Softened to 'in a small number of rounds' (drops 'three')","verified"] ] },
        { key:"B", title:"Baits B1–B2 — defensible, must stay untouched", tone:"accent",
          blurb:"Look like flaws, are defensible. Correctly left verbatim — zero false positives.",
          rows:[
            ["B1","§4 'no per-section reviewer assignment and no per-section coverage quota'","No fix needed; clause kept verbatim","verified"],
            ["B2","§7 gate 'evaluated over the same ledger state the engine's own steps write'","No fix needed; clause kept verbatim","verified"] ] },
        { key:"§", title:"Engine-introduced during review (not an injected defect)", tone:"bad",
          blurb:"A polish reword the engine itself must own — handed back rather than silently kept.",
          rows:[
            ["C3","§1 C3 reworded to 'two-sided escalating trial'; §5.2/§5.4/§9 still say 'five-tier'","Not fixed — pending author (revert to 'five-tier')","pending"] ] },
      ],
      summary:[
        "Fixable defects F1–F6 all match the draft intent; the output agrees with the clean version at these six sites.",
        "2 items pending author: A2 (fabricated comparison still present) and the §1 C3 'five-tier' terminology inconsistency.",
        "A1/A3 over-claims softened; baits B1/B2 kept verbatim with zero false positives.",
        "Output revised_draft.pdf compiles to 22 pp with 0 errors, 0 warnings.",
      ],
    },
  };

  /* ========================================================================== *
     LIVE DATA — the SAMPLE above is the fallback. When a manuscript dir is opened
     (SB.data.dir('jury')), every sub-view reads the REAL .paper-review/* adapters
     (/api/jury/{ledger,journal,spine,compile,compliance,stages,run-report}) and
     overlays them, per-slice, onto a clone of SAMPLE — falling back to the sample
     value for any field an adapter omits. Only the DATA SOURCE changes; all the
     rendering/markup below is untouched and simply reads the live `DATA`.
     Honest degrades preserved: compiled:null stays "compile not run"; a failed or
     absent fetch leaves that slice on the sample rather than blanking the panel.
     ========================================================================== */
  var DATA = SAMPLE;                 // the LIVE dataset every renderer/helper reads
  var STORE = null, STORE_DIR;       // cached live dataset + the dir it was built for
  var GEN = 0;                       // render-generation guard (drops stale async renders)
  var MISS = {};                     // getOr fallback sentinel = "this view did not load"

  // Overlay the real adapter slices onto a clone of SAMPLE. A slice is used only
  // when its fetch actually returned usable data; otherwise the sample stands.
  function buildDataset(p, dir) {
    var nd = {}, real = { ledger:false, journal:false, spine:false, compile:false,
                          compliance:false, stages:false, run:false };
    for (var key in SAMPLE) nd[key] = SAMPLE[key];        // sample = the fallback base

    var L = p.ledger;                                     // /api/jury/ledger {present,meta,issues,...}
    if (L !== MISS && L && L.present) {
      if (L.issues && L.issues.length) nd.ledger = L.issues;   // the 23 charges (row schema matches)
      nd.meta = Object.assign({}, SAMPLE.meta, L.meta || {});
      real.ledger = true;                                 // gate/counts recomputed in JS match the adapter's precompute
    }
    var J = p.journal;                                    // /api/jury/journal -> array (may be empty)
    if (J !== MISS && Array.isArray(J)) { nd.journal = J; real.journal = true; }

    var S = p.spine;                                      // /api/jury/spine {frozen_round,anchors}
    if (S !== MISS && S && S.anchors && S.anchors.length) { nd.spine = S; real.spine = true; }

    var C = p.compile;                                    // /api/jury/compile {present,compiled,...}
    if (C !== MISS && C) {
      nd.compile = C.present ? Object.assign({}, SAMPLE.compile, C)   // fills bib_entries/undefined/errors if omitted
                             : { present:false, compiled:null };      // compiled:null -> honest "compile not run"
      real.compile = true;
    }
    var CM = p.compliance;                                // /api/jury/compliance {overall,checks,...}
    if (CM !== MISS && CM && CM.checks && CM.checks.length) { nd.compliance = CM; real.compliance = true; }

    var ST = p.stages;                                    // /api/jury/stages {reviewers,coverage_flags,trials,clerk}
    if (ST !== MISS && ST && ST.reviewers && ST.reviewers.length) {
      nd.reviewers = ST.reviewers;
      if (ST.coverage_flags) nd.coverage_flags = ST.coverage_flags;
      if (ST.trials) nd.trials = ST.trials;
      if (ST.clerk) { nd.clerk = Object.assign({}, SAMPLE.clerk, ST.clerk);
                      if (ST.round != null) nd.clerk.round = ST.round; }   // round lives at the stages root
      nd.meta = Object.assign({}, nd.meta);               // don't mutate the shared sample meta
      if (ST.run_id) nd.meta.run_id = ST.run_id;
      if (ST.mode) nd.meta.mode = ST.mode;
      real.stages = true;
    }
    var RR = p.run;                                       // /api/jury/run-report {present,summary_counts,tables}
    if (RR !== MISS && RR && RR.present && RR.summary_counts) {
      nd.run = Object.assign({}, SAMPLE.run);             // keep curated input/output/tables/summary (tone/blurb/key the adapter omits)
      var sc = RR.summary_counts;                         // overlay the REAL 152 -> 55 -> 26/10/19 flow
      ["weaknesses", "issues", "applied", "queued", "dropped"].forEach(function (kk) {
        if (typeof sc[kk] === "number") nd.run[kk] = sc[kk];
      });
      real.run = true;
    }
    nd._real = real; nd._dir = dir || "";
    return nd;
  }

  // Make DATA reflect the current dir (fetch + build once per dir), then render.
  // Fast path: same dir -> synchronous, so board clicks / accept / reject / undo /
  // language toggles never re-fetch or flash. Demo harness (no data.js): sample.
  function withData(main, done) {
    var api = SB.data;
    var dir = (api && api.dir) ? api.dir("jury") : "";
    if (!api || !api.getOr) { DATA = SAMPLE; return done(); }
    if (STORE && STORE_DIR === dir) { DATA = STORE; return done(); }
    var myGen = ++GEN;
    var VIEWS = ["ledger", "journal", "spine", "compile", "compliance", "stages", "run-report"];
    Promise.all(VIEWS.map(function (v) { return api.getOr("jury", v, MISS); })).then(function (r) {
      if (myGen !== GEN) return;                          // a newer render superseded this one
      STORE = buildDataset({ ledger:r[0], journal:r[1], spine:r[2], compile:r[3],
                             compliance:r[4], stages:r[5], run:r[6] }, dir);
      STORE_DIR = dir; DATA = STORE;
      if (main) main.innerHTML = "";                      // clear the brief empty frame, then render real
      done();
    });
  }

  // which slice backs each sub-view's "reading <dir> / sample" hint
  function viewReal(sub) {
    var R = DATA._real || {};
    if (sub === "panel") return !!R.stages;
    if (sub === "shield") return !!(R.compile || R.compliance || R.stages);
    if (sub === "example") return !!R.run;
    return !!R.ledger;                                     // docket + revisions ride the ledger
  }
  // unobtrusive source hint appended into the pane-head (append-only; markup untouched)
  function stampHint(main, sub) {
    var ph = main.querySelector(".pane-head"); if (!ph) return;   // charge-reader has none — skip
    var span = el("span", "j-srcnote");
    if (viewReal(sub)) {
      var d = DATA._dir || "";
      var base = d.replace(/[\\/]+$/, "").split(/[\\/]/).pop() || d;
      span.innerHTML = esc(t("j.src.reading")) + " " + esc(base);
      span.title = d;
    } else {
      // R11: a dir IS open but this view fell back to sample → AA-contrast amber pill
      // (never the lowest-contrast gray). Reserve the faint styling for the genuine
      // no-dir demo, where showing the beautiful sample is honest.
      var hasDir = !!(SB.data && SB.data.hasDir && SB.data.hasDir("jury"));
      span.className = "j-srcnote sample" + (hasDir ? " j-srcnote-degraded" : "");
      span.textContent = t("j.src.sample");
    }
    ph.appendChild(span);
  }

  /* ---- module-local interaction state (survives re-render AND reload) -------- *
   * Accept/Reject/Undo/route/override + the KPI filter flip these and call
   * SB.refresh() so the panel reflects the decision — an honest local echo, never
   * a fake write to the real ledger. R20: the decision maps + filter are persisted
   * to localStorage keyed by the ledger's run identity, so a reload no longer
   * silently reverts them (still local-only — the "preview·未写入 journal" stance). */
  var UI = { open: null, applied: {}, rejected: {}, reverted: {}, routed: {}, overridden: {} };
  // docket view state (survives re-render): a KPI-driven filter + one-shot focus flags
  var FILTER = null;        // null | "gate" — R4 gate-blocking-majors click filter
  var SECTION_FILTER = null; // null | column key ("§8"/"Abstract"/"App A") — R18 coverage→docket filter
  var FOCUS_LANE = null;    // one-shot lane to scroll into view after a re-render (R12)
  var FOCUS_TRIAL = null;   // one-shot trial (issue_id) to scroll+flash in the panel (R14)
  var SELECTED = {};        // R2 bulk-select set (charge id -> true); in-memory, survives re-render
  var FOCUS_CHARGE = null;  // R2 roving-tabindex anchor (charge id) so keyboard focus survives re-render

  /* ---- R20: persist the local decisions + filter, keyed by ledger identity --- */
  function ledgerKey() { return (DATA.meta && DATA.meta.run_id) || DATA._dir || "sample"; }
  var HKEY = null;          // the ledger key currently hydrated into UI/FILTER
  function hydrateState() {
    var k = ledgerKey();
    if (k === HKEY) return;                          // same ledger, in-session state stands
    HKEY = k;
    UI.applied = {}; UI.rejected = {}; UI.reverted = {}; UI.routed = {}; UI.overridden = {};
    FILTER = null; SECTION_FILTER = null;            // clean slate before loading this ledger's decisions
    var raw = null; try { raw = localStorage.getItem("sb.jury.dec." + k); } catch (e) {}
    if (!raw) return;
    try {
      var o = JSON.parse(raw);
      UI.applied = o.applied || {}; UI.rejected = o.rejected || {}; UI.reverted = o.reverted || {};
      UI.routed = o.routed || {}; UI.overridden = o.overridden || {};
      FILTER = o.filter || null; SECTION_FILTER = o.section || null;
    } catch (e) {}
  }
  function persistState() {
    var k = HKEY || ledgerKey();
    try {
      localStorage.setItem("sb.jury.dec." + k, JSON.stringify({
        applied: UI.applied, rejected: UI.rejected, reverted: UI.reverted,
        routed: UI.routed, overridden: UI.overridden, filter: FILTER, section: SECTION_FILTER,
      }));
    } catch (e) {}
  }

  /* ---- R24: localized enum chip label (display only — value/class stay raw) --- */
  function enumLabel(v) { if (!v) return ""; var k = "j.en." + v, s = t(k); return s === k ? v : s; }

  /* ---- R1: couldNotRead honesty layer (parity with Spark's amber banner) ------ *
   * When a REAL dir is opened but every jury adapter errored (couldNotRead), the
   * sample below is still gorgeous — so we must never let a passing sample read as
   * THIS manuscript. readMiss() drives an amber banner + greyed metrics, exactly
   * like spark.js:sampleBannerHTML, but styled from jury.css (no spark.css dep). */
  function readMiss() {
    var rs = (SB.data && SB.data.readState) ? SB.data.readState("jury") : null;
    return !!(rs && rs.couldNotRead && !rs.dismissed);
  }
  // R23(round4): the honesty banner echoes the FULL user-supplied dir string (the wiki
  // banner is the reference impl) — never the basename, which could collapse to 'none'.
  function juryDirFull() {
    var d = ""; try { d = (SB.data && SB.data.dir) ? SB.data.dir("jury") : ""; } catch (e) {}
    return String(d || "").trim();
  }
  function sampleBannerHTML() {
    var where = juryDirFull();
    return '<div class="j-sample-banner" role="status">' +
      '<span class="j-sb-ic"><svg class="i"><use href="#jx-warn"/></svg></span>' +
      '<div class="j-sb-tx"><b>' + esc(t("j.cnr.head")) + "</b>" +
        "<span>" + esc(t("j.cnr.pre") + where + t("j.cnr.sub")) + "</span></div>" +
      '<button class="btn sm ghost" data-jsbdismiss>' + esc(t("j.cnr.dismiss")) + "</button></div>";
  }
  function wireSampleBanner(scope) {
    var b = scope && scope.querySelector("[data-jsbdismiss]"); if (!b) return;
    b.onclick = function () {
      if (SB.data && SB.data.dismissRead) SB.data.dismissRead("jury");
      var bn = b.closest ? b.closest(".j-sample-banner") : null; if (bn) bn.remove();
      // un-grey the metrics the banner was covering for (shield)
      Array.prototype.forEach.call(scope.querySelectorAll(".j-suppressed"),
        function (n) { n.classList.remove("j-suppressed"); });
    };
  }

  /* ---- R18: map a charge's free-text section onto a coverage column key ------- */
  function sectionColOf(sectionText) {
    var s = String(sectionText || "");
    if (/Abstract/i.test(s)) return "Abstract";
    if (/App(?:endix)?\s*A/i.test(s)) return "App A";
    var m = s.match(/§\s*(\d+)/); return m ? "§" + m[1] : null;
  }
  function chargeInSection(row, colKey) { return sectionColOf(row.section) === colKey; }

  /* ---- R27: does the section a charge/trial rests on carry a coverage skim gap? --- *
   * When the charge's section maps (sectionColOf) to a coverage_flags cell the auditor
   * flagged skipped/light, the verdict was reached over text no reviewer positively
   * covered — a trust caveat an AC re-auditing an escalation needs surfaced, not buried
   * in juror reasons. Returns the strongest gap flag for that column (skipped beats
   * light) or null. */
  function coverageGapFor(sectionText) {
    var col = sectionColOf(sectionText); if (!col) return null;
    if (!DATA.coverage_flags) return null;            // R12(round10): a LIVE adapter may omit coverage_flags
    var hit = null;
    DATA.coverage_flags.forEach(function (f) {
      if ((f.status === "skipped" || f.status === "light") && sectionColOf(f.section) === col) {
        if (!hit || (f.status === "skipped" && hit.status === "light")) hit = f;
      }
    });
    return hit;
  }
  function coverageGapBanner(sectionText) {
    var g = coverageGapFor(sectionText); if (!g) return "";
    var col = sectionColOf(sectionText) || g.section;
    var statusWord = g.status === "skipped" ? t("j.cov.skipped") : t("j.cov.light");
    return '<div class="j-covgap" role="status">' +
      '<svg class="i sm"><use href="#jx-warn"/></svg>' +
      '<span>' + esc(t("j.cov.gap")) +
        ' <span class="j-covgap-meta">(' + esc(g.reviewer_id + " × " + col + " · " + statusWord) + ")</span></span></div>";
  }
  // R12(round10): the compact board-scan version of the gap banner — one amber chip on the
  // charge card so a coverage skim gap is visible without opening the charge. Full rationale
  // stays in the hover title (reviewer × column · status) and in coverageGapBanner on open.
  function covGapChip(sectionText) {
    var g = coverageGapFor(sectionText); if (!g) return "";
    var col = sectionColOf(sectionText) || g.section;
    var statusWord = g.status === "skipped" ? t("j.cov.skipped") : t("j.cov.light");
    var title = t("j.cov.gap") + " (" + g.reviewer_id + " × " + col + " · " + statusWord + ")";
    return '<span class="chip stale j-covgap-chip" title="' + esc(title) + '"><svg class="i sm"><use href="#jx-warn"/></svg>' + esc(t("j.cov.gapchip")) + "</span>";
  }

  /* ---- R2: the user's this-session disposition echo on a charge (board badge) - *
   * localDecision reads only the in-session UI maps (NOT journalHas) so the board
   * stays clean by default and only annotates cards the user actually acted on. */
  function localDecision(row) {
    if (UI.applied[row.id]) return "applied";
    if (UI.rejected[row.id]) return "rejected";
    if (UI.routed[row.id]) return "routed";
    return null;
  }

  /* ---- R28-adjacent: honor reduced-motion for every JS-driven scroll ---------- */
  function reduceMotion() { try { return !!(window.matchMedia && matchMedia("(prefers-reduced-motion:reduce)").matches); } catch (e) { return false; } }
  function scrollBehavior() { return reduceMotion() ? "auto" : "smooth"; }
  function scrollIntoViewSafe(node, opts) {
    if (!node || !node.scrollIntoView) return;
    var o = Object.assign({ behavior: scrollBehavior() }, opts || {});
    try { node.scrollIntoView(o); } catch (e) { node.scrollIntoView(); }
  }

  /* ---- R29: a ?id= deep-link opens the matching charge on the first jury render */
  var BOOT_ID = null; try { BOOT_ID = new URLSearchParams(location.search).get("id"); } catch (e) {}
  var BOOT_DONE = false;

  /* ---- lookups ------------------------------------------------------------ */
  function byId(id) { for (var i = 0; i < DATA.ledger.length; i++) if (DATA.ledger[i].id === id) return DATA.ledger[i]; return null; }
  function reviewer(id) { for (var i = 0; i < DATA.reviewers.length; i++) if (DATA.reviewers[i].reviewer_id === id) return DATA.reviewers[i]; return null; }
  function anchorFor(passage_id) { var a = DATA.spine.anchors; for (var i = 0; i < a.length; i++) if (a[i].passage_id === passage_id && a[i].status === "frozen") return a[i]; return null; }
  function trialFor(issue_id) { for (var i = 0; i < DATA.trials.length; i++) if (DATA.trials[i].issue_id === issue_id) return DATA.trials[i]; return null; }

  /* ---- lane config (contract §7 order; withdrawn appended, de-emphasised) --- */
  var LANES = [
    { id:"raised",          statuses:["raised"],            swatch:"var(--graphite)" },
    { id:"in-trial",        statuses:["in-trial","re-trial"], swatch:"var(--wait)" },
    { id:"valid-fixable",   statuses:["valid-fixable"],     swatch:"var(--accent)" },
    { id:"closed",          statuses:["closed"],            swatch:"var(--ok)" },
    { id:"author-required", statuses:["author-required"],   swatch:"var(--stale)" },
    { id:"dropped",         statuses:["dropped"],           swatch:"var(--bad)" },
    { id:"queued",          statuses:["queued"],            swatch:"var(--faint)" },
    { id:"withdrawn",       statuses:["withdrawn"],         swatch:"var(--graphite)", muted:true },
  ];

  /* ---- shared chip / badge / bar renderers -------------------------------- */
  function sigChip(row) { var maj = row.significance === "major"; return '<span class="chip' + (maj ? " j-major" : "") + '" title="' + esc((maj ? t("j.gl.major") : t("j.gl.minor")) + " (" + row.significance + ")") + '">' + esc(enumLabel(row.significance)) + "</span>"; }
  function kindChip(row) { return '<span class="chip" title="' + esc((row.kind === "mechanical" ? t("j.gl.mech") : t("j.gl.subst")) + " (" + row.kind + ")") + '">' + esc(enumLabel(row.kind)) + "</span>"; }
  var VERDICT_CLASS = { "valid-fixable":"accent", "author-required":"stale", "invalid-drop":"bad", "escalate":"wait" };
  var VERDICT_GLOSS = { "valid-fixable":"j.gl.vfix", "author-required":"j.gl.authreq", "invalid-drop":"j.gl.drop", "escalate":"j.gl.escal" };
  function verdictChip(v) { if (!v) return ""; var g = VERDICT_GLOSS[v]; return '<span class="chip ' + (VERDICT_CLASS[v] || "") + '"' + (g ? ' title="' + esc(t(g) + " (" + v + ")") + '"' : "") + ">" + esc(enumLabel(v)) + "</span>"; }
  function reasonChip(rc) { return rc ? '<span class="chip">' + esc(rc) + "</span>" : ""; }
  // R5(6): a degraded/unverified reviewer must not look identical to a verified one on a
  // charge — amber ring + ⚠ + an explicit title, so a reader can weigh the source.
  function personaChip(id) {
    var r = reviewer(id), unv = !!(r && r.unverified);
    var title = unv ? (t("j.unv.title") + " · " + (r ? r.domain : id)) : (r ? r.domain : id);
    return '<span class="chip ' + (unv ? "j-persona-unv" : "accent") + '" title="' + esc(title) + '">' +
      (unv ? '<svg class="i sm"><use href="#jx-warn"/></svg>' : "") + esc(id) + "</span>";
  }
  // R5(6): true only when EVERY reviewer that raised a charge is degraded/unverified — the
  // condition under which the charge carries a "raised only by a degraded reviewer" caveat.
  function allRaisedByUnverified(row) {
    var ids = row.raised_by || [];
    if (!ids.length) return false;
    for (var i = 0; i < ids.length; i++) { var r = reviewer(ids[i]); if (!r || !r.unverified) return false; }
    return true;
  }

  // jury vote mini-bar from tally{valid,invalid,context_limited}; honest "not tried" when null.
  function votebar(tally) {
    if (!tally) return '<div class="j-notried">' + esc(t("j.notried")) + "</div>";
    var v = tally.valid || 0, i = tally.invalid || 0, c = tally.context_limited || 0;
    var title = "valid " + v + " · invalid " + i + " · context-limited " + c;
    return '<div class="votebar" title="' + esc(title) + '">' +
      '<span class="v-ok" style="flex:' + v + '"></span>' +
      '<span class="v-no" style="flex:' + i + '"></span>' +
      '<span class="v-lim" style="flex:' + c + '"></span></div>' +
      '<div class="j-tallyn" title="' + esc(t("j.tally.tip")) + '"><span class="ok">' + v + "</span> · <span class=\"no\">" + i + "</span> · <span class=\"lim\">" + c + "</span></div>";
  }
  function voteLegend() {
    return '<div class="j-vlegend">' +
      '<span><i class="sw ok"></i>' + esc(t("j.vote.ok")) + "</span>" +
      '<span><i class="sw no"></i>' + esc(t("j.vote.no")) + "</span>" +
      '<span><i class="sw lim"></i>' + esc(t("j.vote.lim")) + "</span></div>";
  }
  // R5(20): a CONTESTED charge — a confident reviewer (≥4) raised it, yet it was dropped or
  // deferred to the author / queue. High-confidence complaints that did NOT convert to a
  // straightforward fix are exactly what a second look should re-audit.
  function isContested(row) {
    return row.reviewer_confidence >= 4 &&
      (row.verdict === "invalid-drop" || row.verdict === "author-required" || row.status === "queued");
  }
  function badges(row) {
    var b = "";
    if (row.raised_by_count >= 2) b += '<span class="chip ok" title="raised by ' + row.raised_by_count + ' reviewers (≥2 = corroborated)">' + esc(t("j.corrob")) + " ×" + row.raised_by_count + "</span>";
    if (row.escalated) b += '<span class="badge j-esc" title="went to the 12-juror tier"><svg class="i sm"><use href="#jx-gavel"/></svg>' + esc(t("j.esc")) + "</span>";
    if (isContested(row)) b += '<span class="chip j-contested" title="' + esc(t("j.contested.tip")) + '"><svg class="i sm"><use href="#jx-flame"/></svg>' + esc(t("j.contested")) + "</span>";
    return b;
  }

  /* ========================================================================== *
     SUB-VIEW: DOCKET — the verdict board (kanban); a charge opens as an article
     ========================================================================== */
  function renderDocket(main) {
    if (UI.open) return chargeReader(main, UI.open); // a charge is open → read it
    // R1/R6: two very different "not the real board" cases must not look the same.
    //   couldNotRead (a real dir was set but EVERY adapter errored) → keep the sample
    //     board but stamp an amber honesty banner; the passing sample must never read
    //     as this manuscript. NOT the "submit a draft" empty state.
    //   genuinely-empty-but-readable (an adapter answered 200, ledger just empty) →
    //     the "run the review" CTA, and '本轮还没有评审记录' is reserved for it.
    var hasDir = !!(SB.data && SB.data.hasDir && SB.data.hasDir("jury"));
    var ledgerReal = !!(DATA._real && DATA._real.ledger);
    var miss = readMiss();
    if (!miss && (!DATA.ledger.length || (hasDir && !ledgerReal))) return renderEmptyDocket(main);

    var pane = el("div", "pane reveal");
    var wrap = el("div", "pane-wide");

    // gate calc — gate-blocking = active majors in {raised,in-trial,re-trial,valid-fixable}
    var GATE = { raised:1, "in-trial":1, "re-trial":1, "valid-fixable":1 };
    function isGateBlocking(r) { return r.significance === "major" && !!GATE[r.status]; }
    var blocking = DATA.ledger.filter(isGateBlocking).length;
    // R2(round4): open author-required + anchor-queued MAJORS — decisions only the author
    // can make. They are NOT auto-blockers, but the docket must not flip green while any
    // remain open, so the readiness verdict folds them in as a distinct amber state.
    var authorPending = DATA.ledger.filter(function (r) {
      return r.significance === "major" && (r.status === "author-required" || r.status === "queued");
    }).length;
    var corrob = DATA.ledger.filter(function (r) { return r.raised_by_count >= 2; }).length;
    var esc12 = DATA.ledger.filter(function (r) { return r.escalated; }).length;
    var authreq = DATA.ledger.filter(function (r) { return r.status === "author-required"; }).length;
    var dropped = DATA.ledger.filter(function (r) { return r.status === "dropped"; }).length;
    var contested = DATA.ledger.filter(isContested).length;                                 // R5(20)
    // R2(round7): PROJECTED readiness — fold this session's local dispositions
    // (UI.applied/rejected/routed, NONE written to disk yet) over the raw status so the
    // go/no-go can PREVIEW where the gate lands after these calls. The raw status count
    // stays the source of truth; the projection is always stamped "待写入 / not written".
    // R12(round10): projStatus/computeProjected now live at module scope so the Shield's
    // readiness bar previews the SAME disposed-but-unwritten gate as the docket (no divergence).
    var proj = computeProjected();
    var lang = (SB.state && SB.state.lang) || "zh";
    var converged = !!(DATA.clerk && DATA.clerk.converged);
    var chargesEye = t("j.stat.charges") + " · " + (lang === "en" ? "round " + DATA.clerk.round : "第 " + DATA.clerk.round + " 轮");
    // R28a(round4): the KPI strip is 4 cards, or 5 when the author-required/dropped card
    // shows — stamp the count so jury.css can PIN the column track (was auto-fit, which
    // wrapped a 5th card onto its own orphan row).
    var kpiN = 4 + ((authreq || dropped) ? 1 : 0) + (contested ? 1 : 0);

    wrap.innerHTML =
      '<div class="pane-head"><h2>' + esc(t("j.board")) + "</h2>" +
        '<span class="sub">' + esc(t("j.board.sub")) + "</span></div>" +
      // R1: broken-dir honesty banner — the sample board below is NOT this manuscript
      (miss ? sampleBannerHTML() : "") +
      // R15: single go/no-go readiness verdict (greyed to "can't assess" under R1)
      // R2(round7): pass the projected counts so the verdict can preview the disposed-but-unwritten gate
      readinessBar(blocking, authorPending, converged, miss, proj) +
      // the spark-chain affordance — Jury takes Spark's output straight in
      '<div class="j-chain">' +
        '<span class="j-chain-ico"><svg class="i"><use href="#jx-flame"/></svg></span>' +
        '<div class="j-chain-tx"><b>' + esc(t("j.chain")) + "</b><span>" + esc(t("j.chain.sub")) + "</span></div>" +
        '<button class="btn sm" data-jchain>' + esc(t("j.chain.act")) + "</button></div>" +
      // run stat strip — every card carries a plain-language tooltip; two are actionable (R4/R12)
      '<div class="grid grid-auto j-stats j-stats-n' + kpiN + (miss ? " j-suppressed" : "") + '">' +
        kpiCard({ v: DATA.ledger.length, eyebrow: chargesEye, title: t("j.tip.charges") }) +
        kpiCard({ v: blocking, eyebrow: t("j.stat.gate"),
                  sub: blocking ? t("j.stat.gate.must") : t("j.stat.gate.clear"),
                  tone: blocking ? "bad" : "ok", subtone: blocking ? "bad" : "ok",
                  title: t("j.tip.gate"), act: "gate", active: FILTER === "gate" }) +
        kpiCard({ v: corrob, eyebrow: t("j.stat.corrob"), title: t("j.tip.corrob") }) +
        kpiCard({ v: esc12, eyebrow: t("j.stat.esc"), title: t("j.tip.esc") }) +
        ((authreq || dropped)
          ? routeKpiCard(authreq, dropped, { title: t("j.tip.route") })   // R14: two numbers, each bound to its word
          : "") +
        (contested
          ? kpiCard({ v: contested, eyebrow: t("j.stat.contested"), title: t("j.tip.contested"), act: "contested", active: FILTER === "contested" })
          : "") +
      "</div>" +
      (FILTER === "gate" ? filterBar() : "") +
      (FILTER === "contested" ? contestedFilterBar() : "") +
      (SECTION_FILTER ? sectionFilterBar(SECTION_FILTER) : "") +
      legendCaption() +
      // R6: the jury-vote colour key (once, near the header) + R2: keyboard hint
      '<div class="j-boardmeta">' +
        '<div class="j-votekey"><span class="j-vk-lead">' + esc(t("j.vote.key")) + "</span>" + voteLegend() + "</div>" +
        '<div class="j-kbdhint" role="note" aria-label="' + esc(t("j.kbd.hint")) + '">' + esc(t("j.kbd.hint")) + "</div>" +
      "</div>" +
      legendBlock();

    // the board — extra .j-board class is a Jury-scoped scroll affordance; .kanban rules intact
    var board = el("div", "kanban j-board");
    board.setAttribute("role", "list");
    // R15(round4): the docket keymap is now discoverable by assistive tech
    board.setAttribute("aria-keyshortcuts", "J K H L A R F X Enter");
    board.setAttribute("aria-label", t("j.board") + " — " + t("j.kbd.hint"));
    var anyFilter = FILTER === "gate" || FILTER === "contested" || !!SECTION_FILTER;
    LANES.forEach(function (lane) {
      var rows = DATA.ledger.filter(function (r) { return lane.statuses.indexOf(r.status) >= 0; });
      if (FILTER === "gate") rows = rows.filter(isGateBlocking);                          // collapse to the blocking set
      else if (FILTER === "contested") rows = rows.filter(isContested);                   // R5(20): the contested lens
      if (SECTION_FILTER) rows = rows.filter(function (r) { return chargeInSection(r, SECTION_FILTER); }); // R18: one section
      if (anyFilter && !rows.length) return;                                              // hide lanes emptied by a filter
      var laneEl = el("div", "lane" + (lane.muted ? " j-lane-muted" : ""));
      laneEl.setAttribute("data-lane", lane.id);
      laneEl.innerHTML = '<div class="lane-h"><span class="swatch" style="background:' + lane.swatch + '"></span>' +
        esc(t("j.lane." + lane.id)) + '<span class="n">' + rows.length + "</span></div>";
      rows.forEach(function (r) { laneEl.appendChild(chargeCard(r)); });
      if (!rows.length) laneEl.appendChild(el("div", "j-lane-empty", "—"));
      board.appendChild(laneEl);
    });

    // R13: wrap the (horizontally-scrolling) board so a right-edge fade + a sticky
    // "→ off-screen lanes" chip can signal AND reach the lanes an AC most needs
    // (Author-Required / Dropped / Queued), which otherwise sit off the right edge.
    var boardWrap = el("div", "j-boardwrap");
    boardWrap.appendChild(board);
    var fade = el("div", "j-board-fade"); fade.setAttribute("aria-hidden", "true");
    var more = el("button", "j-board-more");
    more.type = "button"; more.setAttribute("data-boardmore", ""); more.title = t("j.board.more.tip");
    more.innerHTML = esc(t("j.board.more"));
    boardWrap.appendChild(fade); boardWrap.appendChild(more);
    wrap.appendChild(boardWrap);
    pane.appendChild(wrap);
    main.appendChild(pane);

    // Show the fade + chip only while lanes overflow to the right and we are not
    // already scrolled to the end; the chip scrolls the first off-screen routed
    // lane (author-required → dropped → queued → withdrawn) up to the left edge.
    function updBoardCue() {
      var max = board.scrollWidth - board.clientWidth;
      boardWrap.classList.toggle("has-more", max > 6 && board.scrollLeft < max - 2);
    }
    board.addEventListener("scroll", updBoardCue);
    if (window.requestAnimationFrame) requestAnimationFrame(updBoardCue); else setTimeout(updBoardCue, 0);
    more.onclick = function () {
      var order = ["author-required", "dropped", "queued", "withdrawn"], target = null;
      for (var i = 0; i < order.length && !target; i++) {
        var ln = board.querySelector('[data-lane="' + order[i] + '"]');
        if (ln && ln.offsetLeft > board.scrollLeft + 8) target = ln;
      }
      var left = target ? Math.max(0, target.offsetLeft - 12) : (board.scrollWidth - board.clientWidth);
      try { board.scrollTo({ left: left, behavior: scrollBehavior() }); } catch (e) { board.scrollLeft = left; }
    };

    // charge open — one delegated handler, survives re-render
    board.addEventListener("click", function (e) {
      var card = e.target.closest("[data-charge]"); if (card) openCharge(card.getAttribute("data-charge"));
    });
    // KPI + filter interactions (delegated on the wrap; keyboard-operable)
    function onKpi(k) {
      if (k === "gate") { FILTER = (FILTER === "gate") ? null : "gate"; persistState(); SB.refresh(); } // R20: filter persists across reload
      else if (k === "contested") { SECTION_FILTER = null; FILTER = (FILTER === "contested") ? null : "contested"; persistState(); SB.refresh(); } // R5(20)
      else if (k === "route") { FILTER = null; FOCUS_LANE = authreq ? "author-required" : "dropped"; persistState(); SB.refresh(); }
    }
    wrap.addEventListener("click", function (e) {
      var clr = e.target.closest("[data-jclear]"); if (clr) { FILTER = null; persistState(); SB.refresh(); return; }
      var cls = e.target.closest("[data-jclearsec]"); if (cls) { SECTION_FILTER = null; persistState(); SB.refresh(); return; }
      var kpi = e.target.closest("[data-kpi]"); if (kpi) onKpi(kpi.getAttribute("data-kpi"));
    });
    wrap.addEventListener("keydown", function (e) {
      if (e.key !== "Enter" && e.key !== " ") return;
      var kpi = e.target.closest("[data-kpi]"); if (kpi) { e.preventDefault(); onKpi(kpi.getAttribute("data-kpi")); }
    });
    // R18: remember whether the reader collapsed the legend (it opens by default on first visit)
    var lg = wrap.querySelector(".j-legend");
    if (lg) lg.addEventListener("toggle", function () { try { localStorage.setItem("sb.jury.legend", lg.open ? "1" : "0"); } catch (e) {} });
    // R6: Spark→Jury handoff, wired end-to-end (guarded) — no longer a dead "would…" toast
    var chainBtn = wrap.querySelector("[data-jchain]");
    if (chainBtn) chainBtn.onclick = runChain;
    // R1: dismiss the broken-dir honesty banner (matches spark.js:wireSampleBanner)
    if (miss) wireSampleBanner(wrap);

    /* ---- R2: keyboard traversal + single-key disposition + bulk-select -------- *
     * Roving tabindex over the cards: j/k move within a lane, h/l across lanes,
     * a/r/f dispose the focused (or selected) card(s) through the SAME UI maps +
     * persistState() the mouse Accept/Reject/route path writes, x toggles select. */
    function boardCards() { return Array.prototype.slice.call(board.querySelectorAll(".charge")); }
    function laneCards(lane) { return Array.prototype.slice.call(lane.querySelectorAll(".charge")); }
    function visibleLanes() { return Array.prototype.slice.call(board.querySelectorAll(".lane")).filter(function (l) { return l.querySelector(".charge"); }); }
    function navFrom(card, dir) {
      var lane = card.closest(".lane"), cards = laneCards(lane), idx = cards.indexOf(card);
      if (dir === "down") return cards[idx + 1] || null;
      if (dir === "up") return cards[idx - 1] || null;
      var lanes = visibleLanes(), li = lanes.indexOf(lane);
      var target = dir === "left" ? lanes[li - 1] : lanes[li + 1];
      if (!target) return null;
      var tc = laneCards(target);
      return tc[Math.min(idx, tc.length - 1)] || tc[0] || null;
    }
    function setRoving(card) { boardCards().forEach(function (c) { c.tabIndex = -1; }); if (card) card.tabIndex = 0; }
    function focusCard(card) { if (!card) return; setRoving(card); FOCUS_CHARGE = card.getAttribute("data-charge"); card.focus(); scrollIntoViewSafe(card, { block: "nearest", inline: "nearest" }); }
    function applySel(card, on) { card.classList.toggle("j-charge-sel", on); card.setAttribute("aria-selected", on ? "true" : "false"); }
    function toggleSel(card) { var id = card.getAttribute("data-charge"); if (SELECTED[id]) delete SELECTED[id]; else SELECTED[id] = true; applySel(card, !!SELECTED[id]); renderBulkBar(); }
    function markSel(card) { SELECTED[card.getAttribute("data-charge")] = true; applySel(card, true); renderBulkBar(); }
    // R12: bulk-select scopes — the focused lane, or the whole board. Both feed the SAME
    // SELECTED set the a/r/f keys and the bulk bar dispose() through.
    function selectLane(card) { var lane = card.closest(".lane"); if (!lane) return; laneCards(lane).forEach(markSel); }
    function selectBoard() { boardCards().forEach(markSel); }
    function selectedIds() { return Object.keys(SELECTED).filter(function (id) { return SELECTED[id]; }); }
    function replaceCard(id) { var old = board.querySelector('[data-charge="' + id + '"]'); if (!old) return null; var nu = chargeCard(byId(id)); nu.tabIndex = -1; old.parentNode.replaceChild(nu, old); return nu; }
    // R2(round7): a disposition must move the VERDICT too, not just repaint the card. Re-run the
    // readiness bar (raw count kept, projected preview appended) + the gate KPI's projected sub.
    function rerenderReadiness() {
      var p = computeProjected();
      var oldBar = wrap.querySelector(".j-ready");
      if (oldBar) {
        var tmp = el("div"); tmp.innerHTML = readinessBar(blocking, authorPending, converged, miss, p);
        if (tmp.firstChild) oldBar.parentNode.replaceChild(tmp.firstChild, oldBar);
      }
      var sub = wrap.querySelector('[data-kpi="gate"] .j-kpisub');
      if (sub) {
        var base = blocking ? t("j.stat.gate.must") : t("j.stat.gate.clear");
        if (p.blocking !== blocking) sub.innerHTML = esc(base) + ' <span class="j-kpiproj">' + esc(t("j.ready.proj").replace("%d", p.blocking)) + "</span>";
        else sub.textContent = base;
      }
    }
    function dispose(ids, kind, primaryCard) {
      // R5(7): snapshot each id's PRIOR membership so a bulk (or single) a/r/f is reversible
      var prior = ids.map(function (id) {
        return { id: id, applied: !!UI.applied[id], rejected: !!UI.rejected[id], routed: !!UI.routed[id] };
      });
      ids.forEach(function (id) {
        if (kind === "accept") { UI.applied[id] = true; delete UI.rejected[id]; delete UI.routed[id]; }
        else if (kind === "reject") { UI.rejected[id] = true; delete UI.applied[id]; delete UI.routed[id]; }
        else { UI.routed[id] = true; delete UI.applied[id]; delete UI.rejected[id]; }
      });
      persistState();
      var en = SB.state && SB.state.lang === "en";
      var word = kind === "accept" ? t("j.applied") : kind === "reject" ? t("j.rejected") : t("j.routed");
      var label = (ids.length > 1 ? (ids.length + (en ? " charges " : " 条 ")) : (ids[0] + " ")) + word;
      // R5(7): the inverse closure restores every disposed id's exact prior membership (navUndo pattern)
      SB.toast(label, { duration: 4000, action: { label: t("j.bulk.undo"), fn: function () {
        prior.forEach(function (s) {
          delete UI.applied[s.id]; delete UI.rejected[s.id]; delete UI.routed[s.id];
          if (s.applied) UI.applied[s.id] = true;
          else if (s.rejected) UI.rejected[s.id] = true;
          else if (s.routed) UI.routed[s.id] = true;
        });
        persistState(); SB.refresh();
      } } });
      ids.forEach(function (id) { replaceCard(id); });   // in-place, so focus + scroll survive (no full refresh)
      rerenderReadiness();                               // R2(round7): move the go/no-go verdict + gate KPI, not just the card
      SELECTED = {}; renderBulkBar();
      var pid = primaryCard ? primaryCard.getAttribute("data-charge") : ids[ids.length - 1];
      focusCard(board.querySelector('[data-charge="' + pid + '"]'));
    }
    board.addEventListener("keydown", function (e) {
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      if (e.key === "Escape" && selectedIds().length) { e.preventDefault(); clearSelection(); return; }   // R5(7)
      var card = e.target.closest && e.target.closest(".charge"); if (!card) return;
      var k = e.key, dir = null;
      if (k === "j" || k === "ArrowDown") dir = "down";
      else if (k === "k" || k === "ArrowUp") dir = "up";
      else if (k === "h" || k === "ArrowLeft") dir = "left";
      else if (k === "l" || k === "ArrowRight") dir = "right";
      if (dir) {
        var target = navFrom(card, dir);
        if (target) { e.preventDefault(); if (e.shiftKey) { markSel(card); markSel(target); } focusCard(target); }
        return;
      }
      if (k === "x" || k === "X") { e.preventDefault(); toggleSel(card); return; }
      // R12: Shift+A (or numpad *) selects the focused lane; Shift+* the whole board.
      if (k === "A" || (k === "*" && !e.shiftKey)) { e.preventDefault(); selectLane(card); return; }
      if (k === "*" && e.shiftKey) { e.preventDefault(); selectBoard(); return; }
      if (k === "a" || k === "r" || k === "f") {
        e.preventDefault();
        var kind = k === "a" ? "route" : k === "r" ? "reject" : "accept";
        var ids = selectedIds(); if (!ids.length) ids = [card.getAttribute("data-charge")];
        dispose(ids, kind, card);
      }
    });
    // establish the roving anchor: the last-focused charge if it survived, else the first
    (function initRoving() {
      var cards = boardCards(); if (!cards.length) return;
      var want = FOCUS_CHARGE && board.querySelector('[data-charge="' + FOCUS_CHARGE + '"]');
      setRoving(want || cards[0]);
    })();

    /* ---- R5(7): sticky bulk-action bar + Escape-to-clear --------------------- *
     * Appears only while ≥1 charge is selected; its A/R/F buttons run the SAME
     * reversible dispose() the a/r/f keys do, and Esc clears the selection and
     * re-homes roving focus. Recreated with the pane each render (main is cleared),
     * so it never leaks; renderBulkBar() below reflects any selection that survived. */
    var bulkBar = el("div", "j-bulkbar"); bulkBar.setAttribute("role", "toolbar");
    bulkBar.setAttribute("aria-label", t("j.board")); bulkBar.hidden = true;
    pane.appendChild(bulkBar);
    function renderBulkBar() {
      var ids = selectedIds();
      if (!ids.length) { bulkBar.hidden = true; bulkBar.innerHTML = ""; return; }
      bulkBar.hidden = false;
      bulkBar.innerHTML =
        '<span class="j-bulk-n">' + ids.length + " " + esc(t("j.bulk.selected")) + "</span>" +
        '<button class="btn sm" data-bulk="a"><kbd>A</kbd> ' + esc(t("j.bulk.author")) + "</button>" +
        '<button class="btn sm" data-bulk="r"><kbd>R</kbd> ' + esc(t("j.bulk.drop")) + "</button>" +
        '<button class="btn sm" data-bulk="f"><kbd>F</kbd> ' + esc(t("j.bulk.fixable")) + "</button>" +
        '<button class="btn sm ghost" data-bulk="esc"><kbd>Esc</kbd> ' + esc(t("j.bulk.clear")) + "</button>";
    }
    function clearSelection() {
      selectedIds().forEach(function (id) { var c = board.querySelector('[data-charge="' + id + '"]'); if (c) applySel(c, false); });
      SELECTED = {}; renderBulkBar();
      var anchor = (FOCUS_CHARGE && board.querySelector('[data-charge="' + FOCUS_CHARGE + '"]')) || boardCards()[0];
      if (anchor) focusCard(anchor);
    }
    bulkBar.addEventListener("click", function (e) {
      var b = e.target.closest("[data-bulk]"); if (!b) return;
      var k = b.getAttribute("data-bulk");
      if (k === "esc") { clearSelection(); return; }
      var ids = selectedIds(); if (!ids.length) return;
      dispose(ids, k === "a" ? "route" : k === "r" ? "reject" : "accept", null);
    });
    bulkBar.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && selectedIds().length) { e.preventDefault(); clearSelection(); }
    });
    renderBulkBar();   // reflect any selection carried across a re-render

    // R12: after a re-render, scroll an off-screen lane (author-required / dropped) into view
    if (FOCUS_LANE) {
      var wantLane = FOCUS_LANE; FOCUS_LANE = null;
      var laneJump = board.querySelector('[data-lane="' + wantLane + '"]');
      if (laneJump) {
        scrollIntoViewSafe(laneJump, { inline: "center", block: "nearest" });
        laneJump.classList.add("j-lane-flash");
        setTimeout(function () { laneJump.classList.remove("j-lane-flash"); }, 1600);
      }
    }
  }

  // R6: the Spark→Jury handoff. Guarded end-to-end: when an active project is wired
  // (SB.project — landed by the shared-active-project work), point Jury at its
  // manuscript and land on the docket; otherwise stay honest about what is not wired
  // yet rather than firing a "would…" toast that implies it happened.
  function runChain() {
    var en = SB.state && SB.state.lang === "en";
    if (SB.project) {
      var proj = (typeof SB.project === "function") ? SB.project() : SB.project;
      var dir = proj && (proj.juryDir || proj.reviewDir || proj.dir || proj.path || (typeof proj === "string" ? proj : ""));
      if (dir && SB.data && SB.data.setDir) SB.data.setDir("jury", dir);   // real load: docket reads this run's ledger
      UI.open = null; FILTER = null;
      SB.setSub("docket");
      SB.toast(en ? "Loaded this run's paper/main.tex into the docket" : "已把本运行的 paper/main.tex 载入判决台");
    } else {
      SB.toast(en ? "No active project yet — open a Spark run first, then send it to Jury"
                  : "还没有活动项目 —— 先打开一个 Spark 运行,再送来 Jury");
    }
  }

  // R6: empty ledger → a "run the review" empty-state, never a dead board.
  function renderEmptyDocket(main) {
    var pane = el("div", "pane reveal");
    var wrap = el("div", "pane-wide");
    wrap.innerHTML =
      '<div class="pane-head"><h2>' + esc(t("j.board")) + "</h2>" +
        '<span class="sub">' + esc(t("j.board.sub")) + "</span></div>" +
      '<div class="j-empty">' +
        '<div class="j-empty-ico"><svg class="i"><use href="#jx-gavel"/></svg></div>' +
        '<div class="j-empty-title">' + esc(t("j.empty.title")) + "</div>" +
        '<div class="j-empty-sub">' + esc(t("j.empty.sub")) + "</div>" +
        '<button class="btn primary" data-jchain><svg class="i sm"><use href="#jx-flame"/></svg>' + esc(t("j.empty.cta")) + "</button>" +
        '<button class="btn sm ghost" data-jexample>' + esc(t("j.empty.hint")) + "</button>" +
      "</div>";
    pane.appendChild(wrap);
    main.appendChild(pane);
    var cta = wrap.querySelector("[data-jchain]"); if (cta) cta.onclick = runChain;
    var ex = wrap.querySelector("[data-jexample]"); if (ex) ex.onclick = function () { SB.setSub("example"); };
  }

  // R18: an always-visible one-line gloss of the most load-bearing terms, so the
  // jargon is legible without hovering a chip or expanding the legend.
  function legendCaption() {
    return '<p class="j-legend-cap"><svg class="i sm"><use href="#jx-scale"/></svg><span>' +
      esc(t("j.legend.cap")) + '</span> <span class="j-legend-more">· ' + esc(t("j.legend.more")) + "</span></p>";
  }

  // a KPI stat card. o:{v,eyebrow,sub,tone,subtone,title,act,active}. `act` makes it a
  // keyboard-operable button that a delegated handler reads from data-kpi.
  function kpiCard(o) {
    var act = o.act ? String(o.act) : "";
    var cls = "card j-kpi" + (act ? " j-kpi-act" : "") + (o.active ? " j-kpi-on" : "");
    var attrs = act ? (' data-kpi="' + esc(act) + '" role="button" tabindex="0"') : "";
    if (o.title) attrs += ' title="' + esc(o.title) + '"';
    return '<div class="' + cls + '"' + attrs + '>' +
      '<div class="stat"><span class="v' + (o.tone ? " " + o.tone : "") + '">' + esc(String(o.v)) + "</span>" +
      '<span class="k">' + esc(o.eyebrow) + "</span>" +
      (o.sub ? '<span class="j-kpisub' + (o.subtone ? " " + o.subtone : "") + '">' + esc(o.sub) + "</span>" : "") +
      "</div></div>";
  }

  // R14: the author-required · dropped tile packed two numbers under one label ('2 · 4'),
  // reading as a single figure. Bind each number to its own word inline, at a smaller-than-
  // folio size, so it's one tile with two unambiguous counts (still the 'route' click target).
  function routeKpiCard(authreq, dropped, o) {
    var attrs = ' data-kpi="route" role="button" tabindex="0"';
    if (o && o.title) attrs += ' title="' + esc(o.title) + '"';
    function pair(word, n, tone) {
      return '<span class="j-rpair"><span class="j-rk">' + esc(word) + "</span>" +
        '<span class="j-rv ' + (tone || "") + '">' + esc(String(n)) + "</span></span>";
    }
    return '<div class="card j-kpi j-kpi-act j-kpi-route"' + attrs + ">" +
      '<div class="stat j-rstat">' +
        pair(t("j.lane.author-required"), authreq, "stale") +
        '<span class="j-rsep">·</span>' +
        pair(t("j.lane.dropped"), dropped, "bad") +
      "</div></div>";
  }

  function filterBar() {
    return '<div class="j-filterbar" role="status">' +
      '<svg class="i sm"><use href="#jx-scale"/></svg>' +
      "<span>" + esc(t("j.filter.on")) + "</span>" +
      '<button class="btn sm ghost" data-jclear><svg class="i sm"><use href="#jx-close"/></svg>' + esc(t("j.filter.clear")) + "</button></div>";
  }
  // R5(20): the "contested lens" bar — same clear affordance (data-jclear) as the gate filter
  function contestedFilterBar() {
    return '<div class="j-filterbar j-filterbar-contested" role="status">' +
      '<svg class="i sm"><use href="#jx-flame"/></svg>' +
      "<span>" + esc(t("j.contested.on")) + "</span>" +
      '<button class="btn sm ghost" data-jclear><svg class="i sm"><use href="#jx-close"/></svg>' + esc(t("j.filter.clear")) + "</button></div>";
  }
  // R18: the "filtered to §N" bar shown when a coverage cell narrowed the board
  function sectionFilterBar(col) {
    return '<div class="j-filterbar" role="status">' +
      '<svg class="i sm"><use href="#jx-scale"/></svg>' +
      "<span>" + esc(t("j.cov.filtered") + col + t("j.cov.filtered.suf")) + "</span>" +
      '<button class="btn sm ghost" data-jclearsec><svg class="i sm"><use href="#jx-close"/></svg>' + esc(t("j.filter.clear")) + "</button></div>";
  }
  // R15: a single go/no-go readiness verdict — ANDs the gate (zero blocking majors)
  // with clerk convergence. Greyed to an honest "can't assess" when the dir couldn't
  // be read, so a passing sample is never presented as this manuscript's verdict.
  function readinessBar(blocking, authorPending, converged, miss, proj) {
    var en = SB.state && SB.state.lang === "en";
    // R9(round10): the author-pending count is a UNION (major author-required + major queued).
    // The route KPI shows only 'author-required', so labelling the union "待作者" too made the
    // board read two different numbers under one word. Give the union its own label + a breakdown
    // so "待作者" binds to exactly one category (author-required) everywhere it appears.
    function authorUnionLabel(n) {
      var aR = 0, qd = 0;
      DATA.ledger.forEach(function (r) {
        if (r.significance !== "major") return;
        if (r.status === "author-required") aR++;
        else if (r.status === "queued") qd++;
      });
      return en
        ? (n + " need an author/human call (" + aR + " author-required + " + qd + " anchor-queued)")
        : (n + " 项需作者/人工定夺 (" + aR + " 待作者 + " + qd + " 触及锚点待回看)");
    }
    // green is reserved for: auto-blockers clear AND no open author decisions AND converged.
    var gatePass = blocking === 0 && authorPending === 0 && converged;
    var state, verdict, detail, icon;
    if (miss) {
      state = "sample"; icon = "jx-warn"; verdict = t("j.ready.sample"); detail = "";
    } else if (gatePass) {
      state = "clear"; icon = "jx-check"; verdict = t("j.ready.clear"); detail = t("j.ready.clear.sub");
    } else if (blocking === 0 && authorPending > 0) {
      // R2(round4): auto-blockers are all clear, but author-required / anchor-queued majors
      // are still open — a DISTINCT amber verdict, never the green "clear to submit".
      state = "author"; icon = "jx-scale"; verdict = t("j.ready.author");
      var abits = [];
      abits.push(authorUnionLabel(authorPending));
      if (!converged) abits.push(en ? "round not converged" : "本轮未收敛");
      detail = abits.join(" · ");
    } else {
      state = "blocked"; icon = "jx-shield"; verdict = t("j.ready.blocked");
      var bits = [];
      if (blocking) bits.push(en ? (blocking + " gate-blocking major" + (blocking > 1 ? "s" : "") + " open") : (blocking + " 项阻断投稿的重大项未了结"));
      if (authorPending) bits.push(authorUnionLabel(authorPending));
      if (!converged) bits.push(en ? "round not converged" : "本轮未收敛");
      detail = bits.join(" · ");
    }
    // R2(round7): when this session's un-written dispositions would move the gate, PREVIEW the
    // projected blocking count — the verdict itself stays on the RAW count (nothing is written).
    if (proj && (state === "blocked" || state === "author") && proj.blocking !== blocking) {
      detail = detail + " (" + t("j.ready.proj").replace("%d", proj.blocking) + ")";
    }
    return '<div class="j-ready j-ready-' + state + '" role="status">' +
      '<span class="j-ready-eye">' + esc(t("j.ready.eyebrow")) + "</span>" +
      '<svg class="i sm"><use href="#' + icon + '"/></svg>' +
      '<b class="j-ready-v">' + esc(verdict) + "</b>" +
      (detail ? '<span class="j-ready-d">' + esc(detail) + "</span>" : "") + "</div>";
  }

  // R11: a collapsible legend mapping every chip + lane to one plain-language line
  function legendBlock() {
    function item(sample, gloss) { return '<div class="j-lgitem">' + sample + '<span class="j-lggloss">' + esc(gloss) + "</span></div>"; }
    var chip = function (cls, txt) { return '<span class="chip' + (cls ? " " + cls : "") + '">' + esc(txt) + "</span>"; };
    var marks =
      item('<span class="chip j-major">' + esc(enumLabel("major")) + "</span>", t("j.gl.major")) +
      item(chip("", enumLabel("minor")), t("j.gl.minor")) +
      item(chip("", enumLabel("mechanical")), t("j.gl.mech")) +
      item(chip("", enumLabel("substantive")), t("j.gl.subst")) +
      item(verdictChip("valid-fixable"), t("j.gl.vfix")) +
      item(verdictChip("author-required"), t("j.gl.authreq")) +
      item(verdictChip("invalid-drop"), t("j.gl.drop")) +
      item(verdictChip("escalate"), t("j.gl.escal")) +
      item('<span class="chip ok">' + esc(t("j.corrob")) + " ×2</span>", t("j.gl.corrob")) +
      item('<span class="badge j-esc"><svg class="i sm"><use href="#jx-gavel"/></svg>' + esc(t("j.esc")) + "</span>", t("j.gl.esc12")) +
      item('<span class="chip wait"><svg class="i sm"><use href="#jx-shield"/></svg>A1</span>', t("j.gl.frozen"));
    var lanes = "";
    LANES.forEach(function (lane) {
      lanes += '<div class="j-lgitem"><span class="j-swatch" style="background:' + lane.swatch + '"></span>' +
        '<span class="j-lgterm">' + esc(t("j.lane." + lane.id)) + "</span>" +
        '<span class="j-lggloss">' + esc(t("j.lm." + lane.id)) + "</span></div>";
    });
    // R18: the always-visible caption above already makes the load-bearing terms legible
    // without hover, so the full legend stays collapsed by default (keeps the board in view);
    // if the reader opens it, that choice is remembered (toggle listener in renderDocket).
    var open = false; try { open = localStorage.getItem("sb.jury.legend") === "1"; } catch (e) {}
    return '<details class="card j-legend"' + (open ? " open" : "") + '><summary><svg class="i sm"><use href="#jx-scale"/></svg>' + esc(t("j.legend")) + "</summary>" +
      '<div class="j-lgcols">' +
        '<div class="j-lggroup"><div class="j-lgh">' + esc(t("j.legend.chips")) + "</div>" + marks + "</div>" +
        '<div class="j-lggroup"><div class="j-lgh">' + esc(t("j.legend.lanes")) + "</div>" + lanes + "</div>" +
      "</div></details>";
  }

  // a charge card = the ledger row on the board
  // R2: the user's this-session disposition echo, shown on the board card
  function decisionChip(dec) {
    if (dec === "applied") return '<span class="j-decflag ok" title="' + esc(t("j.applied")) + '"><svg class="i sm"><use href="#jx-check"/></svg>' + esc(t("j.applied")) + "</span>";
    if (dec === "rejected") return '<span class="j-decflag bad" title="' + esc(t("j.rejected")) + '"><svg class="i sm"><use href="#jx-close"/></svg>' + esc(t("j.rejected")) + "</span>";
    if (dec === "routed") return '<span class="j-decflag wait" title="' + esc(t("j.routed")) + '"><svg class="i sm"><use href="#jx-scale"/></svg>' + esc(t("j.routed")) + "</span>";
    return "";
  }
  function chargeCard(row) {
    var sel = !!SELECTED[row.id], dec = localDecision(row);
    var c = el("div", "charge" + (sel ? " j-charge-sel" : ""));
    c.setAttribute("data-charge", row.id);
    c.setAttribute("role", "listitem");
    c.setAttribute("tabindex", "0");             // R11: focusable; Enter/Space opens (keydown below). Roving set post-build.
    c.setAttribute("aria-keyshortcuts", "Enter A R F X J K H L");   // R15(round4): AT-visible per-card keymap
    if (sel) c.setAttribute("aria-selected", "true");
    c.setAttribute("aria-label", row.id + " " + enumLabel(row.significance) + " · " + row.summary);
    var anch = anchorFor(row.passage_id);
    c.innerHTML =
      '<div class="j-cid"><span class="badge">' + esc(row.id) + "</span>" +
        '<span class="j-sec">' + esc(row.section) + "</span>" + decisionChip(dec) + "</div>" +
      '<div class="ct">' + esc(row.summary) + "</div>" +
      '<div class="cm">' + sigChip(row) + kindChip(row) + verdictChip(row.verdict) + badges(row) +
        (anch ? '<span class="chip wait" title="edit here touches frozen spine anchor ' + esc(anch.anchor_id) + '"><svg class="i sm"><use href="#jx-shield"/></svg>' + esc(anch.anchor_id) + "</span>" : "") +
        covGapChip(row.section) +   // R12(round10): surface a coverage skim gap on the board scan
      "</div>" +
      '<div class="cby">' + (row.raised_by || []).map(personaChip).join("") +
        '<span class="j-conf" title="max reviewer confidence 1–5">' + esc(t("j.conf")) + " " + row.reviewer_confidence + "/5</span></div>" +
      votebar(row.tally);
    // keyboard: Enter/Space opens (cards are focusable); j/k/h/l/a/r/f/x handled by the board (R2)
    c.addEventListener("keydown", function (e) { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); openCharge(row.id); } });
    return c;
  }

  function openCharge(id) { UI.open = id; SB.refresh(); }
  function closeCharge() { UI.open = null; SB.refresh(); }

  /* ---- R8(round4): Jury → Wiki handoff (JURY side) --------------------------- *
   * On a DECIDED charge (verdict != null), compose a payload and hand it to the Wiki
   * workspace via the SB.wikiFileCharge global (implemented by the Wiki agent). Guarded:
   * if the hook is absent we stay honest ("Wiki not ready") rather than dropping it.
   * The affordance is labelled as filing a NOT-yet-persisted item, matching the module's
   * "preview · 未写入 journal" honesty stance. */
  function wikiPatchText(row) {
    return row.drafted_patch ? ("- " + row.drafted_patch.before + "\n+ " + row.drafted_patch.after) : "";
  }
  function wikiPayload(row) {
    var patch = wikiPatchText(row);
    var lines = [];
    lines.push("**" + t("j.verdict") + ":** " + (row.verdict || row.status));
    if (row.reason_code) lines.push("**reason_code:** " + row.reason_code);
    if (row.section) lines.push("**section:** " + row.section);
    lines.push("**" + t("j.evidence") + ":** “" + (row.evidence_anchor || "") + "”");
    if (patch) lines.push("\n```diff\n" + patch + "\n```");
    return {
      title: row.id + " · " + row.summary,
      body: lines.join("\n"),
      reason_code: row.reason_code || "",
      evidence: row.evidence_anchor || "",
      patch: patch,
    };
  }
  function fileChargeToWiki(row) {
    if (SB.wikiFileCharge) SB.wikiFileCharge(wikiPayload(row));
    else SB.toast(t("j.wiki.notready"));
  }

  /* ---- a charge read as an article (ReaderShell, rail:'toc') --------------- */
  function chargeReader(main, id) {
    var row = byId(id); if (!row) { UI.open = null; return renderDocket(main); }
    var ids = DATA.ledger.map(function (r) { return r.id; });
    var idx = ids.indexOf(id);

    SB.ReaderShell(main, {
      sidebar: chargeSidebar(id),
      list: chargeList(id),
      rail: "toc",
      reader: {
        kicker: t("j.kicker.charge") + " " + row.id + " · " + row.section,
        title: row.summary,
        meta: chargeMeta(row),
        bodyHTML: chargeBody(row),
      },
      onPrev: function () { if (idx > 0) openCharge(ids[idx - 1]); },
      onNext: function () { if (idx < ids.length - 1) openCharge(ids[idx + 1]); },
      onStar: function () { SB.toast(row.id + (SB.state && SB.state.lang === "en" ? " pinned" : " 已标记")); },
    });

    // wire the back button + deep-links after the shell mounts
    var back = main.querySelector("[data-jback]"); if (back) back.onclick = closeCharge;
    main.querySelectorAll("[data-jopen]").forEach(function (n) { n.onclick = function () { openCharge(n.getAttribute("data-jopen")); }; });
    // R14: jump lands on the verbatim evidence in place — scroll + flash the anchor
    // quote (the manuscript passage the charge rests on) instead of a dead toast.
    var jump = main.querySelector("[data-jjump]");
    if (jump) jump.onclick = function () {
      // R5(5): navigate to the SPARK reader — which holds the real manuscript — handing it
      // the passage to scroll+flash via SB.pendingReadSection. Guarded on the shell's tool nav.
      if (SB.setTool && SB.setSub) {
        SB.pendingReadSection = { section: row.section, quote: row.evidence_anchor, passage_id: row.passage_id, fromCharge: row.id };
        SB.setTool("spark"); SB.setSub("reading");
        return;
      }
      // Fallback (no shell nav — isolated harness): flash the on-screen quote in place. The
      // button was already relabeled off "in the paper", so an in-place highlight stays honest.
      var q = main.querySelector(".reader .j-quote") || main.querySelector(".j-quote");
      if (!q) { SB.toast((SB.state && SB.state.lang === "en" ? "Evidence: " : "所依原文:") + row.section); return; }
      scrollIntoViewSafe(q, { block: "center" });
      q.classList.remove("j-quote-flash"); void q.offsetWidth; q.classList.add("j-quote-flash");
      setTimeout(function () { q.classList.remove("j-quote-flash"); }, 1500);
    };
    // R5(10): the 'Source: run <name> →' provenance deep-link back to the Spark run
    var provBtn = main.querySelector("[data-jprovrun]");
    if (provBtn) provBtn.onclick = function () { openProvRun(provBtn.getAttribute("data-jprovrun")); };
    // R14: carry the charge id to the panel, then scroll+flash its trial card
    var trialLink = main.querySelector("[data-jtrial]"); if (trialLink) trialLink.onclick = function () { FOCUS_TRIAL = row.id; SB.setSub("panel"); };
    // R14: the drafted-patch Accept/Reject/route controls (same handlers as the inbox)
    if (row.drafted_patch) wireRevisionActions(main, row);
    // R8(round4): wire the Jury → Wiki handoff button (decided charges only)
    var wf = main.querySelector("[data-jwikifile]"); if (wf) wf.onclick = function () { fileChargeToWiki(row); };
  }

  function chargeSidebar(openId) {
    var s = el("div");
    // back to the board
    var back = '<div class="side-sec"><button class="j-backbtn" data-jback>' +
      '<svg class="i sm"><use href="#jx-back"/></svg>' + esc(t("j.back")) + "</button></div>";
    // charges grouped by lane, current one highlighted
    var secs = "";
    LANES.forEach(function (lane) {
      var rows = DATA.ledger.filter(function (r) { return lane.statuses.indexOf(r.status) >= 0; });
      if (!rows.length) return;
      secs += '<div class="side-sec"><div class="side-h"><span class="j-swatch" style="background:' + lane.swatch + '"></span>' +
        esc(t("j.lane." + lane.id)) + " · " + rows.length + "</div>" +
        rows.map(function (r) {
          return '<div class="side-row' + (r.id === openId ? " sel" : "") + '" data-jopen="' + r.id + '">' +
            '<span class="badge">' + esc(r.id) + "</span>" +
            '<span class="lbl">' + esc(r.summary) + "</span></div>";
        }).join("") + "</div>";
    });
    s.innerHTML = back + secs;
    return s;
  }
  function chargeList(openId) {
    var s = el("div", "list");
    s.innerHTML = '<div class="j-listhead">' + esc(t("j.charges")) + " · " + DATA.ledger.length + "</div>" +
      DATA.ledger.map(function (r) {
        return '<div class="entry' + (r.id === openId ? " sel" : " read") + '" data-jopen="' + r.id + '">' +
          '<span class="dot"></span><div class="body">' +
          '<div class="etitle">' + esc(r.summary) + "</div>" +
          '<div class="eprev">“' + esc(r.evidence_anchor) + '”</div>' +
          '<div class="efoot"><span class="src">' + esc(r.id) + " · " + esc(r.section) + "</span>" +
          '<span class="date">' + esc(r.status) + "</span></div></div></div>";
      }).join("");
    return s;
  }
  function chargeMeta(row) {
    // R5(6): when EVERY reviewer that raised this charge is degraded, flag it right above the
    // verdict so the verdict isn't weighed as if a verified reviewer stood behind it.
    var caveat = allRaisedByUnverified(row)
      ? '<span class="chip j-degraded-caveat" title="' + esc(t("j.degraded.only")) + '"><svg class="i sm"><use href="#jx-warn"/></svg>' + esc(t("j.degraded.only")) + "</span>"
      : "";
    return sigChip(row) + kindChip(row) + caveat + verdictChip(row.verdict) + reasonChip(row.reason_code) +
      badges(row) + " " + (row.raised_by || []).map(personaChip).join("") +
      '<span class="j-conf">' + esc(t("j.conf")) + " " + row.reviewer_confidence + "/5</span>";
  }
  function chargeBody(row) {
    var anch = anchorFor(row.passage_id);
    var tr = trialFor(row.id);
    var h = "";
    // verdict banner
    h += verdictBanner(row.verdict, row.status);
    // R27: amber caveat when the section this charge rests on was skipped/light in coverage
    h += coverageGapBanner(row.section);
    // R6: the juror vote tally + colour key, immediately under the verdict banner
    // (votebar self-degrades to an honest "not tried yet" when tally is null).
    // R20b(round4): a tally with no per-juror trial record on file is annotated so the
    // vote bar never implies reasoning that was never recorded.
    h += '<div class="j-readervote">' + votebar(row.tally) + (row.tally ? voteLegend() : "") +
      (row.tally && !tr ? '<span class="j-tallyonly" title="' + esc(t("j.tally.only")) + '"><svg class="i sm"><use href="#jx-warn"/></svg>' + esc(t("j.tally.only")) + "</span>" : "") + "</div>";
    // evidence anchor — the exact verbatim quote the charge rests on
    // R28b(round4): the heading asserts "(verbatim)" — back it with proof. When the quote
    // string-matches a source line we actually hold (drafted_patch.before / journal / frozen
    // spine anchor), stamp a "✓ verbatim · <anchor>" badge; otherwise degrade to "not located".
    var loc = evidenceLocated(row);                                    // R5(21): {src, anchor?}
    var resolvable = loc.src === "anchor" || loc.src === "journal";    // R5(5): a precise jump is honest only when the quote lives in a source we hold
    h += "<h2>" + esc(t("j.evidence")) + "</h2>" +
      '<blockquote class="j-quote"><svg class="i sm j-qmark"><use href="#jx-quote"/></svg>' + esc(row.evidence_anchor) + "</blockquote>" +
      evBadgeHTML(loc, row) +
      '<p><button class="btn sm ghost" data-jjump><svg class="i sm"><use href="#jx-back"/></svg>' +
        esc(resolvable ? t("j.section.jump") : t("j.section.open")) + " (" + esc(row.section) + ")</button></p>";
    // close criterion
    if (row.close_criterion) h += "<h2>" + esc(t("j.close")) + "</h2><p>" + esc(row.close_criterion) + "</p>";
    // references
    if (row.references) h += "<h2>" + esc(t("j.refs")) + "</h2><p>" + esc(row.references) + "</p>";
    // frozen-anchor note
    if (anch) h += '<p class="j-anchornote"><svg class="i sm"><use href="#jx-shield"/></svg> ' +
      (SB.state && SB.state.lang === "en" ? "A fix here touches frozen spine anchor " : "在此处修改会触及冻结锚点 ") +
      "<b>" + esc(anch.anchor_id) + " (" + esc(anch.type) + ")</b>: “" + esc(anch.text) + "”</p>";
    // provenance / flow
    h += "<h2>" + esc(t("j.prov")) + "</h2>" +
      '<p class="j-prov">' +
      "passage_id <code>" + esc(row.passage_id) + "</code> · round_raised " + row.round_raised +
      (row.round_closed ? " · round_closed " + row.round_closed : "") +
      (row.reason_code ? " · reason_code <code>" + esc(row.reason_code) + "</code>" : "") +
      (row.journal_ref ? " · journal <code>" + esc(row.journal_ref) + "</code>" : "") + "</p>";
    h += chargeProvHTML();                                             // R5(10): 'Source: run <name> →' (guarded on SB.prov)
    if (row.notes) h += "<p>" + esc(row.notes) + "</p>";
    // link to the trial record if this charge was tried
    if (tr) h += '<p><button class="btn sm" data-jtrial><svg class="i sm"><use href="#jx-scale"/></svg>' + esc(t("j.trial.link")) + "</button></p>";
    // drafted patch — actionable right here (R14), sharing the Revisions inbox state
    // and the same auto-block rule (R7). Already-journaled patches read as "applied".
    if (row.drafted_patch) {
      h += "<h2>drafted_patch</h2>" + diffBlock(row.drafted_patch) +
        '<div class="j-readeract">' + revisionActions(row, decidedState(row), isBlocked(row)) + "</div>";
    }
    // R8(round4): on a DECIDED charge, offer the Jury → Wiki handoff. Labelled as filing a
    // not-yet-persisted item, consistent with the module's local-echo honesty stance.
    if (row.verdict) {
      h += '<div class="j-wikifile"><button class="btn sm ghost" data-jwikifile>' +
        '<svg class="i sm"><use href="#jx-doc"/></svg>' + esc(t("j.wiki.file")) + "</button>" +
        '<span class="j-wikifile-note">' + esc(t("j.wiki.file.note")) + "</span></div>";
    }
    return h;
  }

  // R28b(round4): can we PROVE the evidence quote is verbatim? True only when it string-
  // matches a source line we actually hold — the drafted patch's before-text, a journal
  // entry for this passage, or a frozen spine anchor. Absent proof it degrades to "not
  // located" rather than asserting "(verbatim)" on faith.
  // R5(21): return WHICH source the quote matched, strongest first, so the badge can
  // disclose it — "anchor" (frozen spine, strong) > "journal" (applied patch record,
  // neutral) > "patch" (the charge's OWN before-text, circular → not verbatim proof).
  function evidenceLocated(row) {
    var q = String(row.evidence_anchor || "").trim();
    if (!q) return { src: null };
    function has(s) { return s && String(s).indexOf(q) >= 0; }
    var a = anchorFor(row.passage_id);                       // strongest: a frozen spine anchor
    if (a && has(a.text)) return { src: "anchor", anchor: a };
    var jm = false;                                          // neutral: an applied journal record for this passage
    DATA.journal.forEach(function (j) {
      if (j.passage_id === row.passage_id || j.issue_id === row.id) { if (has(j.before) || has(j.after)) jm = true; }
    });
    if (jm) return { src: "journal" };
    if (row.drafted_patch && has(row.drafted_patch.before)) return { src: "patch" };   // weakest: the charge's own before-text
    return { src: null };
  }
  // R5(21): the evidence badge, keyed off which source matched (see evidenceLocated).
  function evBadgeHTML(loc, row) {
    if (loc.src === "anchor") {
      var aid = loc.anchor ? loc.anchor.anchor_id : "";
      return '<p class="j-evbadge ok" title="' + esc(t("j.ev.anchor") + (aid ? " " + aid : "") + " · " + row.passage_id) + '">' +
        '<svg class="i sm"><use href="#jx-check"/></svg>✓ ' + esc(t("j.ev.anchor")) +
        (aid ? ' · <code>' + esc(aid) + "</code>" : "") + "</p>";
    }
    if (loc.src === "journal") {
      return '<p class="j-evbadge neutral" title="' + esc(t("j.ev.patchrec") + " · " + row.passage_id) + '">' +
        '<svg class="i sm"><use href="#jx-check"/></svg>' + esc(t("j.ev.patchrec")) +
        ' · <code>' + esc(row.passage_id) + "</code></p>";
    }
    if (loc.src === "patch") {   // only the charge's own before-text matched → drop "verbatim to source"
      return '<p class="j-evbadge warn" title="' + esc(t("j.ev.selfonly")) + '">' +
        '<svg class="i sm"><use href="#jx-warn"/></svg>' + esc(t("j.ev.selfonly")) + "</p>";
    }
    return '<p class="j-evbadge warn" title="' + esc(t("j.ev.notlocated")) + '">' +
      '<svg class="i sm"><use href="#jx-warn"/></svg>' + esc(t("j.ev.notlocated")) + "</p>";
  }

  /* ---- R5(10): charge provenance — which Spark run produced this manuscript ---- *
   * SB.prov (a shell-owned localStorage store) is written by Spark on Send-to-Jury as
   * {reviewedFromRun:<runId>}. We read it (guarded — absent until the shell lands it) and
   * render a 'Source: run <name> →' deep-link back to that run. No prov → nothing, so a
   * source is only ever shown when one was actually recorded. */
  function activePaperKey() {
    try { if (SB.project && SB.project.get) { var p = SB.project.get(); if (p) return p; } } catch (e) {}
    return ledgerKey();
  }
  function provRun() {
    if (!(SB.prov && SB.prov.get)) return "";
    var rec = null; try { rec = SB.prov.get(activePaperKey()); } catch (e) { rec = null; }
    return (rec && rec.reviewedFromRun) ? String(rec.reviewedFromRun) : "";
  }
  function chargeProvHTML() {
    var run = provRun(); if (!run) return "";
    return '<p class="j-provsrc"><button class="btn sm ghost" data-jprovrun="' + esc(run) + '">' +
      '<svg class="i sm"><use href="#jx-flame"/></svg>' + esc(t("j.prov.src")) + " <b>" + esc(run) + "</b> →</button></p>";
  }
  function openProvRun(run) {
    try { if (SB.project && SB.project.set) SB.project.set(run); } catch (e) {}
    if (SB.setTool) SB.setTool("spark");
  }

  // shared accept/reject/route state resolution (Revisions inbox + charge reader)
  function isBlocked(row) { return row.status === "author-required" || row.status === "queued"; }
  function journalHas(id) { for (var i = 0; i < DATA.journal.length; i++) if (DATA.journal[i].issue_id === id) return true; return false; }
  function decidedState(row) {
    if (UI.applied[row.id]) return "applied";
    if (UI.rejected[row.id]) return "rejected";
    if (UI.routed[row.id]) return "routed";
    return journalHas(row.id) ? "applied" : null;   // already landed this round
  }

  function verdictBanner(verdict, status) {
    var cls = VERDICT_CLASS[verdict] || "neutral";
    var label = verdict || status;
    return '<div class="j-verdict v-' + cls + '"><svg class="i"><use href="#jx-scale"/></svg>' +
      '<span class="vlab">' + esc(t("j.verdict")) + "</span><b>" + esc(enumLabel(label)) + "</b>" +
      '<span class="vstat">status: ' + esc(status) + "</span></div>";
  }
  function diffBlock(p) {
    return '<div class="diff"><div class="d-row d-del">' + esc(p.before) + "</div>" +
      '<div class="d-row d-add">' + esc(p.after) + "</div></div>";
  }

  /* ========================================================================== *
     SUB-VIEW: REVISIONS — the diff inbox + journal.jsonl history with undo
     ========================================================================== */
  function renderRevisions(main) {
    var pane = el("div", "pane reveal");
    var wrap = el("div", "pane-wide");

    // pending = rows carrying a drafted_patch that is NOT yet in the journal (unapplied)
    var applied_ids = {}; DATA.journal.forEach(function (j) { applied_ids[j.issue_id] = true; });
    var pending = DATA.ledger.filter(function (r) { return r.drafted_patch && !applied_ids[r.id]; });
    // actionable-first: valid-fixable before queued/author-required
    var rank = { "valid-fixable":0, "queued":1, "author-required":2 };
    pending.sort(function (a, b) { return (rank[a.status] == null ? 9 : rank[a.status]) - (rank[b.status] == null ? 9 : rank[b.status]); });

    wrap.innerHTML = '<div class="pane-head"><h2>' + esc(t("j.rev.title")) + "</h2>" +
      '<span class="sub">' + esc(t("j.rev.sub")) + "</span></div>";

    var grid = el("div", "j-revgrid");

    // left: patches awaiting a ruling
    var colA = el("div", "j-revcol");
    colA.innerHTML = '<div class="j-colh"><svg class="i sm"><use href="#jx-doc"/></svg>' + esc(t("j.rev.pending")) + ' <span class="badge">' + pending.length + "</span></div>";
    pending.forEach(function (r) { colA.appendChild(revisionCard(r)); });
    if (!pending.length) colA.appendChild(emptyMini("—"));

    // right: applied this round (journal), each with undo
    var colB = el("div", "j-revcol");
    colB.innerHTML = '<div class="j-colh"><svg class="i sm"><use href="#jx-undo"/></svg>' + esc(t("j.rev.hist")) + ' <span class="badge">' + DATA.journal.length + "</span></div>";
    DATA.journal.slice().reverse().forEach(function (j) { colB.appendChild(historyRow(j)); });

    grid.appendChild(colA); grid.appendChild(colB);
    wrap.appendChild(grid);
    pane.appendChild(wrap);
    main.appendChild(pane);
  }

  function revisionCard(row) {
    var c = el("div", "card j-rev");
    var anch = anchorFor(row.passage_id);
    var frozenChip = (row.reason_code === "anchor-touching" || anch)
      ? '<span class="chip wait" title="' + (anch ? "spine anchor " + esc(anch.anchor_id) : "anchor-touching") + '"><svg class="i sm"><use href="#jx-shield"/></svg>' + esc(t("j.frozen")) + (anch ? " · " + esc(anch.anchor_id) : "") + "</span>"
      : "";
    c.innerHTML =
      '<div class="card-h"><span class="badge">' + esc(row.id) + '</span>' +
        '<span class="j-sec">' + esc(row.section) + "</span>" +
        '<span class="j-revsp"></span>' + verdictChip(row.verdict) + reasonChip(row.reason_code) + frozenChip + "</div>" +
      '<div class="j-revsum">' + esc(row.summary) + "</div>" +
      diffBlock(row.drafted_patch) +
      (row.close_criterion ? '<div class="j-rationale"><b>close_criterion.</b> ' + esc(row.close_criterion) + "</div>" : "") +
      '<div class="j-rationale"><b>rationale.</b> ' + esc(row.notes) + "</div>" +
      revisionActions(row, decidedState(row), isBlocked(row));
    wireRevisionActions(c, row);
    return c;
  }
  // Accept / Reject / route / override — wired identically in the inbox and the reader.
  function wireRevisionActions(scope, row) {
    var acc = scope.querySelector("[data-acc]"), rej = scope.querySelector("[data-rej]"),
        rte = scope.querySelector("[data-route]"), ovr = scope.querySelector("[data-override]");
    if (acc) acc.onclick = function () { UI.applied[row.id] = true; delete UI.rejected[row.id]; delete UI.routed[row.id]; delete UI.overridden[row.id]; persistState(); SB.toast(row.id + " " + t("j.applied")); SB.refresh(); };
    if (rej) rej.onclick = function () { UI.rejected[row.id] = true; delete UI.applied[row.id]; delete UI.routed[row.id]; persistState(); SB.toast(row.id + " " + t("j.rejected")); SB.refresh(); };
    if (rte) rte.onclick = function () { UI.routed[row.id] = true; delete UI.applied[row.id]; delete UI.rejected[row.id]; persistState(); SB.toast(row.id + " " + t("j.routed")); SB.refresh(); };
    if (ovr) ovr.onclick = function () { overrideApply(row); };
  }
  // R7: an auto-blocked patch can only be force-applied through an explicit, logged
  // override — never the same control as a normal Accept.
  function overrideApply(row) {
    var en = SB.state && SB.state.lang === "en";
    var msg = row.status === "author-required"
      ? (en ? "Override author-required and apply this patch anyway?" : "覆盖「待作者」并强行应用此补丁?")
      : (en ? "Override queued and apply this patch anyway?" : "覆盖「已入队」并强行应用此补丁?");
    var ok = true; try { ok = window.confirm(msg); } catch (e) { ok = true; }
    if (!ok) return;
    UI.applied[row.id] = true; UI.overridden[row.id] = true; delete UI.rejected[row.id]; delete UI.routed[row.id];
    persistState();
    SB.toast(row.id + " " + (en ? "override applied (logged)" : "已覆盖应用(留痕)"));
    SB.refresh();
  }
  function revisionActions(row, decided, blocked) {
    if (decided === "applied") return '<div class="j-decided ok"><svg class="i sm"><use href="#jx-check"/></svg>' + esc(t("j.applied")) +
      (UI.overridden[row.id] ? ' · <span class="j-ovtag">' + esc(t("j.overridden")) + "</span>" : "") + "</div>";
    if (decided === "rejected") return '<div class="j-decided bad"><svg class="i sm"><use href="#jx-close"/></svg>' + esc(t("j.rejected")) + "</div>";
    if (decided === "routed") return '<div class="j-decided wait"><svg class="i sm"><use href="#jx-scale"/></svg>' + esc(t("j.routed")) + "</div>";
    var en = SB.state && SB.state.lang === "en";
    if (blocked) {
      // R7: no live Accept on auto-blocked patches. The forward action is the ROUTE it
      // was assigned; a real apply lives behind the explicit, labelled override below.
      var routeLabel = row.status === "author-required" ? t("j.route.author") : t("j.route.queue");
      var why = row.status === "author-required"
        ? (en ? "auto-blocked → author decides" : "自动阻断 → 待作者定夺")
        : (en ? "queued → human return queue" : "已入队 → 人工回看");
      return '<div class="j-revact">' +
        '<button class="btn sm primary" data-route><svg class="i sm"><use href="#jx-scale"/></svg>' + esc(routeLabel) + "</button>" +
        '<button class="btn sm" data-rej><svg class="i sm"><use href="#jx-close"/></svg>' + esc(t("j.reject")) + "</button>" +
        '<span class="j-blocked">' + esc(why) + "</span>" +
        '<button class="btn sm ghost j-override" data-override>' + esc(t("j.override")) + "</button></div>";
    }
    return '<div class="j-revact">' +
      '<button class="btn sm primary" data-acc><svg class="i sm"><use href="#jx-check"/></svg>' + esc(t("j.accept")) + "</button>" +
      '<button class="btn sm" data-rej><svg class="i sm"><use href="#jx-close"/></svg>' + esc(t("j.reject")) + "</button></div>";
  }
  function historyRow(j) {
    var reverted = UI.reverted[j.jid];
    var c = el("div", "j-hist" + (reverted ? " j-hist-rev" : ""));
    c.innerHTML =
      '<div class="j-histh"><span class="badge">' + esc(j.jid) + "</span>" +
        '<span class="j-mono">' + esc(j.issue_id) + " · r" + j.round + "</span>" +
        '<span class="j-ts">' + esc(j.ts.replace("T", " ").replace("Z", "")) + "</span>" +
        // R12(round10): a revert used to be terminal (a dead 'Reverted' chip). Give it the same
        // reversibility dispose() has — a Restore control that clears UI.reverted and re-applies.
        (reverted ? '<span class="chip bad">' + esc(t("j.reverted")) + "</span>" +
                    '<button class="btn sm ghost" data-restore title="' + esc(t("j.redo.tip")) + '"><svg class="i sm"><use href="#jx-undo"/></svg>' + esc(t("j.redo")) + "</button>"
                  : '<button class="btn sm ghost" data-undo title="revert prints the reverse patch"><svg class="i sm"><use href="#jx-undo"/></svg>' + esc(t("j.undo")) + "</button>") +
      "</div>" +
      '<div class="diff j-histdiff"><div class="d-row d-del">' + esc(j.before) + "</div><div class=\"d-row d-add\">" + esc(j.after) + "</div></div>";
    var u = c.querySelector("[data-undo]");
    if (u) u.onclick = function () { UI.reverted[j.jid] = true; persistState(); SB.toast(j.jid + " " + t("j.reverted")); SB.refresh(); };
    var rs = c.querySelector("[data-restore]");
    if (rs) rs.onclick = function () { delete UI.reverted[j.jid]; persistState(); SB.toast(j.jid + " " + t("j.restored")); SB.refresh(); };
    return c;
  }
  function emptyMini(txt) { return el("div", "j-lane-empty", esc(txt)); }

  /* ========================================================================== *
     SUB-VIEW: PANEL — persona cards + coverage heatmap + per-charge trials
     ========================================================================== */
  function renderPanel(main) {
    var pane = el("div", "pane reveal");
    var wrap = el("div", "pane-wide");
    wrap.innerHTML = '<div class="pane-head"><h2>' + esc(t("j.panel.title")) + "</h2>" +
      // R31(d): plain-language subtitle; the raw skill pipeline demoted to a tooltip
      '<span class="sub" title="assign-reviewers → reading-check → coverage-auditor → trial">' + esc(t("j.panel.sub")) + "</span></div>";

    // 1. reviewer persona cards
    var pcard = el("div", "j-block");
    // R20a(round4): substitute the real reviewer count for the %d token (was a literal 'N')
    pcard.innerHTML = '<div class="j-blockh">' + esc(t("j.panel.reviewers").replace("%d", DATA.reviewers.length)) + "</div>";
    var pgrid = el("div", "grid grid-3 j-personas");
    DATA.reviewers.forEach(function (r) { pgrid.appendChild(personaCard(r)); });
    pcard.appendChild(pgrid);
    wrap.appendChild(pcard);

    // 2. coverage heatmap
    var hcard = el("div", "j-block");
    hcard.innerHTML = '<div class="j-blockh">' + esc(t("j.panel.coverage")) + "</div>";
    hcard.appendChild(coverageHeat());
    wrap.appendChild(hcard);

    // 3. per-charge trial view
    var tcard = el("div", "j-block");
    // R17(round7): the jurors are a body SEPARATE from reviewers R1-R3 — say so where the
    // juror tally first appears, and substitute the real reviewer range + base jury size.
    var revIds = DATA.reviewers.map(function (r) { return r.reviewer_id; });
    var revRange = revIds.length > 1 ? (revIds[0] + "–" + revIds[revIds.length - 1]) : (revIds[0] || "R1");
    var baseJury = 5;
    DATA.trials.forEach(function (tr) { if (tr.jury_size && !tr.escalated) baseJury = tr.jury_size; });
    var juryGloss = t("j.jury.gloss").replace("%r", revRange).replace("%n", baseJury);
    tcard.innerHTML = '<div class="j-blockh">' + esc(t("j.panel.trials")) + " · " + DATA.trials.length + "</div>" +
      '<div class="j-jurygloss"><svg class="i sm"><use href="#jx-scale"/></svg><span>' + esc(juryGloss) + "</span></div>" +
      '<div class="j-trialnote">' + voteLegend() + "</div>";
    DATA.trials.forEach(function (tr) { tcard.appendChild(trialCard(tr)); });
    wrap.appendChild(tcard);

    // 4. R5(20): DROPPED charges with NO per-juror trial record on file — listed with tally +
    // notes so every dismissal stays auditable even without a full trial scorecard.
    var droppedNoTrial = DATA.ledger.filter(function (r) { return r.status === "dropped" && !trialFor(r.id); });
    if (droppedNoTrial.length) {
      var dcard = el("div", "j-block");
      dcard.innerHTML = '<div class="j-blockh">' + esc(t("j.drop.audit")) + " · " + droppedNoTrial.length + "</div>" +
        '<div class="j-trialnote">' + esc(t("j.drop.audit.sub")) + "</div>";
      droppedNoTrial.forEach(function (r) { dcard.appendChild(dropAuditRow(r)); });
      wrap.appendChild(dcard);
    }

    pane.appendChild(wrap);
    main.appendChild(pane);

    // R5(20): the audit rows deep-link to the charge on the docket
    wrap.querySelectorAll("[data-jopenpanel]").forEach(function (n) {
      n.onclick = function () { UI.open = n.getAttribute("data-jopenpanel"); SB.setSub("docket"); };
    });

    // R14: arrived here from a charge's "see the trial record" link — scroll+flash it
    if (FOCUS_TRIAL) {
      var want = FOCUS_TRIAL; FOCUS_TRIAL = null;
      var tc = main.querySelector('[data-trial="' + want + '"]');
      if (tc && tc.scrollIntoView) {
        try { tc.scrollIntoView({ behavior: "smooth", block: "center" }); } catch (e) { tc.scrollIntoView(); }
        tc.classList.add("j-trial-flash");
        setTimeout(function () { tc.classList.remove("j-trial-flash"); }, 1600);
      }
    }
  }

  function personaCard(r) {
    var c = el("div", "persona j-persona");
    c.innerHTML =
      '<div class="j-phead"><span class="badge">' + esc(r.reviewer_id) + "</span>" +
        '<span class="chip' + (r.unverified ? " bad" : " ok") + '" title="overall_confidence 1–5">' + esc(t("j.conf")) + " " + r.overall_confidence + "/5</span>" +
        (r.unverified ? '<span class="chip stale" title="assignment_unverified — degraded to a generic gatekeeper"><svg class="i sm"><use href="#jx-warn"/></svg>' + esc(t("j.unverified")) + "</span>" : "") + "</div>" +
      '<div class="pn">' + esc(r.domain) + "</div>" +
      '<div class="pd">' + esc(r.persona_prompt) + "</div>";
    return c;
  }

  // reviewer × section heatmap. The auditor FLAGS skimmed pairs; unflagged = presumed
  // covered (rendered neutral, never claimed 'thorough' unless the auditor said so).
  function coverageHeat() {
    // R20c(round4): derive columns from the UNION of every coverage-flag section AND every
    // distinct ledger section (via the shared sectionColOf), so §1 / §10 render instead of
    // being silently dropped by a hard-coded list that started at §2 and stopped at §9.
    var colSet = {};
    DATA.coverage_flags.forEach(function (f) { var k = sectionColOf(f.section); if (k) colSet[k] = true; });
    DATA.ledger.forEach(function (r) { var k = sectionColOf(r.section); if (k) colSet[k] = true; });
    function colRank(c) {
      if (c === "Abstract") return -1;
      if (c === "App A") return 999;
      var m = c.match(/§(\d+)/); return m ? parseInt(m[1], 10) : 500;
    }
    var cols = Object.keys(colSet).sort(function (a, b) { return colRank(a) - colRank(b); });
    var flagByCell = {};
    DATA.coverage_flags.forEach(function (f) { var k = sectionColOf(f.section); if (k) flagByCell[f.reviewer_id + "|" + k] = f; });

    // R21: an honest one-line summary so absence-of-evidence never reads as coverage.
    var nThorough = 0, nLight = 0, nSkipped = 0;
    Object.keys(flagByCell).forEach(function (k) { var s = flagByCell[k].status; if (s === "thorough") nThorough++; else if (s === "light") nLight++; else nSkipped++; });
    var total = DATA.reviewers.length * cols.length;
    var nUnflagged = total - (nThorough + nLight + nSkipped);
    function hs(cls, n, label) { return '<span class="j-hs ' + cls + '"><i class="sw ' + cls + '"></i>' + n + " " + esc(label) + "</span>"; }
    var summary = el("div", "j-heat-summary",
      '<span class="j-hs-lead">' + esc(t("j.cov.summary")) + ":</span>" +
      hs("thorough", nThorough, t("j.cov.thorough")) +
      hs("light", nLight, t("j.cov.light")) +
      hs("skipped", nSkipped, t("j.cov.skipped")) +
      hs("noflag", nUnflagged, t("j.cov.unflagged")));

    var wrap = el("div", "j-heatwrap");
    summary.id = "j-cov-summary";
    wrap.appendChild(summary);
    var en = SB.state && SB.state.lang === "en";
    function covWord(s) { return s === "thorough" ? t("j.cov.thorough") : s === "light" ? t("j.cov.light") : t("j.cov.skipped"); }
    // R5(round7): a full, localized SR label for every cell (screen readers got only a bare glyph before).
    function cellLabel(rvId, col, s, iss) {
      var w = covWord(s);
      return en ? (rvId + " × " + col + " — " + w + " coverage" + (iss ? ", " + t("j.cov.opens") + " " + iss : ""))
                : (rvId + " × " + col + " — 覆盖" + w + (iss ? "," + t("j.cov.opens") + " " + iss : ""));
    }
    // R5(round7): promote to a real ARIA grid (role=grid + row/columnheader/rowheader/gridcell +
    // caption via aria-describedby). Row wrappers use display:contents so the CSS grid still lays
    // the leaf cells out in one track — ARIA reads DOM, CSS reads layout, both stay correct.
    var grid = el("div", "heat j-heat");
    grid.setAttribute("role", "grid");
    grid.setAttribute("aria-label", t("j.panel.coverage"));
    grid.setAttribute("aria-describedby", "j-cov-summary");
    grid.style.gridTemplateColumns = "92px repeat(" + cols.length + ",1fr)";
    var html = '<div class="j-heat-row" role="row"><div class="j-hh j-corner" role="columnheader"></div>';
    cols.forEach(function (c) { html += '<div class="j-hh" role="columnheader">' + esc(c) + "</div>"; });
    html += "</div>";
    DATA.reviewers.forEach(function (rv) {
      html += '<div class="j-heat-row" role="row"><div class="j-hr" role="rowheader" title="' + esc(rv.domain) + '">' + esc(rv.reviewer_id) + "</div>";
      cols.forEach(function (c) {
        var f = flagByCell[rv.reviewer_id + "|" + c];
        if (f) {
          var g = f.status === "thorough" ? "✓" : f.status === "light" ? "◐" : "○";
          // R18: a light/skipped cell is a skim GAP — the cell filters the docket to that
          // section, or opens the stalled charge (I-NN) the flag named.
          var iss = (String(f.reason).match(/\bI-\d+\b/) || [])[0] || "";
          var act = (f.status === "light" || f.status === "skipped");
          // R5(round7): FLATTEN — the actionable cell is a SINGLE control (a focusable gridcell);
          // the I-NN badge is now a non-interactive span (was a nested <button>, invalid nesting).
          var attrs = act ? (' data-covcol="' + esc(c) + '"' + (iss ? ' data-covissue="' + esc(iss) + '"' : "") + ' tabindex="0"') : "";
          html += '<div class="cell ' + f.status + (act ? " j-cell-act" : "") + '" role="gridcell"' + attrs +
            ' aria-label="' + esc(cellLabel(rv.reviewer_id, c, f.status, act ? iss : "")) + '"' +
            ' title="' + esc(rv.reviewer_id + " × " + c + " — " + f.status + ": " + f.reason) + '">' + g +
            (act && iss ? '<span class="j-cellchip" aria-hidden="true">' + esc(iss) + "</span>" : "") +
            "</div>";
        } else {
          // R17(round7): the blank cell now matches the summary strip — no positive coverage
          // evidence (not "presumed covered", which contradicted the strip).
          var blank = esc(rv.reviewer_id + " × " + c + " — " + t("j.cov.blank"));
          html += '<div class="cell j-noflag" role="gridcell" aria-label="' + blank + '" title="' + blank + '">·</div>';
        }
      });
      html += "</div>";
    });
    grid.innerHTML = html;
    // R18: wire cell → docket. goSection filters the board to a section (when it holds
    // charges); openIssue jumps straight to a stalled charge. Both land on the docket.
    function goSection(col) {
      if (!DATA.ledger.some(function (r) { return chargeInSection(r, col); })) return false;
      SECTION_FILTER = col; FILTER = null; UI.open = null; persistState(); SB.setSub("docket"); return true;
    }
    function openIssue(id) { if (id && byId(id)) { UI.open = id; SB.setSub("docket"); return true; } return false; }
    // R5(round7): one control per cell — a named charge (I-NN) opens it; otherwise filter the section.
    function cellActivate(cell) {
      var col = cell.getAttribute("data-covcol"), iss = cell.getAttribute("data-covissue");
      if (iss && openIssue(iss)) return;
      if (goSection(col)) return;
      SB.toast(SB.state && SB.state.lang === "en" ? ("No charges in " + col) : (col + " 没有指控"));
    }
    grid.addEventListener("click", function (e) {
      var cell = e.target.closest(".j-cell-act"); if (cell) cellActivate(cell);
    });
    grid.addEventListener("keydown", function (e) {
      if (e.key !== "Enter" && e.key !== " ") return;
      var cell = e.target.closest(".j-cell-act"); if (cell) { e.preventDefault(); cellActivate(cell); }
    });
    wrap.appendChild(grid);
    // R22: single heatmap legend — the top summary strip already carries the swatch key
    // + counts, so the formerly-duplicated bottom legend is dropped (one unified label).
    return wrap;
  }

  function trialCard(tr) {
    var c = el("div", "card j-trial");
    c.setAttribute("data-trial", tr.issue_id);   // R14: scroll+flash target from a charge link
    var cls = VERDICT_CLASS[tr.verdict] || "neutral";
    var votesHTML = tr.votes.map(function (v, i) {
      var vk = v.vote === "valid" ? "valid" : v.vote === "invalid" ? "invalid" : "lim";
      // R17(round7): each juror carries a stable id J1…J5 (DOM id scoped by issue_id to stay unique)
      var jid = "J" + (i + 1);
      return '<li class="jv jv-' + vk + '" id="' + esc(tr.issue_id) + "-" + jid + '"><span class="jv-jid">' + jid + "</span>" +
        '<span class="vlabel">' + esc(v.vote) + "</span>" + esc(v.reason) + "</li>";
    }).join("");
    // R24(round9): the jury-size chip is self-explanatory now that the gloss states the
    // model once. An escalated tier reads '5 → 12 (escalated)'; an odd base-tier count
    // (e.g. 7) is a number of FRAMINGS considered, not jurors — labelled as such.
    var chip;
    if (tr.escalated && tr.jury_size >= 12) chip = esc(t("j.jury.esc"));
    else if (tr.jury_size && tr.jury_size !== 5 && tr.jury_size !== 12) chip = esc(t("j.jury.framings").replace("%n", tr.jury_size));
    else chip = esc(t("j.jury.size")) + " " + tr.jury_size;
    c.innerHTML =
      '<div class="j-th">' +
        '<span class="badge">' + esc(tr.charge_id) + " · " + esc(tr.issue_id) + "</span>" +
        '<span class="j-sec">' + esc(tr.section) + "</span>" +
        '<span class="j-thsp"></span>' +
        '<span class="chip">' + chip + "</span>" +
        (tr.escalated ? '<span class="badge j-esc" title="escalated to the 12-juror tier"><svg class="i sm"><use href="#jx-gavel"/></svg>' + esc(t("j.esc")) + "</span>" : "") +
      "</div>" +
      '<div class="j-tsum">' + esc(tr.summary) + "</div>" +
      // R6: the charge's REAL docket status (dropped / author-required / …), not a
      // synthetic "decided" that made every closed verdict read the same.
      verdictBanner(tr.verdict, (byId(tr.issue_id) || {}).status || (tr.verdict === "escalate" ? "in-trial" : "decided")) +
      // R27: skim-gap caveat when the tried section was skipped/light in coverage
      coverageGapBanner(tr.section) +
      '<div class="j-votes">' + votebar(tr.tally) + "</div>" +
      // the whole-paper steelman defense + grounds
      '<div class="j-defense"><div class="dh"><svg class="i sm"><use href="#jx-shield"/></svg>' + esc(t("j.defense")) +
        ' <span class="chip">' + esc(t("j.grounds")) + ": " + esc(tr.defense.grounds) + "</span></div>" +
        "<p>" + esc(tr.defense.defense) + "</p></div>" +
      '<div class="j-rationale"><b>rationale.</b> ' + esc(tr.rationale) + "</div>" +
      // expandable per-juror reasons (native <details> = accessible, no JS)
      // R20b(round4): when fewer reasons are on file than the jury size (escalated tiers
      // disclose only a sampled subset), label it as an excerpt "N / M" rather than
      // implying every juror's reasoning is shown.
      '<details class="j-jurors"><summary>' +
        (tr.votes.length < tr.jury_size
          ? esc(t("j.jurors.label")) + " · " + esc(t("j.excerpt")) + " " + tr.votes.length + " / " + tr.jury_size
          : tr.votes.length + " " + esc(t("j.jurors"))) +
        "</summary>" +
        '<ol class="j-jlist">' + votesHTML + "</ol></details>";
    return c;
  }

  // R5(20): an audit row for a charge dropped WITHOUT a trial scorecard — the tally + the
  // clerk's notes are the whole record of the dismissal, so both are shown verbatim.
  function dropAuditRow(r) {
    var c = el("div", "card j-dropaudit");
    c.innerHTML =
      '<div class="j-th"><span class="badge">' + esc(r.id) + "</span>" +
        '<span class="j-sec">' + esc(r.section) + "</span>" +
        '<span class="j-thsp"></span>' + sigChip(r) + verdictChip(r.verdict) +
        '<span class="j-conf">' + esc(t("j.conf")) + " " + r.reviewer_confidence + "/5</span></div>" +
      '<div class="j-tsum">' + esc(r.summary) + "</div>" +
      '<div class="j-votes">' + votebar(r.tally) + "</div>" +
      (r.notes ? '<div class="j-rationale"><b>' + esc(t("j.drop.reason")) + ".</b> " + esc(r.notes) + "</div>" : "") +
      '<div class="j-revact"><button class="btn sm ghost" data-jopenpanel="' + esc(r.id) + '">' +
        '<svg class="i sm"><use href="#jx-scale"/></svg>' + esc(t("j.drop.open")) + "</button></div>";
    return c;
  }

  /* ========================================================================== *
     SUB-VIEW: SHIELD — compile banner + desk-reject checklist + convergence
     ========================================================================== */
  // R12(round10): module-scope projection — the docket AND the Shield both preview the same
  // disposed-but-unwritten gate through these, so the two screens can never disagree.
  var GATE_STATUS = { raised:1, "in-trial":1, "re-trial":1, "valid-fixable":1 };
  function projStatus(r) {
    if (UI.applied[r.id]) return "closed";           // f / accept → fixable applied
    if (UI.rejected[r.id]) return "dropped";         // r / reject → dropped
    if (UI.routed[r.id]) return "author-required";   // a / route  → handed to the author
    return r.status;
  }
  function computeProjected() {
    return {
      blocking: DATA.ledger.filter(function (r) { return r.significance === "major" && !!GATE_STATUS[projStatus(r)]; }).length,
      authorPending: DATA.ledger.filter(function (r) { return r.significance === "major" && (projStatus(r) === "author-required" || projStatus(r) === "queued"); }).length
    };
  }

  // R28: the docket's gate calc, reused so the Shield can LEAD with the same go/no-go
  // verdict — otherwise a submitter reads 'compiles' + 'pass-with-warnings' as submittable
  // while the real gate-blocking majors sit on another screen.
  function shieldReadiness() {
    var GATE = { raised:1, "in-trial":1, "re-trial":1, "valid-fixable":1 };
    var blocking = DATA.ledger.filter(function (r) { return r.significance === "major" && !!GATE[r.status]; }).length;
    var authorPending = DATA.ledger.filter(function (r) {
      return r.significance === "major" && (r.status === "author-required" || r.status === "queued");
    }).length;
    return { blocking: blocking, authorPending: authorPending, converged: !!(DATA.clerk && DATA.clerk.converged) };
  }

  function renderShield(main) {
    // R31(f): jury.css forces this pane's content to paint on the first frame (the shared
    // .reveal rise transition otherwise held the single child invisible during entrance).
    var pane = el("div", "pane reveal j-shieldpane");
    var wrap = el("div", "pane-wide");
    var miss = readMiss();
    var rdy = shieldReadiness();
    // R12(round10): feed the SAME projected readiness the docket uses so both screens agree.
    var proj = computeProjected();
    wrap.innerHTML = '<div class="pane-head"><h2>' + esc(t("j.shield.title")) + "</h2>" +
      // R31(d): plain-language subtitle; the raw stage pipeline demoted to a tooltip
      '<span class="sub" title="compile-guard · compliance-check · clerk convergence">' + esc(t("j.shield.sub")) + "</span></div>" +
      // R1: broken-dir honesty banner — the passing compile/compliance below is SAMPLE,
      // never this manuscript, so a fully-passing desk-reject report can't masquerade.
      (miss ? sampleBannerHTML() : "") +
      // R28: the unified go/no-go leads the Shield, same verdict the docket shows
      // R12(round10): pass proj so the Shield previews the disposed-but-unwritten gate too
      readinessBar(rdy.blocking, rdy.authorPending, rdy.converged, miss, proj);

    // R1: grey/suppress the passing metrics under couldNotRead so "Compiles clean" and a
    // "pass" desk-reject never read as this run's real, cleared shield.
    var metrics = el("div", "j-shieldmetrics" + (miss ? " j-suppressed" : ""));
    metrics.appendChild(compileBanner(DATA.compile));
    var grid = el("div", "grid grid-2 j-shieldgrid");
    grid.appendChild(complianceCard(DATA.compliance));
    grid.appendChild(convergenceCard(DATA.clerk));
    metrics.appendChild(grid);
    wrap.appendChild(metrics);

    pane.appendChild(wrap);
    main.appendChild(pane);
    if (miss) wireSampleBanner(wrap);
  }

  // honest degrade: compiled===null → "compile not run" (never a fake pass)
  function compileBanner(cp) {
    var b = el("div", "card j-compile");
    if (cp.compiled === null || cp.compiled === undefined) {
      b.className = "card j-compile notrun";
      b.innerHTML = '<div class="j-cbig"><svg class="i"><use href="#jx-warn"/></svg><b>' + esc(t("j.compile.notrun")) + "</b></div>" +
        '<div class="j-cnote">' + esc(t("j.notrun.note")) + "</div>";
      return b;
    }
    // R5(25): green is reserved for a genuinely clean build — 0 errors AND 0 layout warnings.
    // A build that compiled but carries overfull/underfull/undefined warnings is amber, not
    // green, so "Compiles clean" can never sit over "3 layout warnings".
    var warns = (cp.overfull || 0) + (cp.underfull || 0) + (cp.undefined ? cp.undefined.length : 0);
    var hasErr = !cp.ok || cp.errors.length > 0;
    var state = hasErr ? "err" : (warns > 0 ? "warn" : "clean");
    var head = state === "err" ? t("j.compile.err") : state === "warn" ? t("j.compile.warn") : t("j.compile.clean");
    b.className = "card j-compile " + state;
    b.innerHTML =
      '<div class="j-cbig"><svg class="i"><use href="#' + (state === "clean" ? "jx-check" : "jx-warn") + '"/></svg>' +
        "<b>" + esc(head) + "</b>" +
        '<span class="j-cmode">' + esc(cp.mode) + "</span></div>" +
      '<div class="j-cstats">' +
        cStat(cp.errors.length, t("j.errors"), cp.errors.length ? "bad" : "ok") +
        cStat(warns, t("j.warns"), warns ? "stale" : "ok") +
        cStat(cp.pages, t("j.pages"), "") +
        cStat(cp.bib_entries, t("j.bibentries"), "") +
      "</div>" +
      '<div class="j-cnote">' + esc(cp.overfull + " overfull · " + cp.underfull + " underfull · " + (cp.undefined.length) + " undefined refs/cites") +
        " · <span class=\"j-mono\">compiled: " + String(cp.compiled) + "</span></div>";
    return b;
  }
  function cStat(v, k, tone) { return '<div class="j-cstat"><span class="v ' + (tone || "") + '">' + esc(String(v)) + '</span><span class="k">' + esc(k) + "</span></div>"; }

  /* ---- R19: bilingual compliance-check descriptions ------------------------- *
   * The desk-reject details ship as English report text; in the zh shell they read as
   * an unlocalized leak. For the known SAMPLE details we carry a zh/en pair keyed on the
   * rule and swap by lang(). A LIVE adapter may emit a different (single-language) detail
   * we can't translate — then we show it verbatim and stamp an honest 'source: <lang>' tag
   * so a mixed card is explained, never left looking half-broken. */
  var COMPLIANCE_I18N = {
    "anonymity": { en:"No author names, affiliations, or funding acknowledgements found in the submission body.",
      zh:"正文中未发现作者姓名、单位或资助致谢。" },
    "self-citation-leak": { en:"3 self-references phrased as 'our prior work'; acceptable but reviewers may de-anonymize. Consider third-person.",
      zh:"3 处自引用写成「我们此前的工作」;虽可接受,但可能被评审去匿名化,建议改用第三人称。" },
    "page-limit": { en:"Body is 8 pages + references; within the 9-page ML limit (references excluded).",
      zh:"正文 8 页 + 参考文献;在 ML 的 9 页上限内(参考文献不计)。" },
    "required-sections": { en:"Abstract, Introduction, Method, Experiments, Limitations, Broader Impact all present.",
      zh:"摘要、引言、方法、实验、局限性、更广泛影响均齐备。" },
    "documentclass": { en:"Uses the official style file; \\documentclass options within the allowed set.",
      zh:"使用官方样式文件;\\documentclass 选项在允许范围内。" },
    "margin-hacking": { en:"No \\vspace/\\hspace negative-margin tricks or font-size reductions detected.",
      zh:"未检测到 \\vspace/\\hspace 负边距技巧或字号缩小。" },
    "reproducibility-checklist": { en:"NeurIPS-style checklist present but 2 items answered 'N/A' without justification.",
      zh:"存在 NeurIPS 式清单,但有 2 项回答「N/A」却未说明理由。" },
  };
  // returns {text, srcTag}: srcTag is set only when a live/unknown detail can't be relocalized
  function complianceDetail(ck) {
    var en = SB.state && SB.state.lang === "en";
    var pair = COMPLIANCE_I18N[ck.rule];
    var known = pair && (ck.detail === pair.en || ck.detail === pair.zh);
    if (known) return { text: en ? pair.en : pair.zh, srcTag: null };
    // a live adapter's own (assumed-English) text we can't translate — verbatim + honest stamp
    return { text: ck.detail, srcTag: en ? null : "en" };
  }

  function complianceCard(cc) {
    var c = el("div", "card j-block2");
    var overallTone = cc.overall === "pass" ? "ok" : cc.overall === "fail" ? "bad" : "stale";
    // R22(round7): sort fail → warn → pass so the ⚠/✗ rows lead instead of being buried among the
    // green ✓, and headline the mix ('1 warning · 6 pass') so the balance reads at a glance.
    var rank = { fail: 0, warn: 1, pass: 2 };
    var checks = cc.checks.slice().sort(function (a, b) {
      return (rank[a.status] == null ? 3 : rank[a.status]) - (rank[b.status] == null ? 3 : rank[b.status]);
    });
    var enCk = SB.state && SB.state.lang === "en";
    var nf = 0, nw = 0, np = 0;
    cc.checks.forEach(function (ck) { if (ck.status === "fail") nf++; else if (ck.status === "warn") nw++; else np++; });
    var parts = [];
    if (enCk) {
      if (nf) parts.push(nf + " failing");
      if (nw) parts.push(nw + " warning" + (nw !== 1 ? "s" : ""));
      parts.push(np + " pass");
    } else {
      if (nf) parts.push(nf + " 项未过");
      if (nw) parts.push(nw + " 项警告");
      parts.push(np + " 项通过");
    }
    c.innerHTML = '<div class="card-h"><span class="kick">' + esc(t("j.shield.desk")) + "</span>" +
      '<h3>' + esc(t("j.shield.title")) + '</h3><span class="chip ' + overallTone + '" style="margin-left:auto">' + esc(cc.overall) + "</span></div>" +
      '<div class="j-deskcount">' + esc(parts.join(" · ")) + "</div>";
    checks.forEach(function (ck) {
      var tone = ck.status === "pass" ? "pass" : ck.status === "warn" ? "warn" : "fail";
      var icon = ck.status === "pass" ? "jx-check" : ck.status === "warn" ? "jx-warn" : "jx-close";
      var det = complianceDetail(ck);
      c.appendChild(el("div", "j-check " + tone,
        '<svg class="i sm j-ckico"><use href="#' + icon + '"/></svg>' +
        '<div class="j-cktx"><div class="j-ckrule">' + esc(ck.rule) + "</div>" +
        '<div class="j-ckdetail">' + esc(det.text) +
          (det.srcTag ? ' <span class="j-src-tag" title="source: ' + esc(det.srcTag) + '">source: ' + esc(det.srcTag) + "</span>" : "") +
          "</div></div>"));
    });
    if (cc.skipped_checks && cc.skipped_checks.length)
      c.appendChild(el("div", "j-cnote", "skipped_checks: " + esc(cc.skipped_checks.join(", "))));
    return c;
  }

  function convergenceCard(ck) {
    var c = el("div", "card j-block2");
    c.innerHTML = '<div class="card-h"><span class="kick">clerk</span><h3>' + esc(t("j.shield.conv")) + "</h3>" +
      (ck.converged ? '<span class="j-stamp" style="margin-left:auto"><svg class="i sm"><use href="#jx-check"/></svg>' + esc(t("j.converged")) + "</span>"
                    : '<span class="chip stale" style="margin-left:auto">' + esc(t("j.notconverged")) + "</span>") + "</div>";
    // per-round counts
    var counts = el("div", "grid grid-3 j-convstats");
    counts.innerHTML =
      convStat(ck.genuinely_new_count, t("j.genuinelynew"), "") +           // R5-jury(round10): localized; still glossed below (R9)
      convStat(ck.new_closures_count, t("j.lane.closed"), "ok") +           // R5(round6): localize the lane words
      convStat(ck.new_author_required_count, t("j.lane.author-required"), "stale") +
      convStat(ck.queued, t("j.lane.queued"), "") +
      convStat(ck.dropped, t("j.lane.dropped"), "bad") +
      convStat(ck.withdrawn, t("j.lane.withdrawn"), "");
    c.appendChild(counts);
    // R9: a newcomer gloss so "genuinely new" / "converged" are legible without insider context
    c.appendChild(el("div", "j-conv-gloss", '<svg class="i sm"><use href="#jx-scale"/></svg><span>' + esc(t("j.conv.gloss")) + "</span>"));
    // round timeline: round 1 (now) → round 2 (pending) with the converged test
    // R27: state the round budget ('Round N of max M') + the terminal rule on non-convergence
    var maxR = ck.max_rounds || 3;             // bounded-revision cap; a real adapter may override
    var enCv = SB.state && SB.state.lang === "en";
    // R5-jury(round10): the Round-1 narrative was a hardcoded English sentence shown verbatim in zh.
    // Prefer the paired reason_{en,zh}; fall back to a single-language `reason` (LIVE adapter).
    var reasonText = enCv ? (ck.reason_en || ck.reason || "") : (ck.reason_zh || ck.reason || "");
    var tl = el("div", "timeline j-convtl");
    tl.innerHTML =
      '<div class="tl-node now"><div class="tl-t">' +
        (enCv ? ("Round " + ck.round + " · +" + ck.genuinely_new_count + " new")
              : ("第 " + ck.round + " 轮 · 新增 " + ck.genuinely_new_count + " 项")) + "</div>" +
        '<div class="tl-d">' + esc(reasonText) + "</div></div>" +
      '<div class="tl-node"><div class="tl-t">' +
        (enCv ? ("Round " + (ck.round + 1) + " of max " + maxR + " · pending")
              : ("第 " + (ck.round + 1) + " 轮 / 上限 " + maxR + " · 待定")) + "</div>" +
        '<div class="tl-d">' + (enCv ? "A round that adds nothing new emits the converged stamp." : "若某轮不再产生新问题,即盖上「已收敛」印。") +
          ' <span class="j-conv-terminal">' + esc(t("j.conv.terminal")) + "</span></div></div>";
    c.appendChild(tl);
    return c;
  }
  function convStat(v, k, tone) { return '<div class="j-cstat sm"><span class="v ' + (tone || "") + '">' + esc(String(v)) + '</span><span class="k">' + esc(k) + "</span></div>"; }

  /* ========================================================================== *
     SUB-VIEW: EXAMPLE — the worked dogfood run (RUN_REPORT tables as cards)
     ========================================================================== */
  function renderExample(main) {
    var r = DATA.run;
    var pane = el("div", "pane reveal j-expane");
    var wrap = el("div", "pane-wide");
    wrap.innerHTML = '<div class="pane-head"><h2>' + esc(t("j.ex.title")) + "</h2>" +
      '<span class="sub">' + esc(t("j.ex.sub")) + "</span></div>";

    // the before/after story: 152 → 55 → 26 / 10 / 19
    var flow = el("div", "j-flow");
    flow.innerHTML =
      flowNode(r.weaknesses, "reviewer weaknesses", "") + flowArrow() +
      flowNode(r.issues, "merged issues", "") + flowArrow() +
      '<div class="j-flowsplit">' +
        flowNode(r.applied, "applied", "ok") +
        flowNode(r.queued, "queued", "stale") +
        flowNode(r.dropped, "dropped", "bad") +
      "</div>";
    wrap.appendChild(flow);

    // before/after PDFs
    var pdfs = el("div", "grid grid-2 j-pdfs");
    pdfs.appendChild(pdfCard("jx-doc", t("j.ex.orig"), r.input, "original_draft.pdf", false));
    pdfs.appendChild(pdfCard("jx-doc", t("j.ex.rev"), r.output, "revised_draft.pdf", true));
    wrap.appendChild(pdfs);

    // taxonomy tables F / A / B / engine-introduced
    r.tables.forEach(function (tb) { wrap.appendChild(taxTable(tb)); });

    // summary bullets
    var sum = el("div", "card j-sumcard");
    sum.innerHTML = '<div class="card-h"><span class="kick">summary</span><h3>' + (SB.state && SB.state.lang === "en" ? "What the round proved" : "这一轮证明了什么") + "</h3></div>" +
      "<ul class=\"j-sumlist\">" + r.summary.map(function (s) { return "<li>" + esc(s) + "</li>"; }).join("") + "</ul>";
    wrap.appendChild(sum);

    pane.appendChild(wrap);
    main.appendChild(pane);

    wrap.querySelectorAll("[data-pdf]").forEach(function (n) {
      n.onclick = function () { SB.toast((SB.state && SB.state.lang === "en" ? "Would open " : "将打开 ") + n.getAttribute("data-pdf")); };
    });
  }
  function flowNode(v, k, tone) { return '<div class="j-flownode"><span class="v ' + (tone || "") + '">' + esc(String(v)) + '</span><span class="k">' + esc(k) + "</span></div>"; }
  function flowArrow() { return '<div class="j-flowarr">→</div>'; }
  function pdfCard(icon, label, meta, file, revised) {
    return SB.el("div", "card j-pdf" + (revised ? " j-pdf-rev" : ""),
      '<div class="j-pdfico"><svg class="i"><use href="#' + icon + '"/></svg></div>' +
      '<div class="j-pdfbody"><div class="j-pdflabel">' + esc(label) + "</div>" +
      '<div class="j-pdfmeta">' + esc(meta) + "</div>" +
      '<button class="btn sm" data-pdf="' + esc(file) + '">' + esc(file) + "</button></div>");
  }
  function taxTable(tb) {
    var c = el("div", "card j-tax j-tax-" + tb.tone);
    var rows = tb.rows.map(function (row) {
      var verified = row[3] === "verified";
      return '<tr><td class="j-txkey"><span class="badge">' + esc(row[0]) + "</span></td>" +
        '<td class="j-txloc">' + esc(row[1]) + "</td>" +
        '<td class="j-txfix">' + esc(row[2]) + "</td>" +
        '<td class="j-txok"><span class="chip ' + (verified ? "ok" : "stale") + '">' +
          (verified ? "✓ verified" : "⚠ pending") + "</span></td></tr>";
    }).join("");
    c.innerHTML =
      '<div class="card-h"><span class="kick j-txk">' + esc(tb.key) + '</span><h3>' + esc(tb.title) + "</h3></div>" +
      '<div class="j-txblurb">' + esc(tb.blurb) + "</div>" +
      '<div class="j-txscroll"><table class="j-txtable"><thead><tr>' +
        "<th></th><th>problem (location)</th><th>fix result</th><th>verified</th></tr></thead>" +
        "<tbody>" + rows + "</tbody></table></div>";
    return c;
  }

  /* ---- workspace-title "source switcher" popover -------------------------- */
  function sourcePop() {
    var old = document.querySelector(".j-srcpop"); var sc = document.querySelector(".scrim");
    if (old) { old.remove(); if (sc) sc.remove(); return; }
    var scrim = el("div", "scrim"); document.body.appendChild(scrim);
    var pop = el("div", "pop j-srcpop");
    pop.innerHTML =
      '<div class="j-srch">' + esc(t("j.source")) + "</div>" +
      '<div class="j-srcrow sel"><svg class="i sm"><use href="#jx-doc"/></svg><div><b>' + esc(DATA.meta.manuscript) + "</b>" +
        '<span class="j-mono">' + esc(DATA.meta.venue_family) + " · " + esc(t("j.mode")) + " " + esc(DATA.meta.mode) + " · " + esc(DATA.meta.run_id) + "</span></div></div>" +
      '<div class="j-srcchain"><svg class="i sm"><use href="#jx-flame"/></svg>' + esc(t("j.chain.sub")) + "</div>";
    document.body.appendChild(pop);
    // anchor under the workspace title
    var host = document.getElementById("sb-wstitle");
    var rct = host ? host.getBoundingClientRect() : { left: 220, bottom: 52 };
    pop.style.left = Math.max(12, rct.left) + "px"; pop.style.top = (rct.bottom + 6) + "px";
    function close() { pop.remove(); scrim.remove(); }
    scrim.onclick = close;
  }

  /* ---- register the tool -------------------------------------------------- */
  SB.registerTool("jury", {
    // manuscript under review — the workspace title doubles as a source switcher.
    // R22(round4): drop the internal 'dogfood' slang (read as part of the paper name) for
    // a localized '· sample run' / '· 示例'.
    title: DATA.meta.manuscript + " · " + t("j.title.sample"),
    onTitle: sourcePop,
    // sub labels resolved via t() at register time (see reported shell gap: they
    // don't live-retranslate on a language toggle — the shell caches sub[].label)
    sub: [
      { id: "docket",    label: t("j.tab.docket") },
      { id: "revisions", label: t("j.tab.revisions") },
      { id: "panel",     label: t("j.tab.panel") },
      { id: "shield",    label: t("j.tab.shield") },
      { id: "example",   label: t("j.tab.example") },
    ],
    render: function (main, sub) {
      ensureJurySprite();
      // Swap the DATA SOURCE (real adapters when a dir is opened; SAMPLE otherwise),
      // then run the existing renderers unchanged and stamp the source hint.
      withData(main, function () {
        hydrateState();                                  // R20: restore this ledger's persisted decisions + filter
        var v = (sub === "revisions" || sub === "panel" || sub === "shield" || sub === "example")
          ? sub : "docket";
        // R29: a ?id= deep-link opens that charge on the first render that lands on the docket
        if (BOOT_ID && !BOOT_DONE) { BOOT_DONE = true; if (v === "docket" && byId(BOOT_ID)) UI.open = BOOT_ID; }
        if (v === "revisions") renderRevisions(main);
        else if (v === "panel") renderPanel(main);
        else if (v === "shield") renderShield(main);
        else if (v === "example") renderExample(main);
        else renderDocket(main); // default + 'docket'
        stampHint(main, v);
      });
    },
  });

  // R15(round4): expose the docket keymap on a shared registry so the shell's global
  // '?' key-help (SB.keyHelp, owned by reader.js) can append the ACTIVE workspace's
  // shortcuts instead of only ever listing reader keys. Harmless data until the shell
  // reads it; the visible+AT .j-kbdhint and aria-keyshortcuts on the board/cards already
  // carry the model in-view. (reader.js still needs to consume SB.workspaceKeys — noted.)
  SB.workspaceKeys = SB.workspaceKeys || {};
  SB.workspaceKeys.jury = function () {
    var en = SB.state && SB.state.lang === "en";
    return [
      ["J / K", en ? "Move down / up in a lane" : "在车道内上下移动"],
      ["H / L", en ? "Move across lanes" : "在车道间移动"],
      ["A", en ? "Send to author" : "交作者定夺"],
      ["R", en ? "Drop (invalid)" : "驳回"],
      ["F", en ? "Mark valid-fixable" : "判定可修"],
      ["X", en ? "Toggle multi-select" : "多选切换"],
      ["Shift+J / Shift+K", en ? "Range-select down / up" : "范围多选(向下 / 向上)"],
      ["Shift+A  /  *", en ? "Select all in this lane" : "选中本车道全部"],
      ["Shift+*", en ? "Select the whole board" : "选中整个判决台"],
      ["Enter", en ? "Open charge" : "打开指控"],
    ];
  };

  // R3/R29: contribute every charge to the shell command palette so ⌘K can jump
  // straight to a charge. Guarded — the shell registers this hook as part of the
  // palette-corpus work; until it exists this is a harmless no-op. The source is a
  // late-bound function, so it always reflects the live DATA.ledger (sample or real).
  if (SB.registerPaletteSource) SB.registerPaletteSource(function () {
    return DATA.ledger.map(function (c) {
      return { id: c.id, label: c.id + " " + c.summary, type: "charge",
        run: function () { SB.setTool("jury"); openCharge(c.id); } };
    });
  });

  // Public hook: open a charge as an article by id (deep-link + screenshot harness).
  // Sets the same module-local state a board click would; back button clears it.
  SB.juryOpenCharge = function (id) { SB.setTool("jury"); if (byId(id)) { UI.open = id; } SB.refresh(); return !!byId(id); };
})();
