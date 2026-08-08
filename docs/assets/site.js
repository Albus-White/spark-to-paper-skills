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
    "nav.code": { en: "Code", zh: "代码" },

    /* --- hero --- */
    "hero.subtitle": {
      en: "14 composable Claude Code skills turn a one-line idea into a <strong>compiled paper PDF</strong> — real verified references, editable vector figures, and <strong>machine-checked integrity</strong> included. Claude owns the judgment; deterministic Python gates own the facts. <em>No app. No server. No setup.</em>",
      zh: "14 个可组合的 Claude Code skill，把一句话想法变成<strong>编译完成的论文 PDF</strong>——真实且经核验的参考文献、可编辑的矢量图、<strong>机器校验的诚实性</strong>，一样不少。判断交给 Claude，事实交给确定性的 Python 闸门。<em>不装应用，不起服务，零配置。</em>"
    },
    "hero.btn.papers": { en: "See the papers", zh: "看论文成品" },
    "hero.btn.figures": { en: "Figure engine", zh: "画图引擎" },
    "hero.btn.pipeline": { en: "How it works", zh: "工作原理" },
    "hero.btn.code": { en: "Code Repo", zh: "代码仓库" },
    "hero.btn.sample": { en: "Sample paper", zh: "论文样例" },
    "hero.btn.sample.aria": { en: "Open a sample generated paper (PDF)", zh: "打开一篇生成的论文样例（PDF）" },
    "hero.btn.release": { en: "v1.2.0", zh: "v1.2.0" },
    "hero.related.tag": { en: "14 skills &middot; one orchestrator", zh: "14 个 skill · 一个调度者" },
    "backends.sub": { en: "ts-paper routes any input shape and drives the chain end to end", zh: "ts-paper 识别任意输入形态，驱动整条链走到底" },
    "backends.in": { en: "You drop", zh: "你丢进来" },
    "backends.out": { en: "You get", zh: "你拿到" },
    "backends.orch": { en: "Stage 0 &middot; route", zh: "Stage 0 · 路由" },
    "backends.a11y": {
      en: "A one-line idea, a proposal, a proposal with real results, or a corpus file all route through ts-paper and the 14-skill suite, and come out as a compiled PDF with sources, figures and logs on disk.",
      zh: "一句话想法、proposal、带真实结果的 proposal、语料文件，都交给 ts-paper 调度、由这套 14 个 skill 协作处理，最终产出编译好的 PDF，以及落在磁盘上的源文件、图和日志。"
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
      zh: "下次 Claude Code 会话自动加载。编译需要 Python&nbsp;3.10+ 和 <span style=\"white-space:nowrap\">LaTeX（<code>latexmk</code>）</span>。"
    },
    "qs.hint.run": {
      en: "Paste an idea, a proposal, or a proposal + real results. Stage&nbsp;0 routes it, the chain runs, and every stage leaves its trace under <code>logs/</code>.",
      zh: "贴进来一个想法、一份 proposal，或者 proposal + 真实结果。Stage&nbsp;0 负责路由，链条跑完，每个阶段都在 <code>logs/</code> 留下痕迹。"
    },

    /* --- scoreboard --- */
    "sb.kicker": { en: "Generated end-to-end &middot; zero fabricated numbers", zh: "端到端生成 · 零编造数字" },
    "sb.copy": {
      en: "Seven papers went in as research proposals and came out as compiled, publication-format PDFs. The pipeline planned each paper, verified every reference it cited, drafted and adversarially reviewed the text, drew editable vector figures, and compiled the result &mdash; with deterministic gates checking every step.",
      zh: "七篇论文以研究 proposal 的形态进入，以出版格式的编译版 PDF 出来。流水线为每篇论文做规划，核验所引的每条参考文献，起草并对抗式评审全文，绘制可编辑矢量图，最后编译成品——每一步都有确定性闸门把关。"
    },
    "sb.s1": { en: "papers, end to end", zh: "篇论文，端到端" },
    "sb.s2": { en: "research domains", zh: "个研究领域" },
    "sb.s3": { en: "compiled pages", zh: "页编译成品" },
    "sb.s4": { en: "verified references", zh: "条核验过的引用" },
    "sb.s5": { en: "editable vector figures", zh: "张可编辑矢量图" },
    "sb.note": {
      en: "Totals across the seven showcase papers below. References verified via WebSearch + Crossref; figures delivered as editable vector PDFs; integrity gates passed on all seven.",
      zh: "以上为下方七篇 showcase 论文的合计。参考文献经 WebSearch + Crossref 核验；图以可编辑矢量 PDF 交付；七篇全部通过诚实性闸门。"
    },

    /* --- overview strip --- */
    "ov.kicker": { en: "Overview", zh: "总览" },
    "ov.title": { en: "Every page below came out of the pipeline.", zh: "下面每一页，都是流水线生成的。" },

    /* --- 01 core idea --- */
    "idea.eyebrow": { en: "Core Idea", zh: "核心理念" },
    "idea.title": { en: "The model does the reasoning. The code keeps it honest.", zh: "模型负责推理，代码负责诚实。" },
    "idea.lede": {
      en: "Autonomous paper generators fail in three familiar ways: they invent numbers, they cite papers that do not exist, and they ship figures nobody can edit. spark-to-paper splits every stage between two actors &mdash; <strong>Claude owns the judgment</strong> (writing, research, critique, review) and <strong>deterministic Python gates own the facts</strong>. A red gate does not warn; it fails the build.",
      zh: "自动写论文的系统有三种熟悉的翻车方式：编造数字、引用不存在的文献、交付谁也没法编辑的图。spark-to-paper 把每个阶段拆给两个角色——<strong>判断归 Claude</strong>（写作、检索、批评、评审），<strong>事实归确定性的 Python 闸门</strong>。红色闸门不是警告，是直接让构建失败。"
    },
    "problem.p1.title": { en: "Fabricated numbers", zh: "编造数字" },
    "problem.p1.body": {
      en: "A draft that needs a result will happily invent one. Once a made-up metric enters the text, every later revision inherits and defends it.",
      zh: "初稿缺个结果，模型就会顺手编一个。编造的指标一旦进入正文，之后的每次修改都会继承它、为它辩护。"
    },
    "problem.p2.title": { en: "Phantom citations", zh: "幽灵引用" },
    "problem.p2.body": {
      en: "Title-only stubs generated to hit a quota. They look like a bibliography and collapse at the first reviewer who checks a DOI.",
      zh: "为凑数生成的只有标题的空条目。看着像参考文献，遇到第一个查 DOI 的审稿人就原形毕露。"
    },
    "problem.p3.title": { en: "Dead bitmap figures", zh: "死板的位图" },
    "problem.p3.body": {
      en: "AI image models produce rasters. A camera-ready paper needs vectors you can still edit the day before the deadline &mdash; not a flattened PNG.",
      zh: "AI 图像模型输出的是位图，而 camera-ready 需要截稿前一天还能改的矢量图——不是一张压平的 PNG。"
    },
    "idea.statement.title": { en: "Machine-checked integrity: not a style suggestion &mdash; a hard stop.", zh: "机器校验的诚实性：不是风格建议，是一道硬闸门。" },
    "idea.statement.body": {
      en: "One command, <code>run_gates.py &lt;workdir&gt; all</code>, chains the suite&rsquo;s finish-line gates and exits nonzero on the first red one: citation completeness, no-fabrication, word bands, editable-vector presence, figure-critique traces, and a zero-error LaTeX log. A nonzero exit means the paper is <em>not done</em> &mdash; no matter how good it looks.",
      zh: "一条命令 <code>run_gates.py &lt;workdir&gt; all</code> 串起套件的完工闸门，遇到第一个红色闸门就以非零码退出：引用完整性、不编造、字数区间、矢量图在位、图批评留痕、LaTeX 零报错。非零退出就意味着论文<em>没有完成</em>——看起来再好也不算。"
    },
    "idea.fig.caption": {
      en: "<b>From spark to paper.</b> The project&rsquo;s README banner &mdash; the workflow at a glance: one spark goes in; Claude Code drives the literature search, the experiments and the writing; a finished paper comes out.",
      zh: "<b>从火花到论文。</b>README 的项目横幅，一眼看全工作流：丢进一颗火花，Claude Code 驱动文献检索、实验与写作，出来一篇完整论文。"
    },
    "idea.f1.value": { en: "Claude", zh: "Claude" },
    "idea.f1.title": { en: "Model reasons", zh: "模型负责判断" },
    "idea.f1.body": {
      en: "Judgment-heavy work stays with the model: framing the story, planning the blueprint, reading candidate references, writing and refining prose, critiquing figures with its own vision, arguing against the draft in review.",
      zh: "重判断的活留给模型：定研究故事、规划 blueprint、逐篇读候选文献、写作与润色、用自己的视觉批评图、在评审阶段跟稿子对着干。"
    },
    "idea.f2.value": { en: "Python", zh: "Python" },
    "idea.f2.title": { en: "Code backstops", zh: "代码负责兜底" },
    "idea.f2.body": {
      en: "Deterministic tasks go to code: linting drafts, checking citation completeness, plotting from data, vectorizing figures, assembling LaTeX, compiling, and gating. Code never authors content; it only verifies it.",
      zh: "确定性的活交给代码：lint 草稿、查引用完整性、按数据画图、矢量化、组装 LaTeX、编译、设闸。代码从不产出内容，只负责核验内容。"
    },
    "idea.p1.title": { en: "Layer 1 &middot; Deterministic gates", zh: "第一层 · 确定性闸门" },
    "idea.p1.body": {
      en: "Section shape, word bands, no-fabrication, citation completeness, vector-PDF presence, compile status. Run per stage or all at once; the first red gate stops the line.",
      zh: "章节结构、字数区间、不编造、引用完整性、矢量 PDF 在位、编译状态。可以按阶段跑也可以一次跑全量，第一个红灯就停线。"
    },
    "idea.p2.title": { en: "Layer 2 &middot; Self-review", zh: "第二层 · 自查" },
    "idea.p2.body": {
      en: "The refine stage right-sizes every section to its band, scrubs AI tells from the prose, and re-reads each edit for the contradiction it may have introduced.",
      zh: "refine 阶段把每节调整到字数区间内，洗掉行文里的 AI 腔，并复读每一处修改，防止改出新的自相矛盾。"
    },
    "idea.p3.title": { en: "Layer 3 &middot; Adversarial review", zh: "第三层 · 对抗式评审" },
    "idea.p3.body": {
      en: "Isolated reviewers read the whole draft and must quote it verbatim to raise an issue; perspective-diverse skeptics then try to refute each finding. The loop runs until dry.",
      zh: "隔离的评审员通读全稿，提意见必须给出原文引用；再由视角各异的质疑者逐条反驳。循环跑到再也挖不出新问题为止。"
    },
    "idea.p4.title": { en: "Layer 4 &middot; Vision critique", zh: "第四层 · 视觉批评" },
    "idea.p4.body": {
      en: "Claude looks at every rendered figure with its own eyes &mdash; faithfulness to the method, semantic agreement with the equations, readability, aesthetics &mdash; and a measured geometry audit drives at least four repair rounds on every redrawn SVG.",
      zh: "Claude 亲眼看每张渲染出的图——是否忠实于方法、语义是否与公式一致、可读性、美观度——重绘出的每张 SVG 还要再过几何审计，至少驱动四轮修复。"
    },

    /* --- 02 pipeline --- */
    "pipe.eyebrow": { en: "Pipeline", zh: "流水线" },
    "pipe.title": { en: "One input in. Eight stages later, a compiled PDF.", zh: "丢进一个输入，八个阶段之后，一份编译好的 PDF。" },
    "pipe.lede": {
      en: "You drop <strong>one</strong> input &mdash; a bare idea, a structured proposal, a proposal with real results, or a story from a previous run. Stage&nbsp;0 of <code>ts-paper</code> classifies it with no fixed schema, sets the one switch the whole suite reads (<code>results_mode</code>), and drives the chain. <strong>Files on disk are the contract between stages</strong>; each stage writes an INPUT / DECISIONS / OUTPUT trace to <code>logs/</code>.",
      zh: "你只丢<strong>一个</strong>输入——一句想法、一份结构化 proposal、带真实结果的 proposal，或上次运行留下的 story。<code>ts-paper</code> 的 Stage&nbsp;0 不靠固定 schema，自行判断输入属于哪一类，设好全套件唯一的开关（<code>results_mode</code>），然后驱动整条链。<strong>磁盘上的文件就是阶段间的契约</strong>；每个阶段都往 <code>logs/</code> 写一份 INPUT / DECISIONS / OUTPUT 记录。"
    },
    "pipe.route.title": { en: "Stage&nbsp;0 &middot; What you drop decides the route.", zh: "Stage&nbsp;0 · 丢什么，走什么路。" },
    "pipe.route.th1": { en: "You dropped", zh: "你丢进来的" },
    "pipe.route.th2": { en: "Route", zh: "路由" },
    "pipe.route.a1": { en: "A one-line idea", zh: "一句话想法" },
    "pipe.route.a2": { en: "<code>ts-idea2story</code> builds the story first, then the chain", zh: "先由 <code>ts-idea2story</code> 构建研究故事，再进主链" },
    "pipe.route.b1": { en: "A structured proposal", zh: "一份结构化 proposal" },
    "pipe.route.b2": { en: "Straight into the chain &mdash; result cells stay blank", zh: "直接进主链——结果单元格保持空白" },
    "pipe.route.c1": { en: "A proposal + measured results", zh: "proposal + 实测结果" },
    "pipe.route.c2": { en: "<code>ts-paper-data</code> distills the numbers into <code>results.facts.json</code>", zh: "<code>ts-paper-data</code> 把数字提炼进 <code>results.facts.json</code>" },
    "pipe.route.d1": { en: "A <code>story.json</code> from a prior run", zh: "上次运行留下的 <code>story.json</code>" },
    "pipe.route.d2": { en: "Skips idea2story, straight to planning", zh: "跳过 idea2story，直接进入规划" },
    "pipe.route.caption": {
      en: "Any real measured number in the input &mdash; a filled table, &ldquo;achieved 0.62 HOTA&rdquo; &mdash; forces the data-aware route; it is never sent down the no-numbers proposal path. Optional upstream: <code>ts-kg-build</code> turns a <code>corpus.jsonl</code> into a research-pattern knowledge graph for story recall, degrading gracefully when no embedding endpoint is configured.",
      zh: "输入里只要出现真实测量值——填好的一张表、一句「achieved 0.62 HOTA」——就强制走 data-aware 路线，绝不会被送进无数字的 proposal 路径。可选上游：<code>ts-kg-build</code> 把 <code>corpus.jsonl</code> 建成研究模式知识图谱供故事召回，没配 embedding 端点时平滑降级。"
    },
    "pipe.fig.title": { en: "The chain and its artifacts", zh: "链条与它的产物" },
    "pipe.fig.note": {
      en: "Every stage owns one artifact &mdash; blueprint.json, refs.bib, sections/*.tex, figures/*.pdf, main.pdf &mdash; and the next stage consumes it from disk.",
      zh: "每个阶段负责一件产物——blueprint.json、refs.bib、sections/*.tex、figures/*.pdf、main.pdf——下一阶段从磁盘上接手。"
    },
    "pipe.s1.title": { en: "1 &middot; Plan", zh: "1 · 规划" },
    "pipe.s1.body": {
      en: "One reasoning pass emits <code>blueprint.json</code>: title, keywords, exactly three contributions, notation, terminology, experiment design, per-section word targets.",
      zh: "一次推理产出 <code>blueprint.json</code>：标题、关键词、恰好三条 contribution、符号表、术语表、实验设计、逐节字数目标。"
    },
    "pipe.s2.title": { en: "2 &middot; Cite", zh: "2 · 引用" },
    "pipe.s2.body": {
      en: "Broad WebSearch per angle, abstracts read, metadata fetched via Crossref / arXiv. Floor of 40 real references, every one mapped to the claim it supports.",
      zh: "按检索角度大面积 WebSearch、逐篇读摘要、经 Crossref / arXiv 取元数据。至少 40 条真实文献，每条都对应到它支撑的论断。"
    },
    "pipe.s3.title": { en: "3 &middot; Write", zh: "3 · 写作" },
    "pipe.s3.body": {
      en: "All sections in one holistic pass &mdash; terminology stays consistent because the whole paper is in context. In proposal mode, result cells stay <code>--</code>.",
      zh: "所有章节一气呵成——整篇论文都在上下文里，术语不会漂移。proposal 模式下，结果单元格一律 <code>--</code>。"
    },
    "pipe.s4.title": { en: "4 &middot; Refine", zh: "4 · 润色" },
    "pipe.s4.body": {
      en: "Right-size to the enforced word bands, scrub the AI tells, self-check the logic of every edit. &ldquo;Right-sized&rdquo; is verified in code, not by eye.",
      zh: "把篇幅调进强制的字数区间，洗掉 AI 腔，每处修改都自查逻辑。「篇幅合格」由代码验证，不靠目测。"
    },
    "pipe.s5.title": { en: "5 &middot; Review", zh: "5 · 评审" },
    "pipe.s5.body": {
      en: "The adversarial panel argues against the paper: isolated reviewers, verbatim-quote anti-skim, skeptic verification, loop until dry. Fixes route back through refine.",
      zh: "对抗评审团站在论文对面：隔离评审、原文引用防略读、质疑者复核、循环挖到无新问题。修复统一回流 refine 处理。"
    },
    "pipe.s6.title": { en: "6 &middot; Figures", zh: "6 · 画图" },
    "pipe.s6.body": {
      en: "Data plots are born-vector matplotlib; schematics are PaperBanana renders whose design language is learned, then redrawn as native, audited SVG.",
      zh: "数据图由 matplotlib 生成、天生矢量；示意图先由 PaperBanana 渲染，学其设计语言后重绘为原生 SVG，并经几何审计。"
    },
    "pipe.s7.title": { en: "7 &middot; Compile", zh: "7 · 编译" },
    "pipe.s7.body": {
      en: "Template-driven assembly and <code>latexmk</code>. Zero-error logs and a resolved bibliography required; the fix loop is bounded at three tries.",
      zh: "按模板组装，<code>latexmk</code> 编译。要求日志零报错、参考文献全部解析；修复循环上限三次。"
    },
    "pipe.s8.title": { en: "8 &middot; Experiments (auto)", zh: "8 · 实验（自动）" },
    "pipe.s8.body": {
      en: "Runs automatically after the first gates-green draft: diagnoses the paper&rsquo;s logic, runs only feasible experiments on real data, fills the tables, recompiles.",
      zh: "首版全绿后自动启动：诊断论文逻辑，只在真实数据上跑可行的实验，把表填上真实数字，重新编译。"
    },
    "pipe.mode.p.tag": { en: "results_mode &middot; proposal", zh: "results_mode · proposal" },
    "pipe.mode.p.title": { en: "No numbers, ever", zh: "一个数字都不许有" },
    "pipe.mode.p.body": {
      en: "Forward-looking prose only. A concrete metric in a sentence &mdash; &ldquo;18.3%&rdquo;, &ldquo;0.72 F1&rdquo;, &ldquo;2.5&times;&rdquo;, even &ldquo;doubles&rdquo; &mdash; hard-fails the lint; bare-integer results are caught in self-review. Result tables exist with every cell literally <code>--</code>; the only place a dash may appear. No results figure is drawn at all, because drawing one would fabricate data.",
      zh: "只允许面向未来的行文。句子里出现具体指标——「18.3%」「0.72 F1」「2.5&times;」甚至「翻倍」——lint 直接判负；裸整数结果由自查兜住。结果表照常存在，但每个单元格都是 <code>--</code>，这也是横线唯一允许出现的地方。结果图一张也不画：画了就等于捏造数据。"
    },
    "pipe.mode.d.tag": { en: "results_mode &middot; data_aware", zh: "results_mode · data_aware" },
    "pipe.mode.d.title": { en: "Every number traced", zh: "每个数字可溯源" },
    "pipe.mode.d.body": {
      en: "Your real results are distilled into <code>results.facts.json</code> &mdash; the audit ground truth. Result sections switch to definitive past tense; any decimal or percent in prose that is not in the facts file fails the build. A measured-but-missing value is written <code>TBD</code> and never guessed.",
      zh: "你的真实结果被提炼进 <code>results.facts.json</code>——审计用的 ground truth。结果章节改用确定的过去时；正文里任何不在 facts 文件中的小数或百分数都会让构建失败。测过但拿不到的值写 <code>TBD</code>，绝不猜。"
    },

    /* --- 03 figure engine --- */
    "fig.eyebrow": { en: "Figure Engine", zh: "画图引擎" },
    "fig.title": {
      en: "AI image models make rasters. Papers need editable vectors. This engine ships both.",
      zh: "AI 图像模型画的是位图，论文要的是可编辑矢量图——这台引擎两头都给你。"
    },
    "fig.lede": {
      en: "The engine is decided by <strong>which section a figure lives in</strong>. Results plots draw from real data with matplotlib &mdash; numerically exact, born vector, never from an image model. Every other figure runs a three-act pipeline: the official <strong>PaperBanana</strong> agent team renders candidate images; <code>ts-figure-svg</code> learns the winner&rsquo;s design language and <strong>redraws the figure natively</strong> &mdash; real <code>&lt;rect&gt;/&lt;path&gt;/&lt;text&gt;</code>, its content taken from the paper&rsquo;s own facts, never traced from pixels; then a stdlib geometry audit drives a repair loop of at least four rounds. If native redraw is impossible, the DrawAI hybrid &mdash; then the approved PNG &mdash; steps in. <strong>Never a lossy trace.</strong>",
      zh: "用哪台引擎，取决于<strong>图长在哪个章节</strong>。结果图用 matplotlib 从真实数据画——数值精确、天生矢量，绝不出自图像模型。其余每张图走三幕流水线：官方 <strong>PaperBanana</strong> 智能体团队先渲染候选图；<code>ts-figure-svg</code> 学会胜出那张的设计语言，<strong>按论文自己的事实原生重绘</strong>——真正的 <code>&lt;rect&gt;/&lt;path&gt;/&lt;text&gt;</code> 对象，绝不描摹像素；随后 stdlib 几何审计驱动至少四轮修复。原生重绘实在不可行时，才轮到 DrawAI hybrid、再到定稿 PNG。<strong>绝不做有损描摹。</strong>"
    },
    "fig.s1.title": { en: "Render candidates", zh: "渲染候选" },
    "fig.s1.body": {
      en: "The official PaperBanana pipeline &mdash; Retriever &rarr; Planner &rarr; Stylist &rarr; Visualizer &rarr; Critic &mdash; produces candidate images; a distilled image-model loop stands in when no key is configured.",
      zh: "官方 PaperBanana 管线——Retriever &rarr; Planner &rarr; Stylist &rarr; Visualizer &rarr; Critic——产出候选图；没配 key 时由蒸馏版图像模型循环顶上。"
    },
    "fig.s2.title": { en: "Learn the look", zh: "学习设计语言" },
    "fig.s2.body": {
      en: "Claude looks at the chosen render and extracts its design language &mdash; palette, type scale, spacing, idiom &mdash; into a style sheet. The PNG is a <em>style reference only</em>.",
      zh: "Claude 端详选中的渲染图，把它的设计语言——配色、字号层级、留白、视觉习惯——提炼成一份样式表。PNG <em>只当风格参照</em>。"
    },
    "fig.s3.title": { en: "Redraw from the facts", zh: "按事实重绘" },
    "fig.s3.body": {
      en: "The figure is redrawn as a native SVG from the paper&rsquo;s own text: every label live <code>&lt;text&gt;</code>, every edge traceable to the method. Never traced, never embedded &mdash; take the PNG&rsquo;s look, take the paper&rsquo;s content.",
      zh: "整张图按论文自己的文本重绘成原生 SVG：每条标签都是活的 <code>&lt;text&gt;</code>，每条边都能追溯到方法本身。不描摹、不内嵌——要 PNG 的<em>样子</em>，要论文的<em>内容</em>。"
    },
    "fig.s4.title": { en: "Audit &amp; repair", zh: "审计与修复" },
    "fig.s4.body": {
      en: "A stdlib-only geometry audit measures the drawing &mdash; overflow, text-on-text, clipped arrowheads, sub-legible type &mdash; and drives repairs for at least four rounds, with no upper bound while defects remain.",
      zh: "纯 stdlib 的几何审计逐项测量这张图——溢出、文字叠文字、被裁掉的箭头、小到看不清的字号——驱动至少四轮修复；只要还有缺陷，就没有轮数上限。"
    },
    "fig.lane.decompose": { en: "Redraw", zh: "重绘" },
    "fig.lane.decompose.note": { en: "native objects &mdash; no pixels, no tracing", zh: "原生对象——不贴像素，不描摹" },
    "fig.l1.title": { en: "Style sheet from the render", zh: "从渲染图提炼样式表" },
    "fig.l1.body": {
      en: "Palette, type scale, spacing and visual idiom are read off the chosen PaperBanana candidate by eye and written down as a style sheet.",
      zh: "配色、字号层级、留白、视觉习惯，从选中的 PaperBanana 候选图上逐项读出来，写成一份样式表。"
    },
    "fig.l2.title": { en: "Content from the paper", zh: "内容来自论文" },
    "fig.l2.body": {
      en: "Modules, edges and labels come from the figure spec and the paper&rsquo;s equations &mdash; generated renders invent links and garble labels, so their logic is never trusted.",
      zh: "模块、连线、标签全部来自图规格和论文公式——生成的渲染图会瞎编连线、写错标签，它的逻辑一概不信。"
    },
    "fig.l3.title": { en: "Real vector objects", zh: "真正的矢量对象" },
    "fig.l3.body": {
      en: "The figure is drawn as genuine <code>&lt;rect&gt;/&lt;path&gt;/&lt;text&gt;</code> elements &mdash; every label live, editable text, with glyphs kept Times-safe so the PDF embeds fonts cleanly.",
      zh: "整张图由真正的 <code>&lt;rect&gt;/&lt;path&gt;/&lt;text&gt;</code> 元素画成——每条标签都是活的可编辑文本，字形限定在 Times 安全集内，PDF 里字体干干净净地内嵌。"
    },
    "fig.ring.seg": { en: "Draw", zh: "绘制" },
    "fig.ring.read": { en: "Measure", zh: "测量" },
    "fig.ring.build": { en: "Repair", zh: "修复" },
    "fig.ring.core": { en: "<em>PaperBanana+</em><i>&ge;4 rounds</i>", zh: "<em>PaperBanana+</em><i>&ge;4 轮</i>" },
    "fig.lane.rebuild": { en: "Measure", zh: "测量" },
    "fig.lane.rebuild.note": { en: "stdlib-only &mdash; no renderer, no models, no key", zh: "纯 stdlib——不用渲染器、模型和 key" },
    "fig.l4.title": { en: "The audit measures the drawing", zh: "审计逐项测量" },
    "fig.l4.body": {
      en: "<code>audit_svg.py</code> computes text boxes from Times core-14 metrics and fails a round on canvas or card overflow, a clipped arrowhead, text over text, shapes painted over text, sub-legible type, font-fallback glyphs, CSS-cascade colour traps &mdash; and path soup, the signature of a traced raster.",
      zh: "<code>audit_svg.py</code> 用 Times core-14 字体度量算出每个文本框，凡是画布或卡片溢出、箭头被裁、文字叠文字、图形压住文字、字号小到读不清、字形触发字体回退、CSS 级联吃掉颜色——以及描摹位图特有的 path soup——当轮一律判负。"
    },
    "fig.lane.verify": { en: "Verify", zh: "核验" },
    "fig.lane.verify.note": { en: "the gate reads the audit trail, not the report", zh: "闸门看审计记录，不看汇报" },
    "fig.l5.title": { en: "Verified on the compiled page", zh: "在编译成品页上验证" },
    "fig.l5.body": {
      en: "The SVG exports to a vector PDF that must genuinely embed its fonts &mdash; an exporter that outlines every glyph is caught &mdash; and the figure is checked on the real compiled page. The build gate requires at least four audit rounds.",
      zh: "SVG 导出的矢量 PDF 必须真的内嵌字体——把所有字形转成轮廓线蒙混过关的导出器会被识破——最后在真实编译出的页面上检查整张图。构建闸门要求至少四轮审计。"
    },
    "fig.l6.title": { en: "No upper bound while defects remain.", zh: "缺陷不清零，轮数无上限。" },
    "fig.l6.body": {
      en: "Four rounds is the floor, not the ceiling &mdash; the draw&ndash;measure&ndash;repair loop keeps going until the audit comes back clean. And if native redraw is genuinely impossible, the ladder holds: DrawAI hybrid, then the approved PNG. Never a lossy trace.",
      zh: "四轮只是下限——绘制、测量、修复的循环一直跑到审计全绿为止。原生重绘实在不可行时，梯子照样接得住：先 DrawAI hybrid，再定稿 PNG。绝不做有损描摹。"
    },
    "fig.k1.name": { en: "Repair loop", zh: "修复循环" },
    "fig.k1.metric": { en: "audit rounds per figure", zh: "每张图审计轮数" },
    "fig.k1.delta": { en: "gate-enforced", zh: "闸门强制" },
    "fig.k2.name": { en: "Audit cost", zh: "审计成本" },
    "fig.k2.metric": { en: "renderer &middot; models &middot; keys", zh: "渲染器 · 模型 · key" },
    "fig.k2.delta": { en: "stdlib-only", zh: "纯 stdlib" },
    "fig.k3.name": { en: "Fallback hybrid", zh: "兜底 HYBRID" },
    "fig.k3.metric": { en: "SSIM vs full redraw", zh: "SSIM，对比整图重画" },
    "fig.k3.delta": { en: "reported", zh: "项目实测" },
    "fig.k4.name": { en: "Pixel tracing", zh: "像素描摹" },
    "fig.k4.metric": { en: "paths in one auto-trace", zh: "一次自动描摹的 path 数" },
    "fig.k4.delta": { en: "banned", zh: "已禁用" },
    "fig.demo.title": { en: "Born-vector data figures, straight from the showcase papers", zh: "天生矢量的数据图，直接取自 showcase 论文" },
    "fig.demo.note": {
      en: "Results plots are drawn from code with the suite&rsquo;s publication house style &mdash; semantic colors, exact numbers from <code>results.facts.json</code>, and a vector PDF written alongside every PNG with the text kept editable.",
      zh: "结果图由代码按套件的出版级样式绘制——语义化配色、数字精确来自 <code>results.facts.json</code>，每张 PNG 旁边都同时写出一份文字可编辑的矢量 PDF。"
    },
    "fig.f1.title": { en: "Why not just trace the PNG?", zh: "为什么不直接描摹 PNG？" },
    "fig.f1.body": {
      en: "Auto-tracing one figure produced 59,430 paths, 10&nbsp;MB, and not one editable label &mdash; and it was still blurry when zoomed. &ldquo;No <code>&lt;image&gt;</code> element&rdquo; does not mean vector. So the redraw takes the PNG&rsquo;s <em>look</em> and the paper&rsquo;s <em>content</em>, and draws real objects.",
      zh: "自动描摹一张图，得到 59,430 条 path、10&nbsp;MB 体积、零条可编辑标签——放大了照样糊。「没有 <code>&lt;image&gt;</code> 元素」不等于矢量。所以重绘只取 PNG 的<em>样子</em>、只取论文的<em>内容</em>，画的是真对象。"
    },
    "fig.f2.value": { en: "3<em>rungs</em>", zh: "三<em>级</em>" },
    "fig.f2.title": { en: "The fallback ladder", zh: "兜底阶梯" },
    "fig.f2.body": {
      en: "Native SVG first. If the redraw is impossible, the vendored DrawAI hybrid keeps the approved render pixel-exact under an editable text overlay (~0.91 SSIM, key-free via ModelScope). Failing that, the approved PNG goes in as-is &mdash; full richness preserved, editability deferred. Never a lossy trace.",
      zh: "首选原生 SVG。重绘不可行时，内置的 DrawAI hybrid 把定稿渲染图保持像素级不变，叠上可编辑文字层（SSIM 约 0.91，经 ModelScope 免 key）。再不行，定稿 PNG 原样插入——细节一点不丢，可编辑性推迟。绝不做有损描摹。"
    },

    /* --- 04 experiments --- */
    "exp.eyebrow": { en: "Experiments", zh: "实验" },
    "exp.title": {
      en: "Stage 8 runs what the paper claims &mdash; or files a report saying why it can&rsquo;t.",
      zh: "论文声称的实验，Stage 8 要么真跑，要么白纸黑字说明为什么跑不了。"
    },
    "exp.lede": {
      en: "After the chain delivers a gates-green first draft, <code>ts-paper-experiment</code> starts automatically &mdash; no one has to ask. It maps the paper&rsquo;s logic, plans the minimum set of experiments, classifies each as <strong>necessary, feasible, or blocked</strong>, executes only what real data and code support, and recompiles the paper with measured numbers. If nothing can run, it writes a requirements report and leaves the tables in proposal form &mdash; <strong>it never invents results</strong>.",
      zh: "链条交出全绿的首版后，<code>ts-paper-experiment</code> 自动启动——不用任何人开口。它梳理论文逻辑，规划最小实验集，把每个实验标成<strong>必要、可行或受阻</strong>，只执行真实数据和代码撑得起的部分，再用实测数字重新编译论文。什么都跑不了时，就写一份需求报告，让表格保持 proposal 形态——<strong>绝不编造结果</strong>。"
    },
    "exp.s1.title": { en: "Diagnose", zh: "诊断" },
    "exp.s1.body": {
      en: "Three reports map the territory: the paper&rsquo;s logic, its claimed contributions, and the gap between claimed and existing experiments.",
      zh: "三份报告摸清底细：论文的逻辑、声称的 contribution，以及「声称做了」与「实际有」之间的实验缺口。"
    },
    "exp.s2.title": { en: "Plan", zh: "规划" },
    "exp.s2.body": {
      en: "Each experiment is classified necessary / feasible / blocked, with metrics, baselines and commands. Named open datasets must actually be downloaded before &ldquo;blocked&rdquo; may be declared.",
      zh: "每个实验标注必要 / 可行 / 受阻，附指标、baseline 和命令。点名的开放数据集必须真的去下载过，才允许宣布「受阻」。"
    },
    "exp.s3.title": { en: "Run", zh: "执行" },
    "exp.s3.body": {
      en: "Real data and code only, seeds fixed at [1,&nbsp;2,&nbsp;3], cheap local runs auto-approved, costly or external-data runs held for explicit user approval.",
      zh: "只用真实数据和代码，随机种子固定 [1,&nbsp;2,&nbsp;3]；便宜的本地运行自动放行，昂贵或需外部数据的运行等用户明确批准。"
    },
    "exp.s4.title": { en: "Audit &amp; fill", zh: "审计与填表" },
    "exp.s4.body": {
      en: "Every value is recomputed from per-seed raw logs, traced to its source file, and only then written into the paper&rsquo;s own result tables &mdash; nulls and honest failures included.",
      zh: "每个数值都从逐 seed 的原始日志重算、溯源到具体文件，然后才写进论文自己的结果表——空值和诚实的失败照写不误。"
    },
    "exp.f1.title": { en: "Audit reports before any number lands", zh: "数字落表前的审计报告" },
    "exp.f1.body": {
      en: "Provenance, completeness, code&ndash;paper consistency, design correctness, artifact completeness, and a single truthfulness verdict. &ldquo;No value may be guessed, manually invented, or written from memory.&rdquo;",
      zh: "溯源、完整性、代码与论文一致性、实验设计正确性、代码产物完整性，外加一个总的真实性裁定。「任何数值不得靠猜、不得手造、不得凭记忆写。」"
    },
    "exp.f2.value": { en: "weaken<em>or</em><span class=\"finding-ref\">remove</span>", zh: "弱化<em>或</em><span class=\"finding-ref\">删除</span>" },
    "exp.f2.title": { en: "When a claim outruns its evidence", zh: "论断跑到证据前面时" },
    "exp.f2.body": {
      en: "Anything classified CLAIMED_BUT_NOT_RUN gets its claim weakened or removed &mdash; or the run stops to ask. The final step diffs the before/after paper and issues an honesty verdict, admitting when experiments weakened the original story.",
      zh: "凡被判为 CLAIMED_BUT_NOT_RUN 的论断：要么弱化，要么删除，要么停下来问用户。最后一步对比修改前后的论文并给出诚实性裁定，实验削弱了原本故事时也照实承认。"
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
    "exp.t5b": { en: "27 human-approved rules; candidates are never auto-promoted", zh: "27 条人工批准的规则；候选规则绝不自动转正" },
    "exp.table.caption": {
      en: "From the skill&rsquo;s bundled <code>paper_config.yaml</code> and <code>golden_rules.md</code>. Experiments run locally; Overleaf sync is configurable via <code>paper_config.yaml</code> + <code>.env</code>.",
      zh: "出自 skill 内置的 <code>paper_config.yaml</code> 与 <code>golden_rules.md</code>。实验在本地运行；Overleaf 同步经 <code>paper_config.yaml</code> 与 <code>.env</code> 配置。"
    },

    /* --- 05 writing & review --- */
    "wr.eyebrow": { en: "Writing &amp; Review", zh: "写作与评审" },
    "wr.title": {
      en: "Journal-shaped prose, with the AI scrubbed out and a courtroom at the end.",
      zh: "期刊味的行文，洗掉 AI 腔，最后还有一场庭审。"
    },
    "wr.lede": {
      en: "The blueprint fixes the shape before a word is written: per-section word bands, exactly three contributions, a notation table every section must reuse. The draft is written in <strong>one holistic pass</strong> so terminology never drifts; refine right-sizes it and scrubs the tells; and then a review panel does what the rest of the suite never does &mdash; <strong>argues against the paper</strong>.",
      zh: "动笔之前，blueprint 先把形状定死：逐节字数区间、恰好三条 contribution、每节都必须复用的符号表。草稿<strong>一气呵成</strong>，术语不漂移；refine 调篇幅、洗 AI 腔；最后评审团做全套件其他环节都不做的事——<strong>站到论文的对立面</strong>。"
    },
    "wr.s1.title": { en: "Blueprint", zh: "蓝图" },
    "wr.s1.body": {
      en: "Title of 8&ndash;14 words, 4&ndash;6 keywords, three contributions, full notation &mdash; one reasoning pass, linted before anything downstream may start.",
      zh: "标题 8&ndash;14 个词、关键词 4&ndash;6 个、三条 contribution、完整符号表——一次推理完成，先过 lint，下游才准开工。"
    },
    "wr.s2.title": { en: "Real references", zh: "真实参考文献" },
    "wr.s2.body": {
      en: "Floor of 40, built through Crossref and arXiv metadata &mdash; authors, venue, pages, DOI. A title-only stub is forbidden; a claim with no real paper behind it goes uncited.",
      zh: "下限 40 条，经 Crossref 与 arXiv 元数据构建——作者、期刊/会议、页码、DOI 俱全。只有标题的空条目属禁品；找不到真实文献支撑的论断，宁可不引。"
    },
    "wr.s3.title": { en: "Holistic draft", zh: "整体成稿" },
    "wr.s3.body": {
      en: "Method first, ~2000&ndash;3000 words; intro in exactly five paragraphs; related work by theme, never chronology. Every symbol defined before use, no raw Unicode.",
      zh: "方法先行，约 2000&ndash;3000 词；引言恰好五段；相关工作按主题组织，绝不按时间罗列。符号先定义后使用，不写裸 Unicode。"
    },
    "wr.s4.title": { en: "Right-size + de-AI", zh: "调篇幅 + 去 AI 腔" },
    "wr.s4.body": {
      en: "Word bands enforced in code. Comma-soup fragments become connected prose; &ldquo;delve&rdquo;, &ldquo;leverage&rdquo;, &ldquo;it is worth noting&rdquo; and their kin are hunted down; citations, math and labels stay untouched.",
      zh: "字数区间由代码强制执行。逗号连成的碎句改写成连贯行文；「delve」「leverage」「it is worth noting」之流一一清剿；引用、公式和标签分毫不动。"
    },
    "wr.rev.title": { en: "&ldquo;Can&rsquo;t quote = didn&rsquo;t read.&rdquo;", zh: "「引不出原文 = 没读。」" },
    "wr.rev.body": {
      en: "The review panel runs N isolated reviewers &mdash; theory, empirical, applied lenses &mdash; each seeing nothing but the paper. Every issue must carry an exact verbatim quote and a closeable criterion. Each finding then faces three perspective-diverse skeptics &mdash; misreading? already addressed? overblown? &mdash; and survives unless a majority refute it. Fresh panels re-run until a full pass finds nothing new &mdash; within a budget-capped number of rounds. Fixes are minimal, targeted, and re-gated: the linters are re-run after the edits land, because the suite derives &ldquo;green&rdquo; &mdash; it never forecasts it.",
      zh: "评审团由 N 位隔离评审组成——理论、实证、应用三种视角——每人眼里只有论文本身。每条意见必须带精确的原文引用和一条可关闭的验收标准。随后每条意见面对三位视角各异的质疑者——是不是读岔了？是不是早已处理？是不是言过其实？——多数反驳才能否决它。评审团一轮轮重开，直到整轮再无新发现——轮数有预算上限。修复最小化、有的放矢，改完重新过闸：linter 在修改落盘后重跑，因为这套系统只「推导」绿灯，从不「预告」绿灯。"
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
      zh: "想加一个 venue，丢一个 <code>templates/&lt;name&gt;/</code> 目录进来即可——内含 <code>template.json</code> 和该 venue 的 LaTeX 资源，不改一行代码。套件的硬规矩：样式文件要么用户自带，要么从官方渠道原样获取，<strong>绝不伪造</strong>。"
    },

    /* --- 06 showcase --- */
    "sc.eyebrow": { en: "Showcase", zh: "论文展示" },
    "sc.title": { en: "Seven papers. Six domains. Every number traceable.", zh: "七篇论文，六个领域，每个数字都可溯源。" },
    "sc.lede": {
      en: "Each paper below started as a research proposal and ran the full chain &mdash; plan &rarr; cite &rarr; write &rarr; refine &rarr; review &rarr; figure &rarr; compile. Click any card for the compiled PDF.",
      zh: "下面每篇论文都从一份研究 proposal 出发，跑完整条链——plan &rarr; cite &rarr; write &rarr; refine &rarr; review &rarr; figure &rarr; compile。点击卡片查看编译好的 PDF。"
    },
    "sc.read": { en: "Read the PDF &#8599;", zh: "阅读 PDF &#8599;" },
    "sc.p1.domain": { en: "environmental monitoring", zh: "环境监测" },
    "sc.p1.note": {
      en: "The reported superiority of decomposition-ensemble methods shrinks dramatically under proper temporal splitting &mdash; corrected baselines for the field.",
      zh: "在正确的时间切分下，分解-集成方法宣称的优势大幅缩水——为该领域给出修正后的 baseline。"
    },
    "sc.p2.domain": { en: "energy forecasting", zh: "能源预测" },
    "sc.p2.note": {
      en: "The leakage-free framework transfers from environmental to energy time series, revealing consistent overestimation in published results.",
      zh: "无泄漏评测框架从环境时序迁移到能源时序，揭示已发表结果中一致的高估。"
    },
    "sc.p3.domain": { en: "environmental AI", zh: "环境 AI" },
    "sc.p3.note": {
      en: "Competitive accuracy that also exposes feature-level rationale &mdash; bridging the trust gap between black-box models and regulatory transparency.",
      zh: "精度有竞争力，还能给出特征级依据——弥合黑盒模型与监管透明度之间的信任缺口。"
    },
    "sc.p4.domain": { en: "computer vision / agriculture", zh: "计算机视觉 / 农业" },
    "sc.p4.note": {
      en: "Replaces global average pooling with a learnable sparse read-out that focuses on lesions &mdash; higher accuracy on edge-deployable architectures.",
      zh: "用可学习的稀疏读出替换全局平均池化，聚焦病斑——边缘可部署的小模型拿到更高精度。"
    },
    "sc.p5.domain": { en: "clinical AI", zh: "临床 AI" },
    "sc.p5.note": {
      en: "Recasts screening as calibrated, interpretable risk estimation &mdash; and shows where raw accuracy hides clinically useless behavior.",
      zh: "把筛查重塑为校准且可解释的风险估计——并指出裸精度在哪些地方掩盖了临床上毫无用处的行为。"
    },
    "sc.p6.domain": { en: "industrial fault diagnosis", zh: "工业故障诊断" },
    "sc.p6.note": {
      en: "Perfect naive accuracy drops once recordings or loads are held out &mdash; and the compact CNN stops dominating classical baselines.",
      zh: "一旦按录音或负载留出测试集，「完美」的朴素精度应声下跌——小型 CNN 也不再压制经典 baseline。"
    },
    "sc.p7.domain": { en: "computer vision / agriculture", zh: "计算机视觉 / 农业" },
    "sc.p7.note": {
      en: "Separates suspected leakage from measured effects on PlantVillage Tomato: near-duplicate leakage negligible, the background shortcut real but modest.",
      zh: "在 PlantVillage 番茄子集上把「疑似泄漏」与「实测效应」分开：近重复泄漏可忽略，背景捷径确有其事但幅度不大。"
    },
    "sc.caption": {
      en: "References verified via WebSearch + Crossref on every paper; all figures delivered as editable vector PDFs; integrity gates passed on all seven. Four papers use the Traitement du Signal format, three other research formats.",
      zh: "每篇的参考文献都经 WebSearch + Crossref 核验；所有图以可编辑矢量 PDF 交付；七篇全部通过诚实性闸门。四篇采用 Traitement du Signal 版式，其余三篇采用其他研究版式。"
    },

    /* --- 07 compare --- */
    "cmp.eyebrow": { en: "Compare", zh: "横向对比" },
    "cmp.title": { en: "The whole arc, as drop-in skills.", zh: "端到端全流程，装上就能用的 skill。" },
    "cmp.lede": {
      en: "The heavy autonomous scientists match the breadth &mdash; but ship as standalone Python products: Docker, Neo4j, tens of thousands of lines. The lighter skill suites stay in Claude Code &mdash; but don&rsquo;t run experiments or draw figures. This is the only pure Claude Code plugin that runs the entire arc, and the only tool of any kind with an <strong>editable-vector figure engine</strong>.",
      zh: "重型自动科学家们覆盖面相当——但都是独立的 Python 产品：Docker、Neo4j、上万行代码。轻量的 skill 套件留在 Claude Code 里——却既不跑实验也不画图。这是唯一跑通全流程的纯 Claude Code 插件，也是所有工具里唯一带<strong>可编辑矢量画图引擎</strong>的一个。"
    },
    "cmp.fig.title": { en: "Capability matrix across AI-research tools", zh: "AI 科研工具能力矩阵" },
    "cmp.fig.note": {
      en: "&#10003; full &middot; &#9679; partial &middot; &ndash; none. Sources: the linked repos of ARS, Idea2Paper, AutoResearchClaw, AI-Scientist, Kosmos, karpathy/autoresearch and auto_research.",
      zh: "&#10003; 完整 · &#9679; 部分 · &ndash; 无。来源：ARS、Idea2Paper、AutoResearchClaw、AI-Scientist、Kosmos、karpathy/autoresearch、auto_research 各自的仓库。"
    },
    "takeaway.kicker": { en: "The takeaway", zh: "一句话总结" },
    "takeaway.lead": {
      en: "The model does the reasoning. The code keeps it honest. <strong>You get a paper.</strong>",
      zh: "模型负责推理，代码负责诚实。<strong>你拿到一篇论文。</strong>"
    },
    "takeaway.body": {
      en: "No app, no server, no database, no Docker &mdash; copy the skills into <code>~/.claude/skills/</code> and drop a spark. Everything the pipeline produces &mdash; blueprint, bibliography, sections, figures with their editable sources, logs, and the compiled PDF &mdash; lands on disk, yours to keep editing.",
      zh: "不装应用、不起服务、没有数据库、不用 Docker——把 skill 拷进 <code>~/.claude/skills/</code>，丢一颗火花进去。流水线的全部产物——blueprint、参考文献、章节、连同可编辑源文件的图、日志、编译好的 PDF——统统落在磁盘上，随你继续改。"
    },

    /* --- 08 cite / copy --- */
    "cite.eyebrow": { en: "BibTeX", zh: "引用" },
    "cite.title": { en: "Cite this work.", zh: "引用本项目。" },
    "cite.lede": { en: "If spark-to-paper-skills helps your research, please cite the project.", zh: "如果 spark-to-paper-skills 对你的研究有帮助，欢迎引用。" },
    "cite.copy": { en: "Copy", zh: "复制" },
    "cite.copied": { en: "Copied!", zh: "已复制！" },
    "cite.copyFail": { en: "Press Ctrl+C", zh: "请按 Ctrl+C" },

    /* --- footer --- */
    "footer.copy": {
      en: "&copy; 2026 spark-to-paper-skills &middot; MIT License &middot; Built on Claude Code &middot; Figures: PaperBanana+ native SVG, DrawAI hybrid as fallback &middot; Site design after <a href=\"https://lh-harness.pages.dev/\" target=\"_blank\" rel=\"noopener\">LongHorizon-Harness</a>.",
      zh: "&copy; 2026 spark-to-paper-skills · MIT License · 基于 Claude Code 构建 · 画图：PaperBanana+ 原生 SVG，DrawAI hybrid 兜底 · 网站设计参考 <a href=\"https://lh-harness.pages.dev/\" target=\"_blank\" rel=\"noopener\">LongHorizon-Harness</a>。"
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
      { label: () => "corpus.jsonl", h: 172 },
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
      { role: "m", name: "backends.role.up", words: ["idea2story", "kg-build"] },
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
