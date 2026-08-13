/* spark-to-paper-skills — site behaviors.
   Hand-written vanilla JS: i18n (en/zh), theme cycle, scroll-spy TOC,
   quickstart tabs + copy, reveal-on-scroll, hero pipeline animation. */
(() => {
  "use strict";
  const $ = (s, r) => (r || document).querySelector(s);
  const $$ = (s, r) => Array.from((r || document).querySelectorAll(s));
  const root = document.documentElement;
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)");

  /* ================================ i18n ================================ */
  const dict = {
    /* --- nav --- */
    "nav.home": { en: "Home", zh: "首页" },
    "nav.contents": { en: "Contents", zh: "目录" },
    "nav.overview": { en: "Overview", zh: "总览" },
    "nav.idea": { en: "Core Idea", zh: "核心理念" },
    "nav.pipeline": { en: "Pipeline", zh: "流水线" },
    "nav.figures": { en: "Figure Engine", zh: "画图引擎" },
    "nav.experiments": { en: "Experiments", zh: "实验" },
    "nav.writing": { en: "Writing &amp; Review", zh: "写作与评审" },
    "nav.showcase": { en: "Showcase", zh: "论文展示" },
    "nav.compare": { en: "Compare", zh: "横向对比" },
    "nav.cite": { en: "BibTeX", zh: "引用" },
    "nav.papers": { en: "Papers", zh: "论文" },
    "nav.paper": { en: "Paper", zh: "arXiv" },
    "nav.code": { en: "Code", zh: "代码" },

    /* --- hero --- */
    "hero.subtitle": {
      en: "13 composable Claude Code skills turn a one-line idea into a <strong>compiled paper PDF</strong> — real verified references, editable vector figures, and <strong>machine-checked integrity</strong> included. Claude owns the judgment; deterministic Python gates own the facts. <em>No app. No server. No setup.</em>",
      zh: "13 个可组合的 Claude Code skill，把一句话的想法做成<strong>编译完成的论文 PDF</strong>：参考文献真实且经过核验，插图是可编辑的矢量图，<strong>诚实性由机器校验</strong>。判断交给 Claude，事实交给确定性的 Python 闸门。<em>不装应用，不起服务，零配置。</em>"
    },
    "hero.btn.papers": { en: "See the papers", zh: "看论文成品" },
    "hero.btn.figures": { en: "Figure engine", zh: "画图引擎" },
    "hero.btn.pipeline": { en: "How it works", zh: "工作原理" },
    "hero.btn.code": { en: "Code &middot; 500+ stars", zh: "代码 · 500+ star" },
    "hero.btn.sample": { en: "Sample paper", zh: "论文样例" },
    "hero.btn.sample.aria": { en: "Open a sample generated paper (PDF)", zh: "打开一篇生成的论文样例（PDF）" },
    "hero.btn.release": { en: "v1.2.0", zh: "v1.2.0" },
    "hero.flag.hf": { en: "Daily Papers &middot; Aug 13, 2026", zh: "Daily Papers 日榜 · 2026-08-13" },
    "hero.st1": { en: "citation validity", zh: "引文有效率" },
    "hero.st2": { en: "figure editability", zh: "图可编辑率" },
    "hero.st3": { en: "cost per paper", zh: "单篇成本" },
    "hero.st4": { en: "idea to PDF", zh: "出稿耗时" },
    "pipe.wall.tag": { en: "skills, by name", zh: "个 skill，全员点名" },
    "pipe.wall.o": { en: "orchestrator", zh: "调度器" },
    "hero.related.tag": { en: "13 skills &middot; one orchestrator", zh: "13 个 skill · 一个调度器" },
    "backends.sub": { en: "ts-paper routes any input shape and drives the chain end to end", zh: "无论输入是什么形态，ts-paper 都能路由到位，驱动整条链跑完全程" },
    "backends.in": { en: "You drop", zh: "你丢进来" },
    "backends.out": { en: "You get", zh: "你拿到" },
    "backends.orch": { en: "Stage 0 &middot; route", zh: "Stage 0 · 路由" },
    "backends.a11y": {
      en: "A one-line idea, a proposal, a proposal with real results, or a story from a previous run all route through ts-paper and the 13-skill suite, and come out as a compiled PDF with sources, figures and logs on disk.",
      zh: "无论是一句话想法、proposal、带真实结果的 proposal，还是上次运行留下的 story，都由 ts-paper 路由进这套 13 个 skill 的流程，最终产出编译好的 PDF，源文件、插图和日志也都留在磁盘上。"
    },
    "backends.role.up": { en: "UPSTREAM", zh: "上游" },
    "backends.role.chain": { en: "THE CHAIN", zh: "主链" },
    "backends.role.auto": { en: "AUTO-RUN", zh: "自动实验" },
    "bk.in.idea": { en: "one-line idea", zh: "一句话想法" },
    "bk.open.in": { en: "+ ANY SHAPE", zh: "+ 任意形态" },
    "bk.open.out": { en: "+ ON DISK", zh: "+ 全在磁盘" },

    /* --- quickstart --- */
    "qs.tab.install": { en: "Install", zh: "安装" },
    "qs.tab.run": { en: "First run", zh: "首次运行" },
    "qs.copy.aria": { en: "Copy the visible command", zh: "复制当前命令" },
    "qs.installer.aria": { en: "Install method", zh: "安装方式" },
    "qs.alt.plugin": { en: "plugin", zh: "装成插件" },
    "qs.alt.try": { en: "try&nbsp;first", zh: "先试用" },
    "gates.copy.aria": { en: "Copy the gates command", zh: "复制闸门命令" },
    "bib.copy.aria": { en: "Copy BibTeX", zh: "复制 BibTeX" },
    "theme.label": { en: "Theme", zh: "主题" },
    "theme.system": { en: "system", zh: "跟随系统" },
    "theme.light": { en: "light", zh: "浅色" },
    "theme.dark": { en: "dark", zh: "深色" },
    "qs.hint.install": {
      en: "Auto-loads on the next Claude Code session. Needs Python&nbsp;3.10+ and LaTeX (<code>latexmk</code>) to compile.",
      zh: "下次打开 Claude Code 会话时自动加载。编译需要 Python&nbsp;3.10+ 和 <span style=\"white-space:nowrap\">LaTeX（<code>latexmk</code>）</span>。"
    },
    "qs.hint.run": {
      en: "Paste an idea, a proposal, or a proposal + real results. Stage&nbsp;0 routes it, the chain runs, and every stage leaves its trace under <code>logs/</code>.",
      zh: "把想法、proposal，或者 proposal 加上真实结果直接贴进来。Stage&nbsp;0 先路由，随后整条链跑完，每个阶段的记录都留在 <code>logs/</code> 下。"
    },

    /* --- scoreboard --- */
    "sb.kicker": { en: "Generated end-to-end &middot; zero fabricated numbers", zh: "端到端生成 · 零编造数字" },
    "sb.copy": {
      en: "Seven papers went in as research proposals and came out as compiled, publication-format PDFs. The pipeline planned each paper, verified every reference it cited, drafted and adversarially reviewed the text, drew editable vector figures, and compiled the result &mdash; with deterministic gates checking every step.",
      zh: "七篇论文以研究 proposal 的形式进入流水线，出来时已是出版格式的编译版 PDF。流水线规划每篇论文，逐条核验所引的参考文献，起草正文并做对抗式评审，绘制可编辑的矢量图，最后编译成稿，每一步都有确定性闸门把关。"
    },
    "sb.s1": { en: "papers, end to end", zh: "篇论文，端到端" },
    "sb.s2": { en: "research domains", zh: "个研究领域" },
    "sb.s3": { en: "compiled pages", zh: "页编译成品" },
    "sb.s4": { en: "verified references", zh: "条核验过的引用" },
    "sb.s5": { en: "editable vector figures", zh: "张可编辑矢量图" },
    "sb.note": {
      en: "Totals across the seven showcase papers below. References verified via WebSearch + Crossref; figures delivered as editable vector PDFs; integrity gates passed on all seven.",
      zh: "以上数字是下方七篇 showcase 论文的合计。参考文献经 WebSearch + Crossref 核验，图以可编辑矢量 PDF 交付，七篇的诚实性闸门全部通过。"
    },
    "sbp.kicker": { en: "Measured in the paper", zh: "论文实测" },
    "sbp.sub": {
      en: "Across eight controlled research topics, from instrumented runs and a controlled ablation &mdash; <a href=\"https://arxiv.org/abs/2608.11924\" target=\"_blank\" rel=\"noopener\">arXiv:2608.11924</a>.",
      zh: "覆盖八个受控研究课题，数字来自埋点运行与受控消融实验——<a href=\"https://arxiv.org/abs/2608.11924\" target=\"_blank\" rel=\"noopener\">arXiv:2608.11924</a>。"
    },
    "sbp.k1.name": { en: "Citation validity", zh: "引文有效率" },
    "sbp.k1.metric": { en: "resolved references / total", zh: "可解析引文 / 全部引文" },
    "sbp.k1.delta": { en: "384 refs", zh: "384 条" },
    "sbp.k2.name": { en: "Figure editability", zh: "图可编辑率" },
    "sbp.k2.metric": { en: "editable elements / total", zh: "可编辑元素 / 全部元素" },
    "sbp.k2.delta": { en: "~1,900 elems", zh: "1,900 元素" },
    "sbp.k3.name": { en: "Fabrication detection", zh: "伪造检出率" },
    "sbp.k3.metric": { en: "single pass &rarr; full stack", zh: "单遍成稿 &rarr; 完整体系" },
    "sbp.k3.delta": { en: "36 probes", zh: "36 探针" },
    "sbp.k4.name": { en: "Review precision", zh: "评审精确率" },
    "sbp.k4.metric": { en: "verified / raised issues", zh: "查实意见 / 提出意见" },
    "sbp.k4.delta": { en: "42/57", zh: "42/57" },
    "sbp.k5.name": { en: "Per manuscript", zh: "单篇成本" },
    "sbp.k5.metric": { en: "avg &middot; 11.9M tokens", zh: "单篇平均 · 11.9M token" },

    /* --- overview strip --- */
    "ov.kicker": { en: "Overview", zh: "总览" },
    "ov.title": { en: "Every page below came out of <em>the pipeline</em>.", zh: "下面每一页，都是<em>流水线生成的</em>。" },

    /* --- 01 core idea --- */
    "idea.eyebrow": { en: "Core Idea", zh: "核心理念" },
    "idea.title": { en: "The model does the reasoning. <em>The code keeps it honest.</em>", zh: "模型负责推理，<em>代码负责诚实</em>。" },
    "idea.lede": {
      en: "Autonomous paper generators fail in three familiar ways: they invent numbers, they cite papers that do not exist, and they ship figures nobody can edit. Spark-to-Paper splits every stage between two actors &mdash; <strong>Claude owns the judgment</strong> (writing, research, critique, review) and <strong>deterministic Python gates own the facts</strong>. A red gate does not warn; it fails the build.",
      zh: "自动写论文的系统，常见的翻车方式有三种：编造数字、引用不存在的文献、交出没人能编辑的图。Spark-to-Paper 把每个阶段的工作拆给两个角色：<strong>判断交给 Claude</strong>（写作、检索、批评、评审），<strong>事实交给确定性的 Python 闸门</strong>。闸门亮红不发警告，直接让构建失败。"
    },
    "problem.p1.title": { en: "Fabricated numbers", zh: "编造数字" },
    "problem.p1.body": {
      en: "A draft that needs a result will happily invent one. Once a made-up metric enters the text, every later revision inherits and defends it.",
      zh: "草稿缺个结果，模型就会顺手编一个。编造的指标一旦写进正文，之后每轮修改都会继承它，还会替它辩护。"
    },
    "problem.p2.title": { en: "Phantom citations", zh: "幽灵引用" },
    "problem.p2.body": {
      en: "Title-only stubs generated to hit a quota. They look like a bibliography and collapse at the first reviewer who checks a DOI.",
      zh: "为凑数生成的条目，只有个标题。排出来像模像样，乍看是一份正经的参考文献，审稿人一查 DOI 就露馅。"
    },
    "problem.p3.title": { en: "Dead bitmap figures", zh: "改不动的位图" },
    "problem.p3.body": {
      en: "AI image models produce rasters. A camera-ready paper needs vectors you can still edit the day before the deadline &mdash; not a flattened PNG.",
      zh: "AI 图像模型输出的是位图，可 camera-ready 论文需要矢量图：截稿前一天还得能打开来改，压平的 PNG 做不到。"
    },
    "idea.statement.title": { en: "Machine-checked integrity: not a style suggestion &mdash; a hard stop.", zh: "机器校验的诚实性：不是风格建议，是一道硬闸门。" },
    "idea.statement.body": {
      en: "One command, <code>run_gates.py &lt;workdir&gt; all</code>, chains the suite&rsquo;s finish-line gates and exits nonzero on the first red one: citation completeness, no-fabrication, word bands, editable-vector presence, figure-critique traces, and a zero-error LaTeX log. A nonzero exit means the paper is <em>not done</em> &mdash; no matter how good it looks.",
      zh: "一条命令 <code>run_gates.py &lt;workdir&gt; all</code> 把套件的完工闸门串起来跑，碰到第一个红色闸门就以非零码退出。检查项包括：引用完整性、不编造、字数区间、可编辑矢量图在位、图批评留痕，以及零报错的 LaTeX 日志。只要退出码非零，论文就<em>还没完成</em>，看起来再漂亮也不算。"
    },
    "idea.fig.caption": {
      en: "<b>From spark to paper.</b> The project&rsquo;s README banner &mdash; the workflow at a glance: one spark goes in; Claude Code drives the literature search, the experiments and the writing; a finished paper comes out.",
      zh: "<b>从火花到论文。</b>项目 README 的横幅，一张图概括整个工作流：输入一颗火花，Claude Code 驱动文献检索、实验和写作，输出一篇完整的论文。"
    },
    "idea.f1.value": { en: "Claude", zh: "Claude" },
    "idea.f1.title": { en: "Model reasons", zh: "模型负责判断" },
    "idea.f1.body": {
      en: "Judgment-heavy work stays with the model: framing the story, planning the blueprint, reading candidate references, writing and refining prose, critiquing figures with its own vision, arguing against the draft in review.",
      zh: "重判断的工作留在模型手里：确定论文的叙事框架、规划 blueprint、阅读候选文献、撰写并打磨行文、用自己的视觉能力批评图，以及在评审环节跟草稿唱反调。"
    },
    "idea.f2.value": { en: "Python", zh: "Python" },
    "idea.f2.title": { en: "Code backstops", zh: "代码负责兜底" },
    "idea.f2.body": {
      en: "Deterministic tasks go to code: linting drafts, checking citation completeness, plotting from data, vectorizing figures, assembling LaTeX, compiling, and gating. Code never authors content; it only verifies it.",
      zh: "确定性的工作交给代码：对草稿做 lint、核对引用完整性、按数据画图、把图矢量化、组装 LaTeX、编译、把守闸门。代码从不撰写内容，只负责核验内容。"
    },
    "idea.p1.title": { en: "Layer 1 &middot; Deterministic gates", zh: "第一层 · 确定性闸门" },
    "idea.p1.body": {
      en: "Section shape, word bands, no-fabrication, citation completeness, vector-PDF presence, compile status. Run per stage or all at once; the first red gate stops the line.",
      zh: "检查覆盖章节结构、字数区间、不编造、引用完整性、矢量 PDF 在位、编译状态。可以逐阶段跑，也可以一次全跑；第一个红色闸门一出现，流水线就停。"
    },
    "idea.p2.title": { en: "Layer 2 &middot; Self-review", zh: "第二层 · 自查" },
    "idea.p2.body": {
      en: "The refine stage right-sizes every section to its band, scrubs AI tells from the prose, and re-reads each edit for the contradiction it may have introduced.",
      zh: "refine 阶段把每一节的篇幅调回字数区间，清掉行文里的 AI 痕迹，并把每处修改重读一遍，确认没有引入新的自相矛盾。"
    },
    "idea.p3.title": { en: "Layer 3 &middot; Adversarial review", zh: "第三层 · 对抗式评审" },
    "idea.p3.body": {
      en: "Isolated reviewers read the whole draft and must quote it verbatim to raise an issue; perspective-diverse skeptics then try to refute each finding. The loop runs until dry.",
      zh: "相互隔离的评审员通读全稿，提出问题必须附上逐字引文；随后由视角各异的质疑者逐条尝试反驳这些发现。这个循环一直跑到再也提不出新问题为止。"
    },
    "idea.p4.title": { en: "Layer 4 &middot; Vision critique", zh: "第四层 · 视觉复核" },
    "idea.p4.body": {
      en: "Claude looks at every rendered figure with its own eyes &mdash; faithfulness to the method, semantic agreement with the equations, readability, aesthetics &mdash; and a measured geometry audit drives at least four repair rounds on every redrawn SVG.",
      zh: "每张渲染出的图，Claude 都亲眼过目：是否忠实于方法、语义是否与公式一致，还有可读性和美观。重绘的每张 SVG 还要做实测几何审计，并据此至少跑四轮修复。"
    },

    /* --- 02 pipeline --- */
    "idea.ablation": {
      en: "Measured in the paper&rsquo;s controlled ablation: with 36 unsupported claims injected, detection climbs from 14% for a single-pass draft to 69% with the gates, 81% adding self-review, and <strong>92%</strong> with the full stack (<a href=\"https://arxiv.org/abs/2608.11924\" target=\"_blank\" rel=\"noopener\">arXiv:2608.11924</a>, Table&nbsp;4).",
      zh: "论文的受控消融实验实测：注入 36 条无依据论断后，单遍成稿只能查出 14%，加上闸门升到 69%，再加自查升到 81%，完整体系达到 <strong>92%</strong>（<a href=\"https://arxiv.org/abs/2608.11924\" target=\"_blank\" rel=\"noopener\">arXiv:2608.11924</a>，Table&nbsp;4）。"
    },

    "pipe.eyebrow": { en: "Pipeline", zh: "流水线" },
    "pipe.title": { en: "One input in. Eight stages later, <em>a compiled PDF</em>.", zh: "丢进一个输入，走完八个阶段，拿到<em>一份编译好的 PDF</em>。" },
    "pipe.lede": {
      en: "You drop <strong>one</strong> input &mdash; a bare idea, a structured proposal, a proposal with real results, or a story from a previous run. Stage&nbsp;0 of <code>ts-paper</code> classifies it with no fixed schema, sets the one switch the whole suite reads (<code>results_mode</code>), and drives the chain. <strong>Files on disk are the contract between stages</strong>; each stage writes an INPUT / DECISIONS / OUTPUT trace to <code>logs/</code>.",
      zh: "你只需要提供<strong>一个</strong>输入：一句想法、一份结构化 proposal、附带真实结果的 proposal，或者上次运行留下的 story。<code>ts-paper</code> 的 Stage&nbsp;0 不依赖固定 schema，自行判断输入属于哪一类，设好全套件都读取的唯一开关（<code>results_mode</code>），然后驱动整条链跑下去。<strong>阶段之间以磁盘文件为契约</strong>，每个阶段都会把 INPUT / DECISIONS / OUTPUT 记录写进 <code>logs/</code>。"
    },
    "pipe.route.title": { en: "Stage&nbsp;0 &middot; What you drop decides the route.", zh: "Stage&nbsp;0 · 输入决定路线。" },
    "pipe.route.th1": { en: "You dropped", zh: "你丢进来的" },
    "pipe.route.th2": { en: "Route", zh: "路由" },
    "pipe.route.a1": { en: "A one-line idea", zh: "一句话想法" },
    "pipe.route.a2": { en: "<code>ts-idea2story</code> builds the story first, then the chain", zh: "先由 <code>ts-idea2story</code> 生成 story，再走主链" },
    "pipe.route.b1": { en: "A structured proposal", zh: "一份结构化 proposal" },
    "pipe.route.b2": { en: "Straight into the chain &mdash; result cells stay blank", zh: "直接进主链——结果单元格保持空白" },
    "pipe.route.c1": { en: "A proposal + measured results", zh: "proposal + 实测结果" },
    "pipe.route.c2": { en: "<code>ts-paper-data</code> distills the numbers into <code>results.facts.json</code>", zh: "<code>ts-paper-data</code> 把数字提炼进 <code>results.facts.json</code>" },
    "pipe.route.d1": { en: "A <code>story.json</code> from a prior run", zh: "上次运行留下的 <code>story.json</code>" },
    "pipe.route.d2": { en: "Skips idea2story, straight to planning", zh: "跳过 idea2story，直接进入规划" },
    "pipe.route.caption": {
      en: "Any real measured number in the input &mdash; a filled table, &ldquo;achieved 0.62 HOTA&rdquo; &mdash; forces the data-aware route; it is never sent down the no-numbers proposal path.",
      zh: "输入里只要有真实测量值，比如一张填好的表、一句「achieved 0.62 HOTA」，就会强制走 data-aware 路线，绝不会落进无数字的 proposal 路径。"
    },
    "pipe.fig.title": { en: "The chain and its artifacts", zh: "链条与它的产物" },
    "pipe.fig.note": {
      en: "Every stage owns one artifact &mdash; blueprint.json, refs.bib, sections/*.tex, figures/*.pdf, main.pdf &mdash; and the next stage consumes it from disk.",
      zh: "每个阶段各自负责一件产物（blueprint.json、refs.bib、sections/*.tex、figures/*.pdf、main.pdf），下一阶段直接从磁盘接手。"
    },
    "pipe.s1.title": { en: "1 &middot; Plan", zh: "1 · 规划" },
    "pipe.s1.body": {
      en: "One reasoning pass emits <code>blueprint.json</code>: title, keywords, exactly three contributions, notation, terminology, experiment design, per-section word targets.",
      zh: "一次推理产出 <code>blueprint.json</code>，里面定下标题、关键词、恰好三条 contribution、符号约定、术语表、实验设计，以及每节的字数目标。"
    },
    "pipe.s2.title": { en: "2 &middot; Cite", zh: "2 · 引用" },
    "pipe.s2.body": {
      en: "Broad WebSearch per angle, abstracts read, metadata fetched via Crossref / arXiv. Floor of 40 real references, every one mapped to the claim it supports.",
      zh: "按各检索角度做大范围 WebSearch，逐篇读摘要，元数据从 Crossref / arXiv 获取。真实文献不少于 40 条，每一条都标明它支撑哪条论断。"
    },
    "pipe.s3.title": { en: "3 &middot; Write", zh: "3 · 写作" },
    "pipe.s3.body": {
      en: "All sections in one holistic pass &mdash; terminology stays consistent because the whole paper is in context. In proposal mode, result cells stay <code>--</code>.",
      zh: "所有章节在一次整体写作中完成：整篇论文都在上下文里，术语自然前后一致。proposal 模式下，结果单元格保持 <code>--</code>。"
    },
    "pipe.s4.title": { en: "4 &middot; Refine", zh: "4 · 润色" },
    "pipe.s4.body": {
      en: "Right-size to the enforced word bands, scrub the AI tells, self-check the logic of every edit. &ldquo;Right-sized&rdquo; is verified in code, not by eye.",
      zh: "把各节篇幅压进强制的字数区间，清理 AI 痕迹，每处改动都自查逻辑。篇幅是否合格由代码验证，不靠肉眼。"
    },
    "pipe.s5.title": { en: "5 &middot; Review", zh: "5 · 评审" },
    "pipe.s5.body": {
      en: "The adversarial panel argues against the paper: isolated reviewers, verbatim-quote anti-skim, skeptic verification, loop until dry. Fixes route back through refine.",
      zh: "对抗式评审团专挑论文的毛病：评审人彼此隔离，引用原文以防略读，另有质疑者复核结论，反复循环，直到再无新问题。需要的修复一律回流到 refine 阶段处理。"
    },
    "pipe.s6.title": { en: "6 &middot; Figures", zh: "6 · 画图" },
    "pipe.s6.body": {
      en: "Data plots are born-vector matplotlib; schematics are PaperBanana renders reconstructed in code as native, audited vector graphics.",
      zh: "数据图用 matplotlib 直接生成矢量图；示意图先由 PaperBanana 渲染，再用代码重建成原生矢量图，并经过审计。"
    },
    "pipe.s7.title": { en: "7 &middot; Compile", zh: "7 · 编译" },
    "pipe.s7.body": {
      en: "Template-driven assembly and <code>latexmk</code>. Zero-error logs and a resolved bibliography required; the fix loop is bounded at three tries.",
      zh: "按模板组装全文，交给 <code>latexmk</code> 编译。要求日志零错误、参考文献全部解析成功；修复循环最多跑三轮。"
    },
    "pipe.s8.title": { en: "8 &middot; Experiments (auto)", zh: "8 · 实验（自动）" },
    "pipe.s8.body": {
      en: "Runs automatically after the first gates-green draft: diagnoses the paper&rsquo;s logic, runs only feasible experiments on real data, fills the tables, recompiles.",
      zh: "首版通过全部闸门后自动启动：先诊断论文的逻辑，只在真实数据上跑可行的实验，把结果填进表里，再重新编译。"
    },
    "pipe.mode.p.tag": { en: "Proposal Mode &middot; results_mode: proposal", zh: "Proposal Mode · results_mode: proposal" },
    "pipe.mode.p.title": { en: "No numbers, ever", zh: "一个数字都不许有" },
    "pipe.mode.p.body": {
      en: "Forward-looking prose only. A concrete metric in a sentence &mdash; &ldquo;18.3%&rdquo;, &ldquo;0.72 F1&rdquo;, &ldquo;2.5&times;&rdquo;, even &ldquo;doubles&rdquo; &mdash; hard-fails the lint; bare-integer results are caught in self-review. Result tables exist with every cell literally <code>--</code>; the only place a dash may appear. No results figure is drawn at all, because drawing one would fabricate data.",
      zh: "行文只允许写计划和预期。句子里一旦出现具体指标，如「18.3%」「0.72 F1」「2.5&times;」，甚至「翻倍」这样的说法，lint 直接判失败；裸整数形式的结果由自查环节拦截。结果表照常保留，但每个单元格都写成 <code>--</code>，这也是全文唯一允许出现这种横线的地方。结果图一张都不画，因为画出来就是在捏造数据。"
    },
    "pipe.mode.d.tag": { en: "Data-Aware Mode &middot; results_mode: data_aware", zh: "Data-Aware Mode · results_mode: data_aware" },
    "pipe.mode.d.title": { en: "Every number traced", zh: "每个数字可溯源" },
    "pipe.mode.d.body": {
      en: "Your real results are distilled into <code>results.facts.json</code> &mdash; the audit ground truth. Result sections switch to definitive past tense; any decimal or percent in prose that is not in the facts file fails the build. A measured-but-missing value is written <code>TBD</code> and never guessed.",
      zh: "你的真实结果先提炼进 <code>results.facts.json</code>，作为审计用的 ground truth。结果章节改用确定的过去时叙述；正文里任何小数或百分数，只要在 facts 文件里查不到，构建就会失败。测过但缺失的数值写成 <code>TBD</code>，不做任何猜测。"
    },

    /* --- 03 figure engine --- */
    "fig.eyebrow": { en: "Figure Engine", zh: "画图引擎" },
    "fig.title": {
      en: "AI image models make rasters. Papers need editable vectors. <em>This engine ships both.</em>",
      zh: "AI 图像模型画出来的是位图，论文要的是可编辑矢量图：这套引擎<em>两样都给</em>。"
    },
    "fig.lede": {
      en: "The engine is decided by <strong>which section a figure lives in</strong>. Results plots draw from real data with matplotlib &mdash; numerically exact, born vector, never from an image model. Every other figure runs a three-act pipeline: the official <strong>PaperBanana</strong> agent team renders the candidate image that becomes the <strong>visual target</strong>; <code>ts-figure-svg</code> reconstructs it in code as editable vector graphics &mdash; real <code>&lt;rect&gt;/&lt;path&gt;/&lt;text&gt;</code>, every label live text &mdash; rendering each round and comparing it against the target until structure and appearance are recovered; a geometry audit drives at least four repair rounds. If reconstruction stays unreliable, the DrawAI hybrid &mdash; then the approved PNG &mdash; steps in. <strong>Never a lossy trace.</strong>",
      zh: "一张图用哪套引擎，取决于它<strong>属于哪个章节</strong>。结果图由 matplotlib 从真实数据绘制，数值精确、天生就是矢量，绝不出自图像模型。其余图走三段式流水线：官方 <strong>PaperBanana</strong> 智能体团队渲染出的候选图就是<strong>视觉目标</strong>；<code>ts-figure-svg</code> 用代码把它重建成可编辑矢量图——真正的 <code>&lt;rect&gt;/&lt;path&gt;/&lt;text&gt;</code>，每条标签都是活文本——每一轮都把重建结果渲染出来与目标比对，直到复现它的结构与外观；几何审计至少驱动四轮修复。重建始终不可靠时，依次退到 DrawAI hybrid 和定稿 PNG。<strong>绝不做有损描摹。</strong>"
    },
    "fig.s1.title": { en: "Render candidates", zh: "渲染候选" },
    "fig.s1.body": {
      en: "The official PaperBanana pipeline &mdash; Retriever &rarr; Planner &rarr; Stylist &rarr; Visualizer &rarr; Critic &mdash; produces candidate images; a distilled image-model loop stands in when no key is configured.",
      zh: "官方 PaperBanana 流水线（Retriever &rarr; Planner &rarr; Stylist &rarr; Visualizer &rarr; Critic）负责产出候选图；没有配置 key 时，由蒸馏版图像模型循环兜底。"
    },
    "fig.s2.title": { en: "Learn the look", zh: "学习设计语言" },
    "fig.s2.body": {
      en: "Claude looks at the chosen render and extracts its design language &mdash; palette, type scale, spacing, idiom &mdash; into a style sheet. The PNG is also the <em>visual target</em>: the redraw is rendered and compared against it, round by round, until its structure and appearance are recovered.",
      zh: "Claude 观察选中的渲染图，把配色、字号层级、留白、视觉习惯这些设计语言提炼成样式表。这张 PNG 同时也是<em>视觉目标</em>：重建结果要渲染出来与它比对，逐轮修正，直到复现它的结构和外观。"
    },
    "fig.s3.title": { en: "Reconstruct in code", zh: "代码重建" },
    "fig.s3.body": {
      en: "The figure is reconstructed as editable vector graphics through code &mdash; every label live <code>&lt;text&gt;</code>, every element a real object &mdash; with the chosen render as its visual target. Reference grounding and visual review then check the figure against the manuscript itself.",
      zh: "整张图用代码重建为可编辑矢量图：每条标签都是活的 <code>&lt;text&gt;</code>，每个元素都是真实对象；选中的渲染图就是视觉目标。随后再对照论文正文核查图的内容，并做视觉复核。"
    },
    "fig.s4.title": { en: "Audit &amp; repair", zh: "审计与修复" },
    "fig.s4.body": {
      en: "Each round renders the reconstruction and compares it with the target, and a geometry audit measures the drawing &mdash; overflow, text-on-text, clipped arrowheads, sub-legible type &mdash; driving repairs for at least four rounds, with no upper bound while defects remain.",
      zh: "每一轮都把重建结果渲染出来与目标比对，几何审计再逐项测量这张图：查溢出、文字叠压、箭头被裁、字号小到难辨，并据此驱动至少四轮修复；只要缺陷还在，轮数就没有上限。"
    },
    "fig.lane.decompose": { en: "Redraw", zh: "重绘" },
    "fig.lane.decompose.note": { en: "native objects &mdash; no pixels, no tracing", zh: "原生对象——不贴像素，不描摹" },
    "fig.l1.title": { en: "Style sheet from the render", zh: "从渲染图提炼样式表" },
    "fig.l1.body": {
      en: "Palette, type scale, spacing and visual idiom are read off the chosen PaperBanana candidate by eye and written down as a style sheet.",
      zh: "配色、字号层级、留白和视觉习惯，都从选中的 PaperBanana 候选图上目测读出，记录成样式表。"
    },
    "fig.l2.title": { en: "Checked against the paper", zh: "对照论文核查" },
    "fig.l2.body": {
      en: "Modules, edges and labels are then checked against the figure spec and the paper&rsquo;s equations &mdash; reference grounding and visual review catch a garbled label or an invented link before it ships.",
      zh: "模块、连线和标签随后要对照图规格与论文公式核查——引用接地与视觉复核会在出稿前拦下写错的标签、凭空的连线。"
    },
    "fig.l3.title": { en: "Real vector objects", zh: "真正的矢量对象" },
    "fig.l3.body": {
      en: "The figure is drawn as genuine <code>&lt;rect&gt;/&lt;path&gt;/&lt;text&gt;</code> elements &mdash; every label live, editable text, with glyphs kept Times-safe so the PDF embeds fonts cleanly.",
      zh: "整张图用真正的 <code>&lt;rect&gt;/&lt;path&gt;/&lt;text&gt;</code> 元素绘成，每条标签都是可编辑的活文本；字形限定在 Times 安全集内，PDF 能干净地内嵌字体。"
    },
    "fig.ring.seg": { en: "Draw", zh: "绘制" },
    "fig.ring.read": { en: "Measure", zh: "测量" },
    "fig.ring.build": { en: "Repair", zh: "修复" },
    "fig.ring.core": { en: "<em>PaperBanana+</em><i>&ge;4 rounds</i>", zh: "<em>PaperBanana+</em><i>&ge;4 轮</i>" },
    "fig.lane.rebuild": { en: "Measure", zh: "测量" },
    "fig.lane.rebuild.note": { en: "render &amp; compare against the target, then measure", zh: "渲染后与目标比对，再逐项测量" },
    "fig.l4.title": { en: "The audit measures the drawing", zh: "审计逐项测量" },
    "fig.l4.body": {
      en: "Each round renders the reconstruction and compares it with the reference; a gap in layout, geometry or text placement fails the round. <code>audit_svg.py</code> then measures the drawing &mdash; canvas or card overflow, a clipped arrowhead, text over text, sub-legible type, font-fallback glyphs &mdash; and path soup, the signature of a traced raster.",
      zh: "每一轮先把重建结果渲染出来与参考图比对，布局、几何或文字位置有差距，当轮即判失败。<code>audit_svg.py</code> 再逐项测量这张图：画布或卡片溢出、箭头被裁、文字叠压、字号小到读不清、字形触发字体回退，以及描摹位图特有的 path soup。"
    },
    "fig.lane.verify": { en: "Verify", zh: "核验" },
    "fig.lane.verify.note": { en: "the gate reads the audit trail, not the report", zh: "闸门看审计记录，不看汇报" },
    "fig.l5.title": { en: "Verified on the compiled page", zh: "在编译成品页上验证" },
    "fig.l5.body": {
      en: "The SVG exports to a vector PDF that must genuinely embed its fonts &mdash; an exporter that outlines every glyph is caught &mdash; and the figure is checked on the real compiled page. The build gate requires at least four audit rounds.",
      zh: "SVG 导出的矢量 PDF 必须真正内嵌字体，把字形全部转成轮廓来蒙混的导出器会被查出来；整张图还要放到真实编译出的页面上核对。构建闸门要求至少四轮审计。"
    },
    "fig.l6.title": { en: "No upper bound while defects remain.", zh: "缺陷不清零，轮数无上限。" },
    "fig.l6.body": {
      en: "Four rounds is the floor, not the ceiling &mdash; the draw&ndash;measure&ndash;repair loop keeps going until the audit comes back clean. And if native redraw is genuinely impossible, the ladder holds: DrawAI hybrid, then the approved PNG. Never a lossy trace.",
      zh: "四轮只是下限，绘制、测量、修复的循环会一直跑到审计通过为止。要是原生重绘确实走不通，还有后备梯队：先 DrawAI hybrid，再定稿 PNG。绝不做有损描摹。"
    },
    "fig.k1.name": { en: "Repair loop", zh: "修复循环" },
    "fig.k1.metric": { en: "audit rounds per figure", zh: "每张图审计轮数" },
    "fig.k1.delta": { en: "gate-enforced", zh: "闸门强制" },
    "fig.k2.name": { en: "Audit cost", zh: "审计成本" },
    "fig.k2.metric": { en: "extra models &middot; API keys", zh: "额外模型 · API key" },
    "fig.k2.delta": { en: "code-only", zh: "纯代码" },
    "fig.k3.name": { en: "Fallback hybrid", zh: "兜底 HYBRID" },
    "fig.k3.metric": { en: "SSIM vs full redraw", zh: "SSIM，对比整图重画" },
    "fig.k3.delta": { en: "reported", zh: "项目实测" },
    "fig.k4.name": { en: "Pixel tracing", zh: "像素描摹" },
    "fig.k4.metric": { en: "paths in one auto-trace", zh: "一次自动描摹的 path 数" },
    "fig.k4.delta": { en: "banned", zh: "已禁用" },
    "fig.demo.title": { en: "Born-vector data figures, straight from the showcase papers", zh: "天生矢量的数据图，直接取自 showcase 论文" },
    "fig.demo.note": {
      en: "Results plots are drawn from code with the suite&rsquo;s publication house style &mdash; semantic colors, exact numbers from <code>results.facts.json</code>, and a vector PDF written alongside every PNG with the text kept editable.",
      zh: "结果图由代码按套件统一的出版样式绘制：语义化配色，数字精确取自 <code>results.facts.json</code>，每张 PNG 旁还会写出一份矢量 PDF，文字保持可编辑。"
    },
    "fig.f1.title": { en: "Why not just trace the PNG?", zh: "为什么不直接描摹 PNG？" },
    "fig.f1.body": {
      en: "Auto-tracing one figure produced 59,430 paths, 10&nbsp;MB, and not one editable label &mdash; and it was still blurry when zoomed. &ldquo;No <code>&lt;image&gt;</code> element&rdquo; does not mean vector. So the reconstruction draws <em>real objects</em> to match the render &mdash; live labels, editable shapes &mdash; never traced pixels.",
      zh: "自动描摹一张图，结果是 59,430 条 path、10&nbsp;MB 的文件，可编辑标签一条也没有，放大看照样模糊。「没有 <code>&lt;image&gt;</code> 元素」不等于矢量。所以系统用<em>真正的图形对象</em>把它重建出来——标签是活文本，图形可编辑——绝不描摹像素。"
    },
    "fig.f2.value": { en: "3<em>rungs</em>", zh: "三<em>级</em>" },
    "fig.f2.title": { en: "The fallback ladder", zh: "兜底阶梯" },
    "fig.f2.body": {
      en: "Native SVG first. If the redraw is impossible, the vendored DrawAI hybrid keeps the approved render pixel-exact under an editable text overlay (~0.91 SSIM, key-free via ModelScope). Failing that, the approved PNG goes in as-is &mdash; full richness preserved, editability deferred. Never a lossy trace.",
      zh: "首选原生 SVG。重绘不可行时，随包内置的 DrawAI hybrid 会在定稿渲染图上叠一层可编辑文字，底图保持像素级一致（SSIM 约 0.91，走 ModelScope 无需 key）。若这条路也走不通，就把定稿 PNG 原样放进论文：细节完整保留，可编辑性留待以后。绝不做有损描摹。"
    },

    /* --- 04 experiments --- */
    "exp.eyebrow": { en: "Experiments", zh: "实验" },
    "exp.title": {
      en: "Stage 8 <em>runs what the paper claims</em> &mdash; or files a report saying why it can&rsquo;t.",
      zh: "Stage 8 把论文声称的实验<em>真的跑一遍</em>；跑不了的，就交一份报告写清楚原因。"
    },
    "exp.lede": {
      en: "After the chain delivers a gates-green first draft, <code>ts-paper-experiment</code> starts automatically &mdash; no one has to ask. It maps the paper&rsquo;s logic, plans the minimum set of experiments, classifies each as <strong>necessary, feasible, or blocked</strong>, executes only what real data and code support, and recompiles the paper with measured numbers. If nothing can run, it writes a requirements report and leaves the tables in proposal form &mdash; <strong>it never invents results</strong>.",
      zh: "链条交出全绿首稿之后，<code>ts-paper-experiment</code> 会自动启动，无需任何人触发。它先梳理论文的逻辑，规划出最小实验集，把每个实验标为<strong>必要、可行或受阻</strong>，只执行真实数据和代码支撑得起的部分，再用实测数字重新编译论文。如果一个实验都跑不了，它会写一份需求报告，把结果表留在 proposal 形态，<strong>绝不编造结果</strong>。"
    },
    "exp.s1.title": { en: "Diagnose", zh: "诊断" },
    "exp.s1.body": {
      en: "Three reports map the territory: the paper&rsquo;s logic, its claimed contributions, and the gap between claimed and existing experiments.",
      zh: "先产出三份报告摸清现状：论文的逻辑、声称的 contribution，以及声称的实验与已有实验之间的缺口。"
    },
    "exp.s2.title": { en: "Plan", zh: "规划" },
    "exp.s2.body": {
      en: "Each experiment is classified necessary / feasible / blocked, with metrics, baselines and commands. Named open datasets must actually be downloaded before &ldquo;blocked&rdquo; may be declared.",
      zh: "每个实验都标注必要 / 可行 / 受阻，并附上指标、baseline 和运行命令。点名的开放数据集必须实际去下载过，才允许判定「受阻」。"
    },
    "exp.s3.title": { en: "Run", zh: "执行" },
    "exp.s3.body": {
      en: "Real data and code only, seeds fixed at [1,&nbsp;2,&nbsp;3], cheap local runs auto-approved, costly or external-data runs held for explicit user approval.",
      zh: "只用真实数据和真实代码，随机种子固定为 [1,&nbsp;2,&nbsp;3]。开销小的本地运行自动放行；开销大或需要外部数据的，要等用户明确批准才执行。"
    },
    "exp.s4.title": { en: "Audit &amp; fill", zh: "审计与填表" },
    "exp.s4.body": {
      en: "Every value is recomputed from per-seed raw logs, traced to its source file, and only then written into the paper&rsquo;s own result tables &mdash; nulls and honest failures included.",
      zh: "每个数值都从逐 seed 的原始日志重新算出，并溯源到具体文件，然后才写进论文自己的结果表。空值和失败也如实写进去。"
    },
    "exp.f1.title": { en: "Audit reports before any number lands", zh: "数字落表前的审计报告" },
    "exp.f1.body": {
      en: "Provenance, completeness, code&ndash;paper consistency, design correctness, artifact completeness, and a single truthfulness verdict. &ldquo;No value may be guessed, manually invented, or written from memory.&rdquo;",
      zh: "检查溯源、完整性、代码与论文一致性、实验设计正确性、产物完整性，最后给出一个总的真实性裁定。「任何数值不得靠猜、不得手工编造、不得凭记忆填写。」"
    },
    "exp.f2.value": { en: "weaken<em>or</em><span class=\"finding-ref\">remove</span>", zh: "弱化<em>或</em><span class=\"finding-ref\">删除</span>" },
    "exp.f2.title": { en: "When a claim outruns its evidence", zh: "论断跑到证据前面时" },
    "exp.f2.body": {
      en: "Anything classified CLAIMED_BUT_NOT_RUN gets its claim weakened or removed &mdash; or the run stops to ask. The final step diffs the before/after paper and issues an honesty verdict, admitting when experiments weakened the original story.",
      zh: "凡被判为 CLAIMED_BUT_NOT_RUN 的论断，对应说法会弱化或删除，再不然就停下来问用户。最后一步对比修改前后的论文，给出诚实性裁定；如果实验结果削弱了原有的故事，也照实写明。"
    },
    "exp.srl.title": { en: "The Self-Refutation Loop &mdash; named, bounded, survived.", zh: "自我否定循环：点名它，限住它。" },
    "exp.srl.body": {
      en: "Long research trajectories have a failure mode the paper names the <strong>Self-Refutation Loop</strong>: the system keeps judging its own evidence insufficient for the original objective, yet keeps revising the same direction without converging. Spark-to-Paper bounds it at <strong>seven experiment&ndash;critique&ndash;revision cycles</strong>; an unresolved trajectory is terminated and written up as an honest failure report &mdash; idea, methods, experiments, results, and why the evidence fell short &mdash; and the system restarts from a new idea rather than forcing success.",
      zh: "长程研究轨迹有一种论文专门命名的失败模式——<strong>自我否定循环（Self-Refutation Loop）</strong>：系统反复判定证据不足以支撑最初的研究目标，却又一直沿原方向修改，始终不收敛。Spark-to-Paper 给它设了上限：<strong>实验-批评-修改最多七轮</strong>；仍未解决的轨迹会被终止，写成一份诚实的失败报告——想法、方法、实验、结果，以及证据差在哪里——然后系统换一个新想法重新出发，绝不硬凑一个成功。"
    },
    "exp.table.title": { en: "Guardrails, out of the box.", zh: "开箱即有的护栏。" },
    "exp.table.th1": { en: "Guard", zh: "护栏" },
    "exp.table.th2": { en: "Default", zh: "默认值" },
    "exp.t1a": { en: "Random seeds", zh: "随机种子" },
    "exp.t2a": { en: "Max runtime per experiment", zh: "单个实验最长运行时长" },
    "exp.t2b": { en: "6 hours", zh: "6 小时" },
    "exp.t3a": { en: "Traceable results required", zh: "结果必须可溯源" },
    "exp.t4a": { en: "Ask the user before", zh: "先问用户再动的事" },
    "exp.t4b": {
      en: "changing a contribution &middot; deleting a core method &middot; a new experiment type &middot; strong claims from weak results",
      zh: "改 contribution · 删核心方法 · 新增实验类型 · 用弱结果下强结论"
    },
    "exp.t5a": { en: "Golden rules", zh: "黄金规则" },
    "exp.t5b": { en: "27 human-approved rules; candidates are never auto-promoted", zh: "27 条人工批准的规则；候选规则不会自动转正" },
    "exp.table.caption": {
      en: "From the skill&rsquo;s bundled <code>paper_config.yaml</code> and <code>golden_rules.md</code>. Experiments run locally; Overleaf sync is configurable via <code>paper_config.yaml</code> + <code>.env</code>.",
      zh: "出自 skill 内置的 <code>paper_config.yaml</code> 与 <code>golden_rules.md</code>。实验在本地运行；Overleaf 同步在 <code>paper_config.yaml</code> 和 <code>.env</code> 里配置。"
    },

    /* --- 05 writing & review --- */
    "wr.eyebrow": { en: "Writing &amp; Review", zh: "写作与评审" },
    "wr.title": {
      en: "Journal-shaped prose, with the AI scrubbed out and <em>a courtroom at the end</em>.",
      zh: "期刊味的行文，洗掉 AI 腔，最后还有<em>一场庭审</em>。"
    },
    "wr.lede": {
      en: "The blueprint fixes the shape before a word is written: per-section word bands, exactly three contributions, a notation table every section must reuse. The draft is written in <strong>one holistic pass</strong> so terminology never drifts; refine right-sizes it and scrubs the tells; and then a review panel does what the rest of the suite never does &mdash; <strong>argues against the paper</strong>.",
      zh: "动笔之前，blueprint 先把论文的形状定下来：逐节字数区间、恰好三条 contribution，还有一张每节都必须复用的符号表。草稿<strong>一次整体成稿</strong>，术语不会中途漂移；refine 负责调整篇幅、洗掉 AI 痕迹；最后由评审团做套件里其他环节都不做的事：<strong>站到论文的对立面</strong>。"
    },
    "wr.s1.title": { en: "Blueprint", zh: "蓝图" },
    "wr.s1.body": {
      en: "Title of 8&ndash;14 words, 4&ndash;6 keywords, three contributions, full notation &mdash; one reasoning pass, linted before anything downstream may start.",
      zh: "标题 8&ndash;14 个词、关键词 4&ndash;6 个、三条 contribution、完整符号表，一次推理生成；先通过 lint，下游环节才能开工。"
    },
    "wr.s2.title": { en: "Real references", zh: "真实参考文献" },
    "wr.s2.body": {
      en: "Floor of 40, built through Crossref and arXiv metadata &mdash; authors, venue, pages, DOI. A title-only stub is forbidden; a claim with no real paper behind it goes uncited.",
      zh: "参考文献下限 40 条，通过 Crossref 和 arXiv 的元数据构建，作者、venue、页码、DOI 一应俱全。禁止只有标题的空条目；找不到真实文献支撑的论断，宁可不加引用。"
    },
    "wr.s3.title": { en: "Holistic draft", zh: "整体成稿" },
    "wr.s3.body": {
      en: "Method first, ~2000&ndash;3000 words; intro in exactly five paragraphs; related work by theme, never chronology. Every symbol defined before use, no raw Unicode.",
      zh: "先写方法节，约 2000&ndash;3000 词；引言恰好五段；相关工作按主题组织，不按年代罗列。所有符号先定义再使用，不允许裸 Unicode 字符。"
    },
    "wr.s4.title": { en: "Right-size + de-AI", zh: "调篇幅 + 去 AI 腔" },
    "wr.s4.body": {
      en: "Word bands enforced in code. Comma-soup fragments become connected prose; &ldquo;delve&rdquo;, &ldquo;leverage&rdquo;, &ldquo;it is worth noting&rdquo; and their kin are hunted down; citations, math and labels stay untouched.",
      zh: "字数区间由代码强制检查。逗号串起来的碎句会改写成连贯的行文；「delve」「leverage」「it is worth noting」这类词会被逐个清除；引用、公式和标签保持原样。"
    },
    "wr.rev.title": { en: "&ldquo;Can&rsquo;t quote = didn&rsquo;t read.&rdquo;", zh: "「引不出原文 = 没读。」" },
    "wr.rev.body": {
      en: "The review panel runs N isolated reviewers &mdash; theoretical soundness, experimental design, systems validity &mdash; each seeing nothing but the paper. Every issue must carry an exact verbatim quote and a closeable criterion. Each finding then faces three perspective-diverse skeptics &mdash; misreading? already addressed? out of scope? &mdash; and survives unless a majority refute it. Fresh panels re-run until a full pass finds nothing new &mdash; within a budget-capped number of rounds. Fixes are minimal, targeted, and re-gated: the linters are re-run after the edits land, because the suite derives &ldquo;green&rdquo; &mdash; it never forecasts it. In the paper&rsquo;s blinded evaluation, issues raised this way were verified at <strong>74% precision</strong>.",
      zh: "评审团由 N 位互相隔离的评审组成，分别检查理论正确性、实验设计与系统有效性，每人只看论文本身。每条意见都必须附上精确的原文引用和一条可关闭的验收标准。之后，每条意见还要过三位视角各异的质疑者：是不是读岔了？是不是已经处理过？是不是超出论文声明的范围？只有多数质疑者反驳成立，这条意见才会被否决。评审团会换一批人重开，直到完整一轮再无新发现为止，轮数受预算上限约束。修复只做最小的定点改动，改完重新过闸：linter 在修改落盘后重跑，这套系统只从结果推导绿灯，从不预告绿灯。论文的盲评实测：这样提出的意见有 <strong>74%</strong> 被查实。"
    },
    "wr.tpl.title": { en: "Templates &middot; pick a venue, keep the quality.", zh: "模板 · 换 venue，不换质量。" },
    "wr.tpl.th1": { en: "Template", zh: "模板" },
    "wr.tpl.th2": { en: "Venue", zh: "期刊 / 会议" },
    "wr.tpl.th3": { en: "Style", zh: "版式" },
    "wr.tpl.th4": { en: "Ref floor", zh: "引用下限" },
    "wr.tpl.th5": { en: "Status", zh: "状态" },
    "wr.tpl.r1c": { en: "two-column, numeric citations", zh: "双栏，数字引用" },
    "wr.tpl.r1d": { en: "approximation, demo-only", zh: "近似复刻，仅供演示" },
    "wr.tpl.r2c": { en: "single-column, author-year", zh: "单栏，作者-年份" },
    "wr.tpl.r2d": { en: "approximation, demo-only", zh: "近似复刻，仅供演示" },
    "wr.tpl.r3c": { en: "official <code>.sty</code>, fetched verbatim", zh: "官方 <code>.sty</code>，原样获取" },
    "wr.tpl.r3d": { en: "<strong>official style files</strong>", zh: "<strong>官方样式文件</strong>" },
    "wr.tpl.caption": {
      en: "Add any venue by dropping a <code>templates/&lt;name&gt;/</code> directory with a <code>template.json</code> and the venue&rsquo;s LaTeX assets &mdash; no code changes. The suite&rsquo;s hard rule: style files are user-provided or fetched verbatim from the official source, <strong>never fabricated</strong>.",
      zh: "要新增 venue，只需放入一个 <code>templates/&lt;name&gt;/</code> 目录，里面带上 <code>template.json</code> 和该 venue 的 LaTeX 资源，无需改任何代码。套件有一条硬规矩：样式文件只能由用户提供、或从官方渠道原样获取，<strong>绝不伪造</strong>。"
    },

    /* --- 06 showcase --- */
    "sc.eyebrow": { en: "Showcase", zh: "论文展示" },
    "sc.title": { en: "Seven papers. Six domains. <em>Every number traceable.</em>", zh: "七篇论文，六个领域，<em>每个数字都可溯源</em>。" },
    "sc.lede": {
      en: "Each paper below started as a research proposal and ran the full chain &mdash; plan &rarr; cite &rarr; write &rarr; refine &rarr; review &rarr; figure &rarr; compile &mdash; then the experiment stage ran the planned experiments and wrote the measured results back into the draft. Click any card for the compiled PDF.",
      zh: "下面每篇论文都从一份研究 proposal 出发，跑完 plan &rarr; cite &rarr; write &rarr; refine &rarr; review &rarr; figure &rarr; compile 全链条，随后实验阶段把规划好的实验真的跑了一遍，再把实测数字写回论文。点击卡片可查看编译好的 PDF。"
    },
    "sc.read": { en: "Read the PDF &#8599;", zh: "阅读 PDF &#8599;" },
    "sc.p1.fmt": { en: "Traitement du Signal format", zh: "Traitement du Signal 版式" },
    "sc.p2.fmt": { en: "Traitement du Signal format", zh: "Traitement du Signal 版式" },
    "sc.p3.fmt": { en: "Traitement du Signal format", zh: "Traitement du Signal 版式" },
    "sc.p4.fmt": { en: "Traitement du Signal format", zh: "Traitement du Signal 版式" },
    "sc.p5.fmt": { en: "NeurIPS 2025 official style (preprint)", zh: "NeurIPS 2025 官方版式（preprint）" },
    "sc.p6.fmt": { en: "ICML 2025 official style", zh: "ICML 2025 官方版式" },
    "sc.p7.fmt": { en: "NeurIPS 2025 official style (preprint)", zh: "NeurIPS 2025 官方版式（preprint）" },
    "sc.p1.domain": { en: "environmental monitoring", zh: "环境监测" },
    "sc.p1.note": {
      en: "The reported superiority of decomposition-ensemble methods shrinks dramatically under proper temporal splitting &mdash; corrected baselines for the field.",
      zh: "换用正确的时间切分之后，分解-集成方法宣称的优势大幅缩水，本文为该领域给出了修正后的 baseline。"
    },
    "sc.p2.domain": { en: "energy forecasting", zh: "能源预测" },
    "sc.p2.note": {
      en: "The leakage-free framework transfers from environmental to energy time series, revealing consistent overestimation in published results.",
      zh: "把无泄漏评测框架从环境时序迁移到能源时序，发现已发表的结果普遍偏高。"
    },
    "sc.p3.domain": { en: "environmental AI", zh: "环境 AI" },
    "sc.p3.note": {
      en: "Competitive accuracy that also exposes feature-level rationale &mdash; bridging the trust gap between black-box models and regulatory transparency.",
      zh: "精度有竞争力，还能给出特征级依据，弥合了黑盒模型与监管透明要求之间的信任缺口。"
    },
    "sc.p4.domain": { en: "computer vision / agriculture", zh: "计算机视觉 / 农业" },
    "sc.p4.note": {
      en: "Replaces global average pooling with a learnable sparse read-out that focuses on lesions &mdash; higher accuracy on edge-deployable architectures.",
      zh: "把全局平均池化换成可学习的稀疏读出，让模型聚焦病斑，在可部署到边缘设备的架构上拿到更高精度。"
    },
    "sc.p5.domain": { en: "clinical AI", zh: "临床 AI" },
    "sc.p5.note": {
      en: "Recasts screening as calibrated, interpretable risk estimation &mdash; and shows where raw accuracy hides clinically useless behavior.",
      zh: "把筛查重新表述为校准且可解释的风险估计，并指出原始精度会在哪些地方掩盖临床上无用的行为。"
    },
    "sc.p6.domain": { en: "industrial fault diagnosis", zh: "工业故障诊断" },
    "sc.p6.note": {
      en: "Perfect naive accuracy drops once recordings or loads are held out &mdash; and the compact CNN stops dominating classical baselines.",
      zh: "一旦按录音或负载划分留出测试集，原本「完美」的朴素精度应声回落，小型 CNN 对经典 baseline 的优势也随之消失。"
    },
    "sc.p7.domain": { en: "computer vision / agriculture", zh: "计算机视觉 / 农业" },
    "sc.p7.note": {
      en: "Separates suspected leakage from measured effects on PlantVillage Tomato: near-duplicate leakage negligible, the background shortcut real but modest.",
      zh: "在 PlantVillage Tomato 上把疑似泄漏与实测效应分开验证：近重复带来的泄漏可以忽略，背景捷径确实存在，但幅度不大。"
    },
    "sc.caption": {
      en: "Conference-format samples lead the set: one in the official ICML 2025 style and two in the official NeurIPS 2025 style (preprint option); the remaining four use the Traitement du Signal journal format. References verified via WebSearch + Crossref on every paper; all figures delivered as editable vector PDFs; integrity gates passed on all seven. Two of these domains &mdash; chronic-disease screening and PM2.5 forecasting &mdash; are dissected as case studies in the paper.",
      zh: "会议版式的样例排在前面：一篇采用 ICML 2025 官方样式，两篇采用 NeurIPS 2025 官方样式（preprint 选项）；其余四篇为 Traitement du Signal 期刊版式。七篇的参考文献均经 WebSearch + Crossref 核验，插图全部以可编辑的矢量 PDF 交付，诚实性闸门也全部通过。其中慢性病筛查与 PM2.5 预测两个领域，论文还作为案例研究做了拆解。"
    },

    /* --- 07 compare --- */
    "cmp.eyebrow": { en: "Compare", zh: "横向对比" },
    "cmp.title": { en: "The whole arc, <em>as drop-in skills</em>.", zh: "端到端全流程，<em>装上就能用的 skill</em>。" },
    "cmp.lede": {
      en: "The heavy autonomous scientists match the breadth &mdash; but ship as standalone Python products: Docker, Neo4j, tens of thousands of lines. The lighter skill suites stay in Claude Code &mdash; but don&rsquo;t run experiments or draw figures. This is the only pure Claude Code plugin that runs the entire arc, and the only tool of any kind with an <strong>editable-vector figure engine</strong>.",
      zh: "重型的自动科学家覆盖面不输本项目，但它们都是独立的 Python 产品，要装 Docker、Neo4j，代码动辄数万行；轻量的 skill 套件虽然留在 Claude Code 里，却既不跑实验也不画图。本项目是唯一跑通全流程的纯 Claude Code 插件，也是这些工具里唯一带<strong>可编辑矢量画图引擎</strong>的一个。"
    },
    "cmp.fig.title": { en: "Capability comparison across AI-research systems", zh: "AI 科研系统能力对比" },
    "cmp.fig.note": {
      en: "&#10003; full &middot; &#9679; partial &middot; &ndash; not offered or not documented. Reproduced from Table&nbsp;1 of the <a href=\"https://arxiv.org/abs/2608.11924\" target=\"_blank\" rel=\"noopener\">paper</a>, based on each system&rsquo;s own public documentation.",
      zh: "&#10003; 完整 · &#9679; 部分 · &ndash; 未提供或未见文档。复刻自<a href=\"https://arxiv.org/abs/2608.11924\" target=\"_blank\" rel=\"noopener\">论文</a>的 Table&nbsp;1，依据各系统自己的公开文档整理。"
    },
    "cmp.th.sys": { en: "System", zh: "系统" },
    "cmp.th.e2e": { en: "End-to-end", zh: "端到端" },
    "cmp.th.exp": { en: "Runs exper.", zh: "跑实验" },
    "cmp.th.fig": { en: "Draws figures", zh: "画图" },
    "cmp.th.vec": { en: "Editable vectors", zh: "可编辑矢量图" },
    "cmp.th.infra": { en: "No standing infra.", zh: "零常驻服务" },
    "cmp.ours": { en: "(ours)", zh: "（本项目）" },
    "takeaway.kicker": { en: "The takeaway", zh: "一句话总结" },
    "takeaway.lead": {
      en: "The model does the reasoning. The code keeps it honest. <strong>You get a paper.</strong>",
      zh: "模型负责推理，代码负责诚实。<strong>你拿到一篇论文。</strong>"
    },
    "takeaway.body": {
      en: "No app, no server, no database, no Docker &mdash; copy the skills into <code>~/.claude/skills/</code> and drop a spark. Everything the pipeline produces &mdash; blueprint, bibliography, sections, figures with their editable sources, logs, and the compiled PDF &mdash; lands on disk, yours to keep editing.",
      zh: "没有应用、服务和数据库，也不需要 Docker：把 skill 拷进 <code>~/.claude/skills/</code>，丢一颗火花进去就能跑。流水线产出的一切，包括 blueprint、参考文献、各章节、图及其可编辑源文件、日志和编译好的 PDF，全部落在本地磁盘上，你可以随时接着改。"
    },

    /* --- 08 cite / copy --- */
    "cite.eyebrow": { en: "BibTeX", zh: "引用" },
    "cite.title": { en: "Cite this work.", zh: "引用本项目。" },
    "cite.lede": {
      en: "If Spark-to-Paper helps your research, please cite the paper (<a href=\"https://arxiv.org/abs/2608.11924\" target=\"_blank\" rel=\"noopener\">arXiv:2608.11924</a>).",
      zh: "如果 Spark-to-Paper 对你的研究有帮助，欢迎引用论文（<a href=\"https://arxiv.org/abs/2608.11924\" target=\"_blank\" rel=\"noopener\">arXiv:2608.11924</a>）。"
    },
    "cite.copy": { en: "Copy", zh: "复制" },
    "cite.copied": { en: "Copied!", zh: "已复制！" },
    "cite.copyFail": { en: "Press Ctrl+C", zh: "请按 Ctrl+C" },

    /* --- footer --- */
    "footer.copy": {
      en: "&copy; 2026 spark-to-paper-skills &middot; MIT License &middot; Paper: <a href=\"https://arxiv.org/abs/2608.11924\" target=\"_blank\" rel=\"noopener\">arXiv:2608.11924</a> &middot; Built on Claude Code &middot; Figures: PaperBanana+ native SVG, DrawAI hybrid as fallback &middot; Site design after <a href=\"https://lh-harness.pages.dev/\" target=\"_blank\" rel=\"noopener\">LongHorizon-Harness</a>.",
      zh: "&copy; 2026 spark-to-paper-skills · MIT License · 论文：<a href=\"https://arxiv.org/abs/2608.11924\" target=\"_blank\" rel=\"noopener\">arXiv:2608.11924</a> · 基于 Claude Code 构建 · 画图：PaperBanana+ 原生 SVG，DrawAI hybrid 兜底 · 网站设计参考 <a href=\"https://lh-harness.pages.dev/\" target=\"_blank\" rel=\"noopener\">LongHorizon-Harness</a>。"
    }
  };

  const langCallbacks = [];
  const onLang = (fn) => langCallbacks.push(fn);
  const currentLang = () => (root.getAttribute("data-lang") === "zh" ? "zh" : "en");
  const d = (k) => {
    const e = dict[k];
    if (!e) return k;
    const v = e[currentLang()];
    return v != null ? v : (e.en != null ? e.en : k);
  };

  function applyLang(lang) {
    root.setAttribute("data-lang", lang);
    root.setAttribute("lang", lang === "zh" ? "zh-CN" : "en");
    $$("[data-i18n]").forEach((el) => {
      const e = dict[el.dataset.i18n];
      if (e && e[lang] != null) el.innerHTML = e[lang];
    });
    $$("[data-i18n-ph]").forEach((el) => {
      const e = dict[el.dataset.i18nPh];
      if (e && e[lang] != null) el.placeholder = e[lang];
    });
    $$("[data-i18n-label]").forEach((el) => {
      const e = dict[el.dataset.i18nLabel];
      if (e && e[lang] != null) { el.setAttribute("aria-label", e[lang]); el.title = e[lang]; }
    });
    const ll = $("#lang-toggle .lang-label");
    if (ll) ll.textContent = lang === "zh" ? "EN" : "中文";
    langCallbacks.forEach((f) => { try { f(); } catch (_) {} });
  }

  const langToggle = $("#lang-toggle");
  if (langToggle) langToggle.addEventListener("click", () => {
    const t = currentLang() === "zh" ? "en" : "zh";
    applyLang(t);
    try { localStorage.setItem("sp-lang", t); } catch (_) {}
  });
  const qp = new URLSearchParams(location.search);
  if (qp.get("lang") === "zh" || qp.get("lang") === "en") applyLang(qp.get("lang"));
  else if (currentLang() === "zh") applyLang("zh");

  /* =============================== theme =============================== */
  const themeBtn = $("#theme-toggle");
  const mqDark = window.matchMedia("(prefers-color-scheme: dark)");
  const CH = ["system", "light", "dark"];
  const applyTheme = (choice) => {
    const resolved = choice === "system" ? (mqDark.matches ? "dark" : "light") : choice;
    root.setAttribute("data-theme", resolved);
    if (themeBtn) {
      themeBtn.dataset.themeChoice = choice;
      const label = d("theme.label") + ": " + d("theme." + choice);
      themeBtn.title = label;
      themeBtn.setAttribute("aria-label", label);
    }
  };
  onLang(() => applyTheme(themeChoice));
  let themeChoice = (() => {
    const q = new URLSearchParams(location.search).get("theme");
    if (q === "light" || q === "dark") return q;
    try { const s = localStorage.getItem("sp-theme"); return s === "light" || s === "dark" ? s : "system"; }
    catch (_) { return "system"; }
  })();
  applyTheme(themeChoice);
  mqDark.addEventListener("change", () => { if (themeChoice === "system") applyTheme("system"); });
  if (themeBtn) themeBtn.addEventListener("click", () => {
    themeChoice = CH[(CH.indexOf(themeChoice) + 1) % 3];
    applyTheme(themeChoice);
    try { themeChoice === "system" ? localStorage.removeItem("sp-theme") : localStorage.setItem("sp-theme", themeChoice); } catch (_) {}
  });

  /* ==================== topbar, scroll-spy, TOC, anchors ==================== */
  const topbar = $("#topbar");
  const tocBtn = $("#toc-btn"), tocMenu = $("#toc-menu"), tocNum = $("#toc-num"), tocLabel = $("#toc-label");
  const navLinks = $$(".nav > a[href^='#'], .navmenu-pop a[href^='#']");
  const sections = () => $$("main section[id], section.hero[id], section.section[id]");

  const setMenu = (open) => {
    if (!tocMenu || !tocBtn) return;
    tocMenu.hidden = !open;
    tocBtn.setAttribute("aria-expanded", String(open));
  };
  if (tocBtn) tocBtn.addEventListener("click", (e) => { e.stopPropagation(); setMenu(tocMenu.hidden); });
  document.addEventListener("click", (e) => {
    if (tocMenu && !tocMenu.hidden && !tocMenu.contains(e.target) && e.target !== tocBtn) setMenu(false);
    if (tocMenu && e.target.closest && e.target.closest("#toc-menu a")) setMenu(false);
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && tocMenu && !tocMenu.hidden) { setMenu(false); tocBtn && tocBtn.focus(); }
  });

  let spyTick = false;
  function spy() {
    spyTick = false;
    const off = (topbar ? topbar.offsetHeight : 0) + 24;
    const y = window.scrollY + off;
    let cur = null;
    for (const sec of sections()) {
      const top = sec.getBoundingClientRect().top + window.scrollY;
      if (top <= y) cur = sec; else break;
    }
    if (window.innerHeight + window.scrollY >= document.body.scrollHeight - 4) {
      const all = sections();
      cur = all[all.length - 1] || cur;
    }
    const id = cur ? cur.id : "";
    navLinks.forEach((a) => {
      const hit = a.getAttribute("href") === "#" + id;
      a.classList.toggle("current", hit);
      if (hit) a.setAttribute("aria-current", "true"); else a.removeAttribute("aria-current");
    });
    const item = tocMenu ? $(`a[href="#${id}"]`, tocMenu) : null;
    if (tocNum && tocLabel) {
      if (item) {
        tocNum.hidden = false;
        tocNum.textContent = $(".tocnum", item).textContent;
        tocLabel.textContent = $("span:not(.tocnum)", item).textContent;
      } else {
        tocNum.hidden = false;
        tocNum.textContent = "◇";
        tocLabel.textContent = d("nav.contents").replace(/&amp;/g, "&");
      }
    }
    if (topbar) {
      topbar.classList.toggle("scrolled", window.scrollY > 4);
      const p = Math.min(1, window.scrollY / Math.max(1, document.body.scrollHeight - window.innerHeight));
      topbar.style.setProperty("--progress", String(p));
    }
  }
  window.addEventListener("scroll", () => { if (!spyTick) { spyTick = true; requestAnimationFrame(spy); } }, { passive: true });
  window.addEventListener("resize", () => { if (!spyTick) { spyTick = true; requestAnimationFrame(spy); } }, { passive: true });
  onLang(spy);
  spy();

  document.addEventListener("click", (e) => {
    const a = e.target.closest && e.target.closest("a[href^='#']");
    if (!a) return;
    const id = a.getAttribute("href").slice(1);
    const target = id ? document.getElementById(id) : null;
    if (!target && id) return;
    e.preventDefault();
    const top = target ? target.getBoundingClientRect().top + window.scrollY - ((topbar ? topbar.offsetHeight : 0) + 12) : 0;
    window.scrollTo({ top: Math.max(0, top), behavior: reduced.matches ? "auto" : "smooth" });
    try { history.replaceState(null, "", id ? "#" + id : "#top"); } catch (_) {}
  });

  /* ==================== quickstart tabs + copy buttons ==================== */
  const qsTabs = $$(".qs-tab");
  qsTabs.forEach((tab, i) => {
    tab.addEventListener("click", () => selectTab(i));
    tab.addEventListener("keydown", (e) => {
      if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
        const n = (i + (e.key === "ArrowRight" ? 1 : qsTabs.length - 1)) % qsTabs.length;
        selectTab(n); qsTabs[n].focus();
      }
    });
  });
  function selectTab(i) {
    qsTabs.forEach((t, j) => {
      const on = i === j;
      t.classList.toggle("is-on", on);
      t.setAttribute("aria-selected", String(on));
      const pane = document.getElementById(t.getAttribute("aria-controls"));
      if (pane) { pane.classList.toggle("is-on", on); try { pane.inert = !on; } catch (_) {} }
    });
  }
  selectTab(0);

  $$(".qs-alt-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const group = btn.parentElement;
      $$(".qs-alt-btn", group).forEach((b) => {
        const on = b === btn;
        b.classList.toggle("is-on", on);
        b.setAttribute("aria-pressed", String(on));
      });
      const code = $("#qs-install-cmd");
      if (code && btn.dataset.cmd) code.textContent = btn.dataset.cmd;
    });
  });

  function wireCopy(btn, getText, labelSel) {
    if (!btn) return;
    btn.addEventListener("click", async () => {
      const text = getText();
      let ok = false;
      try {
        if (navigator.clipboard && window.isSecureContext !== false) {
          await navigator.clipboard.writeText(text); ok = true;
        }
      } catch (_) {}
      if (!ok) {
        try {
          const ta = document.createElement("textarea");
          ta.value = text; ta.style.position = "fixed"; ta.style.opacity = "0";
          document.body.appendChild(ta); ta.select();
          ok = document.execCommand("copy");
          ta.remove();
        } catch (_) { ok = false; }
      }
      const label = labelSel ? $(labelSel, btn) : btn;
      label.innerHTML = d(ok ? "cite.copied" : "cite.copyFail");
      btn.classList.add("copied");
      setTimeout(() => { label.innerHTML = d("cite.copy"); btn.classList.remove("copied"); }, 1800);
    });
  }
  wireCopy($("#qs-copy"), () => { const c = $(".qs-pane.is-on .qs-code"); return c ? c.innerText : ""; }, ".qs-copy-label");
  wireCopy($("#bib-copy"), () => { const c = $("#bibtex-code"); return c ? c.innerText : ""; }, null);
  wireCopy($("#gates-copy"), () => { const c = $("#gates-code"); return c ? c.innerText : ""; }, null);

  /* ============================ reveal on scroll ============================ */
  const REVEAL_SEL = ".section-header,.step,.table-wrap,.bibtex,.finding-card,.figure-block,.problem-card,.idea-statement,.idea-panel,.paper-card,.takeaway,.kpi-strip,.loop-cycle";
  const staticMode = qp.get("static") === "1";
  const revealTargets = staticMode ? [] : $$(REVEAL_SEL).filter((el) => {
    const p = el.parentElement;
    return !(p && p.closest(REVEAL_SEL));
  });
  if (!staticMode && "IntersectionObserver" in window) {
    revealTargets.forEach((el) => el.classList.add("reveal"));
    const io = new IntersectionObserver((entries) => {
      entries.forEach((en) => {
        if (en.isIntersecting) { en.target.classList.add("visible"); io.unobserve(en.target); }
      });
    }, { threshold: 0.12, rootMargin: "0px 0px -60px 0px" });
    revealTargets.forEach((el) => io.observe(el));
  }

  /* ======================= hero pipeline animation ======================= */
  (function heroStage() {
    const wrap = $("#backends");
    const stage = wrap && $(".backends-stage", wrap);
    const mesh = $("#bk-mesh");
    const laneIn = $("#bk-lane-in");
    const laneOut = $("#bk-lane-out");
    const core = wrap && $(".bk-core", wrap);
    const rolesBox = $("#bk-roles");
    if (!wrap || !stage || !mesh || !laneIn || !laneOut || !core || !rolesBox) return;

    const SVGNS = "http://www.w3.org/2000/svg";
    const IN_CHIPS = [
      { label: () => d("bk.in.idea"), h: 18 },
      { label: () => "proposal.md", h: 30 },
      { label: () => "proposal + results.csv", h: 42 },
      { label: () => "story.json", h: 260 },
    ];
    const OUT_CHIPS = [
      { label: () => "main.pdf", h: 18 },
      { label: () => "sections/*.tex", h: 32 },
      { label: () => "refs.bib", h: 46 },
      { label: () => "figures/*.{pdf,svg,pptx}", h: 172 },
      { label: () => "blueprint.json", h: 186 },
      { label: () => "experiments/", h: 258 },
      { label: () => "logs/*.io.md", h: 272 },
    ];
    const ROLES = [
      { role: "m", name: "backends.role.up", words: ["idea2story"] },
      { role: "e", name: "backends.role.chain", words: ["plan", "cite", "write", "refine", "review", "data", "figure", "figure-svg", "figure-optimize", "latex"] },
      { role: "a", name: "backends.role.auto", words: ["experiment"] },
    ];

    const chip = (c) => `<span class="bk-chip" style="--h:${c.h}"><b>${c.label()}</b></span>`;
    const openChip = (key, h) => `<span class="bk-chip bk-chip-open" style="--h:${h}"><b>${d(key)}</b></span>`;

    function buildLanes() {
      const a = IN_CHIPS.map(chip).join("") + openChip("bk.open.in", 300);
      const b = OUT_CHIPS.map(chip).join("") + openChip("bk.open.out", 300);
      laneIn.innerHTML = a + a;
      laneOut.innerHTML = b + b;
      for (const lane of [laneIn, laneOut]) {
        const half = lane.scrollWidth / 2;
        if (half > 0) lane.style.setProperty("--dur", (half / 42) + "s");
      }
    }

    const counters = [0, 0, 0];
    function buildRoles() {
      rolesBox.innerHTML = ROLES.map((r, i) => `
        <div class="bk-role" data-role="${r.role}">
          <span class="bk-role-name">${d(r.name)}</span>
          <span class="bk-slot" data-slot="${i}"><span class="bk-slot-inner">
            <span class="bk-pair-half"><b class="bk-slot-word"></b></span>
          </span></span>
        </div>`).join("");
      ROLES.forEach((_, i) => setWord(i, false));
    }
    function setWord(i, animate) {
      const half = $(`[data-slot="${i}"] .bk-pair-half`, rolesBox);
      if (!half) return;
      const words = ROLES[i].words;
      const w = words[counters[i] % words.length];
      const b = $(".bk-slot-word", half);
      if (b.textContent === w) return;
      b.textContent = w;
      if (animate && !reduced.matches) {
        half.classList.remove("is-in");
        void half.offsetWidth;
        half.classList.add("is-in");
      }
    }

    function drawMesh() {
      const sb = stage.getBoundingClientRect();
      if (!sb.width || !sb.height) return;
      mesh.setAttribute("viewBox", `0 0 ${sb.width} ${sb.height}`);
      mesh.innerHTML = "";
      const cb = core.getBoundingClientRect();
      const coreTop = cb.top - sb.top, coreBottom = cb.bottom - sb.top;
      const roleXs = $$(".bk-role", rolesBox).map((r) => {
        const rb = r.getBoundingClientRect();
        return rb.left - sb.left + rb.width / 2;
      });
      if (!roleXs.length) return;
      const link = (x1, y1, x2, y2, h, i) => {
        const z = (y2 - y1) * 0.55;
        const p = document.createElementNS(SVGNS, "path");
        p.setAttribute("class", "bk-link");
        p.setAttribute("d", `M${x1} ${y1}C${x1} ${y1 + z} ${x2} ${y2 - z} ${x2} ${y2}`);
        p.setAttribute("style", `--h:${h};--i:${i}`);
        return p;
      };
      const inTrack = $(".bk-rail-models .bk-track", stage).getBoundingClientRect();
      const outTrack = $(".bk-rail-agents .bk-track", stage).getBoundingClientRect();
      let idx = 0;
      IN_CHIPS.forEach((c, i) => {
        const x = inTrack.left - sb.left + inTrack.width * ((i + 0.5) / IN_CHIPS.length);
        mesh.appendChild(link(x, inTrack.bottom - sb.top, roleXs[i % roleXs.length], coreTop, c.h, idx++));
      });
      OUT_CHIPS.forEach((c, i) => {
        const x = outTrack.left - sb.left + outTrack.width * ((i + 0.5) / OUT_CHIPS.length);
        mesh.appendChild(link(roleXs[i % roleXs.length], coreBottom, x, outTrack.top - sb.top, c.h, idx++));
      });
    }

    let timers = [];
    function startTimers() {
      if (timers.length || reduced.matches) return;
      timers = ROLES.map((_, i) => setInterval(() => {
        counters[i]++;
        setWord(i, true);
      }, 1500 + Math.round(Math.random() * 900) + i * 260));
    }
    function stopTimers() { timers.forEach(clearInterval); timers = []; }

    function rebuild() { buildLanes(); buildRoles(); requestAnimationFrame(drawMesh); }

    if (reduced.matches) wrap.classList.add("is-static");
    rebuild();
    requestAnimationFrame(() => requestAnimationFrame(drawMesh));
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(drawMesh).catch(() => {});
    if ("ResizeObserver" in window) new ResizeObserver(() => drawMesh()).observe(stage);
    onLang(rebuild);

    let inView = false;
    if ("IntersectionObserver" in window) {
      new IntersectionObserver((entries) => {
        entries.forEach((en) => {
          inView = en.isIntersecting;
          inView && !document.hidden ? startTimers() : stopTimers();
        });
      }, { threshold: 0.15 }).observe(wrap);
    } else { inView = true; startTimers(); }
    document.addEventListener("visibilitychange", () => {
      document.hidden || !inView ? stopTimers() : startTimers();
    });
  })();
})();
