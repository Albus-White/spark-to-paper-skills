# spark-to-paper-skills — 框架图生成 Prompt 文档

> 用途:把 spark-to-paper-skills 的「方法 / 架构」可视化成一张框架图(对标 AutoResearchClaw 的 `framework_v2.png`),
> 直接复制下面的 prompt 给 GPT 图像模型(gpt-image-1 / DALL·E 等)生成。

---

## ⚠️ 先读:关于图像模型渲染文字

GPT 图像模型**画大量小号精确文字会出错**(拼错、糊、错位)。所以本 prompt 的策略是:
**用图标 + 模块卡片 + 少量短标签**承载信息,长句说明交给你后期在图上叠真实文字。
每个模块都给了**建议出现的短标签**(≤3 词),不要让模型去画长段落。

---

## ① 主提示词(复制这一段给 GPT)

```
A clean, modern, professional technical infographic titled "spark-to-paper-skills",
shown as a horizontal left-to-right pipeline that turns a research spark into a
publication-ready academic paper. Flat vector illustration, academic-poster
aesthetic, generous whitespace, thin elegant connector arrows, subtle soft shadows
for light depth, high clarity, crisp geometric sans-serif labels.

LEFT — three glowing "spark" inputs stacked vertically, each a small rounded card
with an icon, converging via arrows into the center:
  • a lightbulb icon — label "IDEA"
  • a document icon — label "PROPOSAL"
  • a document-with-bar-chart icon — label "PROPOSAL + DATA"

CENTER-LEFT — a prominent rounded hub card labeled "ts-paper / ROUTER", a brain-and-
fork icon, where the three inputs merge; a small branch label "auto-route mode".

CENTER — a horizontal chain of SEVEN connected stage cards, evenly spaced, each a
rounded rectangle with a distinct minimalist icon and a short label, numbered 1–7:
  1 "PLAN" (blueprint icon)
  2 "CITE" (book/quote icon)
  3 "WRITE" (pen icon)
  4 "REFINE" (sliders icon)
  5 "REVIEW" (magnifier-with-debate icon)
  6 "FIGURE" (image icon)
  7 "LATEX" (compiled-PDF icon)

BELOW the FIGURE card — a highlighted call-out sub-pipeline in a tinted panel,
labeled "DrawAI vector engine", a small left-to-right micro-flow of five tiny nodes:
"raster" → "SAM3" → "OCR" → "Box-IR" → "editable SVG/PDF". A small caption tag:
"raster → editable vector".

BOTTOM — a full-width horizontal ribbon under the whole pipeline labeled
"QUALITY STACK", divided into four equal segments with check-shield icons:
"gates", "self-review", "adversarial review", "vision critique".

RIGHT — an output stack of three artifact cards with icons: "main.pdf" (paper),
"refs.bib" (real citations), "vector figures" (editable charts). Above them a small
shield badge labeled "no fabricated numbers". A curved feedback arrow loops from the
output back into the pipeline, labeled "experiments (auto-run)".

COLOR PALETTE: warm coral/terracotta accent (#D97757), deep ink-navy text (#1F2933),
soft off-white background (#FAF7F2), with muted teal (#3A8E8C) and soft violet
(#7C6FD6) as secondary accents. Cohesive, calm, premium.

STYLE: corporate-tech infographic, flat design with minimal gradients, vector look,
no photorealism, no 3D clutter, balanced composition, everything legible.
Aspect ratio 16:9, wide banner format.
```

---

## ② 逐模块细节规格(微调时参考)

| 区域 | 内容 | 图标建议 | 短标签 |
|---|---|---|---|
| **输入(左)** | 三种 spark,竖排,箭头汇聚 | 灯泡 / 文档 / 文档+柱状图 | `IDEA` / `PROPOSAL` / `PROPOSAL + DATA` |
| **路由(中左)** | 总编排器 ts-paper,分类并设模式 | 大脑+分叉 | `ts-paper / ROUTER`,小字 `auto-route` |
| **主链(中)** | 7 个等距阶段卡,带序号 1–7 | 各自极简图标 | `PLAN` `CITE` `WRITE` `REFINE` `REVIEW` `FIGURE` `LATEX` |
| **图引擎(图阶段下方)** | 高亮子流程面板,5 个微节点 | 小流程箭头 | `raster→SAM3→OCR→Box-IR→SVG/PDF` |
| **质量栈(底部通栏)** | 4 段盾牌带 | 对勾盾 ×4 | `gates` `self-review` `adversarial` `vision` |
| **输出(右)** | 3 张产物卡 + 诚信徽章 | 论文/引用/图表 | `main.pdf` `refs.bib` `vector figures` |
| **反馈环** | 从输出弯回主链 | 弧形回环箭头 | `experiments (auto-run)` |

