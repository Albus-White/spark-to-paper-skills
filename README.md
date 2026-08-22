<div align="center">

# 🖥️ SparkBoard

***A calm, paper-first GUI for the Spark-to-Paper skill suite. Reading first, AI second.***

**English** · [中文](#zh)

![Python](https://img.shields.io/badge/python-stdlib%20only-3776ab?style=flat-square&logo=python&logoColor=white)
![No build](https://img.shields.io/badge/build-none-2f9e44?style=flat-square)
![Self-contained](https://img.shields.io/badge/network-zero%20external-495057?style=flat-square)
![Bilingual](https://img.shields.io/badge/中%20·%20EN-bilingual-6f42c1?style=flat-square)

</div>

---

> **SparkBoard is the official local GUI for [Spark-to-Paper](https://github.com/Spark-To-Paper-Skills/spark-to-paper-skills)** — the Claude Code skill suite that turns one sentence into a compiled paper. It opens everything a run leaves on disk — the draft, the reviews, the figures, the literature — as a warm reading surface.
>
> **It's entirely optional.** The suite runs end-to-end from the CLI; SparkBoard is just a nicer window onto the same run artifacts for those who'd rather point-and-read than watch a terminal.

## Reading first, AI second

No sticky chat box, no assistant hovering over your shoulder. SparkBoard is built for **reading** — a serif reading column over paper-grain surfaces — and the helper only speaks when you call it: press **V** for a summary, **C** to translate, or select a phrase to explain / ask. One request at a time; nothing reaches a model until you act.

## Three tools, one shell

One window, three workspaces, switched from the top-left. Each wears its own ink so you always know where you are — and each opens onto a different part of the suite:

|     | Workspace | What you do here | Over which part of the suite |
| :-: | --- | --- | --- |
| 🖋️ | **Spark** · <sub>terracotta</sub> | Draft a paper: read it, watch the runs, inspect every figure's redraw history, edit the LaTeX, audit the governance trail | the `ts-paper` pipeline |
| ⚖️ | **Jury** · <sub>indigo</sub> | Review a paper: a docket of charges with **verbatim** evidence and juror records, a before/after revisions diff, a **go / no-go** submission shield | the adversarial `ts-paper-review` |
| 📚 | **Wiki** · <sub>sage</sub> | Read the literature: a note library with a computed **backlinks** rail, a concept graph, research ideation, coverage, a corpus-grounded **teach / ask** | the research knowledge base |

<details>
<summary><b>What each workspace holds</b></summary>
<br>

**🖋️ Spark**
- **Reading** — a serif reading column with the restrained AI helper, a table-of-contents + backlinks rail, Zen mode, font sizing.
- **Runs** — a pipeline stage board: cost, duration, token usage, and a clear **ready / N blocking** verdict.
- **Figure workshop** — each figure with its generation prompt, the critic and redraw rounds, an audit, and a version carousel.
- **Manuscript** — a native LaTeX editor: file tree, a line-numbered source editor that saves to disk, a compiled-PDF preview, and a GitHub-PR-style **Changes** diff.
- **Governance** — the record of how the draft came to be.

**⚖️ Jury**
- A **docket kanban** of review charges · a **charge reader** with verbatim evidence and juror trial records · a **revisions diff** inbox · a **submission shield** that gives one go / no-go answer.

**📚 Wiki**
- A **note library** with a computed backlinks rail · a **concept graph** · **ideation**, **coverage**, and **sources** · a corpus-grounded **teach / ask**.

**Cross-tool flow** — hand a draft from Spark to Jury, file a review outcome into the Wiki, draft a Wiki idea in Spark. A **⌘K** command palette takes you anywhere.

</details>

## Bilingual, themed, keyboard-driven

- **Bilingual 中 / EN**, with **light and dark** themes.
- Keyboard-driven throughout; a **⌘K** command palette.
- **Fully self-contained**: same-origin, **zero external network**, Python **standard library only** — no build, no dependencies.

## Quick start

```bash
cd cockpit && python serve.py      # or:  python -m cockpit
```

Then open the localhost URL it prints. The server owns the run subprocesses, so closing the window never interrupts a long run.

## What it reads

SparkBoard reads the artifacts a Spark run leaves in a run directory — `main.pdf`, `sections/*.tex`, `figures/`, the per-stage `logs/*.io.md`, the gate JSON, and more. To produce one, run the suite: **[Spark-to-Paper →](https://github.com/Spark-To-Paper-Skills/spark-to-paper-skills)**.

## Under the hood

A stdlib `http.server` (`cockpit/serve.py`) that owns the run subprocesses, a headless-`claude` runner (`cockpit/runner.py`), stdlib data adapters, and a vanilla-JS reader shell — no build step. Full architecture in **[`cockpit/SPARKBOARD.md`](cockpit/SPARKBOARD.md)**.

## Configure the reading AI

Settings → **Reading assistant**: a Base URL (DeepSeek `https://api.deepseek.com` is a cheap default), an API key (stored only in the plugin `.env`, never synced), and a model. Text is sent to a model **only** when you press **V** or pick a selection action — never on its own.

---

<p align="center">
  <sub>SparkBoard is the GUI for <a href="https://github.com/Spark-To-Paper-Skills/spark-to-paper-skills">Spark-to-Paper</a> · <a href="https://spark-to-paper-skills.github.io/spark-to-paper-skills/">Website</a> · <a href="https://arxiv.org/abs/2608.11924">Paper</a> · <a href="LICENSE">MIT License</a></sub>
</p>

<br>

---
---

<br>

<a id="zh"></a>

<div align="center">

# 🖥️ SparkBoard（中文）

***为 Spark-to-Paper 工具套件打造的静谧阅读式 GUI,以论文为先。阅读为先,AI 其次。***

[English](#-sparkboard) · **中文**

![Python](https://img.shields.io/badge/python-stdlib%20only-3776ab?style=flat-square&logo=python&logoColor=white)
![No build](https://img.shields.io/badge/build-none-2f9e44?style=flat-square)
![Self-contained](https://img.shields.io/badge/network-zero%20external-495057?style=flat-square)
![Bilingual](https://img.shields.io/badge/中%20·%20EN-bilingual-6f42c1?style=flat-square)

</div>

---

> **SparkBoard 是 [Spark-to-Paper](https://github.com/Spark-To-Paper-Skills/spark-to-paper-skills) 的官方本地 GUI** —— 那套把一句话变成一篇论文的 Claude Code 技能套件。它把一次运行留在磁盘上的一切 —— 草稿、评审、图表、文献 —— 摊开成一块温润的阅读台。
>
> **它完全可选。** 套件本身端到端跑在 CLI 上;SparkBoard 只是给那些「比起盯终端、更想点着读」的人,套在同一批运行产物上的一扇更好的窗。

## 阅读为先,AI 其次

没有粘在角落的聊天框,也没有悬在肩头的助手。SparkBoard 为**阅读**而生 —— 铺在纸纹表面上的衬线阅读栏 —— 助手只在你召唤时才开口:按 **V** 出摘要、**C** 翻译,或选中一段文字让它解释 / 发问。一次只处理一个请求,不动手就没有一个字送进模型。

## 三个工具,一个界面

一个窗口,三个工作区,从左上角切换。每个都有自己的墨色,你随时知道身在何处 —— 而每一个都对着套件的不同一段:

|     | 工作区 | 你在这里做什么 | 对应套件的哪一段 |
| :-: | --- | --- | --- |
| 🖋️ | **Spark** · <sub>赤陶色</sub> | 起草论文:读它、盯着运行、翻看每张图的重绘历史、改 LaTeX、审阅治理轨迹 | `ts-paper` 流水线 |
| ⚖️ | **Jury** · <sub>靛蓝色</sub> | 评审论文:一块附**原文**证据与陪审记录的条目看板、一个前后对照的修订差异、一块 **go / no-go** 投稿护盾 | 对抗式 `ts-paper-review` |
| 📚 | **Wiki** · <sub>鼠尾草绿</sub> | 读文献:带自动**反向链接**边栏的笔记库、概念图谱、研究构思、覆盖情况,以及一个扎根语料的 **teach / ask** | 研究知识库 |

<details>
<summary><b>每个工作区里有什么</b></summary>
<br>

**🖋️ Spark**
- **阅读** —— 衬线阅读栏,搭配克制的 AI 助手、目录 + 反向链接边栏、Zen 模式、字号调节。
- **运行(Runs)** —— 流水线阶段看板:成本、耗时、token 用量,外加一个清晰的 **ready / N blocking(就绪 / N 项阻断)** 结论。
- **图表工坊** —— 每张图都带它的生成 prompt、critic 与重绘轮次、一份审计,以及一列版本轮播。
- **正文(Manuscript)** —— 原生 LaTeX 编辑器:文件树、带行号并可存盘的源码编辑器、编译后的 PDF 预览,以及一份 GitHub PR 风格的 **Changes** 差异。
- **治理(Governance)** —— 记录这份草稿是怎么来的。

**⚖️ Jury**
- 一块评审条目的 **看板** · 一个附原文证据与陪审审理记录的 **条目阅读器** · 一个 **修订差异** 收件箱 · 一块给出 go / no-go 答复的 **投稿护盾**。

**📚 Wiki**
- 一个带自动反向链接边栏的 **笔记库** · 一张 **概念图谱** · **构思**、**覆盖** 与 **来源** · 一个扎根语料的 **teach / ask**。

**工具间流转** —— 把 Spark 的草稿交给 Jury,把评审结论归档进 Wiki,在 Spark 里起草 Wiki 的想法。一个 **⌘K** 命令面板带你去任何地方。

</details>

## 双语、主题、键盘驱动

- **中 / EN 双语**,支持 **明暗** 主题。
- 全程键盘可驱动;一个 **⌘K** 命令面板。
- **完全自包含**:同源、**零外部网络**、只用 Python **标准库** —— 不构建,无依赖。

## 快速开始

```bash
cd cockpit && python serve.py      # 或:  python -m cockpit
```

然后打开它打印出的 localhost 地址。服务器持有运行子进程,所以关掉窗口也不会打断长跑。

## 它读取什么

SparkBoard 读取一次 Spark 运行留在运行目录里的产物 —— `main.pdf`、`sections/*.tex`、`figures/`、逐阶段的 `logs/*.io.md`、闸门 JSON 等等。想产出一个运行目录,就去跑套件:**[Spark-to-Paper →](https://github.com/Spark-To-Paper-Skills/spark-to-paper-skills)**。

## 底层怎么搭的

一个持有运行子进程的标准库 `http.server`(`cockpit/serve.py`)、一个拉起 headless `claude` 的 runner(`cockpit/runner.py`)、几个标准库数据适配器,加一个原生 JS 的阅读器壳 —— 没有构建步骤。完整架构见 **[`cockpit/SPARKBOARD.md`](cockpit/SPARKBOARD.md)**。

## 配置阅读 AI

设置 → **Reading assistant**:一个 Base URL(DeepSeek `https://api.deepseek.com` 是便宜的默认)、一个 API key(只存在插件的 `.env` 里,从不同步)、一个模型。**只有**你按 **V** 或选一个动作时,文字才会送进模型 —— 它绝不自己发送。

---

<p align="center">
  <sub>SparkBoard 是 <a href="https://github.com/Spark-To-Paper-Skills/spark-to-paper-skills">Spark-to-Paper</a> 的 GUI · <a href="https://spark-to-paper-skills.github.io/spark-to-paper-skills/">项目网站</a> · <a href="https://arxiv.org/abs/2608.11924">论文</a> · <a href="LICENSE">MIT 许可证</a></sub>
</p>
