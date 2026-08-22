/* ============================================================================
   SparkBoard · WIKI workspace — Paper Wiki v2 (reverse-linked LLM knowledge base
   + research ideation). Registers the "wiki" tool into the shared SB shell.

   WHY this module exists / design intent:
   - The corpus IS the reading material, so every note renders as a serif article
     in the shared Reader shell, and the SIGNATURE feature is the col-3 DUAL RAIL:
     section-TOC (top) + computed reverse-links (bottom) + outbound + lint.
   - The wiki on disk is plain Markdown + YAML front-matter + Obsidian [[wikilinks]].
     We embed a faithful, CONNECTED sample corpus (mirrors the real
     examples/sample-research-wiki fixtures: 4 papers → 1 concept → 1 gap →
     ideas → 1 direction → 1 probe → 1 goal, plus field/novelty layers) so the
     backlink graph, concept graph, ideation inbox, coverage, sources, /wiki-auto
     inbox and citation-bound teach are all real and click-through.
   - Backlinks are NEVER stored — we compute them (grep who links [[thisId]]),
     exactly like the tool. Everything degrades honestly (orphan / dangling warn).

   Field names below are the real on-disk schema (WIKI.md.tmpl / protocol):
   venue_status, code, fence_zone, source_path, seeded_from, novelty_ref,
   complexity_tier, status lifecycle, direction_ref, cost_tier, kind:adopted-goal,
   staleness, relied_by, verdict(probe-confirms|…), 状态∈{待人,已阅,翻案}.
   ============================================================================ */