**视觉层级建议**:路由 hub 和「DrawAI vector engine」call-out 是**两个视觉焦点**(略大、用 coral 主色描边),
其余阶段卡用中性色;质量栈 ribbon 用浅色背景压在底部,不抢戏。

---

## ③ 配色 / 字体 / 风格规范

- **主色**:暖珊瑚 / 赤陶 `#D97757`(做焦点描边与箭头)
- **文字色**:墨蓝 `#1F2933`
- **背景**:米白 `#FAF7F2`
- **辅助色**:静音蓝绿 `#3A8E8C`、柔紫 `#7C6FD6`
- **字体**:几何无衬线(Inter / Geist / Helvetica 风),粗细分明,标题加粗
- **风格关键词**:`flat vector infographic`、`academic poster`、`minimal`、`premium`、`lots of whitespace`、`thin arrows`、`subtle soft shadow`、`16:9 wide banner`

---

## ④ 负向提示 + 避坑

**Negative prompt(避免出现):**

```
no photorealism, no 3D render, no clutter, no busy background, no neon/cyberpunk,
no stock-photo people, no gibberish dense paragraphs of text, no tiny illegible
labels, no skewed perspective, no watermark, no drop-shadow overload, not dark theme.
```

**实操避坑:**

1. **文字别贪多**:每张卡只画 1 个短标签;长说明等出图后用 Figma/Keynote 叠真实文字,保证拼写正确。
2. **先出布局再加细节**:可先用「精简版」出一版构图,满意后再用主提示词加模块。
3. **比例固定 16:9** 当 README 横幅;若要方形缩略图改 `1:1`,并把 7 阶段折成两行。
4. 若模型把 7 个卡画乱,补一句:
   `arrange the seven stage cards in a single evenly-spaced horizontal row, left to right, connected by arrows`。

---

## ⑤ 精简版(模型吃长 prompt 困难时用)

```
Wide 16:9 flat vector infographic, academic-poster style, off-white background,
warm coral (#D97757) + ink-navy accents. Left-to-right pipeline titled
"spark-to-paper-skills": three input cards (lightbulb "IDEA", doc "PROPOSAL",
doc+chart "PROPOSAL+DATA") merge into a hub "ts-paper ROUTER", then a single
horizontal row of 7 numbered stage cards — PLAN, CITE, WRITE, REFINE, REVIEW,
FIGURE, LATEX — ending in output cards "main.pdf", "refs.bib", "vector figures".
A highlighted sub-flow under FIGURE: raster → SAM3 → OCR → SVG/PDF. A bottom ribbon
"QUALITY STACK" with 4 shield segments. Clean, minimal, lots of whitespace, thin
arrows, legible geometric sans-serif. No photorealism, no clutter, no tiny text.
```

---

## ⑥-bis 生动具体版（生活化比喻 —— 推荐用这个，更接地气）

> 抽象的方块+箭头不好懂。下面把整条流水线**具象成一个现实场景**，每个阶段对应一个看得见的实物/角色，
> 人不用懂 pipeline 也能秒懂每一步在干嘛。

### 🏭 版本 A（主推）：自动化「论文工厂」流水线

一个发光的**灵感火花**像零件一样被放上传送带，经过一排可爱机器人工位，末端滑出一本**装订好的期刊**。

| 阶段 | 工位场景 | 现实联想 |
|---|---|---|
| 输入 | 传送带入口：灯泡 / 餐巾纸草图 / 带数据的剪贴板 | 一个点子 |
| ROUTER | 分拣机械臂拿起、分类 | 智能分拣 |
| 1 PLAN | 画着蓝图的绘图桌 | 设计图纸 |
| 2 CITE | 图书管理员机器人抽真书、逐本盖「verified」章 | 查证资料 |
| 3 WRITE | 打字机器人打出页面 | 起草 |
| 4 REFINE | 裁缝机器人熨平、裁到合身 | 精修 |
| 5 REVIEW | 戴放大镜的检查员机器人围着稿子争论 | 同行评审 |
| 6 FIGURE | 画家机器人画图，激光雕刻机把画变精密矢量图 | 制图（DrawAI） |
| 7 LATEX | 印刷机装订成期刊 | 印刷出版 |
| 质量栈 | 传送带上扫描安检门亮绿勾；假数字弹进「✗」滑槽 | 质检关卡 |
| 输出 | 聚光灯下崭新期刊滑出 | 成品 |

