<div align="center">

  # SparkBoard

  ***A calm, paper-first reading surface for your papers. Three tools, one shell. Reading first, AI second.***

  **English** · [中文](#sparkboard-中文)

  ![Python](https://img.shields.io/badge/python-stdlib%20only-3776ab?style=flat-square&logo=python&logoColor=white)
  ![No build](https://img.shields.io/badge/build-none-2f9e44?style=flat-square)
  ![Self-contained](https://img.shields.io/badge/network-zero%20external-495057?style=flat-square)

</div>

---

## What is SparkBoard

**SparkBoard** is a paper-first, local reading app — a browser viewer served by a tiny Python standard-library server. It gives you a calm reading surface where the AI stays out of the way until you ask for it.

No sticky chat box, no assistant hovering over your shoulder. SparkBoard is built for reading, and the helper only speaks when you call it.

**Reading first, AI second.**

## Three workspaces, one shell

One window, three workspaces, switched from the top-left. Each tool wears its own accent color so you always know where you are: **Spark** is terracotta, **Jury** is indigo, **Wiki** is sage.

### 🖋️ Spark — draft a paper

- **Reading** — a serif reading column with a restrained AI helper (summary, explain, translate, or ask about a selection), a table-of-contents and backlinks rail, Zen mode, and font sizing.
- **Runs** — a pipeline stage board showing cost, duration, and token usage, with a clear **ready / N blocking** verdict.
- **Figure workshop** — a gallery where each figure shows its generation prompt, the critic and redraw rounds, an audit, and a version carousel of the redraw iterations.
- **Manuscript** — a native LaTeX editor: a file tree, a line-numbered source editor that saves to disk, a compiled-PDF preview, and a GitHub-PR-style **Changes** diff of the pipeline's edits.
- **Governance** — the record of how the draft came to be.

### ⚖️ Jury — review a paper

- A **docket kanban** of review charges.
- A **charge reader** with verbatim evidence and juror trial records.
- A **revisions diff** inbox.
- A **submission shield** that gives you one go / no-go answer.

### 📚 Wiki — a literature knowledge base

- A **note library** with a computed backlinks rail.
- A **concept graph**.
- **Ideation**, **coverage**, and **sources**.
- A corpus-grounded **teach / ask**.

## Cross-tool flow

The three tools talk to each other:

- Hand a draft from **Spark** to **Jury**.
- File a review outcome into the **Wiki**.
- Draft a **Wiki** idea in **Spark**.

A **⌘K command palette** takes you anywhere, and a one-click launcher starts what you need — Wiki only, Spark only, or Wiki → Spark.

## Bilingual, themed, keyboard-driven

- **Bilingual 中 / EN**, with **light and dark** themes.
- Keyboard-driven throughout.
- **Fully self-contained**: same-origin, zero external network.

## Design

Fraunces and IBM Plex typography over paper-grain surfaces. The data is honest — it shows a run's real artifacts, and where a section has no data, it shows a short one-line note instead.

## Quick start

```
cd cockpit && python serve.py
```

Python standard library only — no build, no dependencies. Then open the localhost URL it prints.

## What it reads

SparkBoard reads the artifacts a Spark run leaves in a run directory.

## Screenshots

_Coming soon._

---

<div align="center">

  # SparkBoard （中文）

  ***为你的论文打造的静谧阅读台，以论文为先。三个工具，一个界面。阅读为先，AI 其次。***

  [English](#sparkboard) · **中文**

  ![Python](https://img.shields.io/badge/python-stdlib%20only-3776ab?style=flat-square&logo=python&logoColor=white)
  ![No build](https://img.shields.io/badge/build-none-2f9e44?style=flat-square)
  ![Self-contained](https://img.shields.io/badge/network-zero%20external-495057?style=flat-square)

</div>

---

## 软件简介

**SparkBoard** 是一款以论文为先的本地阅读应用——它由一个用 Python 标准库写成的微型服务器驱动，在浏览器里为你打开阅读界面。它给你一块静谧的阅读台，AI 始终退居幕后，直到你主动召唤。

没有粘在角落的聊天框，也没有悬在肩头的助手。SparkBoard 为阅读而生，助手只在你叫它时才开口。

**阅读为先，AI 其次。**

## 三个工作区，一个界面

一个窗口，三个工作区，从左上角切换。每个工具都有自己的主色，你随时知道身在何处:**Spark** 是赤陶色(terracotta)，**Jury** 是靛蓝色(indigo)，**Wiki** 是鼠尾草绿(sage)。

### 🖋️ Spark——起草一篇论文

- **阅读**——衬线排版的阅读栏,搭配一个克制的 AI 助手(摘要、解释、翻译,或就选中的文字提问),另有目录与反向链接边栏、Zen 模式和字号调节。
- **运行(Runs)**——流水线阶段看板,显示成本、耗时与 token 用量,并给出清晰的 **ready / N blocking(就绪 / N 项阻断)** 结论。
- **图表工坊(Figure workshop)**——一个画廊,每张图都展示它的生成 prompt、critic 与重绘(redraw)轮次、一份审计,以及一列重绘迭代的版本轮播。
- **正文(Manuscript)**——原生 LaTeX 编辑器:文件树、带行号并可存盘的源码编辑器、编译后的 PDF 预览,以及一份 GitHub PR 风格的 **Changes** 差异,呈现流水线所做的改动。
- **治理(Governance)**——记录这份草稿是怎么来的。

### ⚖️ Jury——评审一篇论文

- 一块评审条目(charge)的 **看板(docket kanban)**。
- 一个 **条目阅读器(charge reader)**,附带原文证据与陪审员的审理记录。
- 一个 **修订差异(revisions diff)** 收件箱。
- 一块 **投稿护盾(submission shield)**,给你一个 go / no-go 的答复。

### 📚 Wiki——文献知识库

- 一个 **笔记库(note library)**,带自动计算的反向链接边栏。
- 一张 **概念图谱(concept graph)**。
- **构思(ideation)**、**覆盖(coverage)** 与 **来源(sources)**。
- 一个扎根于语料的 **teach / ask(教 / 问)**。

## 工具间流转

三个工具彼此相连:

- 把 **Spark** 里的草稿交给 **Jury**。
- 把一份评审结论归档进 **Wiki**。
- 在 **Spark** 里起草一个 **Wiki** 的想法。

一个 **⌘K 命令面板** 带你去任何地方;一个一键启动器按需开工——只开 Wiki、只开 Spark,或 Wiki → Spark。

## 双语、主题、键盘驱动

- **中 / EN 双语**,支持 **明暗** 主题。
- 全程可用键盘驱动。
- **完全自包含**:同源(same-origin),零外部网络。

## 设计

Fraunces 与 IBM Plex 字体,铺在带纸纹质感的表面上。数据是诚实的——它展示一次运行的真实产物;若某个板块没有数据,就显示一行简短的说明。

## 快速开始

```
cd cockpit && python serve.py
```

只用 Python 标准库——无需构建,也没有依赖。然后打开它打印出来的 localhost 地址。

## 它读取什么

SparkBoard 读取一次 Spark 运行留在运行目录里的产物。

## 截图

_即将上线。_