(function () {
  "use strict";
  var SB = window.SB;
  if (!SB) return;
  var el = SB.el, esc = SB.esc, $ = SB.$, $$ = SB.$$;

  // String.raw keeps LaTeX backslashes intact ($\bar{A}$, $O(N)$ …) inside the
  // note bodies below — a normal template literal would turn \t \b \s into
  // control chars and corrupt the math. Bodies therefore contain NO backticks.
  var R = String.raw;
  function L(zh, en) { return (SB.state && SB.state.lang === "en") ? en : zh; }

  /* =========================================================================
     1. THE INLINE CORPUS — faithful to examples/sample-research-wiki
     Each note: id, type, folder, title, oneLine (list preview + AI-summary
     ground truth), date, fm (front-matter → header chips), source_path, body
     (Markdown starting at the first ## section, with the real [[links]]).
     ========================================================================= */
  var NOTES = {
    /* ---- wiki/papers/ — the core reading feed --------------------------- */
    "maillard-tiling": {
      type: "paper", folder: "papers",
      title: "Maillard-Tiling: Fast and Sensor-Efficient Exact Grid Browning with IO-Awareness",
      oneLine: "用分块 + 重算把逐格控温做成 IO-aware 融合回路;不近似、精确逐格控温,传感器读写降到线性、整机更快。",
      date: "2026-08-15",
      fm: { authors: "Vance et al.", venue: "IHTC 2022 (arXiv 2205.14135)", venue_status: "peer-reviewed", code: "open", fence_zone: "core", tags: ["large-format", "exact-control", "io-aware", "control-loop"], compiled_at: "2026-08-15" },
      source_path: "raw/uniform-browning-control/maillard-tiling.pdf",
      body: R`## 一句话总结
用分块 + 重算把逐格控温做成 IO-aware 的融合回路,不近似、精确逐格控温,但传感器读写降到线性、整机更快。

## 解决什么问题
标准逐格控温把 $N\times N$ 的逐格互热矩阵整张缓存下来,传感器读写随幅面二次增长、且被传感器总线带宽卡住。大幅面烘烤既慢又占满缓冲。

## 核心方法
分块计算每格的目标火力,用在线重标定在本地控制器缓冲内累加,不整张物化互热矩阵;回扫用重算换缓冲:$B_g=\sum_i w_{gi}\,q_i$ 逐块流式求值。关键是减少传感器读写次数而非总加热能耗。

## 关键实验结果
相对逐格闭环 baseline 约 2–4x 整机提速,控温缓冲占用降到线性(报告约 10–20x 更省),薄片 / 大幅面烘烤均受益。(代表性数字)

## 局限与 Gap
仍是**精确全逐格控温**:控温成本本质二次,只是把常数与读写压下去;运行期逐格控温成本随幅面线性堆积的问题不在其射程内。

## 相关工作反链
- [[bounded-heat-methods]]
- [[grid-sparse]]（GridSparse 走先验固定网格图案,本文走精确 IO-aware;两条正交路线）`
    },
    "grid-sparse": {
      type: "paper", folder: "papers",
      title: "GridSparse: The Large-Format Patterned-Heating Toaster",
      oneLine: "用「局部邻域加热 + 少量常通电全局网格」的先验固定网格图案,把控温成本从二次降到线性,处理大幅面烘烤。",
      date: "2026-08-15",
      fm: { authors: "Okoro and Sato", venue: "arXiv 2004.05150", venue_status: "preprint-only", code: "open", fence_zone: "core", tags: ["large-format", "patterned-heating", "local-global", "toaster"], compiled_at: "2026-08-15" },
      source_path: "raw/uniform-browning-control/grid-sparse.pdf",
      body: R`## 一句话总结
用「局部邻域加热 + 少量常通电全局网格」的先验固定图案,把控温成本从二次降到随幅面线性,处理大幅面烘烤。

## 解决什么问题
标准逐格控温二次标度使大幅面(数千网格)不可行;前人做法多为把面包切块烤,丢跨块的长程热传导。

## 核心方法
每个网格只加热固定宽度 $w$ 的局部邻域(可空洞扩大覆盖),再给关键的少量网格(如中心格、边角格)开**全局常通电**双向可见;复杂度 $O(N\cdot w)$。

## 关键实验结果
在大幅面均匀上色 / 分区烘烤等基准上优于切块 baseline,支持到约 4k+ 网格幅面;全局网格对需要整体聚热的任务贡献显著。(代表性数字)

## 局限与 Gap
图案是**先验固定的**(哪儿局部、哪儿全局要人设);哪些格真正重要是内容相关的,静态图案可能漏掉关键长程热连边。运行期逐格控温成本仍随幅面线性堆。

## 相关工作反链
- [[bounded-heat-methods]]
- [[maillard-tiling]]（对照:精确 IO-aware vs 先验固定图案）
- [[edge-hotspot]]（EdgeHotspot 的滚动加热窗可看作运行期的动态局部图案,与本文静态局部图案呼应）`
    },
    "edge-hotspot": {
      type: "paper", folder: "papers",
      title: "Efficient Streaming Browning Control with Edge Hotspots",
      oneLine: "发现边缘热点——靠近加热丝的少数网格吸走大部分热通量;保住这几个热点网格通电 + 滚动加热窗即可免重标定稳定烘到极大幅面。",
      date: "2026-08-16",
      fm: { authors: "Kwon et al.", venue: "IHTC 2024 (arXiv 2309.17453)", venue_status: "peer-reviewed", code: "open", fence_zone: "core", tags: ["large-format", "power-budget", "streaming", "edge-hotspot", "runtime"], compiled_at: "2026-08-16" },
      source_path: "raw/uniform-browning-control/edge-hotspot.pdf",
      body: R`## 一句话总结
发现「边缘热点」——靠近加热丝的少数网格吸走大部分热通量;只要保留这几个热点网格通电 + 一个滚动加热窗,机器就能免重标定稳定烘到极大幅面。

## 解决什么问题
连续 / 大幅面烘烤里,逐格闭环控温成本随幅面无界增长;简单停掉最早的网格(滑窗)会让上色不均度爆炸,而全程逐格闭环又太贵。

## 核心方法
保留最靠边的若干网格(热点)**不停火** + 最近 $L$ 个网格的滚动加热窗;热点承接必须分配出去的富余热通量,稳住整机温度分布。零重标定,改的是停火策略而非机器硬件。

## 关键实验结果
可稳定处理到百万级网格幅面而上色不均度不发散;相对滑窗全程重烤 baseline 报告显著加速(量级级)。掐掉热点会立刻焦糊,验证了热点的因果作用。(代表性数字)

## 局限与 Gap
保留哪些网格通电的策略是**位置启发式**(边上 k 个 + 最近 L 个),不看内容;加热窗中部真正重要的网格仍会被停火。**在给定加热功率预算下,如何按内容 / 累计热通量决定给谁停火,是空白。**

## 相关工作反链
- [[bounded-heat-methods]]
- [[grid-sparse]]（静态局部图案 vs 运行期滚动窗）
- [[thermal-state]]（ThermalState 用整机固定热质量彻底免逐格控温;本文在保留逐格控温的前提下压成本）`
    },
    "thermal-state": {
      type: "paper", folder: "papers",
      title: "ThermalState: Linear-Time Browning Control with Selective Heat-Mass States",
      oneLine: "用输入相关(selective)的整机热质量模型替代逐格控温:运行期线性并行推进,常数大小热状态、无逐格闭环。",
      date: "2026-08-16",
      fm: { authors: "Okoro and Vance", venue: "ApplThermal 2024 (arXiv 2312.00752)", venue_status: "peer-reviewed", code: "open", fence_zone: "core", tags: ["large-format", "heat-mass-model", "sub-quadratic", "no-closed-loop"], compiled_at: "2026-08-16" },
      source_path: "raw/uniform-browning-control/thermal-state.pdf",
      body: R`## 一句话总结
用输入相关(selective)的整机热质量模型替代逐格控温:运行期线性标度并行推进,常数大小热状态、无逐格闭环控温。

## 解决什么问题
逐格控温二次标度 + 运行期成本随幅面线性增长;前代热质量模型是定常的(不随面包变),不能按内容选择性升温 / 散热,局部焦斑的精确定位弱。

## 核心方法
让热质量模型参数 $(\Delta, \beta, \gamma)$ 随输入变化(selection),用硬件感知的并行推进实现 $O(N)$ 处理;递推每步只更新固定大小整机热状态 $H_t=\alpha H_{t-1}+\beta u_t$,不保存逐格历史。

## 关键实验结果
在薄片 / 厚片 / 冷冻面包上匹配或超过同档逐格控温机,报告约 5x 更高整机吞吐,大幅面近线性标度。(代表性数字)

## 局限与 Gap
放弃了显式逐格控温,**精确局部焦斑定位**在某些任务上仍不如全逐格控温;固定热状态是有损压缩,「该记住哪块热」由标定决定、不可事后审计。这与「保逐格控温但压成本」是互补而非同一路线。

## 相关工作反链
- [[bounded-heat-methods]]
- [[maillard-tiling]]（精确逐格控温加速 vs 放弃逐格换线性热状态）`
    },

    /* ---- wiki/concepts/ — cross-paper synthesis ------------------------- */
    "bounded-heat-methods": {
      type: "concept", folder: "concepts",
      title: "Bounded-cost & bounded-power browning（方法综合）",
      oneLine: "库内四条应对大幅面控温成本墙的方法脉络的综合:精确 IO-aware、先验固定图案、运行期功率停火、整机热状态替换。",
      date: "2026-08-16",
      fm: { type: "concept", related_papers: ["[[maillard-tiling]]", "[[grid-sparse]]", "[[edge-hotspot]]", "[[thermal-state]]"] },
      body: R`## 领域现状
大幅面烘烤的核心张力是逐格控温的 $O(N^2)$ 成本与随幅面增长的加热功率占用。库内四条应对脉络:精确 IO-aware 加速([[maillard-tiling]])、先验固定图案([[grid-sparse]])、运行期功率停火([[edge-hotspot]])、以及以整机热质量模型彻底替换逐格控温([[thermal-state]])。

## 前人忽略的问题
四条线在「标定期算力」上着力多,但**运行期在固定加热功率预算下给哪些格通电**这一决策,只有 [[edge-hotspot]] 正面碰,且用的是位置启发式(边上 k + 最近 L),不看内容。

## 共存的挑战
- 精确 vs 近似:[[maillard-tiling]] 不丢信息但不改二次本质;[[grid-sparse]] / [[thermal-state]] 改标度但有损。
- 功率预算下的取舍:保逐格控温就得管每格火力;免逐格(热状态)就放弃精确局部焦斑定位。

## 主要解决方法族（按方法分类,不按论文分类）
- **精确 IO-aware 回路** —— [[maillard-tiling]]:压读写与缓冲常数,控温成本仍二次。
- **先验固定图案** —— [[grid-sparse]]:先验固定的 local+global 图案,线性标度。
- **运行期功率停火** —— [[edge-hotspot]]:边缘热点 + 滚动窗,免重标定压成本。
- **次二次热状态算子** —— [[thermal-state]]:selective 热质量模型,固定状态、无逐格闭环。

## 开放问题 / Gap
**在给定加热功率预算下,按内容 / 累计热通量决定给哪些网格停火**——四篇都未解;见 [[budget-browning-gap]]。`
    },

    /* ---- wiki/gaps/ — novelty seed ------------------------------------- */
    "budget-browning-gap": {
      type: "gap", folder: "gaps",
      title: "Gap:加热功率预算下的内容感知功率停火",
      oneLine: "在固定加热功率预算 B 下,按内容 / 累计热通量为每个网格定可停火优先级、只给 top-B 通电,是空白。",
      date: "2026-08-18",
      fm: { type: "gap", seeded_from: ["[[bounded-heat-methods]]", "[[edge-hotspot]]", "[[thermal-state]]"], novelty_verified: true },
      body: R`## 问题陈述
连续 / 大幅面烘烤里逐格控温成本随幅面线性堆积。[[edge-hotspot]] 证明**只要给对的网格通电**就能在小加热窗下稳定,但它保留哪些是**位置启发式**(边上 k 个热点 + 最近 L 个);[[grid-sparse]] 的图案也是先验固定的;[[thermal-state]] 干脆免逐格但放弃精确焦斑定位。**在固定加热功率预算 $B$ 下,按内容 / 累计热通量为每个网格定一个可停火优先级、只给 top-$B$ 通电,是空白。**

## 为什么前人没解决
- 边缘热点的发现把「每格同等重要」证伪成「高度不均」,但没人把这不均性**算成一个可停火优先级分数**去做预算内停火。
- 逐格打分要在实时控温回路上便宜可算,且不能破坏 [[maillard-tiling]] 的融合回路——工程约束把朴素方案挡在门外。

## 可能的切入点
- 用累计热通量(历史加热权重和)作为可停火优先级代理,预算内保 top-$B$;
- 把边缘热点当成该分数的一个特例(位置≈高分),看能否被内容分数吸收;
- 与 [[thermal-state]] 的「固定状态即有损压缩」对照,把功率停火看成可审计的显式压缩。

## 相关文献
- [[edge-hotspot]]、[[grid-sparse]](均为固定 / 位置启发式)、[[thermal-state]](免逐格对照)、[[maillard-tiling]](回路工程约束)、[[bounded-heat-methods]]
- 待补:[[hotgrid-oracle]]（HotGrid / heavy-hitter 内容感知停火,search-latest 候选 #1,尚未编译入库）

> 下一步:/wiki-ideate wiki/gaps/budget-browning-gap → 见 idea [[content-aware-browning]]。`
    },

    /* ---- wiki/ideas/ — the ideation candidates ------------------------- */
    "content-aware-browning": {
      type: "idea", folder: "ideas",
      title: "Idea:预算感知的内容化功率停火",
      oneLine: "用累计热通量给每个网格打可停火优先级,固定加热功率预算内只给 top-B 通电,把位置启发式换成内容感知的预算分配。",
      date: "2026-08-18",
      fm: {
        type: "idea", seeded_from: ["[[budget-browning-gap]]"], status: "SCORED",
        novelty_ref: "[[budget-browning-gap]]", delta: "initial", seed_type: "L1 结构迁移",
        complexity_tier: "新颖占坑", venue_targets: ["IHTC", "ApplThermal"],
        archetype: "把一个已观测的不均匀性变成一个可驱动的预算分配分数",
        pitch: "用累计热通量给每个网格打可停火优先级,固定加热功率预算内只给 top-B 通电,把 EdgeHotspot 的位置启发式换成内容感知的预算分配。",
        important_problem: "[[browning-budget]]"
      },
      claim: {
        bold: "现阶段逐格闭环控温的烤面包机族在固定加热功率预算下,存在一个由**累计热通量**导出的每网格可停火优先级,按该分数给 top-$B$ 通电能在同预算下逼近全逐格控温的均匀度、显著优于位置启发式;机制上源于热通量在网格间的持久不均性。Reframe: 通电保留 from 位置先验 to 内容感知的预算分配。",
        now: "当前证据等级只有 [w]:可假设「一个内容感知的可停火优先级在小预算下应当不劣于、多半优于位置启发式」,但**尚不能断言任何具体预算档位的增益幅度**——需探针给出信号量级与方差后才谈数值。"
      },
      ledger: [
        { date: "2026-08-18", node: "立卡", verdict: "pass", action: "完成 SCORED 评级,开探针", link: "scorch-by-heatflux" }
      ],
      body: R`## Observation
- [w] [[edge-hotspot]] 发现靠边网格吸走大部分热通量(边缘热点),掐掉它们上色不均度立刻发散——热通量在网格间**高度不均**。
- [w] [[edge-hotspot]] 的保留策略却是纯**位置启发式**(边上 k 个 + 最近 L 个),不读这份不均性;加热窗中部真正重要的网格仍被无差别停火。
- [w] [[thermal-state]] 用固定大小热状态免逐格控温,等价承认「历史热可有损压缩」,但压什么由标定隐式决定、不可事后审计。

## Surprise & rule-out
- 为何反直觉:既然热通量已知高度不均,「给谁通电」本该由这份不均性驱动,可 SOTA 流式方案却用与内容无关的位置规则,还很好用。
- rule-out 1:不是「热点只是位置现象」——[[edge-hotspot]] 报告把热点换到任意位置的网格仍承接热通量,说明是可被内容分数吸收的角色,而非纯位置 artifact。
- rule-out 2:不是「预算太大以致保留策略无所谓」——正是小预算(强流式)下滑窗基线焦糊,才凸显保留策略的因果作用。

## Claim

### Hypothesis（大胆版）
现阶段逐格闭环控温的烤面包机族在固定加热功率预算下,存在一个由**累计热通量**导出的每网格可停火优先级,按该分数给 top-$B$ 通电能在同预算下逼近全逐格控温的均匀度、显著优于位置启发式;机制上源于热通量在网格间的持久不均性。
Reframe: 通电保留 from 位置先验 to 内容感知的预算分配。

### 当前可断言（assertable now）
当前证据等级只有 [w]:可假设「一个内容感知的可停火优先级在小预算下应当不劣于、多半优于位置启发式」,但**尚不能断言任何具体预算档位的增益幅度**——需探针给出信号量级与方差后才谈数值。

## Scope conditions
| 变量 | 范围 | 预期梯度 |
|---|---|---|
| 加热功率预算 B(通电网格占比) | {5%, 20%, 50%} | 预算越小,内容感知相对位置启发式优势越大 |
| 烘烤幅面 | {4k, 32k, 128k 网格} | 越大,中部重要网格被位置规则误停越多,增益越大 |

## Predictions
- P1 (strong): 在 5% 预算档,内容感知停火的上色不均度严格低于同预算 EdgeHotspot 位置启发式。
- P2 (medium): 被内容分数保留的网格集合与被位置规则保留的集合重叠率随烘烤幅面下降。

## Attributability preconditions
- A1: 打分与停火之外的控温路径(回路、图案、火力曲线)与 baseline 逐格对齐,差异只来自通电集合。
- A2: 分数在实时控温回路上可增量维护(每步 $O(1)$ 摊还),否则「省功率但拖慢」不构成对 thesis 的支持。

## Instantiation & DoF
- 可停火优先级分数: 历史累计加热热通量和 [load-bearing]
- 预算分配粒度: per-加热区独立 top-B [default]
- 热点处理: 作为分数特例、不硬保留 [default]
- 基座机型: 单台开源双槽烤面包机 [free]

#### 候选路径（Candidate paths — advisory）
P1(首选): 累计热通量分数 + 每加热区预算 top-B —— 依据: [[edge-hotspot]] 的热点热通量证据 —— 快速证伪信号: 5% 预算档上色不均度不优于位置启发式
P2(次选): 轻量可学习停火优先级头 —— 依据: [[thermal-state]] 的「标定决定保留」思路 —— 快速证伪信号: 标定后仍不敌无参数累计热通量分数
已剪:
- 全幅面重排序 oracle —— 非因果、运行期不可得,只能做离线上界
- 随机停火 baseline —— 只作对照下界,不是候选路线

## Pivot rules
- R1: 若 A2 不成立(分数无法 $O(1)$ 增量维护)→ 转 P2 可学习头或降到离线分析,记 instantiation-failure,不动 thesis
- R2: 若 P1 在最小预算档被证伪且 P2 亦不敌累计热通量 → 记 instantiation-failure 并触发方向层复盘 [[what-governs-scorch]],不动 thesis

## 实验台账
| 日期 | 节点 | verdict | 动作 | 链接 |
|---|---|---|---|---|
| 2026-08-18 | 立卡 | pass | 完成 SCORED 评级,开探针 | [[scorch-by-heatflux]] |`
    },
    "unified-browning-bench": {
      type: "idea", folder: "ideas",
      title: "Idea:同一加热功率预算下统一评测两条大幅面控温路线",
      oneLine: "把「保逐格控温压功率」与「免逐格换固定热状态」放进同一加热功率预算与同一局部焦斑定位任务下正面对测。",
      date: "2026-08-18",
      fm: {
        type: "idea", seeded_from: ["[[browning-budget]]"], status: "INSTANTIATED",
        novelty_ref: "[[browning-budget]]", delta: "initial", seed_type: "L3 张力-测量-position",
        complexity_tier: "顶会大工程", venue_targets: ["ApplThermal", "IHTC"],
        archetype: "把一对对撞的路线拉到同一坐标系里可比",
        pitch: "同一加热功率预算 × 同一局部焦斑定位任务,统一评测功率停火类与热状态类,给出 Pareto 前沿而非各说各话。",
        important_problem: "[[browning-budget]]"
      },
      claim: {
        bold: "在固定加热功率预算这一共同坐标下,「保逐格控温压功率」([[edge-hotspot]] 族)与「免逐格换固定热状态」([[thermal-state]] 族)存在一条可复现的均匀度–预算 Pareto 前沿,且两族在不同预算 / 幅面区间各自占优——把 tension T1 从口水仗变成一张可测的相图。",
        now: "现可断言的是评测协议成立(同预算、同任务、同回路对齐可实现);两族何处交叉需实测,尚不能预断谁全面占优。"
      },
      ledger: [
        { date: "2026-08-17", node: "立卡", verdict: "pass", action: "采纳 goal,进入 INSTANTIATED", link: "browning-budget" },
        { date: "2026-08-18", node: "协议冻结", verdict: "pass", action: "锁定预算 × 幅面网格与对齐口径", link: "" }
      ],
      body: R`## Observation
- [w] tension T1:[[edge-hotspot]] 主张保逐格控温只压功率即可稳定极大幅面;[[thermal-state]] 主张干脆免逐格换固定热状态。二者在同一目标(大幅面功率 / 算力标度)上给出对撞主张。
- [e] 现有报告各用各的任务与预算口径,无法直接判定谁在什么区间更省。

## Surprise & rule-out
- 反直觉:两族都自称「大幅面更省」,却几乎没有在同一加热功率预算 × 同一局部焦斑定位任务下的正面对测。
- rule-out:不是「已有综述覆盖」——[[bounded-heat-methods]] 按方法归类但未给统一预算下的相图。

## Claim

### Hypothesis（大胆版）
在固定加热功率预算这一共同坐标下,两族存在一条可复现的均匀度–预算 Pareto 前沿,且在不同预算 / 幅面区间各自占优。

### 当前可断言（assertable now）
评测协议成立;两族交叉点位置需实测,尚不能预断。

## Predictions
- P1 (strong): 小预算 + 需精确定位焦斑的任务上,内容感知功率停火([[content-aware-browning]])占优于同预算热状态。
- P2 (medium): 极大幅面 + 可粗放上色的任务上,热状态类在等功率下反超。

## 实验台账
| 日期 | 节点 | verdict | 动作 | 链接 |
|---|---|---|---|---|
| 2026-08-17 | 立卡 | pass | 采纳 goal [[browning-budget]] | [[browning-budget]] |
| 2026-08-18 | 协议冻结 | pass | 锁定预算 × 幅面网格 | [[content-aware-browning]] |`
    },
    "edge-confound": {
      type: "idea", folder: "ideas",
      title: "Position:可停火优先级也许只是被边缘邻近度伪装的旧变量",
      oneLine: "在有强证据前,内容化可停火优先级可能与边缘邻近度高度共线;先把混淆讲清楚再谈内容感知增益。",
      date: "2026-08-18",
      fm: {
        type: "idea", seeded_from: ["[[what-governs-scorch]]"], status: "DRAFT",
        novelty_ref: "[[what-governs-scorch]]", delta: "initial", seed_type: "L2 假设翻转",
        complexity_tier: "理论·position", venue_targets: ["position track"],
        archetype: "把一个被当作新信号的量还原成旧变量的相关物",
        pitch: "先证伪「内容感知 = 新信号」的默认叙事:累计热通量可能只是边缘邻近度的相关物,不控混淆就别声称内容增益。"
      },
      claim: {
        bold: "文献里「按热通量停火」相对「按位置停火」的增益,很可能被边缘邻近度混淆——累计热通量与「离加热丝距离」高度共线;不做去混淆消融,任何内容感知增益都不可归因。",
        now: "可断言的是这是一个尚未被系统控制的混淆源(见方向卡平凡解释清单);能否被消融掉需要探针数据,当前只作 position 提醒,不下结论。"
      },
      ledger: [],
      body: R`## Observation
- [w] 方向卡 [[what-governs-scorch]] 的平凡解释清单第一条:可停火优先级也许等价于边缘邻近度,累计热通量只是边缘邻近度的相关物。
- [w] [[edge-hotspot]] 的滚动加热窗本身就强烈偏向最靠边网格,任何在其上叠加的内容分数都与边缘邻近度天然共线。

## Surprise & rule-out
- 反直觉:社区默认「读内容 > 看位置」,但若二者高度共线,增益也许来自边缘邻近度而非内容。
- 这正是 [[content-aware-browning]] 的 P1 需要用去混淆消融守住的归因前提。

## Claim

### Hypothesis（大胆版）
不做边缘邻近度去混淆消融,任何「内容感知停火」的增益都不可归因。

### 当前可断言（assertable now）
这是一个尚未被系统控制的混淆源;能否消融需探针数据,现只作 position 提醒。

## Predictions
- P1: 控制边缘邻近度后,累计热通量的边际增益显著缩小但不为零(否则退回位置启发式即可)。`
    },

    /* ---- wiki/directions/ — pre-idea exploratory ----------------------- */
    "what-governs-scorch": {
      type: "direction", folder: "directions",
      title: "一个网格的可停火优先级到底由什么决定?",
      oneLine: "方向卡:固定加热功率预算下,可停火优先级是位置、累计热通量,还是别的内容信号?(PROBING)",
      date: "2026-08-17",
      fm: {
        type: "direction", status: "PROBING", interest_prior: "high", feasibility_prior: "medium",
        probe_budget: 3, anchored_surface_entry: "[[browning-budget]]", created_at: "2026-08-17",
        ideal_probe: "在真实大幅面烘烤轨迹上,离线测每个网格的『事后重要性』(留一停火对最终上色不均度的影响)与其累计热通量的相关性", probe_gap: "high"
      },
      body: R`## 方向陈述
在固定加热功率预算下,一个网格的可停火优先级到底由什么决定——是位置、累计热通量,还是别的内容信号?

## Wedges
- [w] [[edge-hotspot]]:边缘热点说明热通量在网格间高度不均,且换位置仍承接热通量(角色像内容而非纯位置)。
- [w] [[thermal-state]]:固定热状态即有损压缩,等价承认历史热可压——但「压什么」不可审计,反衬出一个显式可停火优先级信号的价值。

## 平凡解释候选清单
- 可停火优先级其实就等价于「边缘邻近度」,累计热通量只是边缘邻近度的相关物。
- 热点是纯位置 artifact,和内容无关,换任何面包都保边上 k 个即可。
- 不同加热区的可停火结构差异太大,不存在统一信号。

## 探针计划
- P0 空烤:在几炉大幅面上打印每层每加热区的累计热通量分布,看不均性是否稳定、是否只集中在边缘。
- P1 复分析 ≤2h:离线在烘烤轨迹上算「留一停火 → 上色不均度变化」的事后重要性,与累计热通量求相关(即 [[scorch-by-heatflux]])。
- P2 ≤8 机·h:小规模跑内容感知 top-B 停火 vs 位置启发式的上色不均度对照(可选,信号足才上)。`
    },

    /* ---- wiki/probes/ — preregistered cheap experiment ----------------- */
    "scorch-by-heatflux": {
      type: "probe", folder: "probes",
      title: "Probe:累计热通量 vs 留一停火事后重要性的相关性",
      oneLine: "P1 复分析(≤2h):测累计热通量与留一停火上色不均度增量的 Spearman ρ。verdict = probe-confirms(ρ≈0.61)。",
      date: "2026-08-18",
      fm: { type: "probe", probe_id: "scorch-by-heatflux", direction_ref: "[[what-governs-scorch]]", cost_tier: "P1", time_box_hours: 2, status: "verdict", created_at: "2026-08-18", verdict: "probe-confirms" },
      body: R`## 双向信息量表
- 若 confirms —— 累计热通量与「留一停火事后重要性」高相关(如 Spearman ρ 明显 >0),说明它是可上线的廉价可停火优先级代理,支持 idea [[content-aware-browning]] 的 P1 首选路线继续做 P2 对照实验。
- 若 disconfirms —— 相关性微弱或为负,说明累计热通量不是可停火优先级的好代理,应转 [[content-aware-browning]] 的 P2 可学习头路线,或回方向卡 [[what-governs-scorch]] 重找信号。

## pilot 铁律声明
本探针只估可行性、信号量级与方差,结果一律 indicative,永不确认 claim。

## kill_criterion
(不携带处决权;本探针只给方向信号,不裁 idea 生死。)

## 三值判读
- verdict —— probe-confirms
- 实测值 —— 在 1 台双槽烤面包机、8 炉 32k 网格大幅面烘烤轨迹上,逐网格累计热通量与留一停火上色不均度增量的 Spearman ρ ≈ 0.61(每加热区中位数),明显高于边缘邻近度基线代理(ρ ≈ 0.28)。n_samples = 8 炉 × 全网格。(代表性数字)
- 死亡证明 —— (不适用:非 disconfirms、无 kill_criterion)
- 人签 —— auto 2026-08-18(/wiki-auto 机签;人保留事后翻案权)`
    },

    /* ---- wiki/field/problems/ — adopted goal (kind: adopted-goal) ------- */
    "browning-budget": {
      type: "goal", folder: "field/problems",
      title: "Goal:固定加热功率预算下的可靠大幅面均匀上色",
      oneLine: "六件套 goal 卡:预算收紧时不丢对最终上色仍重要的网格(能力缺口,不预设机制)。ADOPTED(auto)。",
      date: "2026-08-18",
      fm: { kind: "adopted-goal", goal_id: "browning-budget", status: "ADOPTED", statement_version: 1, created_at: "2026-08-17", adopted_at: "2026-08-18", adopted_by: "auto" },
      body: R`## 问题陈述
大幅面烘烤在固定加热功率预算下,无法在保留最相关的加热网格与不超预算之间可靠取舍:预算收紧时,当前做法会停掉对最终上色仍重要的网格,导致均匀度随幅面显著退化。这是一个能力缺口,不预设由何种机制填补。

## Success criteria
- 在固定加热功率预算下,大幅面上色均匀度(上色不均度 / 局部焦斑)不随幅面显著退化 [facet: main]
- 在一个标定期未见的预算档与更大的烘烤幅面上仍成立 [facet: heldout]
- 保留决策与「事后重要性」(留一停火对上色不均度的影响)方向一致,可被留出场景的失效预测检验 [facet: mechanism]

## Admissibility
- 禁止 用「只测边缘窗口内的上色」冒充全幅面均匀能力 —— 锚 [[edge-hotspot]]
- 禁止 靠调大预算把问题掩盖(必须在小预算档也成立)—— 锚 [[budget-browning-gap]]

## Non-goals
- 不含标定期二次墙的加速(那属 [[maillard-tiling]] / [[grid-sparse]] 的射程,已 crowded)。
- 不含彻底放弃逐格控温的路线本身(属 [[thermal-state]],此处只作对照 baseline)。

## Attack surface
- [[what-governs-scorch]]
- [[content-aware-browning]]

## 状态与 closure
status: ADOPTED
death_type: disconfirmed`
    },

    /* ---- wiki/field/ — high-altitude maps ------------------------------ */
    assumptions: {
      type: "field", folder: "field",
      title: "Field — 共享假设台账",
      oneLine: "大幅面控温效率的三条载重假设(瓶颈是传感器读写 / 重要性高度不均 / 保留策略可与硬件解耦),各挂 ≥3 篇。",
      date: "2026-08-17",
      fm: { last_zoomout: "2026-08-17", papers_at_zoomout: 2, staleness: 2, maintainer: "wiki-cartographer" },
      body: R`> 硬规则:每条 field claim 挂 ≥3 篇 wiki 论文出处(去重后 ≥2 个不同目标)。

## A1 — 大幅面控温效率的瓶颈是传感器读写 / 加热功率,不只是总加热能耗
- relied_by: [[maillard-tiling]]、[[edge-hotspot]]、[[thermal-state]]
- evidence_strength: established · constraint_class: hard
- flip_sketch: 若瓶颈重回纯总加热能耗(超低带宽比 / 电价极贵的新硬件),IO-aware 回路与功率停火的收益被重估,固定图案 / 次二次的能耗优势重新主导。

## A2 — 历史网格对最终上色的重要性高度不均且可被压缩
- relied_by: [[edge-hotspot]]、[[thermal-state]]、[[grid-sparse]]
- evidence_strength: assumed · constraint_class: soft
- flip_sketch: 若某类面包里重要性近乎均匀(每个网格都可能被精确定位焦斑),任何有损压缩 / 停火都会掉分,只有精确全逐格控温可用。

## A3 — 运行期保留策略可与机器硬件解耦(免重标定即生效)
- relied_by: [[edge-hotspot]]、[[maillard-tiling]]、[[grid-sparse]]
- evidence_strength: contested · constraint_class: hidden
- flip_sketch: 若最优停火必须与机器硬件联合标定才不掉分,「零重标定换停火策略」这条便宜路线失效,idea [[content-aware-browning]] 的无参数占坑版随之降档。`
    },
    tensions: {
      type: "field", folder: "field",
      title: "Field — 张力 / 矛盾清单",
      oneLine: "两条对撞:保逐格控温压功率 vs 免逐格换固定热状态(T1);图案 / 停火该先验固定还是内容自适应(T2)。",
      date: "2026-08-17",
      fm: { last_zoomout: "2026-08-17", papers_at_zoomout: 3, staleness: 1, maintainer: "wiki-cartographer" },
      body: R`> 每条挂 ≥3 篇出处;same_object 必填以防把跨域术语歧义当矛盾。

## T1 — 保逐格控温压功率 vs 放弃逐格换固定热状态
- side_a: [[edge-hotspot]] claims 保留逐格控温、只压功率(位置启发式)即可稳定极大幅面
- side_b: [[thermal-state]] claims 干脆放弃逐格控温、用固定大小热状态,免逐格闭环且线性标度
- same_object: 同一目标——大幅面烘烤的功率 / 算力标度;冲突在「是否保留显式逐格控温」这一机制选择上。
- 出处补强: [[maillard-tiling]]、[[grid-sparse]]
- resolution_type_guess: 适用域不同(需精确定位焦斑的任务偏 side_a;可粗放上色的任务偏 side_b)

## T2 — 图案 / 停火该是先验固定还是内容自适应
- side_a: [[grid-sparse]] claims 先验固定的 local+global 图案已足够处理大幅面
- side_b: [[edge-hotspot]] 的边缘热点证据 claims 重要性由内容 / 热通量决定,固定图案会漏关键热连边
- same_object: 同一对象——「保留 / 连接哪些网格」的选择规则;冲突在规则是否读内容。
- 出处补强: [[thermal-state]]
- resolution_type_guess: 真矛盾(是本 wiki 的 unification 种子:见 [[budget-browning-gap]])`
    },
    saturation: {
      type: "field", folder: "field",
      title: "Field — 饱和度图(方法 × 问题)",
      oneLine: "crowded:标定期加速已成熟;blank:预算内内容感知功率停火;messy:选择规则是否读内容(unification 富矿)。",
      date: "2026-08-17",
      fm: { last_zoomout: "2026-08-17", papers_at_zoomout: 2, staleness: 2, maintainer: "wiki-cartographer" },
      body: R`> 三类:crowded(拥挤,增量变体多)/ blank(谱系空白)/ messy(饱和且结论互相矛盾,unification 富矿)。每条挂 ≥3 篇出处。

## crowded — 标定期控温加速与固定图案近似
- 位置: (方法=精确 / 图案回路) × (问题=标定期二次墙)
- 出处: [[maillard-tiling]]、[[grid-sparse]]、[[thermal-state]]
- 判词: IO-aware 回路与固定图案已高度成熟,新作多为工程增量;不建议在此占坑。

## blank — 固定加热功率预算下的内容感知功率停火
- 位置: (方法=运行期功率停火) × (问题=预算内给哪些网格通电)
- 出处: [[edge-hotspot]]、[[thermal-state]]、[[maillard-tiling]]
- 判词: [[edge-hotspot]] 只填了「位置启发式」一格,「内容 / 热通量打分」一格空白 → 见 gap [[budget-browning-gap]]。

## messy — 「保留 / 连接哪些网格的规则是否读内容」
- 位置: (方法=图案 / 停火规则) × (问题=选择规则的内容依赖性)
- 出处: [[grid-sparse]]、[[edge-hotspot]]、[[thermal-state]]
- 判词: 固定图案 vs 内容自适应结论对撞(见 tensions T2),是 unification 种子的富矿。`
    },
    problems: {
      type: "field", folder: "field",
      title: "Field — problems.md(Hamming 式候选清单)",
      oneLine: "一行一条能力缺口式问题陈述(比六件套 goal 卡便宜);采纳某条则展开为 goal 卡。",
      date: "2026-08-18",
      fm: { last_zoomout: "2026-08-18", papers_at_zoomout: 4, staleness: 0, maintainer: "wiki-cartographer" },
      body: R`> 一行一条能力缺口式问题陈述(比六件套 goal 卡便宜);采纳某条则展开为 wiki/field/problems/<goal-id>.md。每条挂来源 gap / concept 反链。

- 在固定加热功率预算下,让大幅面烘烤的网格保留由内容而非位置决定 —— 源: [[budget-browning-gap]] · [[bounded-heat-methods]] 【已采纳 → [[browning-budget]]】
- 让有损的大幅面热压缩(固定状态 / 功率停火)变得可事后审计与可解释 —— 源: [[thermal-state]] · [[edge-hotspot]]
- 在同一加热功率预算下统一评测「保逐格控温压功率」与「免逐格换热状态」两条路线 —— 源: [[bounded-heat-methods]] · [[thermal-state]] · [[edge-hotspot]]
- 把幅面外推(预热外插)与加热功率预算管理放进同一权衡框架 —— 源: [[bounded-heat-methods]](adjacent 待补论文)`
    },

    /* ---- wiki/novelty/ — audit + fuel (kept strictly separate) ---------- */
    "novelty-ledger": {
      type: "novelty", folder: "novelty",
      title: "Novelty ledger(既判力台账)",
      oneLine: "append-only 既判力记录:idea vs edge-hotspot 判 component-overlap;goal 层判 problem-open。",
      date: "2026-08-18",
      fm: { append_only: true },
      body: R`> 每条各字段逐行 block-style;append-only,不改写、不删除既有条目。

## N-0001 — novelty · component-overlap
- idea: [[content-aware-browning]] · paper: [[edge-hotspot]]
- verdict: component-overlap
- evidence: "We keep the few edge grids powered together with a rolling window of the most recent grids." / "The edge hotspot emerges because the filament must dump surplus heat flux somewhere."
- defense: 共享「压低逐格控温成本以支持大幅面」这一组件目标,但本 idea 用累计热通量给每网格打分做预算内 top-B 通电,取代其位置启发式;是组件重叠而非同一方法。
- actions_taken: cite, sharpen · adjudicated_by: judge-agent · date: 2026-08-18 · status: standing

## N-0002 — openness · problem-open
- goal_ref: [[browning-budget]] · papers_checked: [[edge-hotspot]]、[[grid-sparse]]、[[thermal-state]]
- verdict: problem-open
- evidence: "Our method keeps a fixed number of edge hotspot grids plus the most recent grids; it does not select what to keep by content."
- defense: 邻域内已裁决的三篇都未在固定预算下按内容 / 热通量选择保留对象;goal [[browning-budget]] 的 main facet 无一被现报告结果满足,问题层判 open。
- adjudicated_by: human · date: 2026-08-18 · status: standing`
    },
    "novelty-fuel": {
      type: "novelty", folder: "novelty",
      title: "Novelty fuel(ideator 唯一可读的 novelty 产物)",
      oneLine: "只含正向迁移素材,永不含指控:从 thermal-state 迁『可学习保留决策』,从 maillard-tiling 迁『分块可增量』。",
      date: "2026-08-18",
      fm: { forward_only: true },
      body: R`> 只含正向迁移素材,永不含指控。字段:source_paper / mechanism(带原文一句) / transferable_insight / adaptation_hint / cite_required。

## F-1 — 从 [[thermal-state]] 迁移
- mechanism: 让热质量模型参数随输入变化(selection),用可学习门决定每步升温 / 散热什么——"The selection mechanism lets the machine choose what heat to keep or shed based on the current grid."
- transferable_insight: 「保留什么」可以是一个可学习、输入相关的决策,而不必是固定规则。
- adaptation_hint: 迁到功率停火时,把「固定状态里学到的散热」外化成一个作用在显式网格上的可停火优先级分数——既保逐格控温的精确定位,又拿到热状态式内容自适应。对应 [[content-aware-browning]] 的 P2 可学习头路线。
- cite_required: true

## F-2 — 从 [[maillard-tiling]] 迁移
- mechanism: 分块 + 在线重标定,避免物化 N×N 互热矩阵——"We compute grid control by tiling and never materialize the full grid-to-grid heat matrix in the buffer."
- transferable_insight: 任何逐网格打分 / 停火都必须在融合回路的分块流式结构里可增量算,否则省了功率却毁了读写收益。
- adaptation_hint: 把累计热通量分数做成随分块前向可摊还累加的量(每块结束更新),别引入需要全矩阵的额外 pass。对应 [[content-aware-browning]] 的 A2 前置条件。
- cite_required: false`
    }
  };

  // Give every note its own id (we keyed the map by id but need it on the value
  // too — n.id is used for self-link exclusion, backlink lookups, data-attrs).
  Object.keys(NOTES).forEach(function (k) { NOTES[k].id = k; });

  // Note-type → the icon used in the sidebar / list / graph legend.
  var TYPE_ICON = { paper: "i-note", concept: "i-globe2", gap: "i-note", idea: "i-spark", direction: "i-compass", probe: "i-flask", goal: "i-target", field: "i-map", novelty: "i-scale" };
  var TYPE_LABEL = { paper: "paper", concept: "concept", gap: "gap", idea: "idea", direction: "direction", probe: "probe", goal: "goal", field: "field", novelty: "novelty", meta: "meta" };
  // Localised note-type WORD (UI chrome, not corpus content) — zh default, en on
  // toggle (R8). The corpus body/title stay their source language; only the kind
  // word flips. Routed through L() so every render re-localises on the 中/EN switch.
  var TYPE_LABEL_ZH = { paper: "论文", concept: "概念", gap: "缺口", idea: "灵感", direction: "方向", probe: "探针", goal: "目标", field: "领域", novelty: "新颖性", meta: "元数据" };
  function typeLabel(t) { return L(TYPE_LABEL_ZH[t] || t, TYPE_LABEL[t] || t); }
  // Strip a leading type-word prefix ("Gap:…", "Idea:…", "Field — …") so a graph
  // node / breadcrumb reads as the human title, not the machine kind (R12/R31).
  function cleanTitle(s) {
    return String(s || "").replace(/^\s*(gap|idea|probe|position|goal|direction|concept|field)\s*[:：—–-]+\s*/i, "").trim();
  }

  /* =========================================================================
     2. GRAPH LAYOUT + STRUCTURED FEEDS (inbox / sources / import / ask)
     ========================================================================= */
  // Hand-placed layered coordinates: papers → concept → gap → idea → direction
  // → probe, with the adopted goal above. Fixed positions keep the SVG tidy and
  // deterministic for screenshots. [x, y] = top-left of a 176×54 node box.
  var GPOS = {
    "maillard-tiling": [24, 36], "grid-sparse": [24, 146], "edge-hotspot": [24, 256], "thermal-state": [24, 368],
    "bounded-heat-methods": [232, 200],
    "browning-budget": [440, 36],
    "budget-browning-gap": [440, 226],
    "unified-browning-bench": [648, 36],
    "content-aware-browning": [648, 168],
    "edge-confound": [648, 312],
    "what-governs-scorch": [856, 200],
    "scorch-by-heatflux": [1064, 200],
    // item 6(3): META sidecars — the /wiki-auto machine-decision ledger + the novelty ledger.
    // Parked in a row BELOW the research spine and DEFAULT-HIDDEN (GHIDE.meta / GHIDE.novelty),
    // revealed by the legend "meta" toggle; the viewport ignores hidden nodes so they add no
    // dead canvas until shown.
    "novelty-ledger": [440, 470],
    "__inbox__": [856, 470]
  };
  // edges [from, to, kind]; kind drives stroke style (seed/synth solid, ref/feed dashed).
  var GEDGES = [
    ["maillard-tiling", "bounded-heat-methods", "synth"], ["grid-sparse", "bounded-heat-methods", "synth"],
    ["edge-hotspot", "bounded-heat-methods", "synth"], ["thermal-state", "bounded-heat-methods", "synth"],
    ["grid-sparse", "maillard-tiling", "ref"], ["edge-hotspot", "thermal-state", "ref"], ["thermal-state", "maillard-tiling", "ref"],
    ["bounded-heat-methods", "budget-browning-gap", "synth"],
    ["edge-hotspot", "budget-browning-gap", "seed"], ["thermal-state", "budget-browning-gap", "seed"],
    ["budget-browning-gap", "content-aware-browning", "seed"],
    ["budget-browning-gap", "browning-budget", "seed"],
    ["browning-budget", "content-aware-browning", "attack"], ["browning-budget", "what-governs-scorch", "attack"],
    ["browning-budget", "unified-browning-bench", "attack"],
    ["edge-hotspot", "unified-browning-bench", "seed"], ["thermal-state", "unified-browning-bench", "seed"],
    ["content-aware-browning", "what-governs-scorch", "ref"],
    ["what-governs-scorch", "scorch-by-heatflux", "probe"],
    ["scorch-by-heatflux", "content-aware-browning", "feed"],
    ["what-governs-scorch", "edge-confound", "seed"],
    // item 6(3): meta-node edges (hidden until the "meta" toggle reveals both endpoints)
    ["novelty-ledger", "content-aware-browning", "ref"],
    ["novelty-ledger", "browning-budget", "ref"],
    ["__inbox__", "scorch-by-heatflux", "feed"],
    ["__inbox__", "content-aware-browning", "feed"],
    ["__inbox__", "browning-budget", "feed"]
  ];
  var GLABEL = {
    "maillard-tiling": "Maillard-Tiling", "grid-sparse": "GridSparse", "edge-hotspot": "EdgeHotspot", "thermal-state": "ThermalState",
    "bounded-heat-methods": "bounded-heat", "browning-budget": "browning-budget", "budget-browning-gap": "budget-browning gap",
    "unified-browning-bench": "unified bench", "content-aware-browning": "content-aware browning",
    "edge-confound": "edge confound", "what-governs-scorch": "what-governs?",
    "scorch-by-heatflux": "heat-flux probe",
    "novelty-ledger": "novelty ledger", "__inbox__": "wiki-auto ledger"
  };
  // item 6(3): synthetic graph nodes that aren't compiled wiki notes. __inbox__ stands in for
  // the /wiki-auto machine-decision ledger and routes to the Inbox sub-view instead of a note;
  // its type "meta" is default-hidden (GHIDE.meta) and toggled by the legend "meta" chip.
  var META_NODES = {
    "__inbox__": { type: "meta", sub: "inbox", zh: "/wiki-auto 机器决策台账", en: "/wiki-auto machine-decision ledger" }
  };
  function metaLabelFor(id) { var m = META_NODES[id]; return m ? L(m.zh, m.en) : (GLABEL[id] || id); }

  // /wiki-auto INBOX.md rows — every unattended machine decision. 状态 flippable.
  var INBOX = [
    { date: "2026-08-18", stage: "compile", obj: "thermal-state", item: "新 paper 笔记入库,机械盖章 venue_status=peer-reviewed / code=open / fence_zone=core", status: "seen" },
    { date: "2026-08-18", stage: "ideate", obj: "content-aware-browning", item: "从 gap 产出 idea 卡并落 SCORED + tiering 工件,complexity_tier=新颖占坑", status: "seen" },
    { date: "2026-08-18", stage: "probe", obj: "scorch-by-heatflux", item: "机器读判据 + 实测,回填三值判读 verdict=probe-confirms(机签 auto)", status: "needs-human" },
    { date: "2026-08-18", stage: "novelty", obj: "budget-browning-gap", item: "邻域三篇裁 problem-open,机器置 novelty_verified=true(人保留翻案权)", status: "needs-human" },
    { date: "2026-08-18", stage: "goal-adopt", obj: "browning-budget", item: "从 problems.md 候选采纳为六件套 goal 卡,frontmatter 记 adopted_by=auto", status: "needs-human" },
    { date: "2026-08-18", stage: "waiver", obj: "content-aware-browning", item: "128k 全预算档探不起(超 P2 时间盒),签 waiver、tier 记一档说明", status: "overturned" },
    { date: "2026-08-17", stage: "novelty", obj: "content-aware-browning", item: "vs edge-hotspot 裁 component-overlap,actions=[cite, sharpen],status=standing", status: "seen" }
  ];
  // 8-line reconciliation block: each claimed number beside a re-runnable command.
  // item 19: claim is a [zh, en] pair localized at paint time via L() (NOT frozen at load);
  // the command stays language-neutral.
  var RECON = [
    [["机签决策数 = 7", "machine-signed decisions = 7"], "grep -c '^| 202' wiki/INBOX.md"],
    [["本轮新增 SCORED idea 卡 = 1", "new SCORED idea cards this round = 1"], "grep -rl 'status: SCORED' wiki/ideas/ | wc -l"],
    [["waiver 占比 = 1/2 条 probe 事项", "waivers = 1 of 2 probe items"], "grep -c '\"event\": \"waiver\"' wiki/probes/ledger.jsonl"],
    [["fence_zone 盖章率 = 4/4 papers", "fence_zone stamped = 4/4 papers"], "grep -rl 'fence_zone:' wiki/papers/ | wc -l"],
    [["blocked / 需 OCR 遗留 = 1(hotgrid-oracle 仍 .pending)", "blocked / pending OCR = 1 (hotgrid-oracle still .pending)"], "ls raw/uniform-browning-control/mineru/*/_paper-wiki-ocr-batch-*.pending.json"],
    [["IMPORT-LOG 累计 = 5/200,本 sponsor 1/10", "IMPORT-LOG total = 5/200, this sponsor 1/10"], "tail -1 raw/IMPORT-LOG.md"],
    [["弃卡 / 新卡 = 0 弃 / 1 新(idea)", "retired / new = 0 retired / 1 new (idea)"], "grep -rl 'status: RETIRED' wiki/ideas/ | wc -l"],
    [["6 类异常 = {dangling:1, orphan:1, over-claim:0, fence-cross:0, quote-fail:0, lint-block:0}", "6 anomaly types = {dangling:1, orphan:1, over-claim:0, fence-cross:0, quote-fail:0, lint-block:0}"], "python scripts/idea_lint.py --census wiki/"]
  ];
  // raw/ ingestion registry — OCR status per source (committed/pending/needs-OCR).
  var SOURCES = [
    { id: "maillard-tiling", file: "maillard-tiling.pdf", topic: "uniform-browning-control", sponsor: "bootstrap", ocr: "committed", note: "已编译 → wiki/papers/maillard-tiling.md" },
    { id: "grid-sparse", file: "grid-sparse.pdf", topic: "uniform-browning-control", sponsor: "bootstrap", ocr: "committed", note: "已编译 → wiki/papers/grid-sparse.md" },
    { id: "edge-hotspot", file: "edge-hotspot.pdf", topic: "uniform-browning-control", sponsor: "bootstrap", ocr: "committed", note: "batch d5ae06f… · tree a4033a1… · 已编译" },
    { id: "thermal-state", file: "thermal-state.pdf", topic: "uniform-browning-control", sponsor: "bootstrap", ocr: "committed", note: "已编译 → wiki/papers/thermal-state.md" },
    { id: "hotgrid-oracle", file: "hotgrid-oracle.pdf", topic: "uniform-browning-control", sponsor: "needs-evidence", ocr: "pending", note: "mineru/hotgrid-oracle/ 仍是 .pending — 不可编译,阻断 idea 查新收尾" }
  ];
  // Look up a raw/ ingestion row by note id (used by the dangling-link hovercard, 19b).
  function sourceRow(id) { for (var i = 0; i < SOURCES.length; i++) { if (SOURCES[i].id === id) return SOURCES[i]; } return null; }
  // IMPORT-LOG.md rows (n/200 cap + per-sponsor m/10).
  var IMPORTLOG = [
    ["2026-08-15", "maillard-tiling", "bootstrap", "1/200", "1/10"],
    ["2026-08-15", "grid-sparse", "bootstrap", "2/200", "2/10"],
    ["2026-08-16", "edge-hotspot", "bootstrap", "3/200", "3/10"],
    ["2026-08-16", "thermal-state", "bootstrap", "4/200", "4/10"],
    ["2026-08-18", "hotgrid-oracle", "needs-evidence", "5/200", "1/10"]
  ];
  // wiki-search-latest candidate feed (arXiv). fenced rows disabled; recommended pre-selected.
  var CANDIDATES = [
    { n: 1, title: "HotGrid: Heavy-Hitter Oracle for Uniform Toaster Browning", authors: "Vance et al.", venue: "IHTC 2023", arxiv: "2306.14048", code: "open", rel: "high", fenced: false, rec: true, why: "按累计热通量(heavy hitters)做内容感知功率停火——最接近 gap [[budget-browning-gap]] 的前作;补它才能把 saturation 的 messy 格做实、给 idea 的查新守住。" },
    { n: 2, title: "SnapGrid: The Toaster Knows Where It Will Scorch Before Heating", authors: "Okoro and Sato", venue: "ApplThermal 2024", arxiv: "2404.14469", code: "open", rel: "high", fenced: false, rec: true, why: "按热通量图案聚类做预热期网格压缩;idea 的 P2 对照又一条内容感知 baseline。" },
    { n: 3, title: "PreHeat: Efficient Format Extension for Large-Format Toasters", authors: "Kwon et al.", venue: "IHTC 2024", arxiv: "2309.00071", code: "open", rel: "medium", fenced: false, rec: false, why: "预热曲线缩放做幅面外推——相邻区(format interpolation);仅当加热功率预算 vs 外推权衡开方向卡时导入。" },
    { n: 4, title: "A Survey of RL for Oven Thermostat Schedules", authors: "Anonymous et al.", venue: "arXiv 2025", arxiv: "2501.09999", code: "closed", rel: "low", fenced: true, rec: false, why: "烤箱恒温器调度,无烘烤幅面标度角度。在 scope fence 排除范围内——展示以求透明,永不自动导入。" }
  ];
  // research.md Scope fence — surfaced in the project-status popover (onTitle).
  var SCOPE = {
    lifecycle_state: "ACTIVE", expansion_mode: "auto",
    core: "大幅面烘烤下逐格控温 / 加热功率的算力与功率标度:精确加速、图案化、运行期停火、次二次替代。",
    adjacent: ["format interpolation / 外推(预热曲线):可作对照证据", "外挂预烤大幅面:仅当与加热功率预算权衡直接对话时纳入"],
    exclude: ["纯标定效率(火力曲线 / 并行)且与烘烤幅面标度无关 → fence_zone: outside", "多层烤盘网格压缩,除非直接改逐格控温标度"],
    todo: [
      { done: true, t: "采纳 problems.md 候选 → goal 卡 [[browning-budget]]" },
      { done: false, t: "跑探针 [[scorch-by-heatflux]](P1,复分析 ≤2h),回填三值判读" },
      { done: false, t: "/wiki-critique [[content-aware-browning]] 后再决定 novelty_verified" },
      { done: false, t: "补一篇 HotGrid / SnapGrid 类功率停火论文(search-latest #1),把 saturation messy 区做实" }
    ]
  };
  // tiering.md four-questions (why-rated) — companion rating artifact, no numeric score.
  var TIERING = {
    "content-aware-browning": {
      whitelist: ["wiki/ideas/content-aware-browning.md", "wiki/gaps/budget-browning-gap.md", "wiki/field/problems.md", "wiki/field/problems/browning-budget.md"],
      unread: "未读任何 raw/ 原文、未联网、未读其它 idea 卡;评级只依据白名单。",
      four: [
        ["a enables", true, "固定加热功率预算下逼近全逐格控温均匀度的大幅面烘烤,不退化成位置滑窗。"],
        ["b connects", true, "把边缘热点 / 功率压缩 / thermal-state 固定状态串成同一个「预算下给谁通电」问题。"],
        ["c unifies", false, "空。"],
        ["d opens", true, "可审计的功率停火(每次停火有可检查的分数)。"],
        ["第五项 important_problem 挂靠", true, "溯源到 [[browning-budget]](field 层已记录),不因空挂靠被逐出顶会档。"]
      ],
      exec: [["compute", "单机小时(最便宜路径=无参数累计热通量分数,免标定)"], ["data", "现成 benchmark(大幅面上色不均度 / 局部焦斑定位)"], ["engineering", "改控温管线(停火钩子,不改硬件)"], ["first_signal", "≤1 周(P1 探针复分析即可给 go/no-go)"], ["expensive_deps", "无 ⇒ 不触发降档"]],
      conclusion: "interest ≥2 问非空 + first_signal ≤1 周 + 卡上同时写了占坑版(无参数累计热通量分数)与完整版(可学习头),且占坑版是完整版真子集 ⇒ complexity_tier = 新颖占坑。",
      why: "未升「顶会大工程」:ladder 尚不足 3 条独立重实验路径(当前 P1/P2 两条);未降「低层级可行」:interest ≥2 问非空且 important_problem 有实锚。"
    }
  };
  // counter.md — the "why kept alive" / kill-decision provenance (adversarial).
  var COUNTER = {
    "content-aware-browning": {
      objection: "最强反方:vs [[edge-hotspot]] 已被 novelty ledger 裁为 component-overlap(共享『压功率支持大幅面』组件);且假设 A3(保留策略可与硬件解耦)被标 contested——若最优停火必须联合标定,无参数占坑版直接降档。",
      keepalive: "留活理由:goal 层 [[browning-budget]] 被独立裁为 problem-open(N-0002,邻域三篇 main facet 无一满足);actions=[cite, sharpen] 已把差异收敛到『内容分数取代位置启发式』;探针 [[scorch-by-heatflux]] 给出 ρ≈0.61 的正向信号。综合判『不 kill,继续 P1』。"
    }
  };
  // Teach panel — pre-seeded citation-bound exchanges (answers only from corpus).
  // Each cite = {id, section} deep-links into the reader on the left.
  var ASK = [
    {
      q: "EdgeHotspot 和 ThermalState 在大幅面上怎么取舍?",
      kind: "table",
      intro: "两篇都在库内,做一张跨论文对比(每格附出处小节):",
      cols: ["机制", "运行期逐格成本", "精确局部焦斑定位", "标度", "出处"],
      rows: [
        ["EdgeHotspot", "边缘热点 + 滚动加热窗(位置启发式)", "保留逐格控温,受窗口限", "强(保逐格控温)", "近线性(压功率)", { id: "edge-hotspot", section: "核心方法" }],
        ["ThermalState", "selective 热质量模型,固定大小状态", "无逐格闭环", "弱(有损压缩)", "标定线性 / 运行常数状态", { id: "thermal-state", section: "核心方法" }]
      ],
      foot: "它们的对撞被登记为 tension T1(见 [[tensions]]);统一评测提案见 [[unified-browning-bench]]。"
    },
    {
      q: "gap budget-browning-gap 现在是什么状态?",
      kind: "gap-status",
      novelty: { verified: true, src: { id: "budget-browning-gap", section: "问题陈述" }, ledger: "novelty ledger N-0002 判 problem-open(human)" },
      ideas: [
        { txt: "[[content-aware-browning]] — SCORED · 新颖占坑", cite: { id: "content-aware-browning", section: "Claim" } }
      ],
      probe: { txt: "[[scorch-by-heatflux]] — probe-confirms,Spearman ρ≈0.61(> 边缘邻近度基线 0.28)", cite: { id: "scorch-by-heatflux", section: "三值判读" } },
      critique: "novelty:vs [[edge-hotspot]] 判 component-overlap → actions [cite, sharpen](见 [[novelty-ledger]])。",
      foot: "待办:补 [[hotgrid-oracle]](search-latest #1)把邻域查新做满,再最终定 novelty_verified。"
    },
    {
      q: "这个方法在咖啡烘焙失重率上效果如何?",
      kind: "notinwiki",
      body: "not in wiki。库内四篇(Maillard-Tiling / GridSparse / EdgeHotspot / ThermalState)与加热功率预算 idea 都不含咖啡烘焙 / 失重率评测——[[thermal-state]] 提到冷冻 / 厚片建模但无咖啡烘焙失重率数字。",
      missing: "缺一篇咖啡烘焙大幅面评测来源。",
      action: "建议 /wiki-search-latest \"streaming coffee-roast large-format power\" → 确认后 import → 编译入库,再来问。"
    }
  ];

  /* =========================================================================
     2.9 LIVE DATA — swap the inline SAMPLE corpus for the server adapters when a
     wiki project is open (SB.data.dir('wiki') → /api/wiki/*); otherwise keep the
     beautiful sample. ONLY the data source changes — every render below is
     untouched. Reverse-links + the concept graph come from the server's own
     grep-for-[[id]] computation, so the dual rail and graph stay faithful.
     ========================================================================= */
  var SAMPLE_NOTES = NOTES;                       // the inline corpus = the fallback
  var SAMPLE_GPOS = GPOS, SAMPLE_GEDGES = GEDGES, SAMPLE_GLABEL = GLABEL;
  var LIVE = null;                                // null = sample mode; else live bundle
  var RGEN = 0;                                   // render generation — drop a stale async paint
  var CORPUS = { key: undefined, promise: null }; // memoized corpus load, keyed by dir
  var SENT = {};                                  // getOr fallback sentinel = "no live data"

  function dirName() { var d = (LIVE && LIVE.dir) || ""; return d.split(/[\\/]/).filter(Boolean).pop() || d; }
  function normType(t) { return t === "adopted-goal" ? "goal" : (t || "note"); }
  // item 6(3): the real corpus surfaces machine-decision sidecars — the /wiki-auto INBOX,
  // the novelty ledger, other ledgers — that are NOT research-spine notes. Classify them as
  // type 'meta' so GHIDE.meta hides them by default (they were rendering on the spine + turning
  // up in every backlink rail). Detect by id or raw type; everything else keeps normType.
  function liveNodeType(id, rawType) {
    var t = normType(rawType);
    if (t === "meta" || t === "ledger" || t === "inbox" || t === "novelty-ledger") return "meta";
    // id ends in .../-/_-separated "inbox" or "ledger" (covers INBOX, novelty-ledger, ledger,
    // wiki-auto ledger) — tight enough not to catch an ordinary note that merely mentions them.
    var key = String(id || "").toLowerCase();
    if (key === "inbox" || key === "__inbox__" || /(^|[\/._-])(inbox|ledger)$/.test(key)) return "meta";
    return t;
  }
  function folderOf(path) {                       // "wiki/field/problems/g.md" -> "field/problems"
    var parts = String(path || "").split("/");
    if (parts[0] === "wiki") parts.shift();
    parts.pop();
    return parts.join("/");
  }
  function firstLinkId(s) { var m = /\[\[\s*([^\]|#]+?)\s*(?:[|#][^\]]*)?\]\]/.exec(String(s || "")); return m ? m[1].trim() : ""; }
  function cleanAnno(a) {                          // drop YAML-list junk the server picks up trailing an FM [[link]]
    a = String(a || "").trim();
    return (!a || /[\[\]"]/.test(a) || a.length > 90) ? "" : a;
  }
  function fetchOr(view, params) { return SB.data.getOr("wiki", view, SENT, params); }

  // Load (once per dir) the shared corpus every view leans on: the note metadata
  // list + the server graph (nodes/edges = the reverse-link index the list counts
  // and dual rail render). Resolves true when live, false when falling back.
  function ensureCorpus() {
    var dir = "";
    try { dir = SB.data.dir("wiki"); } catch (e) { dir = ""; }
    if (CORPUS.key === dir && CORPUS.promise) return CORPUS.promise;
    CORPUS.key = dir;
    if (!dir) { useSample(); return (CORPUS.promise = Promise.resolve(false)); }
    CORPUS.promise = Promise.all([fetchOr("notes"), fetchOr("graph")]).then(function (r) {
      var list = r[0], graph = r[1];
      if (list === SENT || !Array.isArray(list) || !list.length) { useSample(); return false; }
      useLive(dir, list, (graph && graph.nodes) ? graph : { nodes: [], edges: [] });
      return true;
    }, function () { useSample(); return false; });
    return CORPUS.promise;
  }
  function useSample() {
    if (LIVE === null && NOTES === SAMPLE_NOTES) return;
    NOTES = SAMPLE_NOTES; ORDER = Object.keys(SAMPLE_NOTES); _blCache = null; LIVE = null;
  }
  function useLive(dir, list, graph) {
    var map = {}, order = [];
    // item 6(3): a set of the ledger/inbox/novelty-ledger ids across BOTH the notes list and the
    // graph nodes (a ledger can be graph-only). Used to type them 'meta' and to keep them out of
    // the reverse-link rail so they stop polluting every note's backlinks.
    var metaSet = {};
    (graph.nodes || []).forEach(function (gn) { if (liveNodeType(gn.id, gn.type) === "meta") metaSet[gn.id] = 1; });
    list.forEach(function (m) {
      var f = m.front || {}, t = liveNodeType(m.id, m.type);
      if (t === "meta") metaSet[m.id] = 1;
      map[m.id] = {
        id: m.id, type: t, folder: folderOf(m.path), path: m.path,
        title: m.title || m.id, oneLine: m.summary || "", fm: f, tags: m.tags || [],
        source_path: f.source_path || null, companion: !!m.companion, body: null,
        date: f.compiled_at || f.adopted_at || f.created_at || f.last_zoomout || ""
      };
      order.push(m.id);
    });
    var to = {}, from = {};                        // reverse-link index from the server graph
    (graph.edges || []).forEach(function (e) {
      if (metaSet[e.from]) return;                 // item 6(3): a ledger→note edge never counts as a backlink
      (to[e.to] = to[e.to] || []).push({ from: e.from, anno: "" });
      (from[e.from] = from[e.from] || []).push(e.to);
    });
    LIVE = { dir: dir, notes: map, order: order, to: to, from: from, graph: graph, openBL: {} };
    NOTES = map; ORDER = order; _blCache = null;
    if (!NOTES[WS.curId]) { WS.curId = order[0]; WS.curFolder = (NOTES[order[0]] || {}).folder || "papers"; }
  }

  // One note's reader body: inline for sample, fetched-and-cached for live (drops a
  // leading H1 — the reader shell shows the title, and field/inbox notes lead with one).
  function bodyOf(n) {
    if (!n) return Promise.resolve("");
    if (n.body != null) return Promise.resolve(n.body);
    if (!LIVE) return Promise.resolve("");
    return SB.data.get("wiki", "note", { rel: n.path }).then(function (d) {
      var b = ((d && d.body_md) || "").replace(/^\s*#\s+[^\n]*\n/, "");
      n.body = b; n._outbound = (d && d.outbound) || [];
      if (d && d.front && !(n.fm && Object.keys(n.fm).length)) n.fm = d.front;
      return b;
    }, function () { n.body = ""; return ""; });
  }
  // The dual rail's inbound list WITH annotations — the signature reverse-link scan,
  // server-computed for live; the in-module computation for sample.
  function openBacklinks(id) {
    if (!LIVE) return Promise.resolve(backlinksOf(id));
    if (LIVE.openBL[id]) return Promise.resolve(LIVE.openBL[id]);
    return SB.data.get("wiki", "backlinks", { note_id: id }).then(function (arr) {
      var out = (Array.isArray(arr) ? arr : [])
        // item 6(3): a ledger/inbox source is a machine sidecar, not an editorial backlink — drop it.
        .filter(function (b) { return liveNodeType(b.id, b.type) !== "meta"; })
        .map(function (b) { return { from: b.id, anno: cleanAnno(b.anno), type: normType(b.type) }; });
      LIVE.openBL[id] = out; return out;
    }, function () { return LIVE.to[id] || []; });
  }
  // Subtle "reading <dir>" vs "sample" hint, dropped once per painted view.
  function paintBadge(main, live) {
    var b = el("div", "wiki-srchint" + (live ? " live" : ""));
    // item 29c: a hover tooltip so the honesty chip reads as a data-source label, not an instruction.
    b.title = live ? L("数据来源 —— 内容读取自该文件夹", "Data source — content read from this folder")
      : L("示例数据 —— 未连接任何文件夹", "Sample data — no folder connected");
    b.innerHTML = live ? '<span class="srcdot"></span>' + esc(L("读取 ", "reading ") + dirName())
      : esc(L("示例数据", "sample"));
    main.appendChild(b);
  }

  /* ---- R1 honesty layer ----------------------------------------------------
     Two very different "why am I seeing the sample" states:
       • no dir set  → the intentional demo. Silent; keep the quiet "sample corpus"
         pill only (paintBadge above).
       • a dir IS set but EVERY fetch failed (couldNotRead) → the user pointed Wiki
         at a broken/unreadable directory and we silently swapped in the full sample
         corpus. That is dishonest — raise a loud, dismissible AMBER banner so a
         sample note is never mistaken for the user's own project.
     Reuses the shared `.sample-banner` component Spark uses (amber base, no `.cnr`
     red variant), so it is theme-aware + consistent across tools. */
  function wikiCouldNotRead() {
    var rs = null; try { rs = SB.data.readState ? SB.data.readState("wiki") : null; } catch (e) { rs = null; }
    return !!(rs && rs.couldNotRead && !rs.dismissed);
  }
  function cnrBannerHTML() {
    if (!wikiCouldNotRead()) return "";
    var d = ""; try { d = SB.data.dir("wiki"); } catch (e) {}
    var where = String(d || "").trim();
    return '<div class="sample-banner wiki-cnr" role="status">' +
      '<span class="sb-ic">⚠</span>' +
      '<div class="sb-tx"><b>' + esc(L("读不到这个目录", "Couldn't read this directory")) + '</b>' +
      '<span>' + esc(L("无法读取 ", "couldn't read ") + where + L(" —— 下方为示例数据,非本项目。", " — showing sample data, not this project.")) + '</span></div>' +
      '<button class="btn sm ghost" data-wiki-cnr-dismiss>' + esc(L("知道了", "Dismiss")) + '</button>' +
      '</div>';
  }
  function wireCnrBanner(scope) {
    var b = scope && $("[data-wiki-cnr-dismiss]", scope); if (!b) return;
    b.onclick = function () {
      if (SB.data.dismissRead) SB.data.dismissRead("wiki");
      var bn = b.closest ? b.closest(".sample-banner") : null; if (bn) bn.remove();
    };
  }
  // Drop the amber couldNotRead banner atop a pane view (Ideas / Graph / Coverage /
  // Sources / Inbox), so the honesty layer is not Library-only.
  function prependCnr(container) {
    if (!container || !wikiCouldNotRead()) return;
    var tmp = el("div"); tmp.innerHTML = cnrBannerHTML();
    var banner = tmp.firstChild; if (!banner) return;
    container.insertBefore(banner, container.firstChild);
    wireCnrBanner(container);
  }

  /* ---- R11 sample-fixture markers ------------------------------------------
     The sample corpus tags its illustrative experiment numbers inline with a
     "(代表性数字)" fixture marker. Left in the prose it reads as if the paper wrote
     it — a fixture-only marker leaking into content. In sample mode we strip the
     inline markers from the rendered body and fold ONE honest footnote in instead;
     live bodies come from the real wiki and are never rewritten. */
  var FIXNUM_RE = /[（(]\s*代表性数字\s*[）)]/g;
  function hasFixnum(md) { FIXNUM_RE.lastIndex = 0; return FIXNUM_RE.test(String(md || "")); }
  function stripFixnum(md) { return String(md || "").replace(FIXNUM_RE, ""); }
  // item 25: some real fixtures bake an ENGLISH fidelity disclaimer straight into the note
  // body ("Fixture note: real paper, compiled to representative fidelity…"). Left in place it
  // strands an English line inside an otherwise-Chinese reader. Detect + strip the baked line
  // (blockquote / emphasis variants included) and re-surface fidelity through the localized
  // footnote below instead — never depend on the baked English prose.
  var FIXNOTE_EN_RE = /^[ \t>*_]*Fixture note:.*$/gim;
  function hasBakedFixnote(md) { FIXNOTE_EN_RE.lastIndex = 0; return FIXNOTE_EN_RE.test(String(md || "")); }
  function stripBakedFixnote(md) { return String(md || "").replace(FIXNOTE_EN_RE, "").replace(/\n{3,}/g, "\n\n").replace(/\s+$/, ""); }
  function fixnoteHTML() {
    return '<p class="wiki-fixnote">' + esc(L(
      "文中标注的实验数字为示例语料的代表性数值,非真实测量。",
      "Figures in this note are representative values from the sample corpus, not real measurements.")) + "</p>";
  }

  /* item 15: the Spark reader carries a persistent, dismissible "New here?" gloss strip
     (spark.js glossKey/dismissGloss/wireGloss). Mirror that pattern for the Wiki reader so
     the insider vocab on the kicker + meta chips (the note-type word, the fence_zone chip) is
     legible without hover. Content-aware: only the terms actually present on THIS note appear.
     Dismissal persists in localStorage (sb.* namespace), so a returning reader never re-reads it. */
  var GLOSS_KEY = "sb.wiki.gloss.reader";
  function glossDismissed() { try { return localStorage.getItem(GLOSS_KEY) === "1"; } catch (e) { return false; } }
  function dismissGloss() { try { localStorage.setItem(GLOSS_KEY, "1"); } catch (e) {} }
  function readerGlossHTML(n) {
    if (glossDismissed()) return "";
    var f = (n && n.fm) || {}, items = [];
    // note-type role — always present (every note has a type driving the kicker word).
    items.push([L("概念 / 缺口 / 灵感", "concept / gap / idea"),
      L("笔记类型 —— 该笔记在研究流水线里的角色(论文→概念→缺口→灵感→方向→探针)", "note type — this note's role in the research pipeline")]);
    // fence — only when the note carries a fence_zone chip.
    if (f.fence_zone) items.push([L("栅栏 fence", "fence"),
      L("研究范围边界:core 核心 / adjacent 邻接 / outside 排除", "research-scope boundary: core / adjacent / outside")]);
    if (!items.length) return "";
    return '<div class="wiki-gloss" role="note"><span class="wg-h">' + esc(L("术语速览", "New here?")) + "</span>" +
      items.map(function (it) { return '<span class="wg-item"><b>' + esc(it[0]) + "</b>" + esc(it[1]) + "</span>"; }).join("") +
      '<button type="button" class="btn sm ghost wg-dismiss" data-wgloss-dismiss>' + esc(L("知道了", "Got it")) + "</button></div>";
  }
  function wireReaderGloss(scope) {
    if (!scope) return;
    var b = scope.querySelector("[data-wgloss-dismiss]"); if (!b) return;
    b.onclick = function () { dismissGloss(); var strip = b.closest ? b.closest(".wiki-gloss") : null; if (strip) strip.remove(); };
  }
  // A note's reader body HTML: sample bodies get fixture markers stripped + a single
  // footnote; live bodies render verbatim.
  function noteBodyHTML(n) {
    var raw = (n && n.body) || "";
    var hadEnNote = hasBakedFixnote(raw);              // item 25: baked English fidelity line?
    var cleaned = hadEnNote ? stripBakedFixnote(raw) : raw;
    if (LIVE) {
      // Live bodies render verbatim EXCEPT the baked English fidelity line, which we suppress
      // and re-surface through the localized footnote so a zh reader isn't left with English.
      return renderMd(cleaned) + (hadEnNote ? fixnoteHTML() : "");
    }
    var had = hasFixnum(raw);
    return renderMd(stripFixnum(cleaned)) + (had || hadEnNote ? fixnoteHTML() : "");
  }

  /* =========================================================================
     3. LINK GRAPH — outbound / backlinks / lint (computed, never stored)
     ========================================================================= */
  function serializedFM(n) {
    // Flatten front-matter link-bearing fields so [[id]] refs there also count
    // as outbound edges (related_papers / seeded_from / novelty_ref / …).
    var f = n.fm || {}, parts = [];
    ["related_papers", "seeded_from", "novelty_ref", "important_problem", "direction_ref", "anchored_surface_entry"].forEach(function (k) {
      if (f[k]) parts.push([].concat(f[k]).join(" "));
    });
    return parts.join(" ");
  }
  function outboundIds(n) {
    // Live: the open note carries the server's own [[link]] scan (incl. dangling);
    // other notes fall back to their graph out-edges (known targets only).
    if (LIVE) return (n && n._outbound) || (n && LIVE.from[n.id]) || [];
    // Every distinct [[id]] referenced by this note (body + front-matter),
    // in first-seen order, excluding self-links.
    var text = (n.body || "") + " " + serializedFM(n);
    var re = /\[\[([^\]]+)\]\]/g, m, seen = {}, out = [];
    while ((m = re.exec(text))) { var id = m[1].trim(); if (id !== n.id && !seen[id]) { seen[id] = 1; out.push(id); } }
    return out;
  }
  function annotationFor(fromNote, targetId) {
    // Pull the "[[id]]（annotation）" gloss the linking note wrote, if any —
    // this is what makes the backlink rail read like real editorial cross-refs.
    var body = fromNote.body || "";
    var esc2 = targetId.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    var re = new RegExp("\\[\\[" + esc2 + "\\]\\]\\s*[（(]([^）)]+)[）)]");
    var m = re.exec(body);
    return m ? m[1].trim() : "";
  }
  function snippetFor(fromNote, targetId) {
    // Fallback linking-context for the backlink rail (R13): the sentence / list-item
    // in the SOURCE note that contains [[targetId]], with wikilinks + md stripped,
    // truncated to ~90 chars. Only computable when the source body is in memory
    // (sample corpus; live mode leans on the server-supplied gloss instead).
    var body = fromNote && fromNote.body; if (!body) return "";
    var tk = "[[" + targetId + "]]", lines = String(body).split(/\n+/);
    for (var i = 0; i < lines.length; i++) {
      if (lines[i].indexOf(tk) < 0) continue;
      var s = lines[i]
        .replace(/^\s*#{1,6}\s+/, "").replace(/^\s*[-*>]\s+/, "").replace(/^\s*\d+\.\s+/, "")
        .replace(/\[\[[^\]]*\]\]\s*[（(][^）)]*[）)]/g, "")   // drop [[x]]（gloss）whole
        .replace(/\[\[[^\]]*\]\]/g, "")                        // drop remaining [[wikilinks]]
        .replace(/\*\*([^*]+)\*\*/g, "$1").replace(/[*`]/g, "")
        .replace(/\s+/g, " ").trim();
      if (!s) return "";
      if (s.length > 90) s = s.slice(0, 88).replace(/\S*$/, "").trim() + "…";
      return s;
    }
    return "";
  }
  // 19c: when the backlink edge is produced by a front-matter FIELD (seeded_from /
  // relied_by / novelty_ref / …) rather than a body sentence, snippetFor finds nothing.
  // Synthesize a short context from the field that produced the edge, so the rail reads
  // as "seed · gap — seeded from here" instead of a bare "seed · gap".
  function fmEdgeContext(fromNote, targetId) {
    var f = (fromNote && fromNote.fm) || {};
    var fields = [
      ["seeded_from", L("由此播种", "seeded from here")],
      ["relied_by", L("载重依赖", "load-bearing dependency")],
      ["novelty_ref", L("新颖性对照", "novelty reference")],
      ["important_problem", L("对应问题", "the target problem")],
      ["direction_ref", L("方向来源", "direction reference")],
      ["related_papers", L("相关论文", "related paper")],
      ["anchored_surface_entry", L("锚定入口", "anchored entry")]
    ];
    for (var i = 0; i < fields.length; i++) {
      var k = fields[i][0]; if (!f[k]) continue;
      if ([].concat(f[k]).join(" ").indexOf(targetId) >= 0) return fields[i][1];
    }
    return "";
  }
  var _blCache = null;
  function backlinksOf(id) {
    // Live: the open note's richer, annotated list (server backlinks adapter) when
    // we have it, else the graph reverse-index (exact inbound counts for the list).
    if (LIVE) return LIVE.openBL[id] || LIVE.to[id] || [];
    // Reverse index: who links [[id]]. Built once, cheap over a small corpus —
    // exactly the tool's grep-for-inbound-links model.
    if (!_blCache) {
      _blCache = {};
      Object.keys(NOTES).forEach(function (fromId) {
        var fn = NOTES[fromId];
        outboundIds(fn).forEach(function (toId) {
          (_blCache[toId] = _blCache[toId] || []).push({ from: fromId, anno: annotationFor(fn, toId) });
        });
      });
    }
    return _blCache[id] || [];
  }
  function danglingIn(n) { return outboundIds(n).filter(function (id) { return !NOTES[id]; }); }

  /* =========================================================================
     4. MARKDOWN → HTML (with clickable [[wikilinks]]) for the reader articles
     ========================================================================= */
  function slug(s) { return "sec-" + String(s).toLowerCase().replace(/[^a-z0-9一-鿿]+/g, "-").replace(/^-+|-+$/g, ""); }
  function inlineMd(s) {
    s = esc(s);
    // $…$ math → a subtle mono span (reader keeps LaTeX; we never execute it).
    s = s.replace(/\$([^$]+)\$/g, function (_, m) { return '<code class="tex">' + m + "</code>"; });
    // 【已采纳 → [[id]]】 baked into problems.md prose → a localised UI chip (item 22);
    // the inner [[id]] is left for the wikilink pass below to turn into a link.
    s = s.replace(/【\s*已采纳\s*[→>]+\s*(\[\[[^\]]+\]\])\s*】/g, function (_, link) {
      return '<span class="chip ok wiki-adopted">' + esc(L("已采纳", "Adopted")) + " → " + link + "</span>";
    });
    // [[wikilink]] → clickable; unknown target gets .dangling (broken-link lint).
    s = s.replace(/\[\[([^\]]+)\]\]/g, function (_, id) {
      id = id.trim(); var known = !!NOTES[id];
      return '<a class="wl' + (known ? "" : " dangling") + '" data-id="' + esc(id) + '">' + esc(id) + "</a>";
    });
    s = s.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    return s;
  }
  function renderMd(md) {
    var lines = md.replace(/\r/g, "").split("\n"), out = [], i = 0, n = lines.length;
    function flushList(buf, ord) { if (buf.length) out.push("<" + (ord ? "ol" : "ul") + ">" + buf.map(function (x) { return "<li>" + inlineMd(x) + "</li>"; }).join("") + "</" + (ord ? "ol" : "ul") + ">"); }
    while (i < n) {
      var ln = lines[i];
      if (!ln.trim()) { i++; continue; }
      var hm = /^(#{2,4})\s+(.*)$/.exec(ln);
      if (hm) { var lv = hm[1].length, tx = hm[2]; out.push("<h" + lv + ' id="' + slug(tx) + '">' + inlineMd(tx) + "</h" + lv + ">"); i++; continue; }
      if (/^\s*\|.*\|\s*$/.test(ln)) { // GFM pipe table
        var rows = [];
        while (i < n && /^\s*\|.*\|\s*$/.test(lines[i])) { rows.push(lines[i]); i++; }
        var body = rows.filter(function (r) { return !/^\s*\|[\s:|-]+\|\s*$/.test(r); });
        var html = '<div class="tbl-wrap"><table>';
        body.forEach(function (r, ri) {
          var cells = r.replace(/^\s*\|/, "").replace(/\|\s*$/, "").split("|").map(function (c) { return c.trim(); });
          html += "<tr>" + cells.map(function (c) { return ri === 0 ? "<th>" + inlineMd(c) + "</th>" : "<td>" + inlineMd(c) + "</td>"; }).join("") + "</tr>";
        });
        out.push(html + "</table></div>"); continue;
      }
      if (/^>\s?/.test(ln)) { var q = []; while (i < n && /^>\s?/.test(lines[i])) { q.push(lines[i].replace(/^>\s?/, "")); i++; } out.push("<blockquote>" + q.map(inlineMd).join("<br>") + "</blockquote>"); continue; }
      if (/^\s*[-*]\s+/.test(ln)) { var b = []; while (i < n && /^\s*[-*]\s+/.test(lines[i])) { b.push(lines[i].replace(/^\s*[-*]\s+/, "")); i++; } flushList(b, false); continue; }
      if (/^\s*\d+\.\s+/.test(ln)) { var o = []; while (i < n && /^\s*\d+\.\s+/.test(lines[i])) { o.push(lines[i].replace(/^\s*\d+\.\s+/, "")); i++; } flushList(o, true); continue; }
      var p = []; while (i < n && lines[i].trim() && !/^(#{2,4}\s|>\s?|\s*[-*]\s|\s*\d+\.\s|\s*\|)/.test(lines[i])) { p.push(lines[i]); i++; }
      out.push("<p>" + inlineMd(p.join(" ")) + "</p>");
    }
    return out.join("\n");
  }

  /* =========================================================================
     5. HEADER CHIPS + KICKER for a note
     ========================================================================= */
  function chip(cls, txt, title) { return '<span class="chip ' + cls + '"' + (title ? ' title="' + esc(title) + '"' : "") + ">" + esc(txt) + "</span>"; }
  function metaFor(n) {
    var f = n.fm || {}, parts = [];
    if (f.authors) parts.push("<span>" + esc(f.authors) + "</span>");
    if (f.venue) parts.push('<span class="b">•</span><span>' + esc(f.venue) + "</span>");
    var chips = [];
    if (f.venue_status) chips.push(chip(f.venue_status === "peer-reviewed" ? "ok" : "", venueLabel(f.venue_status)));
    if (f.code) chips.push(chip(f.code === "open" ? "ok" : f.code === "closed" ? "bad" : "wait", L("代码:", "code: ") + f.code));
    if (f.fence_zone) chips.push(chip(f.fence_zone === "core" ? "accent" : f.fence_zone === "adjacent" ? "wait" : "stale", L("范围:", "fence: ") + fenceLabel(f.fence_zone), L("研究范围边界:core 核心 / adjacent 邻接 / outside 排除", "research scope fence: core / adjacent / outside")));
    if (typeof f.novelty_verified === "boolean") chips.push(chip(f.novelty_verified ? "ok" : "stale", f.novelty_verified ? "novelty ✓" : "novelty: unverified"));
    if (f.status) chips.push(chip(statusClass(f.status), f.status));
    if (f.complexity_tier) chips.push(chip(tierClass(f.complexity_tier), tierLabel(f.complexity_tier)));
    if (f.cost_tier) chips.push(chip("", f.cost_tier + (f.time_box_hours ? " · ≤" + f.time_box_hours + "h" : "")));
    if (f.verdict) chips.push(chip(f.verdict === "probe-confirms" ? "ok" : f.verdict === "probe-disconfirms" ? "bad" : "stale", f.verdict));
    if (f.kind === "adopted-goal") chips.push(chip("accent", "adopted-goal" + (f.adopted_by ? " · " + f.adopted_by : "")));
    if (f.staleness != null) chips.push(chip(f.staleness >= 8 ? "stale" : "", "staleness " + f.staleness));
    var tags = (f.tags || []).map(function (t) { return chip("", "#" + t); }).join("");
    return '<div class="fmline">' + parts.join(" ") + "</div>" +
      (chips.length || tags ? '<div class="chiprow">' + chips.join("") + tags + "</div>" : "");
  }
  function statusClass(s) {
    return ({ DRAFT: "", SCORED: "accent", INSTANTIATED: "wait", RUNNING: "wait", SUPPORTED: "ok", UNDERMINED: "bad", RETIRED: "stale", PARKED: "stale", PROMOTED: "ok", EXPLORING: "wait", PROBING: "wait", CRYSTALLIZED: "ok", ADOPTED: "accent" })[s] || "";
  }
  function tierClass(t) { return { "顶会大工程": "tier-big", "新颖占坑": "tier-claim", "理论·position": "tier-pos", "低层级可行": "tier-low" }[t] || ""; }
  // item 5-wiki: complexity_tier is a zh-only fixed enum with no EN map, so the tier legend,
  // filter chips, idea-card badge, and kicker rendered Chinese inside the EN workspace. Map each
  // enum value to an EN label; tierLabel flips only the visible WORD (zh keeps the raw value).
  // The raw value still drives the TIER_ORDER sort + tierClass CSS class + data-tier/data-tfilter.
  var TIER_EN = { "顶会大工程": "top-venue build", "新颖占坑": "novelty claim", "理论·position": "theory / position", "低层级可行": "low-tier feasible" };
  function tierLabel(t) { return L(t, TIER_EN[t] || t); }
  // item 13-wiki: localise the eyebrow's fence / venue tokens so the kicker doesn't mix a
  // localized type word with raw 'core' / 'peer-reviewed' under zh. The raw value still drives
  // metaFor's chips + CSS class; only the eyebrow WORD flips (reuses the core→核心 mapping).
  var FENCE_ZH = { core: "核心", adjacent: "邻接", outside: "排除" };
  var VENUE_ZH = { "peer-reviewed": "同行评审", "preprint-only": "预印本", "preprint": "预印本", "published": "已发表" };
  function fenceLabel(z) { return L(FENCE_ZH[z] || z, z); }
  function venueLabel(v) { return L(VENUE_ZH[v] || v, v); }
  function kickerFor(n) {
    var f = n.fm || {}, bits = [typeLabel(n.type)];
    if (f.fence_zone) bits.push(fenceLabel(f.fence_zone));
    if (f.venue_status) bits.push(venueLabel(f.venue_status));
    else if (n.type === "gap") bits.push(f.novelty_verified ? L("新颖性已验证", "novelty verified") : L("未验证", "unverified"));
    else if (n.type === "direction") bits.push((f.status || "") + " · " + L("探针预算", "budget") + " " + f.probe_budget);
    else if (n.type === "probe") bits.push(f.cost_tier + " · " + (f.status || ""));
    else if (n.type === "goal") bits.push(f.status || "");
    else if (n.type === "idea") bits.push(f.complexity_tier ? tierLabel(f.complexity_tier) : (f.status || ""));
    return bits.join(" · ");
  }

  /* =========================================================================
     6. STATE + NAVIGATION
     ========================================================================= */
  var WS = { curId: "edge-hotspot", curFolder: "papers", pendingSection: null, main: null, filter: "", navStack: [],
    graphView: null,          // item 6(4): remembered { zoom, sl, st, key } across Graph re-entries
    listSort: null, listOrphans: false };   // item 26: library list sort mode + orphan-only filter
  var ORDER = Object.keys(NOTES); // stable folder ordering = declaration order
  function folderNotes(folder) { return ORDER.filter(function (id) { return NOTES[id].folder === folder && !NOTES[id].companion; }); }

  function openNote(id, section) {
    var n = NOTES[id];
    if (!n) { // dangling target: it lives in raw/ but is not compiled — go to Sources
      SB.toast(L("该来源尚未编译(raw/ 待 OCR)", "Not compiled yet (pending OCR in raw/)"));
      SB.setSub("sources"); return;
    }
    // Nav history: a cross-reference jump (wikilink / graph / backlink / ask) is a
    // "non-sibling" move — remember where we came from so the Library back-chevron
    // can pop back (siblings prev/next and folder switches don't push).
    if (WS.curId && WS.curId !== id) { WS.navStack.push({ id: WS.curId, folder: WS.curFolder }); if (WS.navStack.length > 50) WS.navStack.shift(); }
    WS.curId = id; WS.curFolder = n.folder; WS.pendingSection = section || null;
    SB.setSub("library"); // re-renders the whole workspace at the Library sub-view
  }
  function goBack() {
    var prev = WS.navStack.pop(); if (!prev || !NOTES[prev.id]) return;
    WS.curId = prev.id; WS.curFolder = prev.folder; WS.pendingSection = null;
    SB.setSub("library");
  }
  // Delegate clicks on any [[wikilink]] inside a rendered article/panel.
  function wireLinks(root) {
    root.addEventListener("click", function (e) {
      var a = e.target.closest(".wl"); if (!a) return;
      e.preventDefault(); openNote(a.dataset.id);
    });
  }
  // Hover-preview (R16): on any resolvable [[wikilink]], show a small card with the
  // target's type / title / one-line / first heading — so a link is legible before
  // you commit to the one-way jump. Wired once, document-level; dangling links (not
  // in NOTES) get no card. Peeks NOTES live, so it follows sample↔live automatically.
  function wireHoverPreview() {
    if (SB._wikiHoverWired) return; SB._wikiHoverWired = true;
    var pop = null, hideT = null;
    function kill() { clearTimeout(hideT); if (pop) { pop.remove(); pop = null; } }
    document.addEventListener("mouseover", function (e) {
      var a = e.target.closest && e.target.closest(".wl[data-id]"); if (!a) return;
      var n = NOTES[a.dataset.id];
      clearTimeout(hideT); if (pop) pop.remove();
      pop = el("div", "wiki-hovercard");
      if (!n) {
        // 19b: a dangling link (target not compiled). Give it its own card and pull the
        // raw/ SOURCES row if the source is registered, so the hover explains the state.
        var sr = sourceRow(a.dataset.id);
        pop.classList.add("dangling");
        pop.innerHTML =
          '<div class="wh-type wh-dang">' + esc(L("未编译 · dangling", "not compiled · dangling")) + "</div>" +
          '<div class="wh-title">' + esc(a.dataset.id) + "</div>" +
          '<div class="wh-line">' + esc(L("尚未编译 —— raw/ 待 OCR", "Not compiled yet — pending OCR in raw/")) + "</div>" +
          (sr ? '<div class="wh-h">' + esc(sr.file + " · " + sr.ocr + (sr.note ? " · " + sr.note : "")) + "</div>" : "");
      } else {
        var firstH = (String(n.body || "").match(/^##\s+(.+)$/m) || [])[1] || "";
        pop.innerHTML =
          '<div class="wh-type">' + esc(typeLabel(n.type) + (n.fm && n.fm.fence_zone ? " · " + n.fm.fence_zone : "")) + "</div>" +
          '<div class="wh-title">' + esc(n.title || a.dataset.id) + "</div>" +
          (n.oneLine ? '<div class="wh-line">' + esc(n.oneLine) + "</div>" : "") +
          (firstH ? '<div class="wh-h">§ ' + esc(firstH) + "</div>" : "");
      }
      document.body.appendChild(pop);
      var r = a.getBoundingClientRect();
      var left = Math.max(8, Math.min(r.left, window.innerWidth - pop.offsetWidth - 12));
      var top = r.bottom + 8;
      if (top + pop.offsetHeight > window.innerHeight - 8) top = Math.max(8, r.top - pop.offsetHeight - 8);
      pop.style.left = left + "px"; pop.style.top = top + "px";
      requestAnimationFrame(function () { if (pop) pop.classList.add("show"); });
    }, true);
    document.addEventListener("mouseout", function (e) {
      var a = e.target.closest && e.target.closest(".wl[data-id]"); if (!a) return;
      hideT = setTimeout(kill, 130);
    }, true);
    document.addEventListener("scroll", kill, true);
  }

  /* =========================================================================
     7. SUB-VIEW: LIBRARY — the reader + the signature DUAL RAIL
     ========================================================================= */
  // Left-rail glosses — the insider folder taxonomy in one plain line on hover (R11).
  // A FUNCTION (not a frozen object): L() must re-evaluate every render so the
  // tooltip follows the 中/EN toggle instead of freezing to the load-time lang (R8).
  function folderGloss(folder) {
    return ({
      papers: L("论文笔记:每篇入库论文的结构化阅读卡", "papers: one structured reading note per compiled paper"),
      concepts: L("概念综合:跨多篇论文的方法脉络", "concepts: cross-paper method synthesis"),
      gaps: L("缺口:已验证的新颖种子(可开 idea)", "gaps: verified novelty seeds (spawn ideas)"),
      ideas: L("灵感卡:大胆假设 + 当前可断言 + 实验台账", "ideas: bold hypothesis + assertable-now + experiment ledger"),
      directions: L("方向卡:立卡前的探索(PROBING)", "directions: pre-idea exploration (PROBING)"),
      probes: L("探针:预注册的廉价实验,只给方向信号", "probes: preregistered cheap experiments — signal only"),
      "field/problems": L("goal 卡:六件套能力缺口(采纳自 problems.md)", "goal cards: adopted capability gaps"),
      field: L("field 图:假设 / 张力 / 饱和度等高空视图", "field maps: assumptions / tensions / saturation"),
      novelty: L("既判力台账 + 正向迁移燃料(严格分离)", "novelty ledger + forward-transfer fuel (kept separate)")
    })[folder];
  }
  function sidebarEl() {
    // Chrome labels localise (R8); folder path headers ("wiki/") stay literal.
    var groups = [
      { h: "wiki/", rows: [["papers", L("论文", "papers")], ["concepts", L("概念", "concepts")], ["gaps", L("缺口", "gaps")], ["ideas", L("灵感", "ideas")], ["directions", L("方向", "directions")], ["probes", L("探针", "probes")]] },
      { h: L("领域 / 目标", "field / goals"), rows: [["field/problems", L("目标", "goals")], ["field", L("领域图", "field maps")]] },
      { h: L("新颖性", "novelty"), rows: [["novelty", L("台账 · 燃料", "ledger · fuel")]] }
    ];
    var s = el("div");
    var html = "";
    groups.forEach(function (g) {
      html += '<div class="side-sec"><div class="side-h">' + esc(g.h) + "</div>";
      g.rows.forEach(function (r) {
        var folder = r[0], label = r[1], cnt = folderNotes(folder).length;
        var ico = TYPE_ICON[({ papers: "paper", concepts: "concept", gaps: "gap", ideas: "idea", directions: "direction", probes: "probe", "field/problems": "goal", field: "field", novelty: "novelty" })[folder]] || "i-note";
        html += '<div class="side-row' + (WS.curFolder === folder ? " sel" : "") + '" data-folder="' + esc(folder) + '" title="' + esc(folderGloss(folder) || label) + '">' +
          '<svg class="i ico"><use href="#' + ico + '"/></svg><span class="lbl">' + esc(label) + "</span>" +
          '<span class="cnt" title="' + esc(cnt + L(" 篇笔记", " notes")) + '">' + cnt + "</span></div>";
      });
      html += "</div>";
    });
    s.innerHTML = html;
    s.addEventListener("click", function (e) {
      var row = e.target.closest("[data-folder]"); if (!row) return;
      WS.curFolder = row.dataset.folder; WS.filter = ""; // new folder context = fresh filter
      var first = folderNotes(WS.curFolder)[0]; if (first) WS.curId = first;
      SB.setSub("library");
    });
    return s;
  }
  // Case-insensitive, CJK-friendly substring match over title + one-line summary
  // + the id/slug (the corpus pairs Chinese titles with English slugs, so matching
  // the slug lets English queries like "budget" find 内容感知功率停火 notes).
  function noteMatches(n, q) {
    if (!q) return true;
    // 19a: also search the note body so a query that only appears in the prose still hits.
    return (((n.title || "") + " " + (n.oneLine || "") + " " + (n.id || "") + " " + (n.body || "")) + "").toLowerCase().indexOf(q) >= 0;
  }
  // 19a: when q hit ONLY the body (not title / one-line / id), surface a little body
  // snippet under the row so the match is explained rather than looking spurious.
  function bodyMatchSnippet(n, q) {
    if (!q) return "";
    var head = ((n.title || "") + " " + (n.oneLine || "") + " " + (n.id || "")).toLowerCase();
    if (head.indexOf(q) >= 0) return "";
    var body = String(n.body || ""), idx = body.toLowerCase().indexOf(q);
    if (idx < 0) return "";
    var start = Math.max(0, idx - 30);
    var snip = body.slice(start, idx + q.length + 46)
      .replace(/\[\[([^\]]*)\]\]/g, "$1").replace(/[#*`>]/g, "").replace(/\s+/g, " ").trim();
    return (start > 0 ? "…" : "") + snip + "…";
  }
  function entryHTML(n, sel, q) {
    var bl = backlinksOf(n.id).length;
    var bodySnip = bodyMatchSnippet(n, q);
    // item 8: each row is a listbox option in a roving-tabindex model (only the current row is
    // tabbable; j/k/Home/End move focus, Enter opens) — mirrors the inbox + jury docket.
    return '<div class="entry' + (sel ? " sel" : "") + '" data-id="' + esc(n.id) + '" role="option" tabindex="' + (sel ? 0 : -1) + '" aria-selected="' + (sel ? "true" : "false") + '">' +
      '<span class="dot"></span><div class="body">' +
      '<div class="etitle">' + esc(n.title) + "</div>" +
      '<div class="eprev">' + esc(n.oneLine || "") + "</div>" +
      (bodySnip ? '<div class="ematch"><span class="ematch-lbl">' + esc(L("正文命中", "in body")) + "</span> " + esc(bodySnip) + "</div>" : "") +
      '<div class="efoot"><span class="src">' + esc(typeLabel(n.type) + (n.fm && n.fm.fence_zone ? " · " + n.fm.fence_zone : "")) + "</span>" +
      '<span class="bl" title="' + esc(L("反链:指入本笔记的链接数", "backlinks: inbound links")) + '">↩ ' + bl + "</span>" +
      '<span class="date">' + esc(n.date || "") + "</span></div></div></div>";
  }
  // item 26: sort the filtered ids by the current list mode. null = declaration order (default),
  // else Title (alpha) / ↩ Backlinks (inbound desc) / Date (newest first). backlinksOf reused.
  var LIST_SORTS = [null, "title", "backlinks", "date"];
  function sortLabel() {
    return ({ title: L("排序:标题", "Sort: title"), backlinks: L("排序:↩ 反链", "Sort: ↩ backlinks"), date: L("排序:日期", "Sort: date") })[WS.listSort] ||
      L("排序:原序", "Sort: default");
  }
  function sortIds(ids) {
    var mode = WS.listSort; if (!mode) return ids;   // default = current declaration order
    var a = ids.slice();
    if (mode === "title") a.sort(function (x, y) { return cleanTitle(NOTES[x].title).localeCompare(cleanTitle(NOTES[y].title)); });
    else if (mode === "backlinks") a.sort(function (x, y) { return (backlinksOf(y).length - backlinksOf(x).length) || cleanTitle(NOTES[x].title).localeCompare(cleanTitle(NOTES[y].title)); });
    else if (mode === "date") a.sort(function (x, y) { return String(NOTES[y].date || "").localeCompare(String(NOTES[x].date || "")); });
    return a;
  }
  // Rebuild ONLY the scrollable list body (+ meta / clear affordance). Called on
  // every keystroke so the filter input keeps focus — never rebuild the input.
  function renderListBody(wrap) {
    var q = (WS.filter || "").trim().toLowerCase();
    var listBox = $("#wiki-list", wrap), meta = $("#wiki-filter-meta", wrap), clr = $(".wiki-clear", wrap);
    if (clr) clr.hidden = !q;
    var ids = folderNotes(WS.curFolder);
    var matched = ids.filter(function (id) { return noteMatches(NOTES[id], q); });
    if (WS.listOrphans) matched = matched.filter(function (id) { return backlinksOf(id).length === 0; });   // item 26: ↩0 only
    var shown = sortIds(matched);
    var html = shown.length
      ? shown.map(function (id) { return entryHTML(NOTES[id], id === WS.curId, q); }).join("")
      : '<div class="wiki-nomatch">' + esc(WS.listOrphans ? L("本文件夹无孤立笔记(↩0)", "No orphan notes (↩0) in this folder") : L("本文件夹无匹配笔记", "No matching note in this folder")) + "</div>";
    // Cross-folder jump-to-note: while filtering, surface matches from OTHER folders
    // so any note is reachable from anywhere (the past-~30-notes scaling path).
    if (q) {
      var cross = ORDER.filter(function (id) {
        var m = NOTES[id]; return m && !m.companion && m.folder !== WS.curFolder && noteMatches(m, q);
      });
      if (cross.length) {
        html += '<div class="wiki-xfolder"><div class="wiki-xfolder-h">' + esc(L("其他文件夹 · " + cross.length + " 条", cross.length + " in other folders")) + "</div>" +
          cross.slice(0, 20).map(function (id) {
            var m = NOTES[id];
            return '<div class="wiki-xrow" data-jump="' + esc(id) + "|" + esc(m.folder) + '" title="' + esc(m.title) + '">' +
              '<span class="wiki-xfld">' + esc(m.folder) + "</span>" +
              '<span class="wiki-xtitle">' + esc(m.title) + "</span></div>";
          }).join("") + "</div>";
      }
    }
    if (listBox) listBox.innerHTML = html;
    if (meta) meta.innerHTML = (q || WS.listOrphans) ? esc(L("显示 " + shown.length + " / " + ids.length + " 篇", shown.length + " / " + ids.length + " shown")) : "";
  }
  // item 26: reflect the sort-mode label + orphan-chip active state without a full rebuild.
  function syncListCtl(wrap) {
    var sb = $("[data-sort]", wrap); if (sb) sb.textContent = sortLabel();
    var ob = $("[data-orphan]", wrap); if (ob) { ob.classList.toggle("on", !!WS.listOrphans); ob.setAttribute("aria-pressed", String(!!WS.listOrphans)); }
  }
  // R31: a compact clickable trail of the multi-hop path (navStack titles + the
  // current note). Each prior segment jumps back to that hop; a single back-button
  // only undoes one step, so this makes a deep traversal legible + reversible.
  function crumbTxt(id) { var n = NOTES[id], t = n ? cleanTitle(n.title) : id; return t.length > 15 ? t.slice(0, 14) + "…" : t; }
  function trailHTML() {
    var st = WS.navStack, start = Math.max(0, st.length - 3), out = [];
    if (start > 0) out.push('<span class="wiki-crumb-more" title="' + esc(L(start + " 个更早的跳转", start + " earlier hops")) + '">…</span>');
    for (var i = start; i < st.length; i++) {
      var e = st[i], n = NOTES[e.id];
      out.push('<button class="wiki-crumb" data-hop="' + i + '" title="' + esc(n ? n.title : e.id) + '">' + esc(crumbTxt(e.id)) + "</button>");
    }
    var cur = NOTES[WS.curId];
    out.push('<span class="wiki-crumb cur" title="' + esc(cur ? cur.title : WS.curId) + '">' + esc(crumbTxt(WS.curId)) + "</span>");
    return out.join('<span class="wiki-trail-sep">›</span>');
  }
  function listEl() {
    var wrap = el("div", "wiki-libnav");
    var backBtn = WS.navStack.length
      ? '<button class="wiki-back" data-back="1" title="' + esc(L("返回上一篇", "Back to previous note")) + '"><svg class="i sm"><use href="#i-arrow-left"/></svg></button>'
      : "";
    wrap.innerHTML =
      '<div class="wiki-filter">' +
        '<div class="wiki-filter-row">' + backBtn +
          '<label class="wiki-search"><svg class="i sm wiki-search-i"><use href="#i-search"/></svg>' +
          '<input type="text" id="wiki-filter-in" class="wiki-filter-in" autocomplete="off" spellcheck="false" ' +
          'aria-label="' + esc(L("筛选笔记", "Filter notes")) + '" placeholder="' + esc(L("筛选笔记…标题 / 摘要", "Filter notes… title / summary")) + '">' +
          '<button class="wiki-clear" data-clear="1" title="' + esc(L("清空", "Clear")) + '" aria-label="' + esc(L("清空筛选", "Clear filter")) + '" hidden>×</button></label>' +
        '</div>' +
        (WS.navStack.length ? '<div class="wiki-trail">' + trailHTML() + '</div>' : '') +
        // item 26: sort toggle (cycles order) + orphan-only (↩0) filter chip
        '<div class="wiki-listctl">' +
          '<button type="button" class="wiki-sort" data-sort title="' + esc(L("切换排序方式:原序 / 标题 / ↩ 反链 / 日期", "cycle sort: default / title / ↩ backlinks / date")) + '">' + esc(sortLabel()) + "</button>" +
          '<button type="button" class="wiki-orphan-chip' + (WS.listOrphans ? " on" : "") + '" data-orphan aria-pressed="' + (WS.listOrphans ? "true" : "false") + '" title="' + esc(L("只看孤立笔记(无反链 ↩0)", "show only orphan notes (no backlinks, ↩0)")) + '">↩0 ' + esc(L("孤立", "orphans")) + "</button>" +
        '</div>' +
        '<div class="wiki-filter-meta" id="wiki-filter-meta"></div>' +
      '</div>' +
      '<div class="list" id="wiki-list" role="listbox" aria-label="' + esc(L("笔记列表", "note list")) + '"></div>';
    var input = $("#wiki-filter-in", wrap);
    if (input) {
      input.value = WS.filter || "";
      input.addEventListener("input", function () { WS.filter = input.value; renderListBody(wrap); });
      input.addEventListener("keydown", function (e) { if (e.key === "Escape") { input.value = ""; WS.filter = ""; renderListBody(wrap); } });
    }
    renderListBody(wrap);
    wrap.addEventListener("click", function (e) {
      if (e.target.closest("[data-back]")) { goBack(); return; }
      var hop = e.target.closest("[data-hop]"); if (hop) {   // R31: jump back to any hop in the trail
        var i = +hop.dataset.hop, tgt = WS.navStack[i];
        if (tgt && NOTES[tgt.id]) { WS.navStack = WS.navStack.slice(0, i); WS.curId = tgt.id; WS.curFolder = tgt.folder; WS.pendingSection = null; SB.setSub("library"); }
        return;
      }
      if (e.target.closest("[data-clear]")) { WS.filter = ""; var i = $("#wiki-filter-in", wrap); if (i) { i.value = ""; i.focus(); } renderListBody(wrap); return; }
      // item 26: cycle sort order / toggle orphan-only filter (in place, list keeps its scroll)
      if (e.target.closest("[data-sort]")) { WS.listSort = LIST_SORTS[(LIST_SORTS.indexOf(WS.listSort) + 1) % LIST_SORTS.length]; renderListBody(wrap); syncListCtl(wrap); return; }
      if (e.target.closest("[data-orphan]")) { WS.listOrphans = !WS.listOrphans; renderListBody(wrap); syncListCtl(wrap); return; }
      var jr = e.target.closest("[data-jump]"); if (jr) { WS.filter = ""; openNote(jr.dataset.jump.split("|")[0]); return; }
      var r = e.target.closest(".entry[data-id]"); if (r) { WS.curId = r.dataset.id; SB.setSub("library"); }
    });
    // item 8: roving-tabindex keyboard model over the note rows (mirrors the inbox + jury docket).
    // Delegated on wrap so it survives renderListBody swapping #wiki-list's innerHTML.
    wrap.addEventListener("keydown", function (e) {
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      var row = e.target.closest && e.target.closest("#wiki-list .entry[data-id]"); if (!row) return;
      var rows = $$("#wiki-list .entry[data-id]", wrap); if (!rows.length) return;
      var k = e.key, idx = rows.indexOf(row), to = idx;
      if (k === "j" || k === "ArrowDown") to = idx + 1;
      else if (k === "k" || k === "ArrowUp") to = idx - 1;
      else if (k === "Home") to = 0;
      else if (k === "End") to = rows.length - 1;
      else if (k === "Enter") { e.preventDefault(); e.stopPropagation(); WS.curId = row.dataset.id; SB.setSub("library"); return; }
      else return;
      e.preventDefault(); e.stopPropagation();
      to = Math.max(0, Math.min(rows.length - 1, to));
      var t = rows[to]; if (!t) return;
      rows.forEach(function (x) { x.tabIndex = -1; });   // roving: only the focused row is tabbable
      t.tabIndex = 0; t.focus();
      if (t.scrollIntoView) t.scrollIntoView({ block: "nearest" });
    });
    return wrap;
  }
  function railExtraEl(n, fieldRefs) {
    // The lower half of the dual rail beyond computed Backlinks: outbound links,
    // the cited raw/ source, and orphan / dangling lint — the "is this note wired
    // into the graph?" answer.
    var wrap = el("div");
    var out = outboundIds(n);
    // outbound
    var oh = '<div class="rail-sec"><div class="rail-h">' + L("出链 Outbound", "Outbound") + "</div>";
    oh += out.map(function (id) {
      var known = !!NOTES[id];
      return '<a class="rail-link ' + (known ? "wl" : "wl dangling") + '" data-id="' + esc(id) + '">' + esc(id) + (known ? "" : ' <span class="anno">' + L("未编译 · dangling", "not compiled · dangling") + "</span>") + "</a>";
    }).join("") || '<div class="rail-empty">' + L("无出链", "none") + "</div>";
    oh += "</div>";
    // cited source (papers)
    if (n.source_path) oh += '<div class="rail-sec"><div class="rail-h">' + L("引用来源 Cited source", "Cited source") + '</div>' +
      '<a class="rail-link rail-src" data-src="1"><svg class="i sm" style="vertical-align:-2px"><use href="#i-file"/></svg> ' + esc(n.source_path) + '<span class="anno">' + L("raw/ 只读证据 · 点按看 Sources", "raw/ read-only evidence · open Sources") + "</span></a></div>";
    // lint
    var dang = danglingIn(n), orphan = backlinksOf(n.id).length === 0;
    var lint = "";
    if (orphan) lint += '<div class="rail-warn bad">⚠ ' + L("孤立:无任何反链指入", "orphan: no inbound links") + "</div>";
    dang.forEach(function (id) { lint += '<div class="rail-warn stale">⚠ ' + L("断链:", "dangling: ") + "[[" + esc(id) + "]] " + L("无对应笔记", "has no note") + "</div>"; });
    if (!lint) lint = '<div class="rail-ok">✓ ' + L("反链健全,无断链", "linked · no broken refs") + "</div>";
    oh += '<div class="rail-sec"><div class="rail-h">' + L("质检 Lint", "Lint") + "</div>" + lint + "</div>";
    // item 27-wiki(4): the field-map backlinks, sub-grouped under a collapsible header (collapsed
    // by default) so they don't drown the substantive gap/idea/concept refs in the main list.
    var fieldHTML = "";
    if (fieldRefs && fieldRefs.length) {
      fieldHTML = '<div class="rail-sec rail-fieldrefs"><button type="button" class="rail-fieldrefs-h" aria-expanded="false" title="' + esc(L("来自领域图(假设 / 张力 / 饱和度 / 问题)的引用", "references from field maps")) + '">' +
        '<span class="rfr-chev" aria-hidden="true">▸</span>' + L("领域图引用", "Field-map refs") +
        ' <span class="rfr-n">(' + fieldRefs.length + ")</span></button>" +
        '<div class="rail-fieldrefs-body" hidden>' +
        fieldRefs.map(function (fr) {
          return '<a class="rail-link wl" data-id="' + esc(fr.id) + '">' + esc(fr.title) +
            '<span class="anno">' + esc(typeLabel(fr.type)) + "</span></a>";
        }).join("") + "</div></div>";
    }
    wrap.innerHTML = fieldHTML + oh;
    wrap.addEventListener("click", function (e) {
      var fh = e.target.closest(".rail-fieldrefs-h");
      if (fh) {
        var fbody = fh.parentNode.querySelector(".rail-fieldrefs-body"); if (!fbody) return;
        var openNow = !fbody.hidden; fbody.hidden = openNow;
        fh.setAttribute("aria-expanded", String(!openNow));
        var chev = fh.querySelector(".rfr-chev"); if (chev) chev.textContent = openNow ? "▸" : "▾";
        return;
      }
      var s = e.target.closest("[data-src]"); if (s) { SB.setSub("sources"); return; }
      var a = e.target.closest(".wl"); if (a) { openNote(a.dataset.id); }
    });
    return wrap;
  }
  /* item 22 — in-place Translate for a note body ------------------------------
     Corpus bodies are authored in ONE language (mostly zh); under the other UI language they
     stay untranslated. Offer a header toggle that translates the rendered note body block-by-block
     in place via the reading-assistant transport (SB.ai op:'translate'), caches each block per note
     so a re-toggle / re-open is instant, and flips back to the stored original. Shown only when
     (a) the REAL transport is wired (the offline mock returns one fixed sentence for every line) AND
     (b) the body's script differs from the UI language. Mirrors the Spark runs' wireNarrTranslate. */
  var NOTE_TRANS = {};   // note.id -> [translated block text …] (cache per note)
  function wLang() { return (SB.state && SB.state.lang === "en") ? "en" : "zh"; }
  function wHasCJK(s) { return /[㐀-鿿豈-﫿]/.test(String(s == null ? "" : s)); }
  function noteTransLabel(state, zh) {
    if (state === "busy") return zh ? "翻译中…" : "Translating…";
    if (state === "translated") return zh ? "显示原文" : "Show original";
    return zh ? "译成中文" : "Translate → EN";
  }
  function noteTransFailed(full) {
    var s = String(full == null ? "" : full);
    if (!s) return true;
    return s.charAt(0) === "（" || /^\(Reading assistant unavailable/.test(s);
  }
  // Keep the rail TOC labels in step with the (translated / restored) headings.
  function syncTocLabels(article) {
    var shell = article.closest && article.closest(".reader-shell"); if (!shell) return;
    var dock = $(".rail-dock", shell); if (!dock) return;
    var toc = $(".rail-sec", dock); if (!toc) return;   // first rail-sec = section TOC
    var btns = $$(".rail-link", toc), heads = $$("h2,h3", article);
    btns.forEach(function (b, i) { if (heads[i]) b.textContent = heads[i].textContent; });
  }
  function wireNoteTranslate(article, note) {
    if (!article || !note || !SB.ai || !SB.aiTransport) return;   // real transport only, never the mock
    var body = $(".wiki-notebody", article); if (!body) return;
    var blocks = $$("p,li,h2,h3,blockquote,td,th", body).filter(function (b) {
      return b.textContent && b.textContent.trim() && !b.querySelector("p,li,td,th");   // leaf blocks only
    });
    if (!blocks.length) return;
    var zh = wLang() === "zh", target = zh ? "zh" : "en";
    var joined = blocks.map(function (b) { return b.textContent; }).join(" ");
    var mismatch = zh ? !wHasCJK(joined) : wHasCJK(joined);
    if (!mismatch) return;   // note already in the UI language → translating is a no-op
    var origHTML = blocks.map(function (b) { return b.innerHTML; });   // restore target (keeps [[links]] + math)
    var origText = blocks.map(function (b) { return b.textContent; }); // translate source
    var bar = el("div", "wiki-trans-bar");
    var btn = el("button", "btn sm ghost wiki-trans-btn");
    btn.innerHTML = '<svg class="i sm"><use href="#i-globe2"/></svg><span class="wt-lbl"></span>';
    bar.appendChild(btn);
    body.insertBefore(bar, body.firstChild);
    var lbl = $(".wt-lbl", btn);
    function setLabel(state) { lbl.textContent = noteTransLabel(state, zh); }
    var cache = NOTE_TRANS[note.id] || (NOTE_TRANS[note.id] = []);
    var done = cache.length >= blocks.length && blocks.every(function (_, i) { return cache[i] != null; });
    var state = "orig", busy = false;
    setLabel("orig");
    function applyOrig() { blocks.forEach(function (b, i) { b.innerHTML = origHTML[i]; }); syncTocLabels(article); }
    function applyTranslated() { blocks.forEach(function (b, i) { if (cache[i] != null) b.textContent = cache[i]; }); syncTocLabels(article); }
    function translateFrom(i) {
      if (i >= blocks.length) { busy = false; done = true; state = "translated"; setLabel("translated"); btn.disabled = false; syncTocLabels(article); return; }
      if (cache[i] != null) { if (state === "translated") blocks[i].textContent = cache[i]; translateFrom(i + 1); return; }
      SB.ai({ op: "translate", text: origText[i], target_lang: target, ui_lang: wLang() },
        function (chunk, isDone, full) {
          if (!isDone) return;                               // wait for the full block (transport is single-in-flight)
          if (i === 0 && noteTransFailed(full)) {            // unreachable / unconfigured → abort cleanly
            busy = false; state = "orig"; applyOrig(); setLabel("orig"); btn.disabled = false;
            SB.toast(zh ? "翻译暂不可用 —— 在「设置 → 阅读助手」里配置" : "Translation unavailable — set it up in Settings → Reading assistant.");
            return;
          }
          cache[i] = (full && !noteTransFailed(full)) ? full : origText[i];
          if (state === "translated") { blocks[i].textContent = cache[i]; syncTocLabels(article); }
          translateFrom(i + 1);
        });
    }
    btn.onclick = function () {
      if (busy) return;
      if (state === "translated") { state = "orig"; applyOrig(); setLabel("orig"); return; }
      state = "translated";
      if (done) { applyTranslated(); setLabel("translated"); return; }   // cached — instant re-toggle
      busy = true; btn.disabled = true; setLabel("busy"); translateFrom(0);
    };
  }
  function renderLibrary(main) {
    var gen = ++RGEN;
    ensureCorpus().then(function () {
      if (gen !== RGEN) return;
      var n = NOTES[WS.curId] || NOTES[ORDER[0]];
      if (!n) { main.innerHTML = ""; paintBadge(main, !!LIVE); return; }
      Promise.all([bodyOf(n), openBacklinks(n.id)]).then(function (res) {
        if (gen !== RGEN) return;
        // item 27-wiki(4): field-map notes (assumptions / tensions / saturation / problems) link
        // out to many papers, so their backlinks DROWN the substantive gap/idea/concept refs in
        // the rail. Split them off — the substantive ones stay in the main BACKLINKS list; the
        // field-map ones move to a collapsed '领域图引用 (N)' section in railExtra (below).
        var fieldBl = [], mainBl = [];
        (res[1] || []).forEach(function (b) {
          var fn = NOTES[b.from];
          if (fn && fn.type === "field") fieldBl.push(b); else mainBl.push(b);
        });
        var fieldRefs = fieldBl.map(function (b) {
          var fn = NOTES[b.from] || { type: "field" };
          return { id: b.from, title: cleanTitle(fn.title || b.from), type: fn.type };
        });
        var bls = mainBl.map(function (b) {
          // R13: the rail's value is the LINKING CONTEXT, not just the target type.
          // Primary label = the source note's TITLE (slug was opaque); the sub-line
          // prefixes the edge kind + source type (graph-legend vocab: seed · gap,
          // ref · paper) then the hand-written gloss or an extracted snippet.
          var fn = NOTES[b.from] || { type: b.type || "note" };
          var ftype = typeLabel(fn.type);
          // R22: the edge KIND (seed/ref/attack…) is always INFERRED from the two
          // note types, never asserted by the note. When the source note wrote its
          // own cross-ref gloss (annotationFor), that gloss is authoritative — echo
          // it and drop the inferred kind; only fall back to the type-derived guess
          // (+ a context snippet) when the note left no gloss of its own.
          var explicit = cleanAnno(b.anno);
          var anno;
          if (explicit) {
            anno = ftype + " — " + explicit.replace(/^[：:·\-—\s]+/, "");
          } else {
            var snip = snippetFor(fn, n.id).replace(/^[：:·\-—\s]+/, "");
            if (!snip) snip = fmEdgeContext(fn, n.id);   // 19c: front-matter-edge fallback
            anno = edgeKind(fn.type, n.type) + " · " + ftype + (snip ? " — " + snip : "");
          }
          return { label: (fn.title || b.from), anno: anno, onClick: function () { openNote(b.from); } };
        });
        main.innerHTML = "";
        var r = SB.ReaderShell(main, {
          sidebar: sidebarEl(), list: listEl(), rail: "dock",
          reader: {
            kicker: kickerFor(n), title: n.title, meta: metaFor(n),
            // item 22: wrap the note prose in .wiki-notebody so the in-place Translate toggle can
            // scope its block sweep to the body (not the CNR banner / gloss / summary card chrome).
            bodyHTML: cnrBannerHTML() + readerGlossHTML(n) + '<div class="wiki-notebody">' + noteBodyHTML(n) + "</div>",
            backlinksLabel: L("反链", "BACKLINKS") + " · " + bls.length,
            backlinks: bls,
            railExtra: railExtraEl(n, fieldRefs)
          },
          onPrev: function () { navSibling(-1); }, onNext: function () { navSibling(1); }
        });
        WS.lastArticle = r.article;
        wireLinks(r.article);
        wireCnrBanner(r.article);
        wireReaderGloss(r.article);   // item 15: persist the "New here?" dismissal
        wireNoteTranslate(r.article, n);   // item 22: in-place note-body Translate (note lang ≠ UI lang)
        paintBadge(main, !!LIVE);
        // Deep-link scroll (from Ask / graph): jump to the requested section heading.
        if (WS.pendingSection) {
          var want = WS.pendingSection; WS.pendingSection = null;
          requestAnimationFrame(function () {
            $$("h2,h3", r.article).forEach(function (h) { if (h.textContent.indexOf(want) >= 0) h.scrollIntoView({ block: "start" }); });
          });
        }
      });
    });
  }
  function navSibling(d) {
    var ids = folderNotes(WS.curFolder), idx = ids.indexOf(WS.curId);
    var ni = idx + d; if (ni < 0 || ni >= ids.length) return;
    WS.curId = ids[ni]; SB.setSub("library");
  }

  /* =========================================================================
     8. SUB-VIEW: IDEAS — tier-sorted candidates inbox
     ========================================================================= */
  var TIER_ORDER = ["顶会大工程", "新颖占坑", "理论·position", "低层级可行"];
  var THIDE = {};        // complexity_tier → hidden: the tier legend chips filter idea cards (item 29d, mirrors the graph GHIDE toggle)
  function sampleIdeas() {
    return Object.keys(SAMPLE_NOTES).filter(function (id) { return SAMPLE_NOTES[id].folder === "ideas"; }).map(function (id) { return SAMPLE_NOTES[id]; });
  }
  function mapLiveIdea(d) {
    // /api/wiki/ideas row -> the card shape ideaCard renders (dual-column Claim +
    // 实验台账 rows); .tiering.md / .counter.md ride along as raw-md provenance.
    return {
      id: d.id, title: (NOTES[d.id] && NOTES[d.id].title) || d.id,
      fm: { status: d.status, complexity_tier: d.complexity_tier, seed_type: d.seed_type, pitch: d.pitch, venue_targets: d.venue_targets || [] },
      claim: { bold: (d.claim && d.claim.hypothesis) || "", now: (d.claim && d.claim.assertable) || "" },
      ledger: (d.ledger || []).map(function (r) { return { date: r[0] || "", node: r[1] || "", verdict: r[2] || "", action: r[3] || "", link: firstLinkId(r[4]) }; }),
      tiering_md: d.tiering_md, counter_md: d.counter_md
    };
  }
  function renderIdeas(main) {
    var gen = ++RGEN;
    ensureCorpus().then(function (live) {
      if (gen !== RGEN) return;
      if (!live) return paintIdeas(main, sampleIdeas());
      fetchOr("ideas").then(function (d) {
        if (gen !== RGEN) return;
        paintIdeas(main, (d !== SENT && Array.isArray(d) && d.length) ? d.map(mapLiveIdea) : sampleIdeas());
      });
    });
  }
  function paintIdeas(main, ideas) {
    ideas = ideas.slice().sort(function (a, b) { return TIER_ORDER.indexOf(a.fm.complexity_tier) - TIER_ORDER.indexOf(b.fm.complexity_tier); });
    var p = el("div", "pane reveal");
    var html = '<div class="pane-wide">' +
      '<div class="pane-head"><h2>' + L("候选灵感箱", "Ideation candidates") + "</h2>" +
      '<span class="sub">' + L("按 complexity_tier 分档(四档标签,永不打数值分)· 睡一觉醒来 = 评过级的卡 + 可审计台账", "tier-sorted by complexity_tier (four labels, never a numeric score)") + "</span></div>";

    // The canned /wiki-ideate run is a sample-only illustration of the ideator
    // report format; live mode has no such stored stream, so it's shown only there.
    if (!LIVE) html += '<details class="ideate-report"><summary><span class="chip accent">/wiki-ideate</span> ' +
      L("最近一次 ideation 运行 · gap budget-browning-gap", "latest ideation run · gap budget-browning-gap") + "</summary>" +
      '<div class="ideate-body">' + renderMd(IDEATE_REPORT) + "</div></details>";

    // Tier legend — also a live filter (item 29d): each chip toggles the idea cards of that
    // complexity_tier on/off (mirrors the graph legend GHIDE toggle pattern). item 27-wiki(3): each
    // chip carries a LIVE count; a tier with no cards is dimmed + disabled (nothing to filter).
    var tierCount = {};
    ideas.forEach(function (n) { var tt = n.fm && n.fm.complexity_tier; if (tt) tierCount[tt] = (tierCount[tt] || 0) + 1; });
    html += '<div class="tier-legend">' + TIER_ORDER.map(function (t) {
      var c = tierCount[t] || 0;
      return '<button type="button" class="chip ' + tierClass(t) + ' tier-toggle' + (THIDE[t] ? " off" : "") + (c === 0 ? " tier-empty" : "") + '" data-tfilter="' + esc(t) + '" aria-pressed="' + (!THIDE[t]) + '"' + (c === 0 ? " disabled" : "") + ' title="' + esc(c === 0 ? L("该档暂无灵感卡", "no idea cards in this tier") : L("点按筛选该档灵感卡", "toggle idea cards of this tier")) + '">' + esc(tierLabel(t)) + '<span class="tier-cnt">' + c + "</span></button>";
    }).join("") + "</div>";
    if (!ideas.length) html += '<div class="ideas-empty">' + esc(L("尚无灵感卡 —— 从某个缺口运行 /wiki-ideate 生成", "No idea cards yet — run /wiki-ideate on a gap")) + "</div>";

    var ideaById = {};
    ideas.forEach(function (n) { ideaById[n.id] = n; html += ideaCard(n); });
    html += "</div>";
    p.innerHTML = html;
    // item 29d: hide the cards whose tier is toggled off (persisted in THIDE across renders).
    function applyTierFilter() { $$(".idea-card", p).forEach(function (c) { c.style.display = THIDE[c.dataset.tier] ? "none" : ""; }); }
    applyTierFilter();
    p.addEventListener("click", function (e) {
      // item 11: 'Draft this in Spark' — hand the idea to Spark's new-paper form, else clipboard.
      var draft = e.target.closest("[data-draft]");
      if (draft) { e.preventDefault(); sparkDraftIdea(ideaById[draft.dataset.draft]); return; }
      // round8 #2: '直接起跑' — same idea to the shell launch hook (prefill + start), else prefill.
      var launch = e.target.closest("[data-launch]");
      if (launch) { e.preventDefault(); sparkLaunchIdea(ideaById[launch.dataset.launch]); return; }
      // item 29d: a tier chip toggles the visibility of that tier's idea cards.
      var tf = e.target.closest("[data-tfilter]");
      if (tf) {
        var tt = tf.dataset.tfilter; THIDE[tt] = !THIDE[tt];
        tf.classList.toggle("off", !!THIDE[tt]); tf.setAttribute("aria-pressed", String(!THIDE[tt]));
        applyTierFilter(); return;
      }
      var a = e.target.closest(".wl"); if (a) { e.preventDefault(); openNote(a.dataset.id); return; }
      var op = e.target.closest("[data-open]"); if (op) { openNote(op.dataset.open); }
    });
    prependCnr($(".pane-wide", p) || p);
    main.innerHTML = "";
    main.appendChild(p);
    paintBadge(main, !!LIVE);
  }
  // round8 #1: build the {title,hypothesis,direction} handoff from EITHER the live /api/wiki
  // adapter shape ({id, pitch, claim:{hypothesis}}) OR the inline-sample card shape
  // ({title, fm:{pitch}, claim:{bold}}) — so wiki→spark works on real ideas without retyping.
  function ideaHandoff(n) {
    return {
      title: (n && (n.title || n.id || n.heading)) || "",
      hypothesis: (n && n.claim && (n.claim.hypothesis || n.claim.bold)) || "",
      direction: (n && (n.pitch || (n.fm && n.fm.pitch))) || ""
    };
  }
  // item 11: prefill Spark's new-paper form from a SCORED idea (guarded interlock);
  // fall back to clipboard + toast when Spark hasn't wired SB.sparkDraft.
  function sparkDraftIdea(n) {
    if (!n) return;
    var payload = ideaHandoff(n);
    if (SB.sparkDraft) { SB.sparkDraft(payload); return; }
    var txt = payload.title + (payload.hypothesis ? "\n\n" + payload.hypothesis : "") + (payload.direction ? "\n\n" + payload.direction : "");
    try { if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(txt); } catch (e) {}
    SB.toast(L("Spark 未就绪 · 已复制灵感到剪贴板", "Spark not ready — idea copied to clipboard"));
  }
  // round8 #2: '直接起跑 / Launch in Spark' — prefer the shell's SB.sparkLaunch (prefill AND,
  // when safe, actually start a run), handed the SAME reconciled payload; degrade to prefill-
  // only via SB.sparkDraft + a toast when the shell hasn't wired the launch hook.
  function sparkLaunchIdea(n) {
    if (!n) return;
    if (SB.sparkLaunch) { SB.sparkLaunch(ideaHandoff(n)); return; }
    sparkDraftIdea(n);   // no launch hook — fall back to prefill-only (may itself toast)
    if (SB.sparkDraft) SB.toast(L("直接起跑未就绪 · 已在 Spark 预填,请手动开跑", "Launch not ready — prefilled in Spark; start it manually"));
  }
  function ideaCard(n) {
    var f = n.fm, t = f.complexity_tier;
    var led = (n.ledger || []);
    var strip = led.length ? '<div class="ledger-strip">' + led.map(function (r) {
      return '<div class="lg-cell ' + (r.verdict === "pass" ? "ok" : "") + '"><span class="lg-d">' + esc(r.date) + '</span><span class="lg-n">' + esc(r.node) + '</span>' +
        '<span class="lg-v">' + esc(r.verdict) + "</span>" + (r.link ? '<a class="wl lg-x" data-id="' + esc(r.link) + '">[[' + esc(r.link) + "]]</a>" : "") + "</div>";
    }).join("") + "</div>" : '<div class="ledger-empty">' + L("实验台账:尚无节点(DRAFT)", "ledger: no nodes yet (DRAFT)") + "</div>";

    // In live mode ignore the sample TIERING/COUNTER maps (their ids can collide
    // with a real idea's id) — use the note's own .tiering.md / .counter.md instead.
    var tierRec = !LIVE && TIERING[n.id], counter = !LIVE && COUNTER[n.id];
    var prov = "";
    if (tierRec) prov += '<details class="prov"><summary>▸ ' + L("为何评这档(tiering.md · 四问)", "why rated (tiering.md)") + '</summary><div class="prov-b">' + tieringHTML(tierRec) + "</div></details>";
    else if (n.tiering_md) prov += '<details class="prov"><summary>▸ ' + L("为何评这档(tiering.md · 四问)", "why rated (tiering.md)") + '</summary><div class="prov-b tiering-raw">' + renderMd(n.tiering_md) + "</div></details>";
    if (counter) prov += '<details class="prov"><summary>▸ ' + L("为何留活 / 反方(counter.md)", "why kept alive (counter.md)") + '</summary><div class="prov-b">' +
      '<p class="cnt-obj"><strong>' + L("反方", "objection") + '</strong> · ' + inlineMd(counter.objection) + "</p>" +
      '<p class="cnt-keep"><strong>' + L("留活", "kept alive") + '</strong> · ' + inlineMd(counter.keepalive) + "</p></div></details>";
    else if (n.counter_md) prov += '<details class="prov"><summary>▸ ' + L("为何留活 / 反方(counter.md)", "why kept alive (counter.md)") + '</summary><div class="prov-b tiering-raw">' + renderMd(n.counter_md) + "</div></details>";

    // item 11 / round8 #2: a SCORED idea is ready to become a paper — offer a one-tap handoff
    // into Spark. Two affordances: '在 Spark 起草' (prefill only, SB.sparkDraft) and '直接起跑'
    // (prefill + actually start when the shell wired SB.sparkLaunch). Only on SCORED cards.
    var draftBtn = (f.status === "SCORED")
      ? '<div class="idea-actions">' +
          '<button type="button" class="btn sm idea-draft" data-draft="' + esc(n.id) + '" title="' + esc(L("把这条灵感填进 Spark 新论文表单", "prefill the Spark new-paper form from this idea")) + '"><svg class="i sm"><use href="#i-flask"/></svg>' + esc(L("在 Spark 起草", "Draft this in Spark")) + "</button>" +
          '<button type="button" class="btn sm primary idea-launch" data-launch="' + esc(n.id) + '" title="' + esc(L("预填并在可行时直接开跑 Spark(否则退回预填)", "prefill and, when safe, actually start a Spark run (else prefill only)")) + '"><svg class="i sm"><use href="#i-play"/></svg>' + esc(L("直接起跑", "Launch in Spark")) + "</button>" +
        "</div>"
      : "";

    return '<div class="idea-card" data-tier="' + esc(t) + '" data-open="' + esc(n.id) + '">' +
      '<div class="idea-head"><span class="chip ' + tierClass(t) + '">' + esc(tierLabel(t)) + '</span>' +
        '<span class="chip ' + statusClass(f.status) + '">' + esc(f.status) + "</span>" +
        (f.seed_type ? '<span class="chip">' + esc(f.seed_type) + "</span>" : "") +
        '<span class="idea-venue">' + esc((f.venue_targets || []).join(" / ")) + "</span></div>" +
      '<h3 class="idea-title wl" data-id="' + esc(n.id) + '">' + esc(n.title) + "</h3>" +
      '<p class="idea-pitch">' + inlineMd(f.pitch || "") + "</p>" +
      '<div class="claim-cols">' +
        '<div class="claim-col bold"><div class="cc-h">' + esc(L("大胆假设", "Bold hypothesis")) + "</div>" + inlineMd(n.claim.bold) + "</div>" +
        '<div class="claim-col now"><div class="cc-h">' + esc(L("当前可断言", "Assertable now")) + "</div>" + inlineMd(n.claim.now) + "</div>" +
      "</div>" +
      '<div class="ledger-h">' + L("实验台账", "experiment ledger") + "</div>" + strip +
      draftBtn + prov + "</div>";
  }
  function tieringHTML(t) {
    var h = '<div class="tier-wl"><strong>' + L("输入白名单", "input whitelist") + "</strong>: " + t.whitelist.map(esc).join(" · ") + "</div>" +
      '<div class="tier-unread">' + esc(t.unread) + "</div>" +
      '<div class="tier-four"><strong>' + L("interest 四问(非空即算数,不打分)", "interest four-questions") + "</strong>" +
      t.four.map(function (q) { return '<div class="fq"><span class="fq-m ' + (q[1] ? "ok" : "bad") + '">' + (q[1] ? "✔" : "✘") + "</span><span class=\"fq-k\">" + esc(q[0]) + "</span><span class=\"fq-t\">" + inlineMd(q[2]) + "</span></div>"; }).join("") + "</div>" +
      '<div class="tier-exec"><strong>' + L("执行五维", "execution dims") + "</strong>" + t.exec.map(function (e) { return '<div class="ex"><span class="ex-k">' + esc(e[0]) + "</span><span class=\"ex-v\">" + esc(e[1]) + "</span></div>"; }).join("") + "</div>" +
      '<div class="tier-conc"><strong>⇒ </strong>' + inlineMd(t.conclusion) + "</div>" +
      '<div class="tier-why">' + inlineMd(t.why) + "</div>";
    return h;
  }
  // The ideator streams this report format before codifying idea cards.
  var IDEATE_REPORT = R`### Constraint map
预算内保留 · 实时控温回路 $O(1)$ 可算 · 不破坏 [[maillard-tiling]] 融合回路 · 免重标定优先。

### Method landscape
| 方法族 | wiki 出处 | 覆盖 | 未覆盖 |
|---|---|---|---|
| 位置启发式停火 | [[edge-hotspot]] | 免重标定稳定极大幅面 | 不读内容,中部重要网格误停 |
| 先验固定图案 | [[grid-sparse]] | 线性标度大幅面 | 先验固定,漏内容相关热连边 |
| 免逐格热状态 | [[thermal-state]] | 常数状态无逐格闭环 | 放弃精确局部焦斑定位 |

### Untried combinations
- Hypothesis 1 = [[content-aware-browning]]:累计热通量分数 → 预算内 top-B(drop-in idea 卡)。

### Wiki coverage holes
- 缺内容感知功率停火前作 [[hotgrid-oracle]](search-latest #1,待编译)—— 见 Coverage / Sources。

### Self-assessment
conservatism: 中(只在 [w] 证据上占坑,数值留给探针)· coverage: 邻域三篇已裁 · altitude: gap→idea 一跳,未过度外推。`;

  /* =========================================================================
     9. SUB-VIEW: GRAPH — the concept graph (SVG, layered, click to open)
     ========================================================================= */
  var _zoom = 1;
  var GHIDE = { field: true, novelty: true, meta: true };   // node-type → hidden; field/novelty/meta default-hidden so the graph opens on the research spine, not the meta sidecars (item 16). The legend "meta" chip toggles all three back on together (item 6(3)).
  var META_TYPES = ["field", "novelty", "meta"];   // grouped under the single "meta" legend toggle
  var GEHIDE = {};       // edge-KIND → hidden (edge legend chips toggle visibility, R7)
  var GFOCUS = false;    // "focus current note" = dim everything not adjacent to curId
  var _gzoom = null;     // null = fit-to-container; else an explicit zoom factor
  var GVSTRETCH = 1.8;   // vertical spread so the wide/short layout fills the tall pane (R22)
  // Reassign GPOS to a vertically-stretched COPY (never mutate SAMPLE_GPOS, which
  // restoreSampleGraph hands back by reference). Rows spread; columns unchanged.
  function stretchGPOS(k) {
    if (!k || k === 1) return;
    var o = {}; Object.keys(GPOS).forEach(function (id) { o[id] = [GPOS[id][0], Math.round(GPOS[id][1] * k)]; });
    GPOS = o;
  }
  function graphNeighbors(id) {
    var nb = {}; nb[id] = 1;
    GEDGES.forEach(function (e) { if (e[0] === id) nb[e[1]] = 1; if (e[1] === id) nb[e[0]] = 1; });
    return nb;
  }
  function shortLabel(id) {
    var m = /^(.*)\.(tiering|counter)$/.exec(id);        // companion nodes: surface the suffix so they don't alias their parent
    if (m) return m[2] + "·" + (m[1].length > 11 ? m[1].slice(0, 10) + "…" : m[1]);
    return id.length > 20 ? id.slice(0, 19) + "…" : id;
  }
  // The graph node's on-canvas label (R12): the HUMAN TITLE, not the raw slug —
  // cleaned of its type prefix and (in graphSVG) wrapped to 2 lines so a node is
  // identifiable without clicking. Companion nodes keep their disambiguating tag.
  function graphLabelFor(id) {
    var m = /^(.*)\.(tiering|counter)$/.exec(id);
    if (m) { var pn = NOTES[m[1]]; return m[2] + "· " + cleanTitle(pn ? pn.title : m[1]); }
    var n = NOTES[id];
    return (n && n.title) ? cleanTitle(n.title) : id;
  }
  function edgeKind(a, b) {
    if (b === "concept") return "synth";
    if (b === "gap") return "seed";
    if (a === "goal") return "attack";
    if (a === "probe" || b === "probe") return "probe";
    if (b === "idea") return "feed";
    return "ref";
  }
  function restoreSampleGraph() { GPOS = SAMPLE_GPOS; GEDGES = SAMPLE_GEDGES; GLABEL = SAMPLE_GLABEL; }
  function applyLiveGraph(g) {
    // item 6(1): a deterministic 2-D layout for the real corpus. The old placement bucketed nodes
    // into type-columns and CENTRED each in a thin band, so a flat corpus (≈one node per type)
    // collapsed onto a single horizontal row — the vertical axis unused, ~60% dead canvas. A pure
    // layered pass can't fix that: with X strictly monotone in the pipeline, a one-node-per-type
    // chain is ALWAYS a straight row. So nodes are ordered by note-type RANK (papers → concept →
    // gap → … → probe, with a few barycentre passes to cluster connected notes) and then laid into
    // a GRID that WRAPS: rows fill the vertical axis while the column count is CAPPED at 6 so a lone
    // outlier can't stretch the graph sideways, and cells (210×116) always exceed the 168×58 node
    // box so nodes never overlap. Rows alternate direction (boustrophedon) to keep a sequential
    // pipeline's edges short. Pure function of the graph (rank + stable id tie-break) → identical
    // every render, so screenshots are stable.
    var RANK = { paper: 0, concept: 1, gap: 2, goal: 3, idea: 4, direction: 5, probe: 6, novelty: 7, field: 8, meta: 9, wiki: 10, note: 10 };
    var byType = {}, ids = [];
    g.nodes.forEach(function (n) {
      if (NOTES[n.id] && NOTES[n.id].companion) return;   // item 16: companions alias their parent
      byType[n.id] = liveNodeType(n.id, n.type); ids.push(n.id);   // item 6(3): ledger/inbox → 'meta'
    });
    var pos = {}, label = {}, X0 = 24, Y0 = 24, N = ids.length;
    if (!N) { GPOS = {}; GEDGES = []; GLABEL = {}; return; }

    var edges = (g.edges || []).filter(function (e) { return byType[e.from] != null && byType[e.to] != null; });
    var adj = {};
    edges.forEach(function (e) { (adj[e.from] = adj[e.from] || []).push(e.to); (adj[e.to] = adj[e.to] || []).push(e.from); });
    function rk(id) { var r = RANK[byType[id]]; return r == null ? 10 : r; }

    // order by (rank, id), then a few barycentre passes reorder within-rank toward the mean
    // sequence-index of each node's neighbours — connected notes end up near each other in the grid.
    var order = ids.slice().sort(function (a, b) { return rk(a) - rk(b) || (a < b ? -1 : a > b ? 1 : 0); });
    var idx = {}; order.forEach(function (id, i) { idx[id] = i; });
    for (var sw = 0; sw < 4; sw++) {
      var key = {};
      order.forEach(function (id) { var nb = adj[id] || [], s = 0, c = 0; for (var i = 0; i < nb.length; i++) { if (idx[nb[i]] != null) { s += idx[nb[i]]; c++; } } key[id] = c ? s / c : idx[id]; });
      order.sort(function (a, b) { return rk(a) - rk(b) || key[a] - key[b] || (a < b ? -1 : a > b ? 1 : 0); });
      order.forEach(function (id, i) { idx[id] = i; });
    }

    // grid: column count capped at 6 (caps horizontal span); rows grow with N (fills the vertical
    // axis). Cells 210×116 > the 168×58 node box, so placement can never overlap.
    var cellW = 210, cellH = 116;
    var cpr = Math.max(2, Math.min(6, Math.round(Math.sqrt(N * 0.7))));
    order.forEach(function (id, s) {
      var row = Math.floor(s / cpr), col = s - row * cpr;
      if (row % 2 === 1) col = cpr - 1 - col;   // boustrophedon: reverse odd rows to shorten chain edges
      pos[id] = [X0 + col * cellW, Y0 + row * cellH]; label[id] = graphLabelFor(id);
    });

    GEDGES = edges.filter(function (e) { return pos[e.from] && pos[e.to]; })
      .map(function (e) { return [e.from, e.to, edgeKind(byType[e.from], byType[e.to])]; });
    GPOS = pos; GLABEL = label;
  }
  // Scale that makes the whole laid-out width fit the scroll container (never
  // upscales past natural) — the default so nothing is clipped on open (R20).
  function fitScale(p) {
    var sc = $(".wgraph-scroll", p), svg = $(".wg-svg", p); if (!sc || !svg) return 1;
    var vb = svg.viewBox.baseVal, availW = sc.clientWidth - 26, availH = sc.clientHeight - 22;
    if (!vb.width || availW <= 0) return 1;
    var sW = availW / vb.width;
    var sH = (vb.height && availH > 0) ? availH / vb.height : sW;
    // item 17: default-fit to HEIGHT so node titles stay legible, and let the wide graph
    // overflow + scroll horizontally in .wgraph-scroll. When width is the binding (smaller)
    // axis, fitting-to-width would shrink labels to ~7px — so never auto-scale below 0.7
    // there; hold 0.7 and scroll sideways instead.
    var s = (sW < sH) ? Math.max(0.7, sH) : sH;
    // item 27-wiki(2): don't clamp the WHOLE-graph scale down to 1.25 — a small live corpus was
    // stranded at 1.25 in a big pane. Allow up to 2.0 (a 168×58 node box → 336×116, still crisp);
    // .wgraph-scroll centres the result (CSS justify-content: safe center) so it isn't top-left.
    return Math.max(.35, Math.min(2.0, s));
  }
  function applyGZoom(p) {
    var svg = $(".wg-svg", p); if (!svg) return;
    var vb = svg.viewBox.baseVal, sc = _gzoom == null ? fitScale(p) : _gzoom;
    svg.setAttribute("width", vb.width * sc); svg.setAttribute("height", vb.height * sc);
  }
  function repaintGraph(p) {
    var sc = $(".wgraph-scroll", p); if (sc) sc.innerHTML = graphSVG();
    applyGZoom(p);
  }
  // item 16: roving focus — make `id` the sole tab stop among the drawn nodes and focus it.
  function focusGraphNode(p, id) {
    var target = null;
    $$(".gnode[data-id]", p).forEach(function (nd) {
      var is = nd.dataset.id === id; nd.setAttribute("tabindex", is ? "0" : "-1"); if (is) target = nd;
    });
    if (target && target.focus) { try { target.focus(); } catch (e) {} }
  }
  // item 16: nearest drawn node in the Arrow direction, by GPOS geometry — the candidate must
  // lie on the requested side; ties break toward the node most aligned with the travel axis.
  function nearestGraphNode(fromId, key, list) {
    var from = GPOS[fromId]; if (!from) return list.length ? list[0].dataset.id : null;
    var fx = from[0], fy = from[1], horiz = (key === "ArrowLeft" || key === "ArrowRight");
    var best = null, bestScore = Infinity;
    for (var i = 0; i < list.length; i++) {
      var id = list[i].dataset.id; if (id === fromId) continue;
      var q = GPOS[id]; if (!q) continue;
      var dx = q[0] - fx, dy = q[1] - fy;
      var ok = key === "ArrowRight" ? dx > 1 : key === "ArrowLeft" ? dx < -1 : key === "ArrowDown" ? dy > 1 : dy < -1;
      if (!ok) continue;
      var along = horiz ? Math.abs(dx) : Math.abs(dy), perp = horiz ? Math.abs(dy) : Math.abs(dx);
      var score = along + perp * 2;
      if (score < bestScore) { bestScore = score; best = id; }
    }
    return best;
  }
  // item 16: announce the live visible node/edge count after a legend toggle for a screen reader.
  function announceGraphCounts(p) {
    if (!SB.announce) return;
    var nn = $$(".gnode[data-id]", p).length, ne = $$(".gedge", p).length;
    SB.announce(L(nn + " 个节点 · " + ne + " 条边 可见", nn + " nodes · " + ne + " edges shown"));
  }
  function renderGraph(main) {
    var gen = ++RGEN;
    ensureCorpus().then(function () {
      if (gen !== RGEN) return;
      var liveGraph = !!(LIVE && LIVE.graph && LIVE.graph.nodes && LIVE.graph.nodes.length);
      if (liveGraph) applyLiveGraph(LIVE.graph);
      else restoreSampleGraph();
      // The hand-placed SAMPLE is short and needs spreading to fill the tall pane (R22); the LIVE
      // grid layout (item 6) already sizes its own rows/columns to the pane, so it must NOT be
      // stretched again or its cells would overshoot into needless vertical scrolling.
      if (!liveGraph) stretchGPOS(GVSTRETCH);
      // item 6(4): remember zoom + scroll across re-entries. Only auto-fit on the FIRST open or
      // when the corpus / dir changes (keyed by source + node count); otherwise restore the last
      // _gzoom + scroll instead of resetting to fit every time.
      var gkey = (LIVE ? "live:" + dirName() : "sample") + ":" + Object.keys(GPOS).length;
      var freshView = !WS.graphView || WS.graphView.key !== gkey;
      if (freshView) WS.graphView = { key: gkey, zoom: null, sl: 0, st: 0 };
      _gzoom = WS.graphView.zoom;   // null → fit-to-container; else the remembered explicit zoom
      var p = el("div", "pane wgraph-pane reveal");
      p.innerHTML = '<div class="pane-head"><h2>' + L("概念图", "Concept graph") +
        "</h2><span class=\"sub\">" + L("节点按类型着色 · 边按种类(综合 / 播种 / 引用 / 攻击面 / 探针 / 回馈)· 图例可开关类型与边种 · 单击选中并高亮邻域,双击 / Enter / ↗ 在 Library 打开", "nodes by type · edges by kind (synth / seed / ref / attack / probe / feed) · legend toggles both · click to select + highlight neighbours; double-click / Enter / ↗ opens in Library") + "</span></div>" +
        graphLegend() +
        '<div class="wgraph"><div class="gzoom"><button data-z="-" title="' + esc(L("缩小", "zoom out")) + '">−</button><button data-z="0" title="' + esc(L("适应容器(按高度铺满,过宽时横向滚动)", "fit to view (fills height; scrolls sideways when wide)")) + '">' + esc(L("适应", "fit")) + '</button><button data-z="+" title="' + esc(L("放大", "zoom in")) + '">+</button></div>' +
        '<div class="wgraph-scroll" tabindex="0" role="region" aria-label="' + esc(L("概念图 · 可滚动画布", "concept graph — scrollable canvas")) + '">' + graphSVG() + "</div></div>";
      p.addEventListener("click", function (e) {
        // node-type legend chip → toggle a node type's visibility (item 16: sync aria-pressed +
        // announce the resulting visible count for a screen reader).
        var gt = e.target.closest("[data-gtype]");
        if (gt) { var t = gt.dataset.gtype; GHIDE[t] = !GHIDE[t]; gt.classList.toggle("off", !!GHIDE[t]); gt.setAttribute("aria-pressed", String(!GHIDE[t])); repaintGraph(p); announceGraphCounts(p); return; }
        // item 6(3): the single "meta" chip toggles ALL meta node-types (field / novelty / meta)
        // together — reveal the sidecar ledgers or hide them back onto the research spine.
        var gm = e.target.closest("[data-gmeta]");
        if (gm) {
          var anyShown = META_TYPES.some(function (mt) { return !GHIDE[mt]; });
          META_TYPES.forEach(function (mt) { GHIDE[mt] = anyShown; });   // any shown → hide all; else show all
          gm.classList.toggle("off", anyShown); gm.setAttribute("aria-pressed", String(!anyShown)); repaintGraph(p); announceGraphCounts(p); return;
        }
        // edge-kind legend chip → toggle that edge kind's visibility (R7). Recoverable:
        // toggling the chip again brings the hidden edges back.
        var get = e.target.closest("[data-getype]");
        if (get) { var ek = get.dataset.getype; GEHIDE[ek] = !GEHIDE[ek]; get.classList.toggle("off", !!GEHIDE[ek]); get.setAttribute("aria-pressed", String(!GEHIDE[ek])); repaintGraph(p); announceGraphCounts(p); return; }
        // focus chip → dim non-neighbours of the current note
        var gf = e.target.closest("[data-gfocus]");
        if (gf) { GFOCUS = !GFOCUS; gf.classList.toggle("on", GFOCUS); gf.setAttribute("aria-pressed", String(GFOCUS)); repaintGraph(p); announceGraphCounts(p); return; }
        // zoom = uniformly resize the SVG viewport (viewBox constant → container scrolls)
        var z = e.target.closest("[data-z]");
        if (z) { var v = z.dataset.z; if (v === "0") { _gzoom = null; } else { var cur = _gzoom == null ? fitScale(p) : _gzoom; _gzoom = Math.max(.4, Math.min(1.8, cur + (v === "+" ? .2 : -.2))); } if (WS.graphView) WS.graphView.zoom = _gzoom; applyGZoom(p); return; }
        // item 19: single-click SELECTS a node — it becomes the current note, GFOCUS pins its
        // neighbourhood highlight (dims non-neighbours), and we STAY in the graph. Opening in
        // Library moved to the per-node ↗ glyph / double-click / Enter-Space. Meta sidecars
        // (no note) keep routing to their sub-view on a plain click.
        var node = e.target.closest("[data-id]");
        if (node) {
          var nid = node.dataset.id;
          var wantOpen = !!e.target.closest("[data-openlib]");   // clicked the ↗ open glyph
          if (wantOpen || (META_NODES[nid] && META_NODES[nid].sub)) {
            if (META_NODES[nid] && META_NODES[nid].sub) SB.setSub(META_NODES[nid].sub); else openNote(nid);
          } else if (NOTES[nid]) {
            WS.curId = nid; GFOCUS = true;                       // select + pin neighbourhood highlight
            var leg = $(".glegend", p); if (leg) leg.outerHTML = graphLegend();   // focus chip now present + "on"
            var gsc = $(".wgraph-scroll", p), gsl = gsc ? gsc.scrollLeft : 0, gst = gsc ? gsc.scrollTop : 0;
            repaintGraph(p);                                     // re-dim; restore scroll so the node stays under the cursor
            focusGraphNode(p, nid);
            if (gsc) { gsc.scrollLeft = gsl; gsc.scrollTop = gst; }
            announceGraphCounts(p);
          }
        }
      });
      // item 19: double-click a node opens it in Library (single-click having only selected it).
      p.addEventListener("dblclick", function (e) {
        var node = e.target.closest(".gnode[data-id]"); if (!node) return;
        e.preventDefault();
        var nid = node.dataset.id;
        if (META_NODES[nid] && META_NODES[nid].sub) SB.setSub(META_NODES[nid].sub); else openNote(nid);
      });
      // A11y (item 6/16): keyboard-activate a focused node (Enter/Space) + Arrow-key roving
      // between nodes using GPOS geometry. Listener on the pane so it survives repaintGraph
      // (which only swaps .wgraph-scroll's innerHTML). Arrows also work from the scroll region
      // itself (before any node is focused), landing on the roving/first node's nearest neighbour.
      p.addEventListener("keydown", function (e) {
        if (e.ctrlKey || e.metaKey || e.altKey) return;
        var inScroll = e.target.closest && e.target.closest(".wgraph-scroll"); if (!inScroll) return;
        var node = e.target.closest(".gnode[data-id]");
        if (node && (e.key === "Enter" || e.key === " " || e.key === "Spacebar")) {
          e.preventDefault(); var nid = node.dataset.id;
          if (META_NODES[nid] && META_NODES[nid].sub) SB.setSub(META_NODES[nid].sub); else openNote(nid); return;
        }
        if (e.key.indexOf("Arrow") === 0) {
          var list = $$(".gnode[data-id]", p); if (!list.length) return;
          var cur = node;
          if (!cur) { for (var i = 0; i < list.length; i++) { if (list[i].getAttribute("tabindex") === "0") { cur = list[i]; break; } } }
          if (!cur) cur = list[0];
          var nextId = nearestGraphNode(cur.dataset.id, e.key, list);
          if (nextId) { e.preventDefault(); focusGraphNode(p, nextId); }
        }
      });
      // Orientation (item 17): hovering a node lights its incident edges + neighbours and
      // fades the rest, reusing the GFOCUS dim vocabulary. Cleared on mouseout.
      function clearGraphHover() {
        $$(".gedge", p).forEach(function (ed) { ed.classList.remove("edge-hot", "edge-mute"); });
        $$(".gnode", p).forEach(function (nd) { nd.classList.remove("node-mute"); });
      }
      p.addEventListener("mouseover", function (e) {
        var node = e.target.closest && e.target.closest(".gnode[data-id]"); if (!node) return;
        var id = node.dataset.id, nb = graphNeighbors(id);
        $$(".gedge", p).forEach(function (ed) {
          var inc = ed.dataset.from === id || ed.dataset.to === id;
          ed.classList.toggle("edge-hot", inc); ed.classList.toggle("edge-mute", !inc);
        });
        $$(".gnode", p).forEach(function (nd) { nd.classList.toggle("node-mute", !nb[nd.dataset.id]); });
      });
      p.addEventListener("mouseout", function (e) {
        var node = e.target.closest && e.target.closest(".gnode[data-id]"); if (!node) return;
        var to = e.relatedTarget;
        if (to && to.closest && to.closest(".gnode[data-id]") === node) return;   // still within same node
        clearGraphHover();
      });
      prependCnr(p);
      main.innerHTML = "";
      main.appendChild(p);
      paintBadge(main, !!LIVE);
      requestAnimationFrame(function () {
        if (gen !== RGEN) return;
        applyGZoom(p);   // fit once laid out
        var sc = $(".wgraph-scroll", p);
        if (!freshView && sc && (WS.graphView.sl || WS.graphView.st)) {
          sc.scrollLeft = WS.graphView.sl; sc.scrollTop = WS.graphView.st;   // item 6(4): restore last scroll
        } else {
          var cur = $(".gnode.gn-current", p);   // item 17: first open → bring the current note into view
          if (cur && cur.scrollIntoView) { try { cur.scrollIntoView({ block: "nearest", inline: "nearest" }); } catch (e) {} }
        }
        // item 6(4): remember scroll position so the next re-entry lands where the user left off
        if (sc) sc.addEventListener("scroll", function () { if (WS.graphView) { WS.graphView.sl = sc.scrollLeft; WS.graphView.st = sc.scrollTop; } });
      });
    });
  }
  // R7: every edge kind, its real stroke (solid vs dash mirrors graphSVG), and a
  // plain-language gloss. One chip per kind — the key is explicit, not a 2-bucket
  // lump — and each chip toggles that kind's visibility (recoverable).
  function edgeLegendKinds() {
    return [
      ["synth",  "solid", L("综合", "synth"),   L("论文汇入概念综合", "papers → concept synthesis")],
      ["seed",   "solid", L("播种", "seed"),    L("为缺口 / 目标 / 灵感播种", "seeds a gap / goal / idea")],
      ["ref",    "dash",  L("引用", "ref"),     L("笔记间交叉引用", "cross-reference between notes")],
      ["attack", "solid", L("攻击面", "attack"), L("目标展开的攻击面", "a goal's attack surface")],
      ["probe",  "solid", L("探针", "probe"),   L("方向派生的探针", "a direction's probe")],
      ["feed",   "dash",  L("回馈", "feed"),    L("探针结果回馈灵感", "a probe feeds an idea")]
    ];
  }
  function graphLegend() {
    // item 6(3): the research-spine types get individual chips; the meta sidecars
    // (field / novelty / meta) fold into ONE "meta" toggle chip appended after them.
    var types = ["paper", "concept", "gap", "idea", "direction", "probe", "goal"];
    var canFocus = !!(WS.curId && GPOS[WS.curId]);
    // item 16: each toggle carries aria-pressed (pressed = the type/kind is SHOWN, focus = on)
    // alongside the visual .off/.on class, so a screen reader hears the toggle state. Kept in
    // sync in the click handlers below.
    var nodeChips = types.map(function (t) { return '<button type="button" class="gl-item gl-toggle' + (GHIDE[t] ? " off" : "") + '" data-gtype="' + t + '" aria-pressed="' + (!GHIDE[t]) + '" title="' + esc(L("点按显示 / 隐藏该类节点", "toggle this node type")) + '"><span class="gl-dot gn-' + t + '"></span>' + esc(typeLabel(t)) + "</button>"; }).join("");
    var metaHidden = META_TYPES.every(function (mt) { return GHIDE[mt]; });
    var metaChip = '<button type="button" class="gl-item gl-toggle' + (metaHidden ? " off" : "") + '" data-gmeta="1" aria-pressed="' + (!metaHidden) + '" title="' + esc(L("元数据 / 侧栏节点(领域图 · 新颖性台账 · /wiki-auto 台账)—— 点按整体显示 / 隐藏", "meta / sidecar nodes (field maps · novelty ledger · /wiki-auto ledger) — toggle all together")) + '"><span class="gl-dot gn-meta"></span>' + esc(L("元数据", "meta")) + "</button>";
    var edgeChips = edgeLegendKinds().map(function (k) {
      return '<button type="button" class="gl-item gl-toggle gl-edgetoggle' + (GEHIDE[k[0]] ? " off" : "") + '" data-getype="' + k[0] + '" aria-pressed="' + (!GEHIDE[k[0]]) + '" title="' + esc(k[3] + " · " + L("点按显示 / 隐藏该类边", "toggle this edge kind")) + '"><span class="gl-edge ' + k[1] + ' ge-' + k[0] + '"></span>' + esc(k[2]) + "</button>";
    }).join("");
    return '<div class="glegend">' +
      '<span class="gl-grp-h">' + L("节点", "nodes") + "</span>" + nodeChips + metaChip +
      '<span class="gl-sep"></span><span class="gl-grp-h">' + L("边", "edges") + "</span>" + edgeChips +
      (canFocus ? '<span class="gl-sep"></span><button type="button" class="gl-item gl-focus' + (GFOCUS ? " on" : "") + '" data-gfocus="1" aria-pressed="' + GFOCUS + '" title="' + esc(L("只高亮当前笔记的邻居", "dim all but the current note's neighbours")) + '"><span class="gl-focus-dot"></span>' + L("聚焦当前", "focus current") + "</button>" : "") +
      "</div>";
  }
  function graphSVG() {
    var W = 168, H = 58;   // H bumped for the 2-line title label (R12)
    function cx(id) { return GPOS[id][0] + W; } function cyR(id) { return GPOS[id][1] + H / 2; }
    function lx(id) { return GPOS[id][0]; }
    function nodeType(id) { return META_NODES[id] ? META_NODES[id].type : (NOTES[id] || { type: "note" }).type; }
    function shown(id) { return GPOS[id] && !GHIDE[nodeType(id)]; }   // legend-toggled visibility (R20)
    var nbrs = GFOCUS && WS.curId && GPOS[WS.curId] ? graphNeighbors(WS.curId) : null;
    function dimmed(id) { return nbrs ? !nbrs[id] : false; }
    // viewport spans only the SHOWN nodes (item 6(3)) — default-hidden meta sidecars sitting in
    // a lower row must NOT inflate the canvas into dead space until the "meta" toggle reveals them.
    var maxX = 0, maxY = 0;
    Object.keys(GPOS).forEach(function (id) { if (!shown(id)) return; if (GPOS[id][0] > maxX) maxX = GPOS[id][0]; if (GPOS[id][1] > maxY) maxY = GPOS[id][1]; });
    var TW = maxX + W + 32, TH = maxY + H + 30;
    // edges first (under nodes); an edge is drawn only when BOTH endpoints are shown
    // AND its kind isn't toggled off in the edge legend (R7).
    var edges = GEDGES.filter(function (e) { return shown(e[0]) && shown(e[1]) && !GEHIDE[e[2]]; }).map(function (e) {
      var a = e[0], b = e[1], kind = e[2];
      var x1 = cx(a), y1 = cyR(a), x2 = lx(b), y2 = cyR(b);
      // if target is left of / same as source (back-edges: feed, some ref), bow downward
      var back = x2 <= x1;
      var mx = (x1 + x2) / 2;
      var d;
      if (back) { var dip = 60 + Math.abs(y2 - y1) * .2; d = "M" + x1 + "," + y1 + " C" + (x1 + 50) + "," + (Math.max(y1, y2) + dip) + " " + (x2 - 50) + "," + (Math.max(y1, y2) + dip) + " " + x2 + "," + y2; }
      else d = "M" + x1 + "," + y1 + " C" + mx + "," + y1 + " " + mx + "," + y2 + " " + x2 + "," + y2;
      var dash = (kind === "ref" || kind === "feed") ? "solid" : "flow"; // synth/seed/attack solid-ish
      var cls = "gedge " + (kind === "ref" || kind === "feed" ? "dash" : "solid") + " ge-" + kind + ((dimmed(a) || dimmed(b)) ? " dim" : "");
      // data-from / data-to let the node-hover handler (item 17) light up incident edges.
      return '<path class="' + cls + '" data-from="' + esc(a) + '" data-to="' + esc(b) + '" d="' + d + '" marker-end="url(#wg-arrow)"/>';
    }).join("");
    // nodes (hidden types dropped entirely; companion sidecars excluded so they don't
    // alias their parent — item 16; non-neighbors dimmed in focus mode)
    // item 16: roving-tabindex — exactly ONE node is in the tab order (the current note if it's
    // shown, else the first shown node); the rest are tabindex=-1 and reached via Arrow keys.
    var shownIds = Object.keys(GPOS).filter(function (id) { return shown(id) && !(NOTES[id] && NOTES[id].companion); });
    var rovingId = (WS.curId && shownIds.indexOf(WS.curId) >= 0) ? WS.curId : shownIds[0];
    var nodes = shownIds.map(function (id) {
      var meta = META_NODES[id];
      var n = NOTES[id] || { type: meta ? meta.type : "note" }, x = GPOS[id][0], y = GPOS[id][1];
      var lbl = meta ? metaLabelFor(id) : (GLABEL[id] || id), full = (NOTES[id] && NOTES[id].title) || lbl;
      // Orientation (item 17): inbound-degree drives a "↩N" badge; 0-inbound → dashed grey
      // (gn-orphan); the current note gets an accent ring (gn-current, independent of focus).
      // Meta sidecars carry no backlinks by nature, so they are exempt from the orphan mark.
      var bl = backlinksOf(id).length;
      var cls = "gnode gn-" + n.type + (dimmed(id) ? " dim" : "") + (bl === 0 && !meta ? " gn-orphan" : "") + (id === WS.curId ? " gn-current" : "");
      // A11y (item 6): each node is a focusable button with a spoken label; Enter/Space
      // opens it (keydown handler in renderGraph). Label = human title + type + inbound count.
      var aria = full + " (" + typeLabel(n.type) + ", " + L("反链 ", "backlinks ") + bl + ")";
      // Label = human title, wrapped to 2 lines in a foreignObject so it stays
      // legible + identifiable without a click, in light AND dark (R12). The div
      // uses --ink (high contrast both themes); title attr gives the full text.
      return '<g class="' + cls + '" data-id="' + esc(id) + '" role="button" tabindex="' + (id === rovingId ? "0" : "-1") + '" aria-label="' + esc(aria) + '" transform="translate(' + x + "," + y + ')">' +
        '<rect width="' + W + '" height="' + H + '" rx="9"/>' +
        '<circle class="gn-dot" cx="15" cy="16" r="4.5"/>' +
        '<text class="gn-type" x="26" y="19">' + esc(typeLabel(n.type)) + "</text>" +
        (bl ? '<text class="gn-deg" x="' + (W - 8) + '" y="19" text-anchor="end">↩' + bl + "</text>" : "") +
        '<foreignObject x="10" y="24" width="' + (W - 19) + '" height="' + (H - 30) + '">' +
          '<div xmlns="http://www.w3.org/1999/xhtml" class="gn-label" title="' + esc(full) + '">' + esc(lbl) + "</div>" +
        "</foreignObject>" +
        // item 19: per-node open glyph — single-click selects, this ↗ opens in Library.
        '<text class="gn-open" data-openlib="1" x="' + (W - 6) + '" y="' + (H - 8) + '" text-anchor="end" aria-hidden="true"><title>' + esc(L("在 Library 打开", "Open in Library")) + "</title>↗</text>" +
        "</g>";
    }).join("");
    return '<svg class="wg-svg" width="' + TW + '" height="' + TH + '" viewBox="0 0 ' + TW + " " + TH + '" role="group" aria-label="' + esc(L("概念图", "concept graph")) + '">' +
      '<defs><marker id="wg-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">' +
      '<path d="M0,0 L10,5 L0,10 z" fill="currentColor"/></marker></defs>' +
      '<g id="wg-root">' + edges + nodes + "</g></svg>";
  }

  /* =========================================================================
     10. SUB-VIEW: COVERAGE — saturation heat + problems + tensions + staleness
     ========================================================================= */
  var SAMPLE_SAT = [
    { cls: "crowded", tag: "crowded", title: "标定期控温加速与固定图案近似", pos: "(方法=精确 / 图案回路) × (标定期二次墙)", srcs: ["maillard-tiling", "grid-sparse", "thermal-state"], verdict: "已成熟,新作多工程增量 — 不建议占坑" },
    { cls: "blank", tag: "blank", title: "预算内内容感知功率停火", pos: "(运行期功率停火) × (预算内给哪些网格通电)", srcs: ["edge-hotspot", "thermal-state", "maillard-tiling"], verdict: "EdgeHotspot 只填位置启发式一格,内容打分一格空白 → gap [[budget-browning-gap]]" },
    { cls: "messy", tag: "messy", title: "选择规则是否读内容", pos: "(图案 / 停火规则) × (规则的内容依赖性)", srcs: ["grid-sparse", "edge-hotspot", "thermal-state"], verdict: "固定图案 vs 内容自适应对撞(tension T2)— unification 富矿" }
  ];
  function satFromLive(d) {
    return (d.saturation || []).map(function (s) {
      var body = s.body || "";
      return {
        cls: s.kind, tag: s.kind,
        title: (s.heading || s.kind).replace(/^[^—\-]*[—\-]\s*/, ""),
        pos: (/位置\s*[:：]\s*(.+)/.exec(body) || [])[1] || "",
        srcs: s.sources || [],
        verdict: (/判词\s*[:：]\s*(.+)/.exec(body) || [])[1] || ""
      };
    });
  }
  function probFromLive(d) {
    return (d.problems || []).map(function (p) {
      var text = p.text || "", adopted = (/已采纳\s*[→>]+\s*\[\[\s*([^\]|#]+?)\s*\]\]/.exec(text) || [])[1] || null;
      return { t: text.split(/\s*——\s*/)[0].trim(), src: (p.sources || []).filter(function (id) { return id !== adopted; }), adopted: adopted };
    });
  }
  function tensFromLive(d) {
    return (d.tensions || []).map(function (t) {
      return { id: (/^(\S+)/.exec(t.heading || "") || [])[1] || (t.heading || ""), a: t.side_a || "", b: t.side_b || "", same: t.same_object || "", res: t.resolution_type_guess || "" };
    });
  }
  function assumFromLive(md) {
    var out = [];
    (md || "").split(/\n(?=##\s)/).forEach(function (sec) {
      var hm = /^##\s+(.+)/.exec(sec); if (!hm) return;
      var head = hm[1].trim(), rel = (/relied_by\s*[:：]\s*(.+)/.exec(sec) || [])[1] || "", by = [], reg = /\[\[\s*([^\]|#]+?)\s*\]\]/g, m;
      while ((m = reg.exec(rel))) by.push(m[1].trim());
      out.push({
        id: (/^(\S+)/.exec(head) || [])[1] || "", t: head.replace(/^[^—\-]*[—\-]\s*/, ""), by: by,
        str: (/evidence_strength\s*[:：]\s*(\S+)/.exec(sec) || [])[1] || "",
        cc: (/constraint_class\s*[:：]\s*(\S+)/.exec(sec) || [])[1] || ""
      });
    });
    return out.length ? out : null;
  }
  // item 20: paint a lightweight skeleton (real header + shimmer rows) SYNCHRONOUSLY so Coverage /
  // Sources don't flash blank through their double await (ensureCorpus → fetch). The resolved paint
  // (paintCoverage / paintSources) clears main and swaps the skeleton out.
  function paintWikiSkeleton(main, heading, sub) {
    var card = '<div class="wiki-skel-card"></div>';
    var p = el("div", "pane reveal");
    p.innerHTML = '<div class="pane-wide" aria-busy="true">' +
      '<div class="pane-head"><h2>' + esc(heading) + '</h2><span class="sub">' + esc(sub) + "</span></div>" +
      '<div class="wiki-skel" aria-hidden="true">' +
        '<div class="wiki-skel-bar"></div>' +
        '<div class="grid grid-3">' + card + card + card + "</div>" +
        '<div class="wiki-skel-card tall"></div>' +
        '<div class="wiki-skel-card tall"></div>' +
      "</div></div>";
    main.innerHTML = "";
    main.appendChild(p);
  }
  function renderCoverage(main) {
    var gen = ++RGEN;
    paintWikiSkeleton(main, L("覆盖 / 缺口", "Coverage / gaps"), L("洞在哪:饱和度热图 + 问题积压 + 待解矛盾 + 新鲜度", "where the holes are"));   // item 20
    ensureCorpus().then(function (live) {
      if (gen !== RGEN) return;
      if (!live) return paintCoverage(main, null, null);
      Promise.all([fetchOr("coverage"), bodyOf(NOTES.assumptions)]).then(function (r) {
        if (gen !== RGEN) return;
        paintCoverage(main, r[0] !== SENT && r[0] ? r[0] : null, r[1]);
      });
    });
  }
  function paintCoverage(main, d, assumBody) {
    var p = el("div", "pane reveal");
    var satFm = (NOTES.saturation || { fm: {} }).fm, probFm = (NOTES.problems || { fm: {} }).fm,
      tenFm = (NOTES.tensions || { fm: {} }).fm, asmFm = (NOTES.assumptions || { fm: {} }).fm;
    var maxStale = Math.max(satFm.staleness || 0, probFm.staleness || 0, tenFm.staleness || 0, asmFm.staleness || 0);
    var html = '<div class="pane-wide"><div class="pane-head"><h2>' + L("覆盖 / 缺口", "Coverage / gaps") +
      "</h2><span class=\"sub\">" + L("洞在哪:饱和度热图 + 问题积压 + 待解矛盾 + 新鲜度", "where the holes are") + "</span></div>";

    // saturation heat
    html += '<div class="cov-h">' + L("饱和度图(方法 × 问题)", "Saturation (method × problem)") + '<a class="cov-src wl" data-id="saturation">saturation</a></div>';   // item 15: clean label, not raw [[brackets]]
    // item 29a: an inline key for the three saturation states, so the CROWDED/BLANK/MESSY
    // column tags are self-explaining rather than jargon.
    html += '<div class="cov-legend">' +
      '<span class="cov-lg crowded"><span class="cov-sw"></span>' + L("crowded = 已饱和", "crowded = saturated") + "</span>" +
      '<span class="cov-lg blank"><span class="cov-sw"></span>' + L("blank = 未探索的空白", "blank = unexplored gap") + "</span>" +
      '<span class="cov-lg messy"><span class="cov-sw"></span>' + L("messy = 相互矛盾", "messy = contradictory") + "</span></div>";
    html += '<div class="grid grid-3 sat-grid">' +
      (d ? satFromLive(d) : SAMPLE_SAT).map(function (s) { return satCard(s.cls, s.tag, s.title, s.pos, s.srcs, s.verdict); }).join("") + "</div>";

    // problems backlog + tensions
    html += '<div class="grid grid-2" style="margin-top:20px">';
    html += '<div class="card"><div class="card-h"><span class="kick">problems.md</span><h3>' + L("问题积压(Hamming 式)", "Problem backlog") + "</h3></div>" +
      probBacklog(d ? probFromLive(d) : null) + "</div>";
    html += '<div class="card"><div class="card-h"><span class="kick">tensions.md</span><h3>' + L("待解矛盾", "Contradictions to resolve") + "</h3></div>" +
      tensionList(d ? tensFromLive(d) : null) + "</div>";
    html += "</div>";

    // assumptions (load-bearing beliefs)
    html += '<div class="card" style="margin-top:20px"><div class="card-h"><span class="kick">assumptions.md</span><h3>' + L("载重假设(翻了会怎样)", "Load-bearing assumptions") + "</h3></div>" + assumList(assumBody ? assumFromLive(assumBody) : null) + "</div>";

    // staleness meter
    html += '<div class="card stale-card" style="margin-top:20px"><div class="card-h"><span class="kick">' + L("新鲜度", "freshness") + '</span><h3>' + L("field 图落后多少", "field-map staleness") + "</h3></div>" +
      '<p class="stale-note">' + L("staleness = 库内篇数 − papers_at_zoomout。compile 在 ≥8 触发重绘,ideate 在 ≥12。", "compile re-maps at ≥8, ideate at ≥12.") + "</p>" +
      staleMeter("saturation", satFm.staleness || 0) + staleMeter("tensions", tenFm.staleness || 0) + staleMeter("assumptions", asmFm.staleness || 0) + staleMeter("problems", probFm.staleness || 0) +
      '<div class="stale-verdict ' + (maxStale >= 8 ? "warn" : "ok") + '">' + (maxStale >= 8 ? "⚠ " + L("需要重绘 field 图", "re-map needed") : "✓ " + L("最大 staleness " + maxStale + " < 8,地图新鲜", "max staleness " + maxStale + " < 8 — fresh")) + "</div></div>";

    // R17: corpus-wide link health — every orphan note + every dangling [[ref]], one
    // click from the note that owns it (computed from the same backlinks/dangling scan
    // the per-note rail uses, just aggregated over the whole corpus).
    html += linkHealthHTML();

    html += "</div>";
    p.innerHTML = html;
    p.addEventListener("click", function (e) { var a = e.target.closest(".wl"); if (a) { e.preventDefault(); openNote(a.dataset.id); } });
    prependCnr($(".pane-wide", p) || p);
    main.innerHTML = "";
    main.appendChild(p);
    paintBadge(main, !!LIVE);
  }
  // R21: localise the field-map enum WORDS (display only — the raw value still drives
  // the CSS class + branch logic). EN keeps the machine term (uppercased for the tag
  // eyebrow); ZH gets the plain-language word.
  // item 20: the zh word must MATCH the cov-legend gloss directly above (crowded = 已饱和,
  // blank = 空白, messy = 相互矛盾) — one word per state, not a different synonym.
  function satTagLabel(tag) { return L(({ crowded: "已饱和", blank: "空白", messy: "矛盾" })[tag] || tag, String(tag || "").toUpperCase()); }
  function evStrLabel(s) { return L(({ established: "已确立", assumed: "假设", contested: "有争议" })[s] || s, s); }
  function constraintLabel(c) { return L(({ hard: "硬(约束)", soft: "软(约束)", hidden: "隐含" })[c] || c, c); }
  // items 14+15: coverage wikilink refs used to render the raw [[brackets]] as the visible
  // label AND masqueraded as live links even when the target was never compiled. covRef strips
  // the brackets (matching inlineMd + the rest of the app) and — like the per-note rail /
  // danglingIn — checks NOTES[id]: a target with no compiled note gets the .dangling class + an
  // explicit '未编译 / uncompiled' marker so a dead ref can't pass for a real link. data-id is
  // preserved so the existing .wl click handler still routes.
  function covRef(id) {
    var known = !!NOTES[id];
    return '<a class="wl' + (known ? "" : " dangling") + '" data-id="' + esc(id) + '">' + esc(id) + "</a>" +
      (known ? "" : ' <span class="cov-uncompiled">' + L("未编译", "uncompiled") + "</span>");
  }
  function satCard(cls, tag, title, pos, srcs, verdict) {
    return '<div class="sat-card sat-' + cls + '"><div class="sat-tag">' + esc(satTagLabel(tag)) + "</div>" +
      '<div class="sat-title">' + esc(title) + "</div>" +
      '<div class="sat-pos">' + esc(pos) + "</div>" +
      '<div class="sat-src">' + srcs.map(covRef).join(" ") + "</div>" +
      '<div class="sat-verdict">' + inlineMd(verdict) + "</div></div>";
  }
  function probBacklog(rows) {
    rows = rows || [
      { t: "固定加热功率预算下,让大幅面网格保留由内容而非位置决定", src: ["budget-browning-gap", "bounded-heat-methods"], adopted: "browning-budget" },
      { t: "让有损大幅面热压缩(固定状态 / 功率停火)可事后审计与可解释", src: ["thermal-state", "edge-hotspot"], adopted: null },
      { t: "同一加热功率预算下统一评测「保逐格控温压功率」与「免逐格换热状态」", src: ["bounded-heat-methods", "thermal-state", "edge-hotspot"], adopted: null },
      { t: "把幅面外推(预热外插)与加热功率预算管理放进同一权衡框架", src: ["bounded-heat-methods"], adopted: null }
    ];
    return '<div class="prob-list">' + rows.map(function (r) {
      return '<div class="prob-row"><div class="prob-t">' + esc(r.t) + "</div>" +
        '<div class="prob-f">' + r.src.map(covRef).join(" · ") +
        (r.adopted ? ' <span class="chip ok">' + L("已采纳", "Adopted") + ' → <a class="wl' + (NOTES[r.adopted] ? "" : " dangling") + '" data-id="' + esc(r.adopted) + '" style="color:inherit">' + esc(r.adopted) + "</a></span>" : ' <span class="chip">' + L("候选", "candidate") + "</span>") + "</div></div>";
    }).join("") + "</div>";
  }
  function tensionList(T) {
    T = T || [
      { id: "T1", a: "[[edge-hotspot]] 保逐格控温、只压功率即稳定极大幅面", b: "[[thermal-state]] 放弃逐格控温、固定状态免逐格闭环", same: "大幅面功率 / 算力标度;冲突在是否保留显式逐格控温", res: "适用域不同" },
      { id: "T2", a: "[[grid-sparse]] 先验固定 local+global 图案已够", b: "[[edge-hotspot]] 热点证据:重要性由内容决定,固定图案漏热连边", same: "「保留 / 连接哪些网格」的选择规则;冲突在是否读内容", res: "真矛盾(unification 种子)" }
    ];
    return T.map(function (t) {
      return '<div class="tension"><div class="t-id">' + esc(t.id) + '<span class="chip ' + (t.res.indexOf("真矛盾") >= 0 ? "bad" : "stale") + '">' + esc(t.res) + "</span></div>" +
        '<div class="t-sides"><div class="t-a">A · ' + inlineMd(t.a) + "</div><div class=\"t-b\">B · " + inlineMd(t.b) + "</div></div>" +
        '<div class="t-same">same_object · ' + esc(t.same) + "</div></div>";
    }).join("");
  }
  function assumList(A) {
    A = A || [
      { id: "A1", t: "大幅面瓶颈是传感器读写 / 加热功率,不只是总加热能耗", by: ["maillard-tiling", "edge-hotspot", "thermal-state"], str: "established", cc: "hard" },
      { id: "A2", t: "历史网格重要性高度不均且可压缩", by: ["edge-hotspot", "thermal-state", "grid-sparse"], str: "assumed", cc: "soft" },
      { id: "A3", t: "运行期保留策略可与硬件解耦(免重标定即生效)", by: ["edge-hotspot", "maillard-tiling", "grid-sparse"], str: "contested", cc: "hidden" }
    ];
    return '<div class="assum-list">' + A.map(function (a) {
      var sc = a.str === "established" ? "ok" : a.str === "contested" ? "bad" : "stale";
      return '<div class="assum"><div class="as-h"><span class="as-id">' + esc(a.id) + "</span><span class=\"as-t\">" + esc(a.t) + "</span>" +
        '<span class="chip ' + sc + '">' + esc(evStrLabel(a.str)) + '</span><span class="chip">' + esc(constraintLabel(a.cc)) + "</span></div>" +
        '<div class="as-by">relied_by · ' + a.by.map(covRef).join(" ") + "</div></div>";
    }).join("") + "</div>";
  }
  function staleMeter(name, v) {
    var pct = Math.min(100, v / 8 * 100);
    return '<div class="stale-row"><span class="stale-k">' + esc(name) + '</span><div class="meter ' + (v >= 8 ? "bad" : "") + '" style="flex:1"><i style="width:' + pct + '%"></i></div><span class="stale-v">' + v + " / 8</span></div>";
  }
  // R17: aggregate the per-note lint over the whole corpus. orphan = no inbound link;
  // dangling = a [[ref]] whose target isn't a compiled note. Excludes companions.
  function linkHealth() {
    var orphans = [], dangling = [];
    ORDER.forEach(function (id) {
      var n = NOTES[id]; if (!n || n.companion) return;
      if (backlinksOf(id).length === 0) orphans.push(id);
      danglingIn(n).forEach(function (t) { dangling.push({ from: id, to: t }); });
    });
    return { orphans: orphans, dangling: dangling };
  }
  function linkHealthHTML() {
    var lh = linkHealth();
    var orphRows = lh.orphans.length
      ? lh.orphans.map(function (id) {
        var n = NOTES[id] || {};
        return '<a class="wl lh-row" data-id="' + esc(id) + '"><span class="lh-title">' + esc(n.title || id) + '</span><span class="lh-id">[[' + esc(id) + "]]</span></a>";
      }).join("")
      : '<div class="rail-ok">✓ ' + L("无孤立笔记,每篇都有反链指入", "no orphans — every note has inbound links") + "</div>";
    var dangRows = lh.dangling.length
      ? lh.dangling.map(function (dd) {
        var fn = NOTES[dd.from] || {};
        return '<div class="lh-row lh-dang"><a class="wl lh-from" data-id="' + esc(dd.from) + '">' + esc(fn.title || dd.from) + '</a>' +
          '<span class="lh-arrow">→</span><a class="wl dangling lh-target" data-id="' + esc(dd.to) + '">[[' + esc(dd.to) + "]]</a></div>";
      }).join("")
      : '<div class="rail-ok">✓ ' + L("无断链,所有 [[链接]] 都有对应笔记", "no dangling links — every [[link]] resolves") + "</div>";
    return '<div class="card lh-card" style="margin-top:20px"><div class="card-h"><span class="kick">lint</span><h3>' +
      L("链接健康(全库)", "Link health (corpus-wide)") + "</h3></div>" +
      '<div class="lh-grid">' +
        '<div class="lh-sec"><div class="lh-h">' + L("孤立 · 无反链指入", "Orphans · no inbound links") +
          '<span class="lh-n">' + lh.orphans.length + '</span></div><div class="lh-rows">' + orphRows + "</div></div>" +
        '<div class="lh-sec"><div class="lh-h">' + L("断链 · 指向缺失笔记", "Dangling · link with no target") +
          '<span class="lh-n">' + lh.dangling.length + '</span></div><div class="lh-rows">' + dangRows + "</div></div>" +
      "</div></div>";
  }

  /* =========================================================================
     11. SUB-VIEW: SOURCES — raw/ library (OCR badges) + search-latest import feed
     ========================================================================= */
  var IMPORT_SEL = {};
  function sampleSources() {
    var last = IMPORTLOG[IMPORTLOG.length - 1], m = /(\d+)\s*\/\s*(\d+)/.exec(last[3] || "");
    return { srcs: SOURCES, implog: IMPORTLOG, cands: CANDIDATES, topic: "uniform-browning-control",
      capStr: last[3], capPct: m ? Math.min(100, +m[1] / +m[2] * 100) : 2.5 };
  }
  function mapLiveSources(d) {
    var rows = (d.import_log && d.import_log.rows) || [], sponsorOf = {};
    rows.forEach(function (r) { if (r[1]) sponsorOf[r[1]] = r[2] || ""; });
    var srcs = (d.entries || []).map(function (e) {
      var known = !!NOTES[e.source];
      var file = e.pdf ? e.pdf.split("/").pop() : (e.projectpage ? e.source + " (projectpage)" : e.source);
      var note = known ? "已编译 → wiki/papers/" + e.source + ".md"
        : e.ocr_status === "committed" ? (e.ocr_markdown || "已 OCR committed · 待编译")
          : e.ocr_status === "pending" ? "mineru/" + e.source + "/ 仍是 .pending — 待 OCR、阻断编译"
            : e.ocr_status === "aborted" ? "OCR 批次 aborted — 需重跑" : "仅 projectpage / 待 OCR";
      return { id: e.source, file: file, topic: e.topic, sponsor: sponsorOf[e.source] || "—", ocr: e.ocr_status, note: note };
    });
    var sl = d.search_latest || {}, prio = sl.recommended_priority || [];
    var cands = (sl.candidates || []).map(function (c) {
      return { n: c.n, title: c.title, authors: c.authors, venue: c.venue_year, arxiv: c.arxiv_id, code: c.code, rel: c.relevance, fenced: !!c.fenced, rec: prio.indexOf(c.arxiv_id) >= 0, why: c.why };
    });
    var cap = (d.import_log && d.import_log.cap) || null;
    return { srcs: srcs, implog: rows, cands: cands, topic: (srcs[0] && srcs[0].topic) || "",
      capStr: cap ? cap.n + "/" + cap.of : "", capPct: cap ? Math.min(100, cap.n / cap.of * 100) : 0 };
  }
  function renderSources(main) {
    var gen = ++RGEN;
    paintWikiSkeleton(main, L("来源库", "Sources"), L("raw/ = 只读、append-only 证据 · OCR 门控 · 搜最新 → 勾选导入", "raw/ read-only evidence · OCR-gated · search → import"));   // item 20
    ensureCorpus().then(function (live) {
      if (gen !== RGEN) return;
      if (!live) return paintSources(main, sampleSources());
      fetchOr("sources").then(function (d) {
        if (gen !== RGEN) return;
        paintSources(main, (d !== SENT && d) ? mapLiveSources(d) : sampleSources());
      });
    });
  }
  function paintSources(main, S) {
    IMPORT_SEL = {}; S.cands.forEach(function (c) { IMPORT_SEL[c.arxiv] = c.rec && !c.fenced; });
    var p = el("div", "pane reveal");
    var html = '<div class="pane-wide"><div class="pane-head"><h2>' + L("来源库", "Sources") +
      "</h2><span class=\"sub\">" + L("raw/ = 只读、append-only 证据 · OCR 门控 · 搜最新 → 勾选导入", "raw/ read-only evidence · OCR-gated · search → import") + "</span></div>";

    // raw/ registry
    html += '<div class="card"><div class="card-h"><span class="kick">raw/' + esc(S.topic || "") + '/</span><h3>' + L("入库登记 + OCR 状态", "Registry + OCR status") + "</h3></div>" +
      '<div class="src-list">' + (S.srcs.length ? S.srcs.map(function (s) {
        var known = !!NOTES[s.id];
        return '<div class="src-row">' +
          '<span class="ocr ocr-' + s.ocr + '"><span class="ocr-dot"></span>' + esc(s.ocr) + "</span>" +
          '<div class="src-mid"><div class="src-file">' + esc(s.file) + (known ? ' <a class="wl src-link" data-id="' + esc(s.id) + '">→ wiki/papers/' + esc(s.id) + ".md</a>" : ' <span class="chip stale">' + L("未编译", "not compiled") + "</span>") + "</div>" +
          '<div class="src-note">' + esc(s.note) + "</div></div>" +
          '<span class="chip">' + esc(s.sponsor) + "</span></div>";
      }).join("") : '<div class="rail-empty">' + L("raw/ 无登记来源", "no registered sources") + "</div>") + "</div></div>";

    // search-latest import feed
    html += '<div class="card" style="margin-top:20px"><div class="card-h"><span class="kick">/wiki-search-latest</span><h3>' + L("导入队列 · 候选表", "Import feed · candidates") + "</h3>" +
      '<span class="sub" style="margin-left:auto">' + L("累计上限", "cap") + " " + esc(S.capStr) + "</span></div>" +
      '<div class="cap-meter meter"><i style="width:' + S.capPct + '%"></i></div>' +
      '<div class="feed-table">' +
      '<div class="feed-row feed-head"><span class="fc-x"></span><span class="fc-n">#</span><span class="fc-t">' + L("标题", "title") + "</span><span class=\"fc-v\">venue</span><span class=\"fc-a\">arXiv</span><span class=\"fc-r\">rel</span></div>" +
      (S.cands.length ? S.cands.map(function (c) {
        var checked = IMPORT_SEL[c.arxiv];
        return '<div class="feed-row' + (c.fenced ? " fenced" : "") + (c.rec ? " rec" : "") + '" data-arxiv="' + esc(c.arxiv) + '">' +
          '<span class="fc-x">' + (c.fenced ? '<span class="fence-tag">[FENCE]</span>' : '<span class="cbx' + (checked ? " on" : "") + '" data-cbx="' + esc(c.arxiv) + '"></span>') + "</span>" +
          '<span class="fc-n">' + esc(c.n) + "</span>" +
          '<span class="fc-t"><span class="ft-title">' + esc(c.title) + '</span><span class="ft-why">' + inlineMd(c.why || "") + "</span></span>" +
          '<span class="fc-v">' + esc(c.venue) + "</span>" +
          '<span class="fc-a">' + esc(c.arxiv) + " · " + esc(c.code) + "</span>" +
          '<span class="fc-r"><span class="chip ' + (c.rel === "high" ? "ok" : c.rel === "low" ? "stale" : "") + '">' + esc(c.rel) + "</span>" + (c.rec ? '<span class="chip accent">rec</span>' : "") + "</span></div>";
      }).join("") : '<div class="rail-empty">' + L("无搜索候选(search-latest.json 缺失)", "no candidates (search-latest.json absent)") + "</div>") + "</div>" +
      '<div class="feed-foot"><button class="btn primary sm" data-import>' + L("导入选中 → fetch · OCR · compile", "Import selected → fetch · OCR · compile") + '</button>' +
      '<span class="feed-hint">' + L("[FENCE] 行在 scope 排除范围内,禁用、永不自动导入", "[FENCE] rows are out-of-scope, disabled") + "</span></div></div>";

    // IMPORT-LOG history
    html += '<div class="card" style="margin-top:20px"><div class="card-h"><span class="kick">raw/IMPORT-LOG.md</span><h3>' + L("导入历史 + n/200 上限", "Import history") + "</h3></div>" +
      '<div class="tbl-wrap"><table class="ilog"><tr><th>' + esc(L("日期", "Date")) + '</th><th>paper id</th><th>sponsor</th><th>' + esc(L("累计 n/200", "n/200 total")) + '</th><th>sponsor m/10</th></tr>' +
      S.implog.map(function (r) { return "<tr><td>" + esc(r[0]) + "</td><td>" + esc(r[1]) + "</td><td>" + esc(r[2]) + "</td><td>" + esc(r[3]) + "</td><td>" + esc(r[4]) + "</td></tr>"; }).join("") +
      "</table></div></div>";

    html += "</div>";
    p.innerHTML = html;
    p.addEventListener("click", function (e) {
      var a = e.target.closest(".wl"); if (a) { e.preventDefault(); openNote(a.dataset.id); return; }
      var cb = e.target.closest("[data-cbx]"); if (cb) { var k = cb.dataset.cbx; IMPORT_SEL[k] = !IMPORT_SEL[k]; cb.classList.toggle("on", IMPORT_SEL[k]); return; }
      if (e.target.closest("[data-import]")) {
        var sel = Object.keys(IMPORT_SEL).filter(function (k) { return IMPORT_SEL[k]; });
        SB.toast(L("将导入 " + sel.length + " 篇 → fetch · OCR · compile(演示)", "Importing " + sel.length + " → fetch · OCR · compile (demo)"));
      }
    });
    prependCnr($(".pane-wide", p) || p);
    main.innerHTML = "";
    main.appendChild(p);
    paintBadge(main, !!LIVE);
  }

  /* =========================================================================
     12. SUB-VIEW: INBOX — /wiki-auto triage + reconciliation report card
     ========================================================================= */
  // Inbox status is a STABLE ENUM (needs-human / seen / overturned) — never the
  // Chinese literal — so header + pill relocalise on the 中/EN toggle (item 5).
  var STATUS_CYCLE = ["needs-human", "seen", "overturned"];
  // Normalise legacy / server Chinese status strings (and persisted overrides) → enum.
  function normStatus(s) {
    return ({ "待人": "needs-human", "已阅": "seen", "翻案": "overturned",
      "needs-human": "needs-human", "seen": "seen", "overturned": "overturned" })[s] || "needs-human";
  }
  function inboxStatusClass(st) { return st === "needs-human" ? "wait" : st === "seen" ? "ok" : "bad"; }
  function statusLabel(st) {
    return L(({ "needs-human": "待人", "seen": "已阅", "overturned": "翻案" })[st] || st,
      ({ "needs-human": "Needs human", "seen": "Seen", "overturned": "Overturned" })[st] || st);
  }
  function stPill(st) { return '<span class="st-pill ' + inboxStatusClass(st) + '">' + esc(statusLabel(st)) + "</span>"; }
  // Two EXPLICIT status targets replacing the old blind 3-way cycle (item 11): clicking
  // "Seen" or "Overturn" sets that exact status (clicking the active one reverts to
  // needs-human). Keys a/o do the same on the focused row.
  function statusControls(st, idx) {
    return '<button type="button" class="st-act ok' + (st === "seen" ? " on" : "") + '" data-set="seen|' + idx + '" aria-pressed="' + (st === "seen") + '" title="' + esc(L("标为已阅 (a)", "Mark seen (a)")) + '">' + esc(L("已阅", "Seen")) + "</button>" +
      '<button type="button" class="st-act bad' + (st === "overturned" ? " on" : "") + '" data-set="overturned|' + idx + '" aria-pressed="' + (st === "overturned") + '" title="' + esc(L("翻案 (o)", "Overturn (o)")) + '">' + esc(L("翻案", "Overturn")) + "</button>";
  }
  // Charges handed over by the Jury (SB.wikiFileCharge). These are PENDING, in-memory
  // only — never written to disk / localStorage — so the inbox labels them honestly as
  // un-persisted (item 8). Newest first.
  var FILED_CHARGES = [];
  // R9: newcomer gloss for each /wiki-auto stage word (tooltip on the stage chip).
  function stageGloss(stage) {
    return ({
      compile: L("compile:把 raw/ 原文编译成结构化笔记并机械盖章", "compile: turn a raw/ source into a structured note + mechanical stamps"),
      ideate: L("ideate:从缺口产出灵感卡并评级(SCORED / tiering)", "ideate: spawn an idea card from a gap and rate it (SCORED / tiering)"),
      probe: L("probe:跑预注册的廉价实验,回填三值判读", "probe: run the preregistered cheap experiment, fill the verdict"),
      novelty: L("novelty:对邻域论文裁新颖性(component-overlap / problem-open)", "novelty: adjudicate against neighbouring papers"),
      "goal-adopt": L("goal-adopt:把 problems.md 候选采纳为六件套 goal 卡", "goal-adopt: promote a problems.md candidate into a goal card"),
      waiver: L("waiver:预算 / 时间盒探不起时签的豁免说明", "waiver: a signed exemption when a probe exceeds its budget / time-box"),
      jury: L("jury:从评审法庭提交、待归档进 wiki 的指控", "jury: a charge filed from the courtroom, pending filing into the wiki")
    })[stage] || L("无人值守的机器决策环节", "an unattended machine-decision stage");
  }
  // R20: 状态 flips persist across re-render AND reload — keyed by project + a stable
  // per-row identity (date|stage|obj), never the array index. A localStorage override
  // map is applied on paint and written on every flip, so a decision is a committed
  // state, not a toast that silently reverts on the next render.
  function inboxKey() { return "sbwiki.inbox." + (LIVE ? dirName() : "sample"); }
  function inboxRowKey(r) { return (r.date || "") + "|" + (r.stage || "") + "|" + (r.obj || ""); }
  function loadInboxOv() { try { return JSON.parse(localStorage.getItem(inboxKey()) || "{}") || {}; } catch (e) { return {}; } }
  function saveInboxOv(o) { try { localStorage.setItem(inboxKey(), JSON.stringify(o)); } catch (e) {} }
  function applyInboxOv(rows) { var ov = loadInboxOv(); rows.forEach(function (r) { var k = inboxRowKey(r); if (ov[k]) r.status = normStatus(ov[k]); }); return rows; }
  // item 19: current UI language + which language a live pipeline string is written in
  // (used to stamp a 'source: zh/en' tag when the machine-emitted content can't match the UI).
  function curLang() { return (SB.state && SB.state.lang === "en") ? "en" : "zh"; }
  function srcLang(s) { return /[一-鿿]/.test(String(s || "")) ? "zh" : "en"; }
  function sampleInbox() {
    // Sample corpus is fully bilingual → localize the RECON claim pairs here, no source tag.
    return { rows: INBOX, present: true, reconLang: null, reversalLang: null,
      recon: RECON.map(function (r) { return [L(r[0][0], r[0][1]), r[1]]; }),
      reversal: L("翻案回执:2026-08-18 waiver / content-aware-browning 被人翻案 —— 下次运行补一行回执并撤回该 tier 说明。",
        "Reversal receipt: on 2026-08-18 the waiver on content-aware-browning was overturned by a human — the next run appends a receipt line and withdraws that tier note.") };
  }
  function mapLiveInbox(d) {
    var rows = (d.rows || []).map(function (r) {
      return { date: r["日期"] || "", stage: r["环节"] || "", obj: r["对象"] || "", item: r["事项"] || "", status: normStatus(r["状态"]) };
    });
    var recon = (d.reconciliation || []).map(function (ln) {
      var s = String(ln).replace(/^\s*\d+\.\s*/, ""), i = s.lastIndexOf("——");
      return i >= 0 ? [s.slice(0, i).trim(), s.slice(i + 2).trim().replace(/^`|`$/g, "")] : [s.trim(), ""];
    });
    var reversal = (d.reversal_notes && d.reversal_notes[0]) || "";
    // item 19: live content is single-language (whatever the pipeline emitted) — detect it so
    // the card can be stamped 'source: zh/en' when it differs from the viewer's UI language.
    var reconLang = recon.length ? srcLang(recon.map(function (r) { return r[0]; }).join(" ")) : null;
    return { rows: rows, recon: recon, present: !!d.present, reversal: reversal,
      reconLang: reconLang, reversalLang: reversal ? srcLang(reversal) : null };
  }
  // item 19: a small visible tag marking the pipeline's content language when it can't
  // be localized to match the UI (so an EN header over ZH claims is explained, not jarring).
  function srcLangTag(lang) {
    if (!lang || lang === curLang()) return "";
    return '<span class="src-lang-tag" title="' + esc(L("此处内容语言由流水线决定,可能与界面语言不同", "content language is set by the pipeline and may differ from the UI")) +
      '">' + esc(L("来源", "source") + ": " + lang) + "</span>";
  }
  function renderInbox(main) {
    var gen = ++RGEN;
    ensureCorpus().then(function (live) {
      if (gen !== RGEN) return;
      if (!live) return paintInbox(main, sampleInbox());
      fetchOr("inbox").then(function (d) {
        if (gen !== RGEN) return;
        paintInbox(main, (d !== SENT && d && d.present) ? mapLiveInbox(d) : sampleInbox());
      });
    });
  }
  function paintInbox(main, INB) {
    var baseRows = applyInboxOv(INB.rows);   // R20: restore any persisted flips before paint
    // Jury-filed charges (item 8) ride at the TOP — pending + honestly labelled un-persisted.
    var rows = FILED_CHARGES.concat(baseRows);
    var p = el("div", "pane reveal");
    function pendCount() { return rows.filter(function (r) { return r.status === "needs-human"; }).length; }
    var html = '<div class="pane-wide"><div class="pane-head"><h2>' + L("自动审查箱", "Auto review inbox") +
      "</h2><span class=\"sub\">/wiki-auto · " + L("每条无人值守机器决策一行 · 逐条标「已阅」或「翻案」,始终保留翻案权", "one row per unattended machine decision — mark each Seen or Overturned; you keep the final say") + "</span></div>";
    // R9: one-paragraph purpose intro for newcomers — what this list is FOR before the table.
    html += '<p class="inbox-intro">' + L(
      "当你不在场时,/wiki-auto 会替你做一批决策:编译盖章、给灵感评级、读探针判据、裁新颖性、采纳目标、签豁免。这里逐条列出每个机器决策,连同它的可复跑对账命令。逐条过目:确认无误点「已阅」,想推翻点「翻案」——你始终保留事后翻案权。",
      "When you're away, /wiki-auto makes a batch of calls on your behalf — stamping compiles, scoring ideas, reading probe verdicts, adjudicating novelty, adopting goals, signing waivers. Every one is listed here with a re-runnable reconciliation command. Review each: click Seen if it holds, or Overturn to reverse it — you keep the final say.") + "</p>";
    html += '<div class="inbox-bar"><span class="chip wait" data-pending-chip>' + L("待人 " + pendCount(), pendCount() + " pending") + "</span>" +
      '<span class="chip">' + L("共 " + rows.length + " 条 · 签名 auto", rows.length + " rows · signed auto") + "</span>" +
      '<button type="button" class="btn sm ghost inbox-ackall" data-ack-all' + (pendCount() ? "" : " disabled") + '>' + esc(L("全部标为已阅", "Mark all seen")) + "</button></div>";

    html += '<div class="inbox-table" role="table" aria-label="' + esc(L("自动审查箱", "auto review inbox")) + '">' +
      '<div class="inbox-row ih" role="row"><span class="ir-d">' + esc(L("日期", "Date")) + '</span><span class="ir-s">' + esc(L("环节", "Stage")) + '</span><span class="ir-o">' + esc(L("对象", "Object")) + '</span><span class="ir-i">' + esc(L("事项", "Item")) + '</span><span class="ir-st">' + esc(L("状态", "Status")) + "</span></div>" +
      rows.map(function (r, idx) {
        var filed = !!r.filed;
        return '<div class="inbox-row' + (r.status === "needs-human" ? " pending" : "") + (filed ? " filed" : "") + '" data-row="' + idx + '" role="row" tabindex="' + (idx === 0 ? 0 : -1) + '" aria-label="' + esc((r.stage || "") + " · " + (r.obj || "") + " · " + statusLabel(r.status)) + '">' +
          '<span class="ir-d" role="cell">' + esc(r.date) + '</span>' +
          '<span class="ir-s" role="cell"><span class="chip" title="' + esc(stageGloss(r.stage)) + '">' + esc(r.stage) + "</span></span>" +
          '<span class="ir-o" role="cell">' + (filed ? esc(String(r.obj || "")) : (String(r.obj).indexOf("[[") >= 0 ? inlineMd(r.obj) : '<a class="wl" data-id="' + esc(r.obj) + '">[[' + esc(r.obj) + "]]</a>")) + "</span>" +
          '<span class="ir-i" role="cell">' + (filed ? '<span class="filed-tag" title="' + esc(L("仅存于本次会话,尚未写入磁盘", "session only — not yet written to disk")) + '">' + esc(L("未落盘", "not saved")) + "</span> " : "") + esc(r.item) + (filed && r.detail ? '<span class="ir-detail">' + esc(r.detail) + "</span>" : "") +
            (filed && r.chargeId ? '<a class="filed-from" data-jump-charge="' + esc(r.chargeId) + '" title="' + esc(L("回到评审法庭中的该指控", "back to this charge in the courtroom")) + '">' + esc(L("来自指控 ", "Filed from ") + r.chargeId + " →") + "</a>" : "") + "</span>" +
          '<span class="ir-st" role="cell">' + statusControls(r.status, idx) + "</span></div>";
      }).join("") + "</div>";
    if (INB.reversal) html += '<div class="reverse-receipt">' + srcLangTag(INB.reversalLang) + esc(INB.reversal) + "</div>";

    // reconciliation report card
    if (INB.recon && INB.recon.length) html += '<div class="card recon-card" style="margin-top:22px"><div class="card-h"><span class="kick">' + L("收尾对账块", "reconciliation") + '</span><h3>' + L("每个数字旁附可复跑命令", "each number beside a re-runnable command") + "</h3>" + srcLangTag(INB.reconLang) + "</div>" +
      '<div class="recon">' + INB.recon.map(function (r, i) {
        return '<div class="recon-row"><span class="recon-n">' + (i + 1) + '</span><span class="recon-claim">' + esc(r[0]) + "</span>" + (r[1] ? "<code class=\"recon-cmd\">" + esc(r[1]) + "</code>" : "") + "</div>";
      }).join("") + "</div></div>";

    html += "</div>";
    p.innerHTML = html;

    // ---- state sync (in-place; keeps focus + avoids a full re-render) ----------
    function persistRow(r) { if (r.filed) return; var ov = loadInboxOv(); ov[inboxRowKey(r)] = r.status; saveInboxOv(ov); }
    function syncRow(idx) {
      var rowEl = $('[data-row="' + idx + '"]', p); if (!rowEl) return;
      var st = rows[idx].status;
      rowEl.classList.toggle("pending", st === "needs-human");
      rowEl.setAttribute("aria-label", (rows[idx].stage || "") + " · " + (rows[idx].obj || "") + " · " + statusLabel(st));
      var stCell = $(".ir-st", rowEl); if (stCell) stCell.innerHTML = statusControls(st, idx);
    }
    function syncBar() {
      var pend = pendCount();
      var pc = $("[data-pending-chip]", p); if (pc) pc.textContent = L("待人 " + pend, pend + " pending");
      var ab = $("[data-ack-all]", p); if (ab) ab.disabled = pend === 0;
    }
    function setStatus(idx, target, announce) {
      var r = rows[idx]; if (!r) return;
      r.status = (r.status === target) ? "needs-human" : target;   // explicit target, toggles off
      persistRow(r); syncRow(idx); syncBar();
      if (announce) SB.toast(L("已置 → " + statusLabel(r.status), "→ " + statusLabel(r.status)));
    }

    // ---- roving-tabindex keyboard model (mirrors the jury docket) --------------
    function rowEls() { return $$("[data-row]", p); }
    function focusRow(i) {
      var els = rowEls(); if (!els.length) return;
      i = Math.max(0, Math.min(els.length - 1, i));
      els.forEach(function (el, j) { el.tabIndex = j === i ? 0 : -1; });
      els[i].focus();
    }
    var tableEl = $(".inbox-table", p);
    if (tableEl) tableEl.addEventListener("keydown", function (e) {
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      var row = e.target.closest && e.target.closest("[data-row]"); if (!row) return;
      var i = +row.dataset.row, k = e.key;
      if (k === "j" || k === "ArrowDown") { e.preventDefault(); e.stopPropagation(); focusRow(i + 1); }
      else if (k === "k" || k === "ArrowUp") { e.preventDefault(); e.stopPropagation(); focusRow(i - 1); }
      else if (k === "a") { e.preventDefault(); e.stopPropagation(); setStatus(i, "seen", true); }
      else if (k === "o") { e.preventDefault(); e.stopPropagation(); setStatus(i, "overturned", true); }
    });

    p.addEventListener("click", function (e) {
      // item 10: 'Filed from <chargeId> →' deep-links back to that charge in the Jury.
      var jc = e.target.closest("[data-jump-charge]");
      if (jc) {
        e.preventDefault(); var cid = jc.dataset.jumpCharge;
        if (SB.deepLink) SB.deepLink("jury", "docket", cid);
        else if (SB.juryOpenCharge) { SB.setTool("jury"); SB.setSub("docket"); SB.juryOpenCharge(cid); }
        else SB.toast(L("评审台未就绪", "Jury not ready"));
        return;
      }
      var a = e.target.closest(".wl"); if (a) { e.preventDefault(); openNote(a.dataset.id); return; }
      var ack = e.target.closest("[data-ack-all]");
      if (ack) {   // bulk-ack: flip every needs-human → seen in one persisted pass, with undo
        var changed = [];
        rows.forEach(function (r, i) { if (r.status === "needs-human") { changed.push({ i: i, prev: r.status }); r.status = "seen"; } });
        if (!changed.length) return;
        var ov = loadInboxOv();
        changed.forEach(function (c) { if (!rows[c.i].filed) ov[inboxRowKey(rows[c.i])] = "seen"; });
        saveInboxOv(ov);
        changed.forEach(function (c) { syncRow(c.i); }); syncBar();
        SB.toast(L("已全部标为已阅 · " + changed.length + " 条", changed.length + " marked seen"), { action: { label: L("撤销", "Undo"), fn: function () {
          var ov2 = loadInboxOv();
          changed.forEach(function (c) { rows[c.i].status = c.prev; if (!rows[c.i].filed) ov2[inboxRowKey(rows[c.i])] = c.prev; });
          saveInboxOv(ov2);
          changed.forEach(function (c) { syncRow(c.i); }); syncBar();
        } } });
        return;
      }
      var sb = e.target.closest("[data-set]");
      if (sb) { var parts = sb.dataset.set.split("|"); setStatus(+parts[1], parts[0], true); return; }
    });

    prependCnr($(".pane-wide", p) || p);
    main.innerHTML = "";
    main.appendChild(p);
    paintBadge(main, !!LIVE);
  }

  /* =========================================================================
     13. SUB-VIEW: ASK — the teach panel (citation-bound, docked beside a reader)
         "Reading First, AI Second": left = the note under discussion; right =
         answers that only cite the corpus (every claim deep-links; else not-in-wiki).
     ========================================================================= */
  var ASK_READ = "edge-hotspot";
  function renderAsk(main) {
    var gen = ++RGEN;
    ensureCorpus().then(function () {
      if (gen !== RGEN) return;
      if (!NOTES[ASK_READ]) ASK_READ = NOTES["edge-hotspot"] ? "edge-hotspot" : ORDER[0];
      var wrap = el("div", "ask-wrap reveal");
      wrap.innerHTML =
        '<div class="ask-read"><div class="ask-read-scroll"><article class="reader" id="ask-article"></article></div></div>' +
        '<div class="ask-panel">' +
          '<div class="ask-head"><svg class="i sm" style="color:var(--accent)"><use href="#i-ask"/></svg><span class="tt">' + L("讲解 · 只答库内", "Teach · corpus only") + "</span></div>" +
          '<div class="ask-sub">' + L("NOT-RAG:每条断言带出处小节链接,点击即在左侧定位;库内没有就说 not in wiki。", "Every claim cites a note+section; otherwise: not in wiki.") + "</div>" +
          '<div class="ask-thread" id="ask-thread"></div>' +
          '<div class="ask-suggest" id="ask-suggest"></div>' +
          '<div class="ask-input"><input type="text" placeholder="' + esc(L("问库内的问题…", "Ask the corpus…")) + '" id="ask-in"><button class="btn primary sm" id="ask-send">' + L("问", "Ask") + "</button></div>" +
        "</div>";
      main.innerHTML = "";
      main.appendChild(wrap);
      renderAskRead();
      // seed the thread with the citation-bound example exchanges (they cite notes
      // that exist in the real corpus too, so their deep-links resolve either way)
      var thread = $("#ask-thread", wrap);
      ASK.forEach(function (x) { thread.appendChild(askExchange(x)); });
      // suggested-question chips (re-ask an example)
      var sug = $("#ask-suggest", wrap);
      sug.innerHTML = '<span class="ask-sug-h">' + L("试问", "Try") + "</span>" + ASK.map(function (x, i) { return '<button class="ask-chip" data-ask="' + i + '">' + esc(x.q.length > 22 ? x.q.slice(0, 22) + "…" : x.q) + "</button>"; }).join("");
      wrap.addEventListener("click", function (e) {
        var c = e.target.closest("[data-cite]"); if (c) { var d = c.dataset.cite.split("|"); ASK_READ = d[0]; renderAskRead(d[1]); return; }
        var a = e.target.closest(".wl"); if (a) { e.preventDefault(); ASK_READ = NOTES[a.dataset.id] ? a.dataset.id : ASK_READ; if (NOTES[a.dataset.id]) renderAskRead(); else SB.toast(L("[[" + a.dataset.id + "]] 尚未编译", "[[" + a.dataset.id + "]] not compiled")); return; }
        var sg = e.target.closest("[data-ask]"); if (sg) { var x = ASK[+sg.dataset.ask]; var th = $("#ask-thread"); th.appendChild(askExchange(x)); th.scrollTop = th.scrollHeight; return; }
        if (e.target.closest("#ask-send")) { doAsk($("#ask-in").value); }
      });
      var inp = $("#ask-in", wrap); if (inp) inp.addEventListener("keydown", function (e) { if (e.key === "Enter") doAsk(inp.value); });
      paintBadge(main, !!LIVE);
    });
  }
  function renderAskRead(section) {
    var art = $("#ask-article"); if (!art) return;
    var n = NOTES[ASK_READ] || NOTES[ORDER[0]]; if (!n) return;
    bodyOf(n).then(function (body) {
      var a = $("#ask-article"); if (!a) return;               // pane still mounted?
      a.innerHTML = '<div class="kicker">' + esc(kickerFor(n)) + '</div><h1>' + esc(n.title) + "</h1>" +
        '<div class="meta">' + metaFor(n) + '</div><hr class="divider">' + renderMd(body || "");
      if (section) requestAnimationFrame(function () { $$("h2,h3", a).forEach(function (h) { if (h.textContent.indexOf(section) >= 0) h.scrollIntoView({ block: "start" }); }); });
    });
  }
  function citeChip(c, label) { return '<button class="cite" data-cite="' + esc(c.id) + "|" + esc(c.section) + '">' + esc(label || (c.id + " · " + c.section)) + "</button>"; }
  function askExchange(x) {
    var box = el("div", "ask-msg");
    var h = '<div class="ask-q">' + esc(x.q) + "</div>";
    if (x.kind === "table") {
      // Transpose: dimensions down the rows, one column per paper — fits the
      // narrow teach dock far better than a wide 5-column table (CJK cells
      // wouldn't collapse to vertical char-stacks). Last col ("出处") = cites.
      var papers = x.rows.map(function (r) { return r[0]; });
      var thead = "<tr><th></th>" + papers.map(function (pp) { return "<th>" + esc(pp) + "</th>"; }).join("") + "</tr>";
      var tbody = x.cols.map(function (col, ci) {
        var cells = x.rows.map(function (r) {
          var v = r[ci + 1];
          if (v && v.id) return "<td>" + citeChip(v, v.section) + "</td>";
          return "<td>" + inlineMd(String(v)) + "</td>";
        }).join("");
        return '<tr><td class="cmp-row-h">' + esc(col) + "</td>" + cells + "</tr>";
      }).join("");
      h += '<div class="ask-a">' + (x.intro ? "<p>" + esc(x.intro) + "</p>" : "") +
        '<div class="tbl-wrap"><table class="cmp-table">' + thead + tbody + "</table></div>" +
        (x.foot ? '<p class="ask-foot">' + inlineMd(x.foot) + "</p>" : "") + "</div>";
    } else if (x.kind === "gap-status") {
      h += '<div class="ask-a"><div class="gap-status">' +
        '<div class="gs-row"><span class="gs-k">novelty</span><span class="gs-v"><span class="chip ok">verified ✓</span> ' + citeChip(x.novelty.src, x.novelty.src.id + " › " + x.novelty.src.section) + " · " + esc(x.novelty.ledger) + "</span></div>" +
        '<div class="gs-row"><span class="gs-k">ideation</span><span class="gs-v">' + x.ideas.map(function (i) { return inlineMd(i.txt) + " " + citeChip(i.cite, "→ Claim"); }).join("<br>") + "</span></div>" +
        '<div class="gs-row"><span class="gs-k">probe</span><span class="gs-v">' + inlineMd(x.probe.txt) + " " + citeChip(x.probe.cite, "→ 三值判读") + "</span></div>" +
        '<div class="gs-row"><span class="gs-k">critique</span><span class="gs-v">' + inlineMd(x.critique) + "</span></div>" +
        "</div>" + (x.foot ? '<p class="ask-foot">' + inlineMd(x.foot) + "</p>" : "") + "</div>";
    } else if (x.kind === "notinwiki") {
      h += '<div class="ask-a notinwiki"><div class="niw-tag">not in wiki</div>' + "<p>" + inlineMd(x.body) + "</p>" +
        '<p class="niw-missing"><strong>' + L("缺什么", "missing") + "</strong> · " + esc(x.missing) + "</p>" +
        '<p class="niw-action"><strong>' + L("建议", "suggest") + "</strong> · " + esc(x.action) + "</p></div>";
    } else { h += '<div class="ask-a"><p>' + inlineMd(x.body || "") + "</p></div>"; }
    box.innerHTML = h;
    return box;
  }
  // Tokenize a question into search terms: latin / number words + CJK bigrams,
  // minus a few generic stop-terms — so a multi-word question retrieves by term
  // OVERLAP, not one brittle whole-string indexOf (R25).
  var ASK_STOP = { "方法": 1, "效果": 1, "如何": 1, "怎么": 1, "什么": 1, "这个": 1, "那个": 1, "是否": 1, "可以": 1, "进行": 1, "实现": 1, "一个": 1, "以及": 1, "区别": 1, "the": 1, "and": 1, "for": 1, "how": 1, "does": 1, "with": 1, "what": 1, "why": 1, "are": 1 };
  function askTerms(q) {
    q = String(q || "").toLowerCase();
    var terms = {}, m, re = /[a-z0-9][a-z0-9\-]+/g;
    while ((m = re.exec(q))) if (!ASK_STOP[m[0]]) terms[m[0]] = 1;
    (q.match(/[㐀-鿿]+/g) || []).forEach(function (run) {
      if (run.length === 1) { if (!ASK_STOP[run]) terms[run] = 1; return; }
      for (var i = 0; i < run.length - 1; i++) { var bg = run.slice(i, i + 2); if (!ASK_STOP[bg]) terms[bg] = 1; }
    });
    return Object.keys(terms);
  }
  function doAsk(q) {
    q = (q || "").trim(); if (!q) return;
    var inp = $("#ask-in"); if (inp) inp.value = "";
    var th = $("#ask-thread"); if (!th) return;
    // Score every note by how many DISTINCT query terms it contains (title + body
    // + one-line + id); keep the best above a light threshold. The winning notes'
    // markdown becomes the ONLY context the citation-bound 'teach' op may cite —
    // still honestly "not in wiki" when nothing overlaps.
    // Threshold = 1 shared term: recall-favouring (the bug being fixed is covered
    // questions wrongly returning "not in wiki"). Notes are ranked by term count and
    // capped at the 3 best, so a single incidental overlap still surfaces the most
    // relevant notes; a question with ZERO corpus overlap still yields "not in wiki".
    var terms = askTerms(q);
    var hits = ORDER.map(function (id) {
      var n = NOTES[id]; if (!n || n.companion) return null;
      var hay = ((n.title || "") + " " + (n.body || "") + " " + (n.oneLine || "") + " " + id).toLowerCase();
      var s = 0; terms.forEach(function (t) { if (hay.indexOf(t) >= 0) s++; });
      return s > 0 ? { id: id, s: s } : null;
    }).filter(Boolean).sort(function (a, b) { return b.s - a.s; }).slice(0, 3).map(function (x) { return x.id; });
    if (!hits.length) {
      th.appendChild(askExchange({ q: q, kind: "notinwiki",
        body: L("库内笔记未命中该问题。", "No matching note in the corpus."),
        missing: L("缺一篇覆盖该主题的来源。", "a source covering this topic."),
        action: "/wiki-search-latest \"" + q + "\" → import → compile。" }));
      th.scrollTop = th.scrollHeight; return;
    }
    var box = el("div", "ask-msg");
    box.innerHTML = '<div class="ask-q">' + esc(q) + '</div><div class="ask-a">' +
      '<p class="ask-cites">' + L("引用:", "cites: ") + hits.map(function (id) { return '<a class="wl" data-id="' + esc(id) + '">[[' + esc(id) + "]]</a>"; }).join(" · ") + "</p>" +
      '<div class="ask-stream" data-stream>' + esc(L("正在只依据上列笔记作答…", "answering from the cited notes…")) + "</div></div>";
    th.appendChild(box); th.scrollTop = th.scrollHeight;
    var out = $(".ask-stream", box);
    Promise.all(hits.map(function (id) {
      var n = NOTES[id];
      return bodyOf(n).then(function (b) { return "## " + (n.title || id) + " (wiki/" + n.folder + "/" + id + ".md)\n" + (b || n.oneLine || ""); });
    })).then(function (parts) {
      SB.ai({ op: "teach", text: q, context: parts.join("\n\n") }, function (chunk, done, full) {
        if (out) out.innerHTML = SB.mdLite(full || "");
        if (done) th.scrollTop = th.scrollHeight;
      });
    });
  }

  /* =========================================================================
     14. PROJECT STATUS popover (onTitle) — research.md Scope fence
     ========================================================================= */
  function fenceLis(v) {                            // md bullet-block (live) or array (sample) -> <li>s
    var arr = Array.isArray(v) ? v : String(v || "").split(/\n/).map(function (s) { return s.replace(/^\s*[-*]\s*/, "").trim(); }).filter(Boolean);
    return arr.map(function (s) { return "<li>" + inlineMd(s) + "</li>"; }).join("");
  }
  function statusHTML(P) {
    return '<div class="ps-h"><h2>' + esc(P.title) + '</h2>' +
      '<span class="chip accent">llm-wiki/1.1' + (P.variant ? " · " + esc(P.variant) : " · v2.1.0") + "</span></div>" +
      '<div class="ps-badges"><span class="chip ok">lifecycle: ' + esc(P.lifecycle_state) + '</span><span class="chip accent">expansion: ' + esc(P.expansion_mode) + '</span>' +
      "<span class=\"chip\">" + Object.keys(NOTES).length + " notes · " + folderNotes("papers").length + " papers</span></div>" +
      '<div class="ps-fence"><div class="ps-k">核心焦点 core</div><p>' + inlineMd(P.core) + "</p>" +
      '<div class="ps-k">相邻可纳入 adjacent</div><ul>' + fenceLis(P.adjacent) + "</ul>" +
      '<div class="ps-k">排除范围 exclude → fence_zone: outside</div><ul>' + fenceLis(P.exclude) + "</ul></div>" +
      (P.todo ? '<div class="ps-k">下一步 TODO</div><div class="ps-todo">' + P.todo.map(function (t) { return '<div class="todo ' + (t.done ? "done" : "") + '"><span class="tk">' + (t.done ? "✓" : "○") + "</span>" + inlineMd(t.t) + "</div>"; }).join("") + "</div>" : "");
  }
  function projectStatus() {
    $$(".scrim,.pop.wiki-status").forEach(function (n) { n.remove(); });
    var sc = el("div", "scrim"); document.body.appendChild(sc);
    var pop = el("div", "pop wiki-status");
    pop.style.cssText = "left:50%;top:64px;transform:translateX(-50%);width:min(560px,94vw);padding:22px;max-height:80vh;overflow:auto";
    var sample = { title: "efficient-uniform-browning · research wiki", variant: "", lifecycle_state: SCOPE.lifecycle_state, expansion_mode: SCOPE.expansion_mode, core: SCOPE.core, adjacent: SCOPE.adjacent, exclude: SCOPE.exclude, todo: SCOPE.todo };
    pop.innerHTML = statusHTML(sample);
    document.body.appendChild(pop);
    sc.onclick = function () { pop.remove(); sc.remove(); };
    pop.addEventListener("click", function (e) { var a = e.target.closest(".wl"); if (a) { e.preventDefault(); pop.remove(); sc.remove(); openNote(a.dataset.id); } });
    ensureCorpus().then(function (live) {
      if (!live || !pop.isConnected) return;
      SB.data.getOr("wiki", "project", null).then(function (d) {
        if (!d || !pop.isConnected) return;
        pop.innerHTML = statusHTML({
          title: d.title || sample.title, variant: d.variant || "",
          lifecycle_state: d.lifecycle_state || sample.lifecycle_state, expansion_mode: d.expansion_mode || sample.expansion_mode,
          core: (d.scope && d.scope.core) || sample.core, adjacent: (d.scope && d.scope.adjacent) || sample.adjacent,
          exclude: (d.scope && d.scope.exclusions) || sample.exclude, todo: null
        });
      });
    });
  }

  /* =========================================================================
     15. AI transport — NOT overridden here.
     /ui/ai.js owns SB.aiTransport (it streams the real reading assistant from
     /api/ai). This module must NOT reassign it: wiki.js loads AFTER ai.js, so an
     override here would clobber Spark/Jury's reading-AI (summary / explain /
     translate). The Teach panel instead calls the SHARED transport with the
     citation-bound 'teach' op — SB.ai({op:'teach', text, context}, cb) — where
     ai.py answers only from the provided note markdown (else "not in wiki").
     ========================================================================= */

  /* =========================================================================
     16. REGISTER THE TOOL
     ========================================================================= */
  SB.registerTool("wiki", {
    title: "efficient-uniform-browning · research wiki",
    onTitle: projectStatus,
    // Getters, not static strings: reader.js renderSubnav() reads s.label fresh on
    // every render (incl. the 中/EN toggle), so a getter re-localises in place (R8).
    sub: [
      { id: "library", get label() { return L("文库", "Library"); } },
      { id: "ideas", get label() { return L("灵感", "Ideas"); } },
      { id: "graph", get label() { return L("图谱", "Graph"); } },
      { id: "coverage", get label() { return L("覆盖", "Coverage"); } },
      { id: "sources", get label() { return L("来源", "Sources"); } },
      { id: "inbox", get label() { return L("审查箱", "Inbox"); } },
      { id: "ask", get label() { return L("讲解", "Teach"); } }
    ],
    render: function (main, sub) {
      WS.main = main;
      if (sub === "ideas") return renderIdeas(main);
      if (sub === "graph") return renderGraph(main);
      if (sub === "coverage") return renderCoverage(main);
      if (sub === "sources") return renderSources(main);
      if (sub === "inbox") return renderInbox(main);
      if (sub === "ask") return renderAsk(main);
      return renderLibrary(main);
    }
  });

  // Small public hook: lets the harness (and, later, cross-tool deep-links) open
  // a specific note in the Library reader by id — e.g. wiki-demo.html?note=<id>.
  SB.wikiOpen = openNote;

  // Jury → Wiki handoff (item 8). The Jury's "File to Wiki" button calls this with
  // {title, body, reason_code, evidence, patch}. We switch to the Wiki inbox and append a
  // PENDING row that the inbox honestly labels as session-only / un-persisted. ADD-only:
  // never reassign or delete any other SB.* global (a prior incident clobbered SB.aiTransport).
  SB.wikiFileCharge = function (payload) {
    payload = payload || {};
    var today; try { today = new Date().toISOString().slice(0, 10); } catch (e) { today = ""; }
    var detail = [];
    if (payload.body) detail.push(payload.body);
    if (payload.reason_code) detail.push(L("理由", "reason") + ": " + payload.reason_code);
    if (payload.evidence) detail.push(L("证据", "evidence") + ": " + payload.evidence);
    if (payload.patch) detail.push(L("补丁", "patch") + ": " + payload.patch);
    // item 10: recover the originating charge id (jury sends it as the title prefix
    // "I-01 · summary") so the filed note can deep-link back to that charge.
    var cid = payload.chargeId || payload.charge_id || payload.id || "";
    if (!cid && payload.title) cid = String(payload.title).split(" · ")[0];
    cid = String(cid || "").trim();
    if (cid.length > 16 || /\s/.test(cid)) cid = "";   // a real short charge id, never a whole title
    FILED_CHARGES.unshift({
      date: today, stage: "jury",
      obj: payload.obj || payload.target || "—",
      item: payload.title || payload.body || L("评审指控", "jury charge"),
      detail: detail.join(" · "),
      chargeId: cid,
      status: "needs-human", filed: true
    });
    SB.setTool("wiki");
    SB.setSub("inbox");
  };

  // Fold the whole corpus into the shared ⌘K palette so it can jump straight to any
  // paper / note (the Wiki's global search). Guarded + lazy: a no-op until reader.js
  // grows the palette-source hook, and re-reads the CURRENT corpus (sample↔live) on
  // each palette open. Excludes companion nodes (they alias their parent).
  if (SB.registerPaletteSource) SB.registerPaletteSource(function () {
    return ORDER.filter(function (id) { return NOTES[id] && !NOTES[id].companion; }).map(function (id) {
      var n = NOTES[id];
      return { id: n.id, label: n.title, sub: "library", type: n.type, run: function () { SB.setTool("wiki"); openNote(n.id); } };
    });
  });

  wireHoverPreview();   // document-level link peek (idempotent)

  /* extra sprite icons the wiki uses (added once; shell sprite already exists) */
  (function addIcons() {
    function add() {
      var sp = document.getElementById("sb-sprite"); if (!sp) return false;
      var defs = sp.querySelector("defs") || sp; var add1 = function (id, inner) { if (!sp.querySelector("#" + id)) { var g = document.createElementNS("http://www.w3.org/2000/svg", "g"); g.id = id; g.innerHTML = inner; g.setAttribute("fill", "none"); g.setAttribute("stroke", "currentColor"); g.setAttribute("stroke-width", "1.5"); defs.appendChild(g); } };
      add1("i-compass", '<circle cx="8" cy="8" r="6"/><path d="M10.5 5.5L9 9l-3.5 1.5L7 7z" fill="currentColor" stroke="none"/>');
      add1("i-flask", '<path d="M6 2v3.5L3 11.5a1 1 0 0 0 .9 1.5h8.2a1 1 0 0 0 .9-1.5L10 5.5V2"/><path d="M5.5 2h5M5 9h6"/>');
      add1("i-target", '<circle cx="8" cy="8" r="6"/><circle cx="8" cy="8" r="3"/><circle cx="8" cy="8" r=".6" fill="currentColor" stroke="none"/>');
      add1("i-map", '<path d="M2 4l4-1.5L10 4l4-1.5v9L10 12 6 13.5 2 12z"/><path d="M6 2.5v11M10 4v9"/>');
      add1("i-scale", '<path d="M8 2v11M4 13h8M3 5l5-1.5L13 5"/><path d="M3 5L1.5 8.5h3zM13 5l-1.5 3.5h3z"/>');
      add1("i-file", '<path d="M4 2.5h5l3 3v8H4z"/><path d="M9 2.5v3h3"/>');
      add1("i-search", '<circle cx="7" cy="7" r="4.2"/><path d="M10.2 10.2L14 14"/>');
      add1("i-arrow-left", '<path d="M12 8H3"/><path d="M6.5 4.5L3 8l3.5 3.5"/>');
      add1("i-play", '<path d="M5 3.5l7 4.5-7 4.5z" fill="currentColor" stroke="none"/>');   // round8 #2: 'Launch in Spark' start glyph
      return true;
    }
    if (!add()) document.addEventListener("DOMContentLoaded", add);
  })();
})();