```
A warm, charming isometric illustration of a miniature "automated paper factory":
a single glowing lightbulb "spark" sits on a conveyor belt at the LEFT entrance and
travels right through a row of cute friendly little robot workstations, ending as a
freshly printed, bound academic journal sliding out under a spotlight on the RIGHT.

Stations along the belt, left to right, each a small machine with a cheerful robot:
  • a sorting robot arm picking up the spark (the router/dispatcher)
  • a drafting table covered in blueprints (planning)
  • a librarian robot pulling real books from tall shelves and stamping each "✓ verified" (citations)
  • a typewriter robot clacking out printed pages (writing)
  • a tailor robot ironing and trimming the pages to fit (refining)
  • a cluster of inspector robots with magnifying glasses debating over a manuscript (peer review)
  • an artist robot painting a diagram, beside a laser engraver turning that painting
    into a precise vector blueprint (figure vectorization)
  • a printing press binding the final journal (typesetting)

Along the belt, glowing green scanner gates flash check marks (quality control); one
side chute marked "✗" rejects a paper with fake numbers. A small looping side-belt
returns to the start, tagged "experiments".

Style: cozy, polished isometric 3D infographic, soft studio lighting, rounded shapes,
warm coral (#D97757) + teal accents on a soft off-white background, clean and
storybook-like but professional. Wide 16:9. Minimal, legible, no clutter, no tiny text.
```

### 🍳 版本 B（温暖向）：米其林「科研厨房」

新鲜食材（火花）经后厨一排厨师，端出米其林摆盘料理（论文）。引用 = 储藏室里贴标签的真食材，
「无人工添加」印章 = 绝不编造数据。

```
A warm, appetizing illustration of a "research kitchen" / Michelin restaurant pass,
left to right: one fresh glowing ingredient (the idea) under a spotlight enters, then
passes a line of cheerful chef robots at stations — mise en place with a recipe card
(plan), a pantry wall of neatly labeled REAL jars each stamped "verified" (citations,
no artificial flavor), a chef cooking at the stove (writing), a chef carefully plating
and trimming the dish (refining), a panel of food critics tasting and debating
(review), a garnish artist drawing a delicate decoration (figures) — ending with a
finished Michelin-plated dish under a glass cloche (the paper). A round badge reads
"100% real, no fabrication". Cozy warm lighting, flat-vector storybook style, coral +
cream + sage palette, soft shadows, professional and clean, wide 16:9, no tiny text.
```

### ✏️ 版本 C（极简故事感）：餐巾纸草图 → 精装期刊

一只手在餐巾纸上画了潦草点子，镜头右移，草图一步步变成排版稿、再变成精装期刊。适合 README 顶部 hero 图。

```
A storytelling left-to-right transformation on a wooden workbench: a hand-drawn messy
idea on a crumpled napkin gradually morphs, step by step, into neatly typeset
manuscript pages, then an engraved printing plate, and finally a beautifully bound,
printed academic journal standing upright under warm light. Cinematic, tactile,
hand-crafted feel, flat-vector with soft texture, coral + warm neutral palette, wide
16:9, focus on the satisfying "rough sketch → polished publication" arc, no tiny text.
```

---

## ⑥ 变体方向(按需取用)

- 🎨 **isometric 等距 3D 风**:把 `flat vector` 换成 `clean isometric 3D infographic, soft studio lighting`,立体科技感更强。
- 🪧 **竖版海报(论文/PPT)**:比例改 `3:4`,7 阶段折成 2–3 行的网格。
- 🔬 **只画 DrawAI 图引擎特写**:单独渲染 `raster → SAM3 → OCR → Box-IR → Codex SVG → vector PDF/PPTX` 一条横向微流程,突出「光栅→可编辑矢量」。
- 🏷️ **logo / hero 图**:一个 spark(火花/灯泡)渐变成一张论文页的极简符号,放 README 顶部。
