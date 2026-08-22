/* ============================================================================
   SparkBoard · SPARK workspace (write papers) — cockpit/ui/spark.js
   Supersedes the basic spark tool in _demo.html with the full four sub-view
   workspace: reading · runs · figures · governance.

   It renders ONE coherent paper across every view — the self-referential
   "Spark-to-Paper" manuscript — because that is the only run on disk with real
   artifacts for all four surfaces (proposal.md, figures.manifest.json,
   results.facts.json, claims_map.json, blueprint.json, sections/*.tex). All
   sample data below mirrors the EXACT on-disk field names from map 03:
     - story.json      : title/abstract/problem_framing/gap_pattern/solution/
                         method_skeleton/innovation_claims[]/experiments_plan/origin
     - blueprint.json  : paper_title/keywords/contributions/terminology/notation/
                         experiment_design
     - LEDGER.json     : budget{gpu_hours_cap,gpu_hours_spent,outer_round,...}/
                         directions{}/runs[{id,dir,status,gpu_h_actual,spend_basis,...}]/
                         councils/scoped_accepts
     - logs/seals/*    : {stage,ts,minter,input_hashes,tree_hash,rollcall{rows[…]}}
     - DECISION_QUEUE  : {id,type,finding,pointer,reversal_cost,resume,reverse,ts}
     - results.facts   : rq1_figure_engine_ssim / rq2_integrity_gates / rq3_end_to_end
     - figures.manifest: figures[{label,type,engine,grounding,reference_used,critic_rounds}]
     - E14-metrics     : ended_by / best_tier_at_end / reversal_rate_by_class / postproc_*

   Missing-on-disk values degrade honestly to "—" / "not run" (non-negotiable #4).
   Vanilla JS, no build; leans on SB primitives + spark.css structural bits.
   ============================================================================ */
(function () {
  "use strict";
  var SB = window.SB;
  if (!SB) { console.error("spark.js requires reader.js (window.SB)"); return; }
  var el = SB.el, esc = SB.esc, $ = SB.$, $$ = SB.$$;

  /* ---- extra icons (prefixed sp- so they never collide with the base sprite) */
  function ensureSparkSprite() {
    if (document.getElementById("sp-sprite")) return;
    var svg = el("svg"); svg.id = "sp-sprite"; svg.setAttribute("aria-hidden", "true");
    svg.setAttribute("width", "0"); svg.setAttribute("height", "0"); svg.style.position = "absolute";
    svg.innerHTML =
      '<defs>' +
      '<g id="sp-doc" fill="none" stroke="currentColor" stroke-width="1.4"><path d="M4 2.2h5l3 3v8.6H4z"/><path d="M9 2.2v3h3"/><path d="M6 8.5h4M6 10.7h4"/></g>' +
      '<g id="sp-flask" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"><path d="M6.4 2.3v3.4L3.2 11a1.4 1.4 0 0 0 1.2 2.1h7.2A1.4 1.4 0 0 0 12.8 11L9.6 5.7V2.3"/><path d="M5.4 2.3h5.2M5.2 9.2h5.6"/></g>' +
      '<g id="sp-seal" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"><path d="M8 1.8l4.4 1.9v3.2c0 3-1.9 5-4.4 5.9-2.5-.9-4.4-2.9-4.4-5.9V3.7z"/><path d="M5.9 7.8l1.5 1.5 2.9-3" stroke-width="1.5"/></g>' +
      '<g id="sp-ladder" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"><path d="M3 13h3.2v-3H9V7h3.2V3.5"/><path d="M3 13v-2.4M6.2 10v-1.6M9 7V5.4"/></g>' +
      '<g id="sp-image" fill="none" stroke="currentColor" stroke-width="1.4"><rect x="2.6" y="3" width="10.8" height="10" rx="1.5"/><circle cx="6" cy="6.3" r="1.1"/><path d="M3 11.5l3.2-3 2.3 2 2-1.7 2.5 2.4"/></g>' +
      '<g id="sp-play" fill="currentColor"><path d="M5 3.4l7 4.6-7 4.6z"/></g>' +
      '<g id="sp-undo" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M5.5 4.5H10a3.3 3.3 0 0 1 0 6.6H4.6"/><path d="M6.8 2.4 4.3 4.5l2.5 2.1"/></g>' +
      '<g id="sp-hash" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"><path d="M5.6 2.6 4.2 13.4M11.8 2.6 10.4 13.4M2.6 5.6h10.4M2.2 10.4h10.4"/></g>' +
      '<g id="sp-copy" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"><rect x="5.4" y="5.4" width="7.6" height="8.6" rx="1.3"/><path d="M10.4 5.4V3.5A1.3 1.3 0 0 0 9.1 2.2H3.8A1.3 1.3 0 0 0 2.5 3.5v7.4"/></g>' +
      '<g id="sp-quote" fill="currentColor"><path d="M3 9.5c0-2.2 1.3-3.8 3.3-4.4l.5 1c-1 .4-1.7 1.1-1.8 2h1.6v3.2H3zM8.4 9.5c0-2.2 1.3-3.8 3.3-4.4l.5 1c-1 .4-1.7 1.1-1.8 2h1.6v3.2H8.4z"/></g>' +
      '<g id="sp-warn" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"><path d="M8 2.6 14 12.5H2z"/><path d="M8 6.4v3.1" stroke-linecap="round"/><circle cx="8" cy="11.2" r=".7" fill="currentColor" stroke="none"/></g>' +
      '<g id="sp-clock" fill="none" stroke="currentColor" stroke-width="1.4"><circle cx="8" cy="8" r="5.6"/><path d="M8 4.8V8l2.3 1.4" stroke-linecap="round"/></g>' +
      '<g id="sp-bolt" fill="currentColor"><path d="M8.6 1.6 3.4 8.8h3.1l-1 5.6 5.2-7.2H7.6z"/></g>' +
      '<g id="sp-route" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"><circle cx="4" cy="4" r="1.7"/><circle cx="12" cy="12" r="1.7"/><path d="M4 5.7v3.1a2.5 2.5 0 0 0 2.5 2.5H10"/></g>' +
      '<g id="sp-book" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"><path d="M8 4.2C6.7 3.1 4.9 2.8 3 3.1v8.4c1.9-.3 3.7 0 5 1.1 1.3-1.1 3.1-1.4 5-1.1V3.1c-1.9-.3-3.7 0-5 1.1z"/><path d="M8 4.2v8.5"/></g>' +
      '</defs>';
    document.body.appendChild(svg);
  }
  function ic(id, cls) { return '<svg class="i ' + (cls || "") + '"><use href="#' + id + '"/></svg>'; }

  /* =========================================================================
     INLINE SAMPLE DATA — faithful field names, real numbers where they exist
     ========================================================================= */
  // story.json (constructed for Spark-to-Paper; EXACT field names from map 03)
  var STORY = {
    title: "Spark-to-Paper: Composable Agent Skills for Integrity-Gated Paper Generation",
    // the "one sentence into a paper" — the spark
    spark_sentence: "Turn a raw research spark into a submittable, integrity-checked manuscript as a drop-in agent-skill suite — no app, no server, no database.",
    problem_framing: "LLMs can draft fluent prose, but turning a spark into a submittable manuscript is still not one trustworthy low-friction workflow: infrastructure is heavyweight, integrity failures (hallucinated citations, fabricated numbers) are treated as stylistic risk, and image models emit rasters where camera-ready papers need editable vectors.",
    gap_pattern: "forbidden: ship end-to-end breadth only behind dedicated infrastructure | cause: the strongest autonomous scientists need Docker, graph DBs, tens of thousands of lines | trigger: the pipeline cannot drop into an existing editor workflow  ·  forbidden: treat hallucinated cites / fabricated numbers as review-later style notes | cause: they are the endemic, damaging failure mode | trigger: no build-breaking machine gate exists",
    solution: "Own all judgement with the LLM holding the whole paper in context; let small deterministic scripts backstop only the irreducible parts (lint, assemble, plot, vectorize). One content router sets a single results_mode that flips the suite between two integrity regimes with opposite rules for numbers and tense.",
    innovation_claims: [
      "A zero-infrastructure end-to-end suite realized purely as composable agent skills with files-on-disk stage contracts.",
      "Integrity-as-a-build-gate: hallucinated-citation and fabricated-number failures are machine-checked, build-breaking errors, not post-hoc style.",
      "A decompose-and-reconstruct editable-vector figure engine (hybrid render-plus-text-overlay) that keeps image-model schematics camera-ready without the loss of a full redraw."
    ],
    origin: "self-generated-with-user-approval"
  };

  // blueprint.json (real values from the ICML workdir)
  var BLUEPRINT = {
    paper_title: "Spark-to-Paper: Composable Agent Skills for Integrity-Gated, End-to-End Scientific Paper Generation with Editable-Vector Figures",
    keywords: ["automated paper generation", "large language model agents", "agent skills", "hallucination mitigation", "editable vector figures", "image segmentation"],
    contributions: [
      { id: "C1", text: "A zero-infrastructure, end-to-end paper-generation suite realized purely as composable agent skills, files-on-disk stage contracts, no app / server / database." },
      { id: "C2", text: "A content-routing orchestration model: a schema-free classifier sets one results_mode that flips the whole pipeline between two opposite integrity regimes." },
      { id: "C3", text: "Integrity-as-a-build-gate: hallucinated-citation and fabricated-number failures are machine-checked, build-breaking errors." },
      { id: "C4", text: "A decompose-and-reconstruct editable-vector figure engine converting an image-model raster into a hybrid render-plus-editable-text figure." }
    ],
    method_name: "Spark-to-Paper",
    template: { display_name: "NeurIPS 2025 (single-column, author-year)", official: true, results_mode: "data_aware" },
    sections: 9, word_target: [6300, 10430], figures_planned: 7, tables_planned: 3, notation_entries: 12
  };

  // sections/*.tex → the reader TOC. Titles are the real template.json titles.
  var SECTIONS = [
    { id: "introduction", title: "Introduction", words: [650, 1000] },
    { id: "related_work", title: "Related Work", words: [600, 1000] },
    { id: "approach", title: "System Design", words: [1000, 1700] },
    { id: "pipeline", title: "The Generation Pipeline", words: [1100, 1800] },
    { id: "integrity", title: "Integrity and the Quality Stack", words: [750, 1300] },
    { id: "figure_engine", title: "The Editable-Vector Figure Engine", words: [650, 1100] },
    { id: "evaluation", title: "Evaluation Protocol", words: [650, 1100] },
    { id: "discussion", title: "Discussion, Limitations, and Broader Impact", words: [600, 1050] },
    { id: "conclusion", title: "Conclusion", words: [150, 280] }
  ];

  // results.facts.json (verified numbers ledger — real)
  var FACTS = {
    rq1_figure_engine_ssim: { system_overview: 0.962, routing_modes: 0.930, pipeline_stages: 0.934, gate_flow: 0.939, hybrid_engine: 0.924, quality_stack: 0.860, mean: 0.925, min: 0.86, max: 0.96 },
    rq1_editable_text_boxes: { mean: 44.5, min: 17, max: 76 },
    rq1_runtime_seconds: { mean: 51.3, min: 42.2, max: 59.5 },
    rq2_integrity_gates: { fabricated_numbers_injected: 8, fabricated_numbers_caught_full_stack: 7, fabricated_numbers_caught_without_audit: 0, citation_probes_injected: 3, citation_probes_caught_full_stack: 3, false_alarms_on_clean_manuscript: 0 },
    rq3_end_to_end: { pages: 20, references: 46, references_resolved: 46, figures: 7, editable_vector_figures: 6, latex_error_count: 0, sections: 9, gates_green: true },
    notes: "Word-form magnitude (“doubled”) is the one injected fabrication the deterministic audit did not catch; it is deferred to the model-judgment layers per the paper's stated design."
  };

  // Rich figures — the SHOWCASE shape mirrors the /api/spark/figures endpoint
  // (label/number/caption/type/engine/grounding/ref/critic_rounds/svg_rounds/
  // audit_ok/files{png,svg,pdf}/prompt/audit{cleanliness,min_text_px,texts,shapes,
  // warnings}/versions[{round,svg_url}]). No per-figure SSIM exists — none is stored.
  // The sample carries null file/svg URLs (no bytes on disk); the gallery falls back
  // to its on-brand schematic thumb and to placeholder version panels, all flagged
  // 示例数据. `formats` is a display convenience derived here so the sample shows the
  // PDF·SVG·PNG chips even without openable files.
  function figPrompt(kind, ref) {
    return "Editorial line-art schematic, single-column figure for a NeurIPS paper. " + kind +
      " Flat vector style, hairline strokes, one accent hue over ink-on-paper, generous whitespace, " +
      "no gradients, no drop shadows, no photographic texture. Every label must be real, legible, " +
      "horizontal text placed OUTSIDE the boxes it names — never baked into the raster. Composition " +
      "grounded on " + ref + ": keep its block topology and reading order, restyle to our palette. " +
      "Leave a clear title band at the top and even margins so the downstream SVG overlay can re-lay " +
      "every caption as editable text without collision.";
  }
  var FIGURES = [
    { label: "system_overview", number: 1, type: "architecture", engine: "image-model", grounding: "image-cond", ref: "arxiv:2308.08155#fig1", critic_rounds: 2, svg_rounds: 3, audit_ok: true,
      caption: "The Spark-to-Paper suite: a spark enters at the left, files-on-disk stage contracts carry it rightward through routing, drafting, integrity gates and the figure engine to a compiled manuscript.",
      formats: ["pdf", "svg", "png"], files: { png: null, svg: null, pdf: null },
      prompt: figPrompt("A left-to-right system diagram: an input spark, a router, four stacked skill lanes, and a compiled-paper output node.", "arxiv:2308.08155#fig1"),
      audit: { cleanliness: 0.98, min_text_px: 12.4, texts: 34, shapes: 62, warnings: [] },
      versions: [{ round: 1, svg_url: null }, { round: 2, svg_url: null }, { round: 3, svg_url: null }] },
    { label: "routing_modes", number: 2, type: "flow", engine: "image-model", grounding: "image-cond", ref: "arxiv:2310.11511#fig1", critic_rounds: 2, svg_rounds: 2, audit_ok: true,
      caption: "One content router sets a single results_mode that flips the whole suite between two integrity regimes with opposite rules for numbers and tense.",
      formats: ["pdf", "svg", "png"], files: { png: null, svg: null, pdf: null },
      prompt: figPrompt("A branching flow: one classifier diamond splitting into two mode lanes (proposal vs data-aware) whose rules mirror each other.", "arxiv:2310.11511#fig1"),
      audit: { cleanliness: 0.99, min_text_px: 13.1, texts: 17, shapes: 28, warnings: [] },
      versions: [{ round: 1, svg_url: null }, { round: 2, svg_url: null }] },
    { label: "pipeline_stages", number: 3, type: "pipeline", engine: "image-model", grounding: "image-cond", ref: "arxiv:2005.11401#fig1", critic_rounds: 2, svg_rounds: 4, audit_ok: true,
      caption: "The nine ordered stages — route, plan, cite, write, refine, review, figures, latex, experiment — each sealing its own roll-call before the next begins.",
      formats: ["pdf", "svg", "png"], files: { png: null, svg: null, pdf: null },
      prompt: figPrompt("A horizontal pipeline of nine chevron stages with a seal stamp under each, densely labelled.", "arxiv:2005.11401#fig1"),
      audit: { cleanliness: 0.95, min_text_px: 11.2, texts: 61, shapes: 88, warnings: ["2 labels below 12px — nudged on round 4"] },
      versions: [{ round: 1, svg_url: null }, { round: 2, svg_url: null }, { round: 3, svg_url: null }, { round: 4, svg_url: null }] },
    { label: "gate_flow", number: 4, type: "diagram", engine: "image-model", grounding: "image-cond", ref: "arxiv:2210.08726#fig1", critic_rounds: 2, svg_rounds: 2, audit_ok: true,
      caption: "Integrity as a build gate: a fabricated number or a hallucinated citation is a build-breaking error, not a post-hoc style note.",
      formats: ["pdf", "svg", "png"], files: { png: null, svg: null, pdf: null },
      prompt: figPrompt("A decision diagram: a manuscript entering a gate, red fail edge looping back, green pass edge continuing.", "arxiv:2210.08726#fig1"),
      audit: { cleanliness: 0.97, min_text_px: 12.8, texts: 35, shapes: 44, warnings: [] },
      versions: [{ round: 1, svg_url: null }, { round: 2, svg_url: null }] },
    { label: "hybrid_engine", number: 5, type: "pipeline", engine: "image-model", grounding: "image-cond", ref: "arxiv:2111.15664#fig1", critic_rounds: 2, svg_rounds: 5, audit_ok: true,
      caption: "The editable-vector figure engine: an image-model raster is decomposed, re-rendered and re-overlaid with editable text — camera-ready without a lossy full redraw.",
      formats: ["pdf", "svg", "png"], files: { png: null, svg: null, pdf: null },
      prompt: figPrompt("A two-track hybrid: a raster path and a text-overlay path merging into one editable figure.", "arxiv:2111.15664#fig1"),
      audit: { cleanliness: 0.93, min_text_px: 10.6, texts: 76, shapes: 121, warnings: ["dense glyph cluster near legend — 5 redraw rounds to converge"] },
      versions: [{ round: 1, svg_url: null }, { round: 2, svg_url: null }, { round: 3, svg_url: null }, { round: 4, svg_url: null }, { round: 5, svg_url: null }] },
    { label: "quality_stack", number: 6, type: "concept", engine: "image-model", grounding: "vision-distill", ref: "vision-distill:layered-stack-convention", critic_rounds: 2, svg_rounds: 3, audit_ok: true,
      caption: "The quality stack: deterministic lint at the base, model-judgment review above it, human-required decisions at the top — each layer catching what the one below cannot.",
      formats: ["pdf", "svg", "png"], files: { png: null, svg: null, pdf: null },
      prompt: figPrompt("A layered concept stack of three horizontal bands, widest at the base, labelled by the assurance each layer adds.", "vision-distill:layered-stack-convention"),
      audit: { cleanliness: 0.9, min_text_px: 12.0, texts: 44, shapes: 39, warnings: ["1 overlap resolved on round 3"] },
      versions: [{ round: 1, svg_url: null }, { round: 2, svg_url: null }, { round: 3, svg_url: null }] },
    { label: "qualitative_figure", number: 7, type: "qualitative", engine: "image-model", grounding: "vision-distill", ref: "vision-distill:before-after-illustration", critic_rounds: 2, svg_rounds: null, audit_ok: null,
      caption: "Before / after: a raw image-model raster beside its decomposed editable-vector counterpart, showing the text that became selectable.",
      formats: ["png"], files: { png: null, svg: null, pdf: null },
      prompt: figPrompt("A side-by-side before/after panel, a dashed divider down the middle, one circled detail on each side.", "vision-distill:before-after-illustration"),
      audit: null,
      versions: [] }
  ];

  // LEDGER.json (schema-faithful; Spark-to-Paper directions)
  var LEDGER = {
    budget: { gpu_hours_cap: 40.0, gpu_hours_spent: 18.0, outer_rounds_cap: 12, outer_round: 3, round_run_cap: 4 },
    directions: { D1: "converged", D2: "active" },
    runs: [
      { id: "D1-figeng-a", dir: "D1", status: "accepted", gpu_h_actual: 6.0, spend_basis: "sacct", job_id: "4180463", host: "a40", verdict_ref: "council:1" },
      { id: "D1-figeng-b", dir: "D1", status: "done", gpu_h_actual: 2.0, spend_basis: "sacct", job_id: "4180988", host: "a40", verdict_ref: null },
      { id: "D2-gates-a", dir: "D2", status: "done", gpu_h_actual: 8.0, spend_basis: "sacct", job_id: "4181902", host: "a40", verdict_ref: null },
      { id: "D2-gates-b", dir: "D2", status: "running", gpu_h_actual: 2.0, spend_basis: "wall-clock-declared", job_id: "4182550", host: "a40", verdict_ref: null }
    ],
    councils: [{ id: "council:1", topic: "D1-terminal", families: "systems,vision", kind: "terminal", verdict: "accept" }],
    scoped_accepts: [{ dir: "D1", claim: "C4", scope: "image-model schematic set, hybrid path on A40", basis: "council:1" }]
  };

  // logs/seals/*  — STAGES order NN: plan21 cite22 write23 refine24 review25 latex26 final27 deliver30
  var SEALS = [
    { stage: "plan", nn: 21, state: "sealed", ts: "2026-08-18T07:12Z", rollcall: [
      { id: "blueprint-present", cls: "integrity", status: "present", artifact: "blueprint.json" },
      { id: "contributions-enumerated", cls: "integrity", status: "present", artifact: "blueprint.json#contributions" },
      { id: "terminology-frozen", cls: "integrity", status: "present", artifact: "blueprint.json#terminology" },
      { id: "proposal-readable", cls: "ceremony", status: "present", artifact: "proposal.md" } ] },
    { stage: "cite", nn: 22, state: "sealed", ts: "2026-08-18T07:41Z", rollcall: [
      { id: "refs-resolve", cls: "integrity", status: "present", artifact: "refs.bib · 46/46" },
      { id: "no-orphan-cites", cls: "integrity", status: "present", artifact: "citations_lint" },
      { id: "per-section-floor", cls: "ceremony", status: "present", artifact: "cites_per_section" } ] },
    { stage: "write", nn: 23, state: "sealed", ts: "2026-08-18T08:55Z", rollcall: [
      { id: "sections-present", cls: "integrity", status: "present", artifact: "sections/*.tex · 9" },
      { id: "word-budget", cls: "ceremony", status: "present", artifact: "6.3k–10.4k words" },
      { id: "notation-table", cls: "ceremony", status: "waived", artifact: "require_notation_table=false" } ] },
    { stage: "refine", nn: 24, state: "sealed", ts: "2026-08-18T09:20Z", rollcall: [
      { id: "ai-tell-scrub", cls: "integrity", status: "present", artifact: "draft_lint" },
      { id: "terminology-coherent", cls: "ceremony", status: "present", artifact: "self-review" } ] },
    { stage: "review", nn: 25, state: "halt", ts: "2026-08-18T09:48Z", rollcall: [
      { id: "adversarial-loop-dry", cls: "integrity", status: "present", artifact: "logs/5_review.io.md" },
      { id: "author-required-cleared", cls: "integrity", status: "missing", artifact: "1 open: fabricated-magnitude" } ] },
    { stage: "latex", nn: 26, state: "unsealed", ts: null, rollcall: [] },
    { stage: "final", nn: 27, state: "unsealed", ts: null, rollcall: [] },
    { stage: "deliver", nn: 30, state: "unsealed", ts: null, rollcall: [] }
  ];

  // DECISION_QUEUE.jsonl rows (open) + terminal state
  var DQ = {
    open: [
      { id: "dq-0007", type: "ask-baseline-parity", finding: "RQ4 efficiency: the micro-call orchestration baseline was run with a different model tier than the whole-context arm. Confirm the intended comparison before the cost table is locked.", pointer: "logs/5_review.io.md#L212 · results.facts.json:rq4_cost", reversal_cost: "expensive", resume: "/ts-run decide dq-0007 --hold", reverse: "/ts-run reverse dq-0007" },
      { id: "dq-0008", type: "ask-citation", finding: "One reference resolved through an arXiv alias (2308.08155 → published venue). Keep the alias or swap to the camera-ready bibkey?", pointer: "refs.bib:wu2023autogen", reversal_cost: "cheap", resume: "/ts-run decide dq-0008 --keep-alias", reverse: "/ts-run reverse dq-0008" }
    ],
    state: "PENDING_REVIEW", dispositioned: 6, total: 8
  };

  // Claim ledger (EVIDENCE.md 信念状态) — C-ids × status + provenance
  var CLAIMS = [
    { id: "C1", dir: "D2", status: "supported", since: "run:D2-gates-a", margin: "20pp / 46 refs / 7 figs @facts", provenance: "results.facts.json:rq3_end_to_end", note: "end-to-end run produced a complete compiled manuscript" },
    { id: "C2", dir: "D2", status: "supported", since: "council:1", margin: "2 regimes @report", provenance: "report.html:routing", note: "results_mode flips numbers + tense rules" },
    { id: "C3", dir: "D2", status: "supported", since: "run:D2-gates-a", margin: "7/8 @facts", provenance: "results.facts.json:rq2_integrity_gates", note: "full stack caught 7/8 fabrications, 3/3 citation probes, 0 false alarms" },
    { id: "C3.a", dir: "D2", status: "refuted", since: "run:D2-gates-a", margin: "word-form escaped", provenance: "results.facts.json:notes", note: "deterministic audit alone misses word-form magnitude; deferred to model-judgment layer" },
    { id: "C4", dir: "D1", status: "supported", since: "council:1", margin: "SSIM 0.93 · 6 vector figs @facts", provenance: "results.facts.json:rq1_figure_engine_ssim", note: "hybrid path, scoped accept on the A40 schematic set" }
  ];

  // FRONTIER.md — dead-ends / negative knowledge
  var DEADENDS = [
    { id: "DE-1", dir: "D1", run: "D1-figeng-b", support: "explicit", hypothesis: "A full vector redraw reconstructs dense schematics faithfully.", failure_mode: "Needs an external account and degrades dense figures (thin lines, dropped glyphs).", lesson: "Hybrid render-plus-overlay, or else keep the high-resolution PNG — never a lossy redraw." },
    { id: "DE-2", dir: "D2", run: "D2-gates-a", support: "inferred", hypothesis: "A single deterministic audit can catch every fabricated number.", failure_mode: "Word-form magnitudes (“doubled”, “halved”) carry no digits for the regex audit to bind.", lesson: "Route word-form magnitude claims to the model-judgment layer; keep the digit audit as the build gate." }
  ];

  // Gates / LaTeX QA (logs/index.md + build_report collectors)
  var GATES = {
    checks: [
      { check: "no-fabrication audit", cls: "integrity", status: "ok" },
      { check: "citation completeness", cls: "integrity", status: "ok" },
      { check: "AI-tell scrub", cls: "ceremony", status: "ok" },
      { check: "figure vector gate", cls: "integrity", status: "ok" },
      { check: "zero-LaTeX-error", cls: "integrity", status: "ok" }
    ],
    latex: { verdict: "ok", pages: 20, errors: 0, undefined: 0, overfull: 3, bib_entries: 46, bytes: 5717980 },
    draft_lint: { ok: true, n_issues: 0, n_warnings: 2 },
    citations_lint: { ok: true, n_cited: 46, n_issues: 0 }
  };

  // E14-metrics.jsonl aggregate — cross-run behavioural analytics
  var E14 = {
    runs: [
      { run_id: "r-08-11", ended_by: "auto-terminal", best_tier: "PRELIMINARY_STUDY" },
      { run_id: "r-08-13", ended_by: "stall", best_tier: "TECHNICAL_REPORT" },
      { run_id: "r-08-15", ended_by: "principal-collect", best_tier: "FULL_PAPER" },
      { run_id: "r-08-18", ended_by: "export-complete", best_tier: "FULL_PAPER" }
    ],
    reversal_rate_by_class: [
      { cls: "figure", delegated: 12, reversals: 1, rate: 0.08 },
      { cls: "cite", delegated: 46, reversals: 2, rate: 0.04 },
      { cls: "number", delegated: 8, reversals: 0, rate: 0.00 }
    ],
    postproc_trend: { integrity: [3, 4, 5, 5], ceremony: [2, 2, 3, 4] },
    upstream_todos: []
  };

  // The run "stage tape" (fixed 9 nodes) + live-feeling narration/apparatus/shelf.
  var STAGE_NODES = ["Route", "Plan", "Cite", "Write", "Refine", "Review", "Figures", "LaTeX", "Experiment"];
  // A representative per-stage token profile for the SAMPLE cockpit's heatmap — keyed by
  // the runner's "<n> <stage>" label shape ({stage: {in, out}}), so the SAME stageHeatProfile
  // path that folds a real telemetry.per_stage folds this. Flagged 示例 wherever it surfaces;
  // never used for a genuine run (those carry their own per_stage, or an honest "not captured").
  var SAMPLE_PER_STAGE = {
    "0 route": { in: 8200, out: 1400 }, "1 plan": { in: 42000, out: 9800 },
    "2 cite": { in: 61000, out: 7200 }, "3 write": { in: 214000, out: 48600 },
    "4 refine": { in: 96000, out: 22400 }, "5 review": { in: 172000, out: 15400 },
    "6 figures": { in: 88000, out: 12600 }, "7 latex": { in: 39000, out: 6100 },
    "8 experiment": { in: 54000, out: 8300 }
  };
  var RUN = {
    now_index: 5,                 // Review is lit
    done_through: 4,              // Route..Refine sealed
    status: "Hardening the draft against 2 adversarial-review issues — one author-required (fabricated ablation magnitude), one auto-fixable (an undefined symbol in Eq. 3).",
    telemetry: { model: "claude-opus (headless)", turns: 214, tok_in: "1.28M", tok_out: "96.4k", cost: "$4.82", duration: "38m 12s", started: "2026-08-18 09:10" },
    narration: [
      { t: "09:47", s: "Reviewer R2 flags an ablation delta stated as “roughly doubled” — no digits, so the audit can't bind it. Escalating as author-required rather than inventing a number." },
      { t: "09:46", s: "Verbatim-quote anti-skim over §5 passed; the adversarial loop is dry except for the one magnitude claim." },
      { t: "09:44", s: "Patched the undefined \\lambda in Eq. 3 to \\alpha to match the notation table; recompiling to confirm 0 undefined." }
    ],
    apparatus: [
      { tool: "Read", arg: "sections/evaluation.tex:198-232", out: "loaded 34 lines" },
      { tool: "Bash", arg: "python scripts/draft_lint.py --facts results.facts.json", out: "ok · 0 issues · 2 warnings" },
      { tool: "Edit", arg: "sections/pipeline.tex  \\lambda → \\alpha", out: "1 replacement" },
      { tool: "Bash", arg: "latexmk -pdf main.tex", out: "20 pp · 0 errors · 3 overfull" },
      { tool: "Bash", arg: "python scripts/citations_lint.py", out: "46 cited · 0 orphan" }
    ],
    shelf: [
      { label: "sections/pipeline.tex", note: "edited · λ→α", state: "ok" },
      { label: "main.pdf", note: "rebuilt · 20 pp", state: "ok" },
      { label: "logs/5_review.io.md", note: "1 author-required", state: "wait" },
      { label: "refs.bib", note: "46 entries · resolved", state: "ok" }
    ],
    waiting: "dq-0007 — RQ4 efficiency: confirm the micro-call baseline's model tier before I lock the cost table. Reply in the Claude chat."
  };

  // Feed (Runs list). The primary run is Spark-to-Paper; the others are toy
  // sibling stories on disk (a toaster-firmware story.json fixture + a negative result).
  var FEED = [
    { id: "spark-to-paper", title: STORY.title, prev: "Zero-infrastructure agent-skill suite; integrity as a build gate; editable-vector figures. Now hardening review.", src: "story.json · FULL_PAPER", date: "2026-08-18", sel: true, star: true, unread: true },
    { id: "toaster-firmware", title: "Scope-Constrained Full-Recheck Calibration for Toaster Firmware", prev: "An external authority freezes the calibration scope; an independent full recheck runs after every firmware tweak.", src: "story.json · PRELIMINARY_STUDY", date: "2026-08-16", sel: false, star: false, unread: true },
    { id: "neg-scorchspot", title: "Negative result: a single color sensor can't catch uneven scorch spots", prev: "The single-point color probe has nothing to bind to; the claim is routed to the panel-judgment layer with a logged lesson.", src: "FRONTIER.md", date: "2026-08-15", sel: false, star: false, unread: false }
  ];

  /* =========================================================================
     LIVE DATA WIRING — real on-disk JSON via SB.data, sample fallback per field
     The render fns read module globals (STORY/BLUEPRINT/FACTS/FIGURES/LEDGER/…).
     We keep the beautiful SAMPLE as the default and, when a directory is opened,
     MAP the adapter JSON onto those SAME globals (sample-fallback per missing
     field), then run the UNCHANGED render. A subtle "reading <dir>" vs "sample"
     hint is shown per view. Live globals are REASSIGNED (never mutated), so the
     frozen SAMPLE snapshot below always survives to fall back to.
     ========================================================================= */
  var SAMPLE = {
    STORY: STORY, BLUEPRINT: BLUEPRINT, SECTIONS: SECTIONS, FACTS: FACTS, FIGURES: FIGURES,
    LEDGER: LEDGER, SEALS: SEALS, DQ: DQ, CLAIMS: CLAIMS, DEADENDS: DEADENDS, GATES: GATES,
    E14: E14, RUN: RUN, FEED: FEED
  };
  var MAST = null, FRESH = null, GOV_TIER = null, READING_PROP = null;
  // FLAT-spark honesty flags (guarded — set only when the backend flags are present):
  //   GOV_FLAT — this run is a linear pipeline (no .research/ engine) → governance is N/A,
  //     an honest one-line note replaces the sample dashboard (distinct from couldNotRead).
  //   FACTS_PROPOSAL — proposal-mode run with no measured results yet → the facts card is
  //     labelled instead of showing SAMPLE RQ numbers.
  var GOV_FLAT = false, FACTS_PROPOSAL = false;

  // R1 — field-scoped hydration registry. Each flag says "THIS data family came from the
  // opened run, not the built-in sample". Render code gates every real-looking number on
  // its own family's flag, so one hydrated field can never bless a whole view's numbers.
  function freshHyd() { return { report: false, story: false, facts: false, figures: false, gov: false, gates: false, prop: false }; }
  var HYD = freshHyd();

  function resetLive() {
    STORY = SAMPLE.STORY; BLUEPRINT = SAMPLE.BLUEPRINT; SECTIONS = SAMPLE.SECTIONS;
    FACTS = SAMPLE.FACTS; FIGURES = SAMPLE.FIGURES; LEDGER = SAMPLE.LEDGER; SEALS = SAMPLE.SEALS;
    DQ = SAMPLE.DQ; CLAIMS = SAMPLE.CLAIMS; DEADENDS = SAMPLE.DEADENDS; GATES = SAMPLE.GATES;
    E14 = SAMPLE.E14; MAST = null; FRESH = null; GOV_TIER = null; READING_PROP = null;
    GOV_FLAT = false; FACTS_PROPOSAL = false;
    HYD = freshHyd();
  }

  /* ---- R1 honesty primitives ------------------------------------------------
     dirOpen(): a real run directory is pointed at (vs the genuine no-dir demo).
     honest(hyd,v): print a value only when its own family hydrated, OR when there is
       no dir at all (the silent-sample demo, where showing the beautiful numbers is
       honest). When a dir IS open but the field fell back to sample, degrade to "—"
       so a sample number is never attributed to the user's run. */
  function dirOpen() { try { return !!SB.data.dir("spark"); } catch (e) { return false; } }
  function honest(hyd, v) { return (hyd || !dirOpen()) ? (v == null ? "—" : v) : "—"; }

  // provenance chip for a view header: green "reading <dir>" when the view hydrated;
  // nothing when a dir is open but the view is sample (a full-width amber banner carries
  // that instead); the quiet "sample" pill only in the genuine no-dir case.
  function provChip(real) {
    if (real) return srcHint(true);
    // item1b — a dir is open but this view is sample: keep a PERSISTENT sample marker in the
    // header (was ""), so it survives the amber banner's dismissal — the way Runs/Wiki keep a
    // standing chip. The full-width amber banner still carries the louder note above.
    if (dirOpen()) return sampleChip();
    return srcHint(false);
  }
  // full-width amber banner shown when a real dir is open but a view/field is sample.
  function sampleBannerHTML(nounZh, nounEn) {
    var zh = lang() === "zh";
    var rs = SB.data.readState ? SB.data.readState("spark") : null;
    var cnr = !!(rs && rs.couldNotRead && !rs.dismissed);
    var d = ""; try { d = SB.data.dir("spark"); } catch (e) {}
    var head, sub;
    if (cnr) {
      // item20f — unify the degrade noun to directory/目录 across both languages (en said "run").
      head = zh ? "读不到这个目录" : "Couldn't read this directory";
      // R23 — echo the FULL user-supplied dir string (the basename can read like "none"
      // → looks null); Wiki is the reference impl for showing the whole path.
      sub = (zh ? "无法读取 " : "couldn't read ") + esc(d || (zh ? "(未指定目录)" : "(no directory)")) + (zh ? " —— 下方为示例。" : " — showing sample.");
    } else {
      head = zh ? ("此运行暂无" + nounZh + "数据") : ("No " + nounEn + " for this run");
      sub = zh ? "下方为示例,不代表本运行" : "showing sample, not this run";
    }
    return '<div class="sample-banner' + (cnr ? " cnr" : "") + '" role="status">' +
      '<span class="sb-ic">' + ic("sp-warn") + '</span>' +
      '<div class="sb-tx"><b>' + head + '</b><span>' + sub + '</span></div>' +
      (cnr ? '<button class="btn sm ghost" data-sb-dismiss>' + (zh ? "知道了" : "Dismiss") + '</button>' : "") +
      '</div>';
  }
  function wireSampleBanner(scope) {
    var b = scope && $("[data-sb-dismiss]", scope); if (!b) return;
    b.onclick = function () {
      if (SB.data.dismissRead) SB.data.dismissRead("spark");
      var bn = b.closest ? b.closest(".sample-banner") : null; if (bn) bn.remove();
    };
  }
  // a small green "this run" chip for a single card whose field IS real while the view
  // as a whole shows the amber sample banner (field-scoped truth for the exceptions).
  function cardRealChip(hyd) {
    if (!(hyd && dirOpen())) return "";
    var d = ""; try { d = SB.data.dir("spark"); } catch (e) {}
    return '<span class="src-hint live card-prov" title="' + esc(d) + '">' + ic("sp-hash", "sm") +
      (lang() === "zh" ? "本运行" : "this run") + '</span>';
  }

  /* ---- path / fetch / hint helpers -------------------------------------- */
  function joinPath(dir, rel) { if (!dir) return rel; return String(dir).replace(/[\\/]+$/, "") + "/" + rel; }
  function fileUrl(rel) { return "/api/file?path=" + encodeURIComponent(joinPath(SB.data.dir("spark"), rel)); }
  function fetchText(url) { return fetch(url).then(function (r) { if (!r.ok) throw 0; return r.text(); }); }
  function dirName(p) { if (!p) return ""; return String(p).replace(/[\\/]+$/, "").split(/[\\/]/).pop(); }
  // R28 — the persistent sample-provenance chip. One standard word ('示例数据' / 'Sample')
  // shared with the Jury/Wiki siblings; '读取' as the live verb (was '实读').
  function sampleChip() {
    return '<span class="src-hint sample">' + (lang() === "zh" ? "示例数据" : "Sample") + '</span>';
  }
  function srcHint(real) {
    var d = SB.data.dir("spark");
    if (real && d) return '<span class="src-hint live" title="' + esc(d) + '">' + ic("sp-hash", "sm") +
      (lang() === "zh" ? "读取 " : "reading ") + esc(dirName(d)) + '</span>';
    return sampleChip();
  }
  // the runs view reads a LIVE subprocess (not a static dir): name its own workdir.
  // R1 — the green "live <workdir>" badge is earned by a GENUINE run poll only. A
  // couldn't-read state, OR the built-in FEED sample (which carries workdir='bench'),
  // falls through to the neutral sample chip: workdir PRESENCE alone must never light it.
  function liveHint(d) {
    if (runIsSample(d)) return sampleChip();
    var wd = dirName(d.workdir);
    return '<span class="src-hint live" title="' + esc(d.workdir) + '">' + ic("sp-hash", "sm") +
      (lang() === "zh" ? "实时 " : "live ") + esc(wd) + '</span>';
  }
  // item10 — the live/sample chip is driven by the TRANSCRIPT's own provenance (a genuine
  // /api/run poll carries a real workdir and no sample flag), NOT the unrelated dir-read side
  // channel. A dir that could not be read no longer relabels a byte-identical live run 'Sample';
  // instead renderRuns/paintSampleRun DEGRADE the whole body to the built-in sample (see
  // sparkCouldNotRead), so the banner and the data below always describe the same run.
  function runIsSample(d) {
    return !d || !d.workdir || d.sample === true;
  }
  // item10 — a real run directory was pointed at but could not be read. When true, the Runs
  // cockpit degrades to the built-in sample rather than polling a live subprocess and then
  // mislabeling it over the dir side channel.
  function sparkCouldNotRead() {
    try { var rs = SB.data && SB.data.readState ? SB.data.readState("spark") : null; return !!(rs && rs.couldNotRead); } catch (e) { return false; }
  }

  /* ---- shared run/telemetry utils (mirror the legacy cockpit) ------------ */
  var TERMINAL = { done: 1, error: 1, stopped: 1 };
  var STAGE_LABELS = ["Route", "Plan", "Cite", "Write", "Refine", "Review", "Figures", "LaTeX", "Experiment"];
  function parseStage(str) {
    var s = String(str == null ? "" : str).trim();
    var m = /^(\d+)\s+(.+)$/.exec(s);
    if (m) { var i = parseInt(m[1], 10); return { idx: Math.max(0, Math.min(8, i)), name: m[2] }; }
    if (!s || s === "not started") return { idx: -1, name: "" };
    return { idx: -1, name: s };
  }
  function toMs(v) { if (v == null || v === "") return null; if (typeof v === "number") return v > 1e11 ? v : v * 1000; var n = Date.parse(v); return isNaN(n) ? null : n; }
  function clock(v) { var ms = toMs(v); if (!ms) return ""; var d = new Date(ms); return pad2(d.getHours()) + ":" + pad2(d.getMinutes()); }
  function compact(sec) { var s = Math.max(0, Math.round(sec)), h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60); return h ? h + "h" + pad2(m) : m + "m"; }
  function tokfmt(n) { if (n == null) return "—"; n = Number(n) || 0; if (n >= 1e6) return (n / 1e6).toFixed(1) + "M"; if (n >= 1e4) return (n / 1e3).toFixed(1) + "k"; return n.toLocaleString("en-US"); }
  function money(v) { return v == null ? "—" : "$" + Number(v).toFixed(2); }
  function fmtStarted(v) {
    var ms = toMs(v); if (!ms) return "—"; var d = new Date(ms);
    var base = d.getFullYear() + "-" + pad2(d.getMonth() + 1) + "-" + pad2(d.getDate()) + " " + pad2(d.getHours()) + ":" + pad2(d.getMinutes());
    // item11 — append the shell's relative-time ('· N 天前' / '· Nd ago') when SB.relTime is exposed.
    var rel = ""; try { if (SB.relTime) { var r = SB.relTime(d.toISOString()); if (r) rel = " · " + r; } } catch (e) {}
    return base + rel;
  }
  function cap1(s) { s = String(s || ""); return s ? s.charAt(0).toUpperCase() + s.slice(1) : s; }

  /* ---- tiny markdown → HTML (proposal.md reader body + run narration) ---- */
  function inlineMd(s) {
    return esc(s)
      .replace(/`([^`]+)`/g, "<code>$1</code>")
      .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
      .replace(/(^|[\s(])\*([^*\s][^*]*?)\*(?=[\s.,;:)]|$)/g, "$1<em>$2</em>");
  }
  function proseLite(t) { return inlineMd(t).replace(/\n{2,}/g, "<br><br>").replace(/\n/g, "<br>"); }
  function mdArticle(md) {
    var lines = String(md).replace(/\r\n?/g, "\n").split("\n"), out = [], para = [], list = null, firstH1 = true;
    function flushPara() { if (para.length) { out.push("<p>" + inlineMd(para.join(" ")) + "</p>"); para = []; } }
    function flushList() { if (list) { out.push("<ul>" + list.map(function (li) { return "<li>" + inlineMd(li) + "</li>"; }).join("") + "</ul>"); list = null; } }
    for (var i = 0; i < lines.length; i++) {
      var t = lines[i].trim(), h = t.match(/^(#{1,6})\s+(.*)$/);
      if (h) {
        flushPara(); flushList();
        var lvl = h[1].length, txt = h[2].replace(/:$/, "");
        if (lvl === 1 && firstH1) { firstH1 = false; continue; }   // the H1 title is already the reader <h1>
        var tag = lvl <= 2 ? "h2" : "h3";
        out.push("<" + tag + ">" + inlineMd(txt) + "</" + tag + ">");
        continue;
      }
      var li = t.match(/^[-*+]\s+(.*)$/);
      if (li) { flushPara(); (list = list || []).push(li[1]); continue; }
      if (!t) { flushPara(); flushList(); continue; }
      if (list) { list[list.length - 1] += " " + t; continue; }
      para.push(t);
    }
    flushPara(); flushList();
    return out.join("");
  }

  /* ---- adapter JSON → module-global shapes (sample fallback per field) --- */
  function parseContrib(s) {
    var m = String(s).match(/^\s*(C\d+(?:\.\w+)?)\s*[:.\-]\s*([\s\S]*)$/);
    return m ? { id: m[1], text: m[2].trim() } : { id: "", text: String(s).trim() };
  }
  function shortTemplate(t) { return String(t || "").split("·")[0].split("—")[0].split("|")[0].trim() || "template"; }

  function hydrateReport(rep) {
    if (!rep || !rep.available || !rep.panels) return false;
    var p = rep.panels; MAST = p.masthead || null; FRESH = p.freshness || null;
    var bp = p.blueprint, m = MAST || {};
    if (bp && bp.present) {
      var contribs = (bp.contributions && bp.contributions.length) ? bp.contributions.map(parseContrib) : SAMPLE.BLUEPRINT.contributions;
      var kw = Array.isArray(bp.keywords) ? bp.keywords : (bp.keywords ? String(bp.keywords).split(/,\s*/) : SAMPLE.BLUEPRINT.keywords);
      BLUEPRINT = {
        paper_title: bp.paper_title || SAMPLE.BLUEPRINT.paper_title,
        keywords: kw, contributions: contribs, method_name: SAMPLE.BLUEPRINT.method_name,
        template: {
          display_name: m.template ? shortTemplate(m.template) : SAMPLE.BLUEPRINT.template.display_name,
          official: m.official != null ? m.official : SAMPLE.BLUEPRINT.template.official,
          results_mode: m.results_mode || SAMPLE.BLUEPRINT.template.results_mode
        },
        sections: bp.n_sections || SAMPLE.BLUEPRINT.sections, word_target: SAMPLE.BLUEPRINT.word_target,
        figures_planned: SAMPLE.BLUEPRINT.figures_planned, tables_planned: SAMPLE.BLUEPRINT.tables_planned,
        notation_entries: bp.n_notation || SAMPLE.BLUEPRINT.notation_entries
      };
    }
    return true;
  }
  function hydrateStory(st) {
    if (!st || typeof st !== "object" || !st.title) return false;
    STORY = {
      title: st.title || SAMPLE.STORY.title,
      spark_sentence: st.solution || st.problem_framing || SAMPLE.STORY.spark_sentence,
      problem_framing: st.problem_framing || SAMPLE.STORY.problem_framing,
      gap_pattern: st.gap_pattern || SAMPLE.STORY.gap_pattern,
      solution: st.solution || SAMPLE.STORY.solution,
      innovation_claims: (st.innovation_claims && st.innovation_claims.length) ? st.innovation_claims : SAMPLE.STORY.innovation_claims,
      origin: st.origin || SAMPLE.STORY.origin
    };
    return true;
  }
  function hydrateFacts(f) {
    if (!f || typeof f !== "object" || !Object.keys(f).length) return false;
    // FLAT/proposal contract: results.facts.json absent AND proposal mode →
    // {found:false, mode:"proposal"}. Flag it and DON'T hydrate (so the card labels
    // itself instead of falling back to SAMPLE RQ numbers under a "real" chip). Guarded:
    // any other payload keeps today's behavior. Reset here so a later real run clears it.
    FACTS_PROPOSAL = (f.mode === "proposal");
    if (FACTS_PROPOSAL) return false;
    var S = SAMPLE.FACTS;
    FACTS = {
      rq1_figure_engine_ssim: f.rq1_figure_engine_ssim || S.rq1_figure_engine_ssim,
      rq1_editable_text_boxes: f.rq1_editable_text_boxes || S.rq1_editable_text_boxes,
      rq1_runtime_seconds: f.rq1_runtime_seconds || S.rq1_runtime_seconds,
      rq2_integrity_gates: f.rq2_integrity_gates || S.rq2_integrity_gates,
      rq3_end_to_end: f.rq3_end_to_end || S.rq3_end_to_end, notes: f.notes || S.notes
    };
    return true;
  }
  // /api/spark/figures?path=<run> → normalized showcase shape (module-global FIGURES).
  // The endpoint already gives file/version URLs as /api/file?path=… so they are used
  // verbatim; formats is derived from which of files.{png,svg,pdf} actually exist. No
  // per-figure SSIM is emitted by the endpoint and none is synthesized here.
  function hydrateRichFigures(resp) {
    var items = resp && resp.figures;
    if (!items || !items.length) return false;
    FIGURES = items.map(function (it) {
      var files = it.files || {};
      var fmts = ["pdf", "svg", "png"].filter(function (x) { return !!files[x]; });
      return {
        label: it.label, number: it.number, caption: it.caption || "",
        type: it.type, engine: it.engine, grounding: it.grounding, ref: it.ref,
        critic_rounds: it.critic_rounds, svg_rounds: it.svg_rounds,
        // item12 — keep the 3-state: null/undefined → N/A, true → pass, false → real failure.
        audit_ok: (it.audit_ok == null ? null : it.audit_ok === true),
        formats: fmts, files: { png: files.png || null, svg: files.svg || null, pdf: files.pdf || null },
        prompt: (typeof it.prompt === "string" && it.prompt.trim()) ? it.prompt : null,
        audit: (it.audit && typeof it.audit === "object") ? it.audit : null,
        versions: Array.isArray(it.versions) ? it.versions : []
      };
    });
    return true;
  }
  var STAGE_SEQ = [["plan", 21], ["cite", 22], ["write", 23], ["refine", 24], ["review", 25], ["latex", 26], ["final", 27], ["deliver", 30]];
  function mapSeals(so) {
    var seals = (so && so.seals) || [], byNo = {};
    seals.forEach(function (s) { byNo[s.stage_no] = s; });
    return STAGE_SEQ.map(function (pair) {
      var s = byNo[pair[1]];
      if (s) return { stage: pair[0], nn: pair[1], state: "sealed", ts: s.ts,
        rollcall: ((s.rollcall && s.rollcall.rows) || []).map(function (r) { return { id: r.id, cls: r["class"], status: r.status, artifact: r.artifact }; }) };
      return { stage: pair[0], nn: pair[1], state: "unsealed", ts: null, rollcall: [] };
    });
  }
  function aggregateE14(rows) {
    if (!rows || !rows.length) return null;
    var runs = rows.map(function (r) { return { run_id: r.run_id, ended_by: r.ended_by, best_tier: r.best_tier_at_end }; });
    var deleg = {}, rev = {};
    rows.forEach(function (r) {
      var d = r.delegated_outcomes || {}, m = r.manual_reversals || {};
      Object.keys(d).forEach(function (k) { deleg[k] = (deleg[k] || 0) + (d[k] || 0); });
      Object.keys(m).forEach(function (k) { rev[k] = (rev[k] || 0) + (m[k] || 0); });
    });
    var cls = {}; Object.keys(deleg).forEach(function (k) { cls[k] = 1; }); Object.keys(rev).forEach(function (k) { cls[k] = 1; });
    var rrbc = Object.keys(cls).map(function (k) { var dl = deleg[k] || 0, rv = rev[k] || 0; return { cls: k, delegated: dl, reversals: rv, rate: dl ? rv / dl : 0 }; });
    var integ = rows.map(function (r) { return r.postproc_integrity; }).filter(function (v) { return v != null; });
    var cere = rows.map(function (r) { return r.postproc_ceremony; }).filter(function (v) { return v != null; });
    return {
      runs: runs, reversal_rate_by_class: rrbc.length ? rrbc : SAMPLE.E14.reversal_rate_by_class,
      postproc_trend: {
        integrity: integ.length >= 2 ? integ : SAMPLE.E14.postproc_trend.integrity,
        ceremony: cere.length >= 2 ? cere : SAMPLE.E14.postproc_trend.ceremony
      }, upstream_todos: []
    };
  }
  function hydrateGovernance(gov) {
    if (!gov || !gov.found) return false;
    var led = gov.ledger || {};
    LEDGER = {
      budget: led.budget || SAMPLE.LEDGER.budget, directions: led.directions || {}, runs: led.runs || [],
      councils: led.councils || [], scoped_accepts: led.scoped_accepts || []
    };
    SEALS = mapSeals(gov.seals);
    var dc = gov.decisions || {}, cn = dc.counts || {};
    DQ = {
      open: (dc.open || []).map(function (d) {
        return { id: d.id, type: d.type, finding: d.finding || "", pointer: d.pointer || "",
          reversal_cost: d.reversal_cost || "cheap", resume: d.resume || "", reverse: d.reverse || "" };
      }),
      state: dc.state || "PENDING_REVIEW",
      dispositioned: (cn.decisions != null ? cn.decisions - (cn.open || 0) : 0),
      total: (cn.decisions != null ? cn.decisions : (dc.open ? dc.open.length : 0)) || 1
    };
    if (gov.claims && gov.claims.rows && gov.claims.rows.length) {
      CLAIMS = gov.claims.rows.map(function (c) {
        return { id: c.id, dir: c.dir, status: c.status, since: c.since,
          margin: c.margin && c.margin !== "-" ? c.margin : "—",
          provenance: c.provenance && c.provenance !== "-" ? c.provenance : (c.facts || "—"),
          note: c.since ? ("since " + c.since) : "" };
      });
    }
    if (gov.deadends && gov.deadends.entries && gov.deadends.entries.length) {
      DEADENDS = gov.deadends.entries.map(function (e) {
        return { id: e.id, dir: e.dir, run: e.run, support: e.support,
          hypothesis: e.hypothesis || "—", failure_mode: e.failure_mode || "—", lesson: e.lesson || "—" };
      });
    }
    var e = aggregateE14(gov.e14); if (e) E14 = e;
    GOV_TIER = gov.tier || null;
    return true;
  }
  function hydrateGates(rep) {
    if (!rep || !rep.available || !rep.panels) return false;
    var p = rep.panels, lx = p.latex, g = p.gates, S = SAMPLE.GATES, any = false;
    var GA = { checks: S.checks, latex: S.latex, draft_lint: S.draft_lint, citations_lint: S.citations_lint };
    if (lx && lx.present) {
      GA.latex = { verdict: lx.verdict, pages: lx.pages, errors: (lx.errors || []).length,
        undefined: (lx.undefined || []).length, overfull: lx.overfull || 0, bib_entries: lx.bib_entries, bytes: lx.bytes };
      any = true;
    }
    // "skip" = the linter did not run (no compiled paper at this dir): not a real
    // gate result, so leave the whole panel on the sample rather than mixing.
    function realState(x) { return x && x.state && x.state !== "skip"; }
    if (g && (realState(g.draft) || realState(g.cites))) {
      var checks = [];
      if (realState(g.draft)) { var dd = g.draft.data || {}; GA.draft_lint = { ok: !!dd.ok, n_issues: dd.n || 0, n_warnings: 0 };
        checks.push({ check: "draft / no-fabrication gate", cls: "integrity", status: g.draft.state === "pass" ? "ok" : "bad" }); }
      if (realState(g.cites)) { var cd = g.cites.data || {}; GA.citations_lint = { ok: !!cd.ok, n_cited: cd.n_cited, n_issues: cd.n_issues };
        checks.push({ check: "citation completeness", cls: "integrity", status: g.cites.state === "pass" ? "ok" : "bad" }); }
      if (lx && lx.present) checks.push({ check: "zero-LaTeX-error", cls: "integrity", status: lx.verdict === "ok" ? "ok" : "bad" });
      GA.checks = checks.length ? checks : S.checks; any = true;
    }
    GATES = GA;
    return any;
  }

  /* =========================================================================
     SUB-VIEW 1 — READING (three-column reader)
     ========================================================================= */
  function sidebarReading() {
    var s = el("div");
    s.appendChild(sec(T("Runs"), FEED.map(function (r, i) {
      return sideRow("sp-book", r.title, i === 1 ? 1 : 0, r.sel, function () { loadRun(r.id); }, r.prev);
    })));
    // "This paper" nav — reading facets stay in reading; ledger facets jump to governance.
    // n = [icon, label, count, onClick, isCurrent, tooltip] — labels localize via T(); tooltips gloss the insider taxonomy (R11)
    var zh = lang() === "zh";
    var nav = [
      ["sp-quote", T("Story"), null, function () { scrollToCard("sp-story"); }, false, zh ? "跳到一句话火种" : "Jump to the spark sentence"],
      ["sp-doc", T("Proposal"), null, null, true, zh ? "当前正文 · proposal.md" : "Current article · the proposal"],
      ["sp-doc", T("Compiled PDF"), null, function () { SB.toast(zh ? "main.pdf · 20 页（查看器稍后接入）" : "main.pdf · 20 pp (viewer wired later)"); }, false, zh ? "main.pdf · 编译好的论文" : "main.pdf · the compiled paper"],
      ["i-check", T("Claims ledger"), null, function () { SB.setSub("governance"); }, false, zh ? "主张 × 证据状态（治理页）" : "Claims × evidence status (Governance)"],
      ["sp-hash", T("Facts"), null, function () { SB.setSub("governance"); }, false, zh ? "核实过的数字（治理页）" : "The verified numbers (Governance)"],
      ["i-ask", T("Decisions"), 2, function () { SB.setSub("governance"); }, false, zh ? "待你处置的决策（治理页）" : "Decisions awaiting you (Governance)"]
    ];
    s.appendChild(sec(T("This paper"), nav.map(function (n) { return sideRow(n[0], n[1], n[2], n[4], n[3], n[5]); })));
    return s;
  }
  function listReading() {
    // R8 — the article feed is a real listbox: roving-tabindex arrow nav, aria-selected,
    // Enter/Space to open (mirrors the accessible sideRow rows on the left).
    var s = el("div", "list");
    s.setAttribute("role", "listbox");
    s.setAttribute("aria-label", lang() === "zh" ? "运行列表" : "Runs");
    s.innerHTML = FEED.map(function (r) { return entryHTML(r); }).join("");
    var opts = $$(".entry", s);
    var selIdx = 0; FEED.forEach(function (r, k) { if (r.sel) selIdx = k; });
    function roam(i) {
      if (i < 0) i = opts.length - 1; else if (i >= opts.length) i = 0;
      opts.forEach(function (o, k) { o.setAttribute("tabindex", k === i ? "0" : "-1"); });
      if (opts[i]) opts[i].focus();
    }
    function openRun(r) { loadRun(r.id); }        // R5 — real run switch, was a toast
    opts.forEach(function (o, i) {
      o.setAttribute("tabindex", i === selIdx ? "0" : "-1");
      o.onclick = function () { openRun(FEED[i]); };
      o.onkeydown = function (e) {
        if (e.key === "ArrowDown") { e.preventDefault(); roam(i + 1); }
        else if (e.key === "ArrowUp") { e.preventDefault(); roam(i - 1); }
        else if (e.key === "Home") { e.preventDefault(); roam(0); }
        else if (e.key === "End") { e.preventDefault(); roam(opts.length - 1); }
        else if (e.key === "Enter" || e.key === " ") { e.preventDefault(); openRun(FEED[i]); }
      };
    });
    return s;
  }

  // View-switch guard: a late async paint must not land in another view's <main>.
  var VIEW_TOKEN = 0;
  function newView() { stopRunsPolling(); return ++VIEW_TOKEN; }

  function renderReading(main) {
    var tk = newView();
    var dir = SB.data.dir("spark");
    Promise.all([
      SB.data.getOr("spark", "report", null),
      SB.data.getOr("spark", "story", null),
      SB.data.getOr("spark", "facts", null),
      dir ? fetchText(fileUrl("proposal.md")).catch(function () { return null; }) : Promise.resolve(null)
    ]).then(function (r) {
      if (tk !== VIEW_TOKEN) return;                 // switched away before data landed
      resetLive();
      HYD.report = hydrateReport(r[0]);
      HYD.story = hydrateStory(r[1]);
      HYD.facts = hydrateFacts(r[2]);
      READING_PROP = (typeof r[3] === "string" && r[3].trim().length > 40) ? r[3] : null;
      HYD.prop = !!READING_PROP;
      paintReading(main, HYD.report || HYD.story || HYD.facts || HYD.prop);
    });
  }

  // item1/item9 — the freshness state, now a COMPACT chip for the inline status bar (was a
  // full-width card). Only ever rendered from REAL freshness data (a hydrated report panel):
  // sample / no-dir gets NO chip and NO CTA, mirroring Runs. There is no /api/recompile backend,
  // so a stale chip is HONEST — it copies the terminal command instead of faking "0 errors".
  // Keeps the .fresh-banner class so SHELL-CSS can Zen-hide it.
  function freshChipHTML(real) {
    if (!(real && FRESH)) return "";
    var zh = lang() === "zh";
    var rawPages = FACTS.rq3_end_to_end && FACTS.rq3_end_to_end.pages;
    var pages = HYD.facts ? (rawPages || "") : "";     // print pages only when the facts family hydrated
    if (FRESH.state === "fresh")
      return '<span class="fresh-banner chip-mode fresh" title="' + esc(T("newer than every source file — the reading below is trustworthy.")) + '">' +
        ic("i-check", "sm") + '<span class="fc-t">' + T("PDF is fresh") + (pages ? " · " + pages + (zh ? " 页" : " pp") : "") + '</span></span>';
    if (FRESH.state === "stale")
      return '<button class="fresh-banner chip-mode stale" data-recompile-copy title="' +
        esc(zh ? "复制重新编译命令 latexmk -pdf main.tex,到终端运行" : "Copy the recompile command latexmk -pdf main.tex to run in your terminal") + '">' +
        ic("sp-warn", "sm") + '<span class="fc-t">' + T("PDF out of date") + '</span>' +
        '<span class="fc-cta">' + (zh ? "在终端重新编译" : "Recompile in terminal") + '</span></button>';
    return "";                                          // "none" — no compiled PDF yet
  }

  // R3 — the "spark" lede must survive a full paragraph, not just a single line. When it
  // hydrates from st.solution it can be 2–5 sentences; rendering that at true display
  // weight/size is a fatiguing wall of bold Fraunces. So: keep display weight ONLY for a
  // genuinely short single-line spark; for longer copy bold just the first sentence and
  // drop the remainder to body weight at a calmer size (the .sc-long cap lives in CSS).
  function sparkLedeHTML(text) {
    text = String(text == null ? "" : text).trim();
    // first sentence = up to the first ./!/?/。/!/? boundary that is followed by more text
    var m = text.match(/^([\s\S]*?[.!?。!?])\s+([\s\S]+)$/);
    var rest = (m && m[2]) ? m[2].trim() : "";
    var isLong = !!rest || text.length > 155;
    if (rest) {
      return '<p class="sc-one sc-long"><strong class="sc-lead">' + esc(m[1].trim()) +
        '</strong> <span class="sc-rest">' + esc(rest) + '</span></p>';
    }
    return '<p class="sc-one' + (isLong ? " sc-long" : "") + '">' + esc(text) + '</p>';
  }

  // R22c — newcomer glosses for the two machine tokens the reading eyebrow surfaces.
  function tierGloss() {
    return lang() === "zh" ? "论文成熟度四级阶梯,最高一级为 FULL_PAPER" : "4-rung maturity ladder, tops out at FULL_PAPER";
  }
  function officialGloss() {
    return lang() === "zh" ? "使用会议官方样式文件(而非近似模板)" : "uses the venue's official style files (not an approximation)";
  }

  // item21 — the 'New here?' gloss strips used to render on every load with no way to dismiss.
  // Remember a per-strip dismissal in localStorage so a returning user never re-reads them.
  function glossKey(id) { return "sb.spark.gloss." + id; }
  function glossDismissed(id) { try { return localStorage.getItem(glossKey(id)) === "1"; } catch (e) { return false; } }
  function dismissGloss(id) { try { localStorage.setItem(glossKey(id), "1"); } catch (e) {} }
  function glossDismissBtn(id) {
    return '<button class="btn sm ghost gg-dismiss" data-gloss-dismiss="' + id + '">' + (lang() === "zh" ? "知道了" : "Got it") + '</button>';
  }
  // item21 — wire the '知道了 / Got it' dismiss on any gloss strip in `scope` (mirrors wireSampleBanner).
  function wireGloss(scope) {
    if (!scope) return;
    $$("[data-gloss-dismiss]", scope).forEach(function (b) {
      b.onclick = function () {
        dismissGloss(b.getAttribute("data-gloss-dismiss"));
        var strip = b.closest ? b.closest(".gov-gloss") : null; if (strip) strip.remove();
      };
    });
  }

  // item9 — Reading is the default landing view yet showed 'bench', 'proposal · FULL_PAPER',
  // and a red '尚不可提交 · N 项阻断' with none glossed, while Governance/Jury got a newcomer
  // strip. Render the SAME govGloss-style 'New here?' block for the four terms actually on
  // screen here. Reuses the .gov-gloss styling.
  function readingGlossHTML() {
    if (glossDismissed("reading")) return "";               // item21 — remembered dismissal
    var zh = lang() === "zh";
    // item25 — bridge the tier chip label to its raw enum: print translated-label(RAW) together
    // ('档位 / 完整论文 (FULL_PAPER)') so the glossary row connects to the '完整论文' chip above.
    var tierRaw = "FULL_PAPER", tierLbl = tierLabel(tierRaw);
    var tierTerm = (tierLbl === tierRaw) ? tierRaw : (tierLbl + " (" + tierRaw + ")");
    var items = zh ? [
      ["bench", "内置示例语料,不是你的真实运行"],
      ["档位 / " + tierTerm, "论文成熟度四级阶梯,最高一级为 FULL_PAPER"],
      ["提案", "proposal.md —— 编成 PDF 前的可读草案"],
      ["可提交", "阻断项已清零,可以投稿"]
    ] : [
      ["bench", "the built-in sample corpus, not your real run"],
      ["tier / " + tierTerm, "4-rung maturity ladder, tops out at FULL_PAPER"],
      ["proposal", "proposal.md — the readable draft before it compiles to a PDF"],
      ["submittable", "every blocking issue cleared — ready to submit"]
    ];
    return '<div class="gov-gloss reading-gloss" role="note"><span class="gg-h">' + (zh ? "术语速览" : "New here?") + '</span>' +
      items.map(function (it) { return '<span class="gg-item"><b>' + esc(it[0]) + '</b>' + esc(it[1]) + '</span>'; }).join("") +
      glossDismissBtn("reading") + '</div>';
  }

  // R13 — a compact submittable go/no-go ribbon for the reading view, driven by the shared
  // needs signal (SB.needs.detail.jury.blocking) so it stays in lockstep with the Jury docket.
  // Renders nothing unless a Jury ledger is actually bound for this paper (else a spurious
  // green "submittable" could show with no ledger behind it).
  function submittableRibbonHTML() {
    var nd = (SB.needs && SB.needs.detail) ? SB.needs.detail.jury : null;
    var juryDir = (SB.needs && SB.needs.dirs) ? SB.needs.dirs.jury : "";
    if (!nd || !juryDir) return "";
    var zh = lang() === "zh";
    // item1d — dirs.jury is set one tick BEFORE detail.jury resolves, so nd is still the initial
    // {} (blocking undefined → 0) and the ribbon would flash a false green "submittable". Hold a
    // neutral "checking" chip until the needs poll has actually landed.
    if (!(SB.needs && SB.needs._loaded)) {
      return '<span class="submit-ribbon checking"><span class="dotb"></span><span>' +
        (zh ? "评审校验中…" : "Checking review…") + '</span></span>';
    }
    var blocking = nd.blocking || 0, ok = blocking === 0;
    var label = ok ? (zh ? "可提交" : "Submittable")
      : (zh ? ("尚不可提交 · " + blocking + " 项阻断") : ("Not submittable · " + blocking + " blocking"));
    return '<button class="submit-ribbon ' + (ok ? "ok" : "bad") + '" data-jury-shield title="' +
      esc(zh ? "跳到投稿护盾" : "Jump to the submission shield") + '">' +
      ic(ok ? "i-check" : "sp-warn", "sm") + '<span>' + esc(label) + '</span></button>';
  }

  // item1/item9 — the inline status bar body: a freshness chip + a go/no-go blocker chip. Emitted
  // inside a stable #sp-statusbar wrapper so the needs-poll can refresh it in place. Suppressed
  // entirely when the dir could not be read (we can't honestly speak to freshness/submittability).
  function readingStatusInner(real, cnr) {
    if (cnr) return "";
    return freshChipHTML(real) + submittableRibbonHTML();
  }
  function wireStatusBar(scope) {
    if (!scope) return;
    var rc = $("[data-recompile-copy]", scope);
    if (rc) rc.onclick = function () { copyCmd("latexmk -pdf main.tex"); };   // honest: no /api/recompile, copy the command
    var sr = $("[data-jury-shield]", scope);
    if (sr) sr.onclick = function () { SB.setTool("jury"); SB.setSub("shield"); };
  }

  function paintReading(main, real) {
    // item1c — when the dir can't be read we stay silent on freshness/submittability entirely.
    var cnr = sparkCouldNotRead();

    // Story origin card — the "one sentence into a paper", with provenance line.
    var zhL = lang() === "zh";
    var storyCard =
      '<div class="story-card" id="sp-story">' +
        '<div class="sc-mark">' + ic("sp-quote") + '</div>' +
        '<div class="sc-kick">' + T("The spark") + '</div>' +
        sparkLedeHTML(STORY.spark_sentence) +
        '<div class="sc-flow">' +
          // R9 — gloss the two insider labels for a newcomer via a title tooltip
          '<div class="sc-cell" title="' + esc(zhL ? "现有方法结构性避开、留下的空白" : "the gap prior work structurally leaves open") + '"><span class="sc-lbl">' + T("gap pattern") + '</span>' + esc(shortGap(STORY.gap_pattern)) + '</div>' +
          '<div class="sc-arrow">' + ic("i-chev") + '</div>' +
          '<div class="sc-cell sc-sol" title="' + esc(zhL ? "本文用来填补那个空白的做法" : "how this paper fills that gap") + '"><span class="sc-lbl">' + T("solution") + '</span>' + esc(STORY.solution) + '</div>' +
        '</div>' +
        '<div class="sc-prov"><span class="chip accent">story.json</span>' +
          '<span class="sc-prov-t">' + T("provenance") + ' · <code>origin: ' + esc(STORY.origin) + '</code></span></div>' +
      '</div>';

    // real proposal.md → article body; else the built-in sample proposal prose.
    var article = (real && READING_PROP) ? mdArticle(READING_PROP) : proposalHTML();
    // R1 — a real dir open but nothing in this view hydrated → the whole reading is sample.
    var amber = (dirOpen() && !real) ? sampleBannerHTML("该", "data") : "";
    // item9 — collapse the freshness card + blocker ribbon into ONE compact inline status bar
    // under .meta (chip + chip, not two stacked full-width cards); the reading now opens on the
    // thesis — status bar → storyCard(lede) → readingGloss → article (the gloss drops BELOW the
    // lede so the go/no-go lands right before the spark sentence).
    var statusBar = '<div class="reading-statusbar" id="sp-statusbar">' + readingStatusInner(real, cnr) + '</div>';
    // item8 — the proposal prose lives in its own .reader-body so the shell's AI summary +
    // reading-time read the article, not the status/story chrome above it (SHELL-JS falls
    // back to .reader when a view provides no .reader-body).
    var body = amber + statusBar + storyCard + readingGlossHTML() +
      '<div class="reader-body">' + article + '</div>';

    var e = FACTS.rq3_end_to_end || {};
    var zh = lang() === "zh";
    var tmpl = BLUEPRINT.template ? BLUEPRINT.template.display_name : "NeurIPS 2025";
    var mode = BLUEPRINT.template ? BLUEPRINT.template.results_mode : "data_aware";
    // R1 — pages/refs/figs come from results.facts.json; print them only when that family
    // hydrated (else "—"), so a sample count is never shown beside a green "reading <dir>".
    // R24 — results_mode is a machine enum: show a human gloss, keep the raw as a tooltip.
    var pagesM = honest(HYD.facts, e.pages), refsM = honest(HYD.facts, e.references), figsM = honest(HYD.facts, e.figures);
    // R22 — drop null-count tokens entirely rather than printing "— pp · — refs · — figs"
    // (a real dir whose facts fell back to sample). Only surviving counts join the strip.
    var counts = [];
    if (pagesM !== "—") counts.push(pagesM + (zh ? " 页" : " pp"));
    if (refsM !== "—") counts.push(refsM + (zh ? " 参考" : " refs"));
    if (figsM !== "—") counts.push(figsM + (zh ? " 图" : " figs"));
    // R29f — one styled dim separator everywhere on the meta line (was a mix of a dim bullet
    // and raw full-ink middots). ·, not •, inside the shared .b span.
    var SEP = '<span class="b">·</span>';
    var countSeg = counts.length ? SEP + counts.join(SEP) : "";
    var official = BLUEPRINT.template && BLUEPRINT.template.official;
    // R22c — the maturity tier + "official" markers used to sit RAW in the eyebrow, but the
    // .kicker is escaped-as-text upstream (no HTML tooltip possible there). Render them on
    // the adjacent meta line instead, each carrying the newcomer gloss as a title= tooltip
    // and the tier localized (raw enum preserved in the tooltip).
    var tierRaw = (GOV_TIER && GOV_TIER.best_tier) ? GOV_TIER.best_tier : "FULL_PAPER";
    var tierSeg = SEP + '<span title="' + esc(tierRaw + " — " + tierGloss()) + '">' + esc(tierLabel(tierRaw)) + '</span>' +
      (official ? SEP + '<span title="' + esc(officialGloss()) + '">' + esc(T("official")) + '</span>' : '');
    var meta = 'systems / methodology' + SEP + esc(tmpl) + SEP +
      '<span title="' + esc(mode) + '">' + esc(modeLabel(mode)) + '</span>' + tierSeg +
      countSeg + provChip(real);

    var out = SB.ReaderShell(main, {
      sidebar: sidebarReading(), list: listReading(), rail: "toc",
      reader: {
        kicker: "Spark · " + esc(tmpl),
        title: BLUEPRINT.paper_title,
        meta: meta,
        bodyHTML: body
      },
      // R5 — prev/next now actually switch runs: step the feed by index and load it
      // (was a dead toast). Reversible, so no confirm gate.
      onPrev: function () { var i = curFeedIdx(); loadRun(FEED[(i - 1 + FEED.length) % FEED.length].id); },
      onNext: function () { var i = curFeedIdx(); loadRun(FEED[(i + 1) % FEED.length].id); },
      onStar: function () { SB.toast(lang() === "zh" ? "已收藏此运行" : "Starred this run"); }
    });

    wireSampleBanner(out.article);
    wireGloss(out.article);   // item21 — '知道了 / Got it' dismiss on the reading gloss strip
    wireStatusBar(out.article);   // item1/item9 — recompile-copy (honest, no fake result) + jury deep-link

    // item1d — the reading isn't the Runs view: it doesn't set _wsNeedsRefresh on its own, so a
    // ribbon rendered as "Checking review…" before the needs poll lands would never resolve.
    // Refresh just the status bar in place the moment needs updates (guarded by the view token).
    var vtoken = VIEW_TOKEN;
    SB._wsNeedsRefresh = function () {
      if (vtoken !== VIEW_TOKEN) return;
      var bar = $("#sp-statusbar", out.article);
      if (!bar || !document.body.contains(bar)) return;
      bar.innerHTML = readingStatusInner(real, cnr);
      wireStatusBar(bar);
    };
    if (SB.onTeardown) SB.onTeardown(function () { if (SB._wsNeedsRefresh) SB._wsNeedsRefresh = null; });

    // item5 — Jury's "jump to this location in the paper" sets SB.pendingReadSection then
    // switches here. Resolve it against the rendered article (passage id → section heading →
    // quote text → honest fallback to the top), scroll + flash, then clear it.
    consumePendingReadSection(out);
    return out;
  }

  // item5 — consume a cross-tool jump request {section, quote, passage_id}. Best-effort
  // resolution because the Jury docket and this reading view can hold different manuscripts;
  // always clears the pending state and always lands the reader *somewhere* honest.
  function consumePendingReadSection(out) {
    var pend = null;
    try { pend = SB.pendingReadSection; } catch (e) {}
    if (!pend) return;
    var fromCharge = pend.fromCharge;                       // item18 — captured before we clear
    try { SB.pendingReadSection = null; } catch (e) {}     // consume once, regardless of outcome
    var article = out.article, target = null;
    // item18 — a jump that originated from a Jury charge gets a dismissible breadcrumb back.
    if (fromCharge) renderReturnToCharge(out, fromCharge);
    // 1) exact passage id (element id) match
    if (pend.passage_id && /^[\w:-]+$/.test(pend.passage_id)) {
      target = document.getElementById(pend.passage_id) || $('[data-passage="' + pend.passage_id + '"]', article);
    }
    // 2) section heading text match (tolerates a leading §)
    if (!target && pend.section) {
      var want = String(pend.section).toLowerCase().replace(/^§\s*/, "").trim();
      if (want) {
        var heads = $$("h1,h2,h3", article);
        for (var i = 0; i < heads.length; i++) {
          var ht = heads[i].textContent.toLowerCase();
          if (ht.indexOf(want) >= 0 || want.indexOf(ht) >= 0) { target = heads[i]; break; }
        }
      }
    }
    // 3) quote text match (a paragraph carrying the cited sentence)
    if (!target && pend.quote) {
      var q = String(pend.quote).toLowerCase().replace(/\s+/g, " ").trim().slice(0, 40);
      if (q) {
        var ps = $$("p,li", article);
        for (var j = 0; j < ps.length; j++) {
          if (ps[j].textContent.toLowerCase().replace(/\s+/g, " ").indexOf(q) >= 0) { target = ps[j]; break; }
        }
      }
    }
    // 4) fallback: the story lede at the top, so the jump still lands honestly
    var fell = !target;
    var node = target || $("#sp-story", article) || article;
    setTimeout(function () {
      try { node.scrollIntoView({ behavior: prefersReduced() ? "auto" : "smooth", block: "start" }); } catch (e) {}
      node.classList.remove("rd-flash"); void node.offsetWidth; node.classList.add("rd-flash");
      setTimeout(function () { node.classList.remove("rd-flash"); }, 1800);
    }, 60);
    var zh = lang() === "zh";
    announce(fell ? (zh ? "未能在本文定位该处,已跳到论文开头" : "Couldn't locate that passage here — jumped to the top of the paper")
                  : (zh ? "已跳到所引位置" : "Jumped to the cited passage"));
  }

  // item18 — a dismissible breadcrumb at the top of the reader that returns to the Jury
  // charge the jump came from. Guarded on SB.juryOpenCharge (which does setTool('jury') +
  // opens the charge); if that hook isn't present yet, at least switch to the Jury tool.
  function renderReturnToCharge(out, id) {
    if (!out || !out.article) return;
    var zh = lang() === "zh";
    var prev = $(".read-breadcrumb", out.article); if (prev) prev.remove();
    var bc = el("div", "read-breadcrumb"); bc.setAttribute("role", "note");
    var label = (zh ? "返回指控 " : "Back to charge ") + id + (zh ? "(评审团)" : " (Jury)");
    bc.innerHTML =
      '<button class="rb-link" type="button"><span class="rb-arrow" aria-hidden="true">←</span>' + esc(label) + '</button>' +
      '<button class="rb-x iconbtn" type="button" aria-label="' + esc(zh ? "关闭" : "Dismiss") + '">' + ic("i-close", "sm") + '</button>';
    out.article.insertBefore(bc, out.article.firstChild);
    var link = $(".rb-link", bc); if (link) link.onclick = function () {
      if (typeof SB.juryOpenCharge === "function") SB.juryOpenCharge(id);
      else SB.setTool("jury");
    };
    var x = $(".rb-x", bc); if (x) x.onclick = function () { bc.remove(); };
  }

  // proposal.md → reader HTML (real content; rich h2/h3 tree feeds the TOC rail)
  function proposalHTML() {
    return [
      '<p><strong>Abstract.</strong> Large language models can draft fluent scientific prose, yet turning a raw research <em>spark</em> into a <em>submittable</em> manuscript remains unsolved as a single, trustworthy, low-friction workflow. We present ' + b(BLUEPRINT.method_name) + ', a suite of composable Claude Code skills organized around one design principle — <em>the model reasons, code backstops</em> — that covers the whole arc from idea to compiled PDF with machine-checked integrity and editable-vector figures.</p>',
      '<h2>Problem and motivation</h2>',
      '<p>Three obstacles recur in practice. First, <strong>heavyweight infrastructure</strong>: the strongest autonomous “AI scientist” systems match the breadth of the task but ship as standalone products — Docker images, graph databases, tens of thousands of lines of orchestration — that the average researcher cannot drop into an editor-based workflow.</p>',
      '<p>Second, <strong>integrity failures are endemic</strong>: LLM-authored papers are notorious for hallucinated citations and fabricated numbers. Most pipelines treat these as stylistic risks to be reviewed later, not as build-breaking errors.</p>',
      '<p>Third, <strong>figures are not camera-ready</strong>: modern image models emit rasters, but a real paper needs editable vectors — text selectable, lines re-colorable, embeddable as PDF. A naive “redraw it as vectors” step loses the richness of a dense schematic.</p>',
      '<h2>Gap in prior work</h2>',
      '<p>The landscape splits into two camps, each missing something. <em>Lightweight agent skills</em> install cleanly but cover only parts of the arc — they do not run experiments and do not draw figures. <em>Heavy autonomous scientists</em> cover the breadth but require dedicated infrastructure, produce no editable-vector figures, and do not expose integrity as a hard gate. The unoccupied point is a pure agent-skill suite that is simultaneously end-to-end, zero-infrastructure, integrity-gated by construction, and able to emit editable-vector figures.</p>',
      '<h2>Proposed approach</h2>',
      '<h3>Architectural principle: model-reasons / code-backstops</h3>',
      '<p>All judgment-heavy work — literature triage, drafting, critique, adversarial review, figure design — is owned by the LLM, which holds the whole paper in context so coherence, anti-repetition, and terminology consistency come for free. Small deterministic Python scripts handle only the irreducible parts: linting, document assembly, plotting, embeddings, and figure vectorization.</p>',
      '<h3>Pillar 1 — Content-routing orchestration</h3>',
      '<p>A schema-free classifier reads the dropped input and sets a single <code>results_mode</code> switch, then drives a seven-stage chain (plan → cite → write → refine → review → figure → assemble) plus an auto-run experiments-and-repair stage. The chain is realized as files-on-disk contracts between stages, making every stage independently inspectable and re-runnable.</p>',
      '<h3>Pillar 2 — A four-layer quality stack</h3>',
      '<p>Quality is layered so each layer does what it is best at: (1) deterministic gates that fail the build; (2) Claude self-review; (3) adversarial peer-review hardening — the one thing self-review structurally cannot do, argue the <em>other</em> side; (4) figure vision-critique. The two integrity rules are mode-dependent and absolute: in <strong>proposal mode</strong> no number is ever invented; in <strong>data-aware mode</strong> every reported number must trace to a real-data ground-truth file.</p>',
      '<h3>Pillar 3 — An editable-vector figure engine (DrawAI hybrid)</h3>',
      '<p>To convert an image-model raster into a camera-ready figure without losing richness, the engine <em>decomposes and reconstructs</em> rather than re-drawing: SAM-style region segmentation, PaddleOCR text reading, and a Box-IR structured layout, then a hybrid build that keeps the approved render pixel-exact and lays an editable text overlay on top. The rule is <strong>hybrid, or else keep the high-resolution PNG — never a lossy redraw</strong>.</p>',
      '<h2>Claimed contributions</h2>',
      '<p>' + BLUEPRINT.contributions.map(function (c) { return b(c.id) + ' ' + esc(c.text.replace(/^C\d+:\s*/, "")); }).join('</p><p>') + '</p>',
      '<h2>Evaluation plan</h2>',
      '<p>We evaluate along four axes; all reported numbers come from real measured runs (figure-engine measurements on an NVIDIA A40). <strong>RQ1 figure fidelity</strong>: SSIM to the approved render, editable-text-box recovery, and vectorization runtime. <strong>RQ2 integrity gates</strong>: detection and false-alarm behavior on injected fabrications. <strong>RQ3 end-to-end production</strong>: stage outcomes, gate pass/fail, references, page count, editability — including this self-referential manuscript. <strong>RQ4 efficiency</strong>: orchestration cost of holding the whole paper in context versus a micro-call baseline.</p>'
    ].join("");
  }

  /* =========================================================================
     SUB-VIEW 2 — RUNS (live cockpit run, rendered as a rich static representative)
     ========================================================================= */
  // Live run state. RV.token invalidates in-flight fetches/timers on view change.
  // RV.want carries a run id requested from another view (reading list / prev-next /
  // switcher / palette) so the Runs cockpit selects it once /api/state lands.
  var RV = { token: 0, runId: null, want: null, cursor: 0, run: null, runs: [], stateTimer: null, runTimer: null, loadTimer: null, settings: null, host: null, $narr: null, $appr: null, pendingDraft: null };

  function stopRunsPolling() {
    RV.token++;
    if (RV.stateTimer) { clearInterval(RV.stateTimer); RV.stateTimer = null; }
    if (RV.runTimer) { clearTimeout(RV.runTimer); RV.runTimer = null; }
    if (RV.loadTimer) { clearTimeout(RV.loadTimer); RV.loadTimer = null; }
  }

  /* ---- R5 — the single run-switching entry point --------------------------
     Every "open this run" affordance (reading list rows, sidebar Runs, the title
     switcher, B/N prev-next, and the ⌘K palette) funnels here instead of toasting.
     It marks the chosen feed row selected and routes to the live Runs cockpit, which
     loads that run by id via the real /api/state → /api/run/<id> path (RV.runId). */
  function feedIndexById(id) { for (var i = 0; i < FEED.length; i++) if (FEED[i].id === id) return i; return -1; }
  function curFeedIdx() { for (var i = 0; i < FEED.length; i++) if (FEED[i].sel) return i; return 0; }
  function loadRun(id) {
    if (id == null) return;
    var i = feedIndexById(id);
    FEED.forEach(function (f, k) { f.sel = (i >= 0 ? k === i : f.id === id); });
    RV.want = id;                                   // honored by fetchRunsState(first)
    RV.focusOnPaint = true;                          // R4 — move focus once the cockpit paints
    announce("Spark · " + ((i >= 0 && FEED[i].title) || id));  // R4 — announce the content swap
    SB.setSub("runs");                              // re-renders the cockpit, which selects it
  }

  // LIVE runs cockpit. Mirrors the legacy ui.html polling: /api/state (~5 s) for
  // the run list + picker, /api/run/<id>?cursor=N (~1.5 s) for the transcript. No
  // server (e.g. the standalone demo) → the beautiful static sample is kept.
  function renderRuns(main) {
    newView();
    var token = RV.token;
    RV.host = el("div", "pane"); main.appendChild(RV.host);
    // item10 — a run dir that could not be read must degrade honestly: don't poll a live
    // subprocess and then mislabel it 'Sample' over the dir side channel. Paint the built-in
    // sample cockpit so the banner and the data below describe the SAME (sample) run.
    if (sparkCouldNotRead()) { paintSampleRun(RV.host); return; }
    // item1 — the verdict banner reads SB.needs.detail.jury.blocking, which is 0 until the async
    // needs fetch lands. When runs is the LANDING view it renders before that, so re-run the
    // chrome (verdict tone + CTA) the moment needs updates, keeping it in lockstep with the
    // reader ribbon / jury docket instead of flashing a false green all-clear.
    SB._wsNeedsRefresh = function () {
      if (RV.token === token && RV.run && RV.host && document.body.contains(RV.host)) updateChrome(RV.run);
    };
    if (SB.onTeardown) SB.onTeardown(function () { if (SB._wsNeedsRefresh) SB._wsNeedsRefresh = null; });
    RV.host.innerHTML = '<div class="pane-wide reveal"><div class="runs-loading"><span class="rl-spin" aria-hidden="true"></span>' +
      (lang() === "zh" ? "正在读取运行…" : "reading runs…") + '</div></div>';
    fetchRunsState(token, true);
    RV.stateTimer = setInterval(function () { fetchRunsState(token, false); }, 5000);
    // item31e — a hung /api/state never rejects, so the spinner would spin forever. After ~8s,
    // if the first paint hasn't replaced the loader, fall back to the built-in sample cockpit.
    if (RV.loadTimer) clearTimeout(RV.loadTimer);
    RV.loadTimer = setTimeout(function () {
      RV.loadTimer = null;
      if (RV.token === token && RV.host && $(".runs-loading", RV.host)) paintSampleRun(RV.host);
    }, 8000);
  }

  function fetchRunsState(token, first) {
    fetch("/api/state").then(function (r) { return r.json(); }).then(function (d) {
      if (RV.token !== token) return;
      if (first && RV.loadTimer) { clearTimeout(RV.loadTimer); RV.loadTimer = null; }   // item31e — first state landed
      RV.runs = d.runs || [];
      if (first) {
        var want = RV.want; RV.want = null;         // R5 — prefer an explicitly requested run
        // item11 — a KB→Spark draft lands straight on the new-paper form, past any run pick.
        if (RV.pendingDraft) { paintNewForm(token); return; }
        var pick = (want && findCard(want)) || chooseRun(RV.runs);
        if (pick) selectRun(pick.id, token);
        else paintNewForm(token);
      } else { updatePicker(token); }
    }).catch(function () {
      if (first && RV.loadTimer) { clearTimeout(RV.loadTimer); RV.loadTimer = null; }   // item31e
      if (RV.token === token && first) paintSampleRun(RV.host);
    });
  }

  function chooseRun(runs) {
    var p = null, i, r;
    for (i = 0; i < runs.length; i++) { r = runs[i]; if (r.needs_reply) return r; if (!p && !TERMINAL[r.status]) p = r; }
    return p || (runs.length ? runs[0] : null);
  }
  function findCard(id) { for (var i = 0; i < RV.runs.length; i++) if (RV.runs[i].id === id) return RV.runs[i]; return null; }

  function selectRun(id, token) {
    if (RV.token !== token) return;
    RV.runId = id; RV.cursor = 0; RV.run = null; RV.waitKey = null;
    var c = findCard(id);                            // R4 — announce with the authoritative title
    announce("Spark · " + ((c && (c.title || c.id)) || id));
    paintRunView(token);
    pollRunOnce(token);
  }

  function triCol(kick, h3, inner) {
    return '<div class="card tri-col"><div class="card-h"><span class="kick">' + esc(T(kick)) + '</span><h3>' + esc(h3) + '</h3></div>' + inner + '</div>';
  }
  function microTape(r) {
    var p = parseStage(r.stage), idx = p ? p.idx : -1, out = "";
    // R13 — an errored/stopped run shows a red node at the halted stage, not a live "cur"
    var bad = r.status === "error" || r.status === "stopped";
    for (var i = 0; i < 9; i++) {
      var c = idx < 0 ? "" : (r.status === "done" ? "ok"
        : bad ? (i < idx ? "done" : i === idx ? "err" : "")
          : (i < idx ? "done" : i === idx ? (r.needs_reply ? "wait" : "cur") : ""));
      out += '<i class="' + c + '"></i>';
    }
    return '<span class="mtape">' + out + '</span>';
  }
  function runsPickerHTML() {
    var chips = RV.runs.map(function (r) {
      return '<button class="run-chip' + (r.id === RV.runId ? " sel" : "") + (r.needs_reply ? " needs" : "") + '" data-run="' + esc(r.id) + '">' +
        '<span class="rc-dot ' + esc(r.status || "") + '"></span>' +
        '<span class="rc-title">' + esc(r.title || r.id) + '</span>' + microTape(r) + '</button>';
    }).join("");
    return '<div class="runs-picker"><div class="rp-runs">' + chips + '</div>' +
      '<button class="btn sm" id="sp-new">' + ic("sp-doc", "sm") + (lang() === "zh" ? "新建论文" : "New paper") + '</button></div>';
  }
  function wirePicker(token) {
    $$(".run-chip", RV.host).forEach(function (b) { b.onclick = function () { if (b.dataset.run !== RV.runId) selectRun(b.dataset.run, token); }; });
    var nb = $("#sp-new", RV.host); if (nb) nb.onclick = function () { paintNewForm(token); };
  }
  function updatePicker(token) {
    if (RV.token !== token) return;
    var pk = $(".runs-picker", RV.host);
    if (pk) { pk.outerHTML = runsPickerHTML(); wirePicker(token); }
  }

  function paintRunView(token) {
    RV.host.innerHTML =
      '<div class="pane-wide reveal">' + runsPickerHTML() +
        '<div class="run-head card" id="sp-head"></div>' +
        '<div id="sp-waitwrap"></div>' +
        '<div class="triptych sp-live">' +
          narrColHTML() +
          apprColHTML() +
          triCol("shelf", T("Artifacts changing"), '<div class="shelf" id="sp-shelf"></div>') +
        '</div>' +
        '<div class="telemetry card" id="sp-telem"></div>' +
      '</div>';
    RV.$narr = $("#sp-narr", RV.host); RV.$appr = $("#sp-appr", RV.host);
    wirePicker(token);
    wireApprToggle();
    wireNarrToggle();
    // R4 — after a user-initiated run swap lands, move focus into the cockpit so a
    // keyboard / screen-reader user follows the content swap (not on the initial mount).
    if (RV.focusOnPaint) {
      RV.focusOnPaint = false;
      var pw = $(".pane-wide", RV.host);
      if (pw) { pw.setAttribute("tabindex", "-1"); try { pw.focus(); } catch (e) {} }
    }
  }

  // R8 — apparatus column with a disclosure. On a terminal run the raw mono tool-log is a
  // wall (the bench run alone has ~295 rows); we collapse it behind a "show log" toggle and
  // lead with a one-line summary, but keep it live-expanded while the run is still going.
  function apprColHTML() {
    return '<div class="card tri-col tri-appr" id="sp-appr-col">' +
      '<div class="card-h"><span class="kick">' + T("apparatus") + '</span><h3>' + T("Tool log") + '</h3>' +
        '<button class="btn sm ghost appr-toggle" id="sp-appr-toggle" aria-expanded="true" hidden></button></div>' +
      '<div class="appr-summary" id="sp-appr-sum" hidden></div>' +
      '<div class="apparatus" id="sp-appr"></div></div>';
  }
  function apprToggleLabel(collapsed) {
    var zh = lang() === "zh";
    return collapsed ? (zh ? "看日志" : "Show log") : (zh ? "收起日志" : "Hide log");
  }
  function wireApprToggle() {
    var at = $("#sp-appr-toggle", RV.host); if (!at) return;
    at.onclick = function () {
      var col = $("#sp-appr-col", RV.host); if (!col) return;
      var collapsed = col.classList.toggle("collapsed");
      col.dataset.userToggled = "1";
      at.setAttribute("aria-expanded", collapsed ? "false" : "true");
      at.textContent = apprToggleLabel(collapsed);
    };
  }
  // Raw text (assigned via textContent, so it must NOT be pre-escaped).
  function apprSummaryText() {
    var zh = lang() === "zh", appr = $("#sp-appr", RV.host);
    var rows = appr ? $$(".ap-row", appr) : [];
    var n = rows.length;
    if (!n) return zh ? "没有工具调用" : "no tool calls";
    var lastRow = rows[n - 1];
    var lt = $(".ap-tool", lastRow), la = $(".ap-out", lastRow) || $(".ap-arg", lastRow);
    var lastTool = lt ? lt.textContent : "", lastOut = (la ? la.textContent : "").trim();
    if (lastOut.length > 64) lastOut = lastOut.slice(0, 61) + "…";   // keep the summary to ~one line
    var head = n + " " + (zh ? "次工具调用" : (n === 1 ? "tool" : "tools"));
    var tail = lastTool ? " · " + (zh ? "最后:" : "last: ") + lastTool + (lastOut ? " " + lastOut : "") : "";
    return head + tail;
  }
  // Toggle the collapse based on the current run's terminal state. Idempotent; safe to
  // call each poll. Respects a user's explicit expand (dataset.userToggled).
  function refreshApprDisclosure() {
    var col = $("#sp-appr-col", RV.host); if (!col) return;
    var toggle = $("#sp-appr-toggle", RV.host), sum = $("#sp-appr-sum", RV.host);
    var terminal = !!(RV.run && TERMINAL[RV.run.status]);
    if (!terminal) {
      col.classList.remove("collapsed");
      if (toggle) toggle.hidden = true;
      if (sum) sum.hidden = true;
      return;
    }
    if (sum) { sum.hidden = false; sum.textContent = apprSummaryText(); }
    if (toggle) {
      toggle.hidden = false;
      if (!col.dataset.userToggled) {
        col.classList.add("collapsed");
        toggle.setAttribute("aria-expanded", "false");
        toggle.textContent = apprToggleLabel(true);
      }
    }
  }

  // item20b — narration bodies are authored in ONE language (the sample RUN.narration is zh; a
  // live run's narration follows the agent). Under the other UI language they stay untranslated.
  // Offer a header toggle that translates every narration line in place via the reading-assistant
  // transport (SB.ai → SB.aiTransport), caches each line so a re-toggle is instant, and flips back
  // to the stored original. Shown only when (a) the real transport is wired — the offline mock
  // returns one fixed sentence for every line, so we don't offer it there — and (b) the body's
  // script differs from the UI language (otherwise translating is a no-op).
  function hasCJK(s) { return /[㐀-鿿豈-﫿]/.test(String(s == null ? "" : s)); }
  function narrTransToggleHTML() {
    return '<button class="btn sm ghost narr-trans" data-narr-trans hidden>' +
      ic("sp-book", "sm") + '<span class="nt-lbl"></span></button>';
  }
  function narrTransLabel(state, zh) {
    if (state === "busy") return zh ? "翻译中…" : "Translating…";
    if (state === "translated") return zh ? "显示原文" : "Show original";
    return zh ? "译成中文" : "Translate → EN";
  }
  function narrTransFailed(full) {
    var s = String(full == null ? "" : full);
    if (!s) return true;
    return s.charAt(0) === "（" || /^\(Reading assistant unavailable/.test(s);
  }
  function wireNarrTranslate(card, live) {
    if (!card) return;
    var btn = $("[data-narr-trans]", card); if (!btn) return;
    if (btn.getAttribute("data-wired") === "1") return;      // bind once (live path calls repeatedly)
    if (!SB.aiTransport) { btn.remove(); return; }           // only the real transport, never the mock
    var narr = $(".narration", card);
    var lines = narr ? $$(".nr-line p", narr) : [];
    if (!lines.length) { if (!live) btn.remove(); return; }  // sample must have lines; live may not yet
    var zh = lang() === "zh", target = zh ? "zh" : "en";
    var joined = lines.map(function (p) { return p.textContent; }).join(" ");
    var mismatch = zh ? !hasCJK(joined) : hasCJK(joined);
    if (!mismatch) { if (!live) btn.remove(); return; }      // already in the UI language
    btn.setAttribute("data-wired", "1");
    btn.hidden = false;
    var lbl = $(".nt-lbl", btn);
    function setLabel(state) { if (lbl) lbl.textContent = narrTransLabel(state, zh); }
    setLabel("orig");
    lines.forEach(function (p) { if (p.getAttribute("data-orig") == null) p.setAttribute("data-orig", p.textContent); });
    var state = "orig", busy = false, done = false, cache = [];
    function apply(which) {
      lines.forEach(function (p, i) {
        p.textContent = (which === "translated") ? (cache[i] != null ? cache[i] : p.getAttribute("data-orig")) : p.getAttribute("data-orig");
      });
    }
    function translateFrom(i) {
      if (i >= lines.length) { busy = false; done = true; state = "translated"; setLabel("translated"); btn.disabled = false; return; }
      if (cache[i] != null) { translateFrom(i + 1); return; }
      SB.ai({ op: "translate", text: lines[i].getAttribute("data-orig"), target_lang: target, ui_lang: lang() },
        function (chunk, isDone, full) {
          if (!isDone) return;                               // wait for the full line (transport is single-in-flight)
          if (i === 0 && narrTransFailed(full)) {            // unreachable / unconfigured → abort cleanly, no half-translation
            busy = false; state = "orig"; apply("orig"); setLabel("orig"); btn.disabled = false;
            SB.toast(zh ? "翻译暂不可用 —— 在「设置 → 阅读助手」里配置" : "Translation unavailable — set it up in Settings → Reading assistant.");
            return;
          }
          cache[i] = (full && !narrTransFailed(full)) ? full : lines[i].getAttribute("data-orig");
          if (state === "translated") lines[i].textContent = cache[i];   // stream each line in as it lands
          translateFrom(i + 1);
        });
    }
    btn.onclick = function () {
      if (busy) return;
      if (state === "translated") { state = "orig"; apply("orig"); setLabel("orig"); return; }
      state = "translated";
      if (done) { apply("translated"); setLabel("translated"); return; }   // cached — instant re-toggle
      busy = true; btn.disabled = true; setLabel("busy");
      translateFrom(0);
    };
  }

  // item18 — narration column with the SAME terminal treatment as the apparatus. On a done run
  // the narration was the whole final assistant turn as a prose wall opening on a filepath
  // fragment, so an explicit ask ("…想采纳哪条告诉我") sat below the fold under a green verdict.
  // Pin the closing line as a bold lead, collapse the body behind "show full", and flag an amber
  // chip when the final turn ends interrogatively.
  function narrColHTML() {
    return '<div class="card tri-col tri-narr" id="sp-narr-col">' +
      '<div class="card-h"><span class="kick">' + T("narration") + '</span><h3>' + T("What the agent is doing") + '</h3>' +
        narrTransToggleHTML() +
        '<button class="btn sm ghost narr-toggle" id="sp-narr-toggle" aria-expanded="true" hidden></button></div>' +
      '<div class="narr-lead" id="sp-narr-lead" hidden></div>' +
      '<div class="narr-ask" id="sp-narr-ask" hidden></div>' +
      '<div class="narration" id="sp-narr"></div></div>';
  }
  function narrToggleLabel(collapsed) {
    var zh = lang() === "zh";
    return collapsed ? (zh ? "看全部" : "Show full") : (zh ? "收起" : "Collapse");
  }
  function wireNarrToggle() {
    var nt = $("#sp-narr-toggle", RV.host); if (!nt) return;
    nt.onclick = function () {
      var col = $("#sp-narr-col", RV.host); if (!col) return;
      var collapsed = col.classList.toggle("collapsed");
      col.dataset.userToggled = "1";
      nt.setAttribute("aria-expanded", collapsed ? "false" : "true");
      nt.textContent = narrToggleLabel(collapsed);
    };
  }
  // item3 — a "pure marker" narration line carries no takeaway: it is empty, or its whole
  // content (stripped of punctuation/decoration) is just a completion word. Such a line must
  // never become the bold lead; walk past it to the last real-content line.
  function isNarrMarker(txt) {
    var s = String(txt == null ? "" : txt).trim();
    if (!s) return true;
    var core = s.replace(/^[\s\W_]+|[\s\W_]+$/g, "");
    return /^(turn\s*complete|done|finished|完成|结束)$/i.test(core);
  }
  function refreshNarrDisclosure() {
    var col = $("#sp-narr-col", RV.host); if (!col) return;
    var toggle = $("#sp-narr-toggle", RV.host), lead = $("#sp-narr-lead", RV.host), ask = $("#sp-narr-ask", RV.host);
    var narr = $("#sp-narr", RV.host);
    wireNarrTranslate(col, true);   // item20b — bind the in-place translate once the narration has lines
    var terminal = !!(RV.run && TERMINAL[RV.run.status]);
    if (!terminal) {
      col.classList.remove("collapsed");
      if (toggle) toggle.hidden = true;
      if (lead) lead.hidden = true;
      if (ask) { ask.hidden = true; ask.innerHTML = ""; }
      return;
    }
    var lines = narr ? $$(".nr-line", narr) : [];
    // item3 — walk backwards past content-free 'turn complete'/empty markers to the last real line.
    var lastText = "";
    for (var li = lines.length - 1; li >= 0; li--) {
      var lp = $("p", lines[li]); var ltx = lp ? lp.textContent.trim() : "";
      if (!isNarrMarker(ltx)) { lastText = ltx; break; }
    }
    if (!lastText) {
      // nothing but markers/empties (or no narration at all) → localized empty-state, and
      // there is nothing more to reveal, so hide the 'show full' toggle and any ask chip.
      if (lead) { lead.hidden = false; lead.textContent = lang() === "zh" ? "本轮已结束 · 无叙述记录" : "Run finished — no narration captured"; }
      if (ask) { ask.hidden = true; ask.innerHTML = ""; }
      if (toggle) { toggle.hidden = true; }
      return;
    }
    if (lead) { lead.hidden = false; lead.textContent = lastText; }   // bold closing takeaway
    if (ask) {
      // a final turn ending in a question is an open ask the green verdict hides — flag it.
      var interro = /[?？]/.test(lastText) || /告诉我/.test(lastText) || /let me know/i.test(lastText);
      if (interro) {
        var n = (lastText.match(/[?？]/g) || []).length || 1, zh = lang() === "zh";
        ask.hidden = false;
        ask.innerHTML = '<button class="narr-ask-chip" id="sp-narr-askbtn">' + ic("sp-warn", "sm") +
          (zh ? ("还有 " + n + " 条待你定夺 →") : (n + " still need" + (n === 1 ? "s" : "") + " your call →")) + '</button>';
        var ab = $("#sp-narr-askbtn", ask);
        if (ab) ab.onclick = function () {
          col.classList.remove("collapsed"); col.dataset.userToggled = "1";
          if (toggle) { toggle.setAttribute("aria-expanded", "true"); toggle.textContent = narrToggleLabel(false); }
          if (narr) narr.scrollTop = narr.scrollHeight;
        };
      } else { ask.hidden = true; ask.innerHTML = ""; }
    }
    if (toggle) {
      toggle.hidden = false;
      if (!col.dataset.userToggled) {
        col.classList.add("collapsed");
        toggle.setAttribute("aria-expanded", "false");
        toggle.textContent = narrToggleLabel(true);
      }
    }
  }

  function pollRunOnce(token) {
    var id = RV.runId;
    fetch("/api/run/" + encodeURIComponent(id) + "?cursor=" + RV.cursor).then(function (r) { return r.json(); }).then(function (d) {
      if (RV.token !== token || RV.runId !== id) return;
      RV.run = d;
      updateChrome(d);
      var evs = d.events || [];
      if (evs.length) appendRunEvents(evs);
      RV.cursor = typeof d.cursor === "number" ? d.cursor : RV.cursor + evs.length;
      if (!TERMINAL[d.status]) RV.runTimer = setTimeout(function () { pollRunOnce(token); }, 1500);
    }).catch(function () {
      if (RV.token !== token || RV.runId !== id) return;
      RV.runTimer = setTimeout(function () { pollRunOnce(token); }, 1500);
    });
  }

  function statusWord(s) {
    var m = { done: lang() === "zh" ? "完成" : "done", error: lang() === "zh" ? "出错" : "error",
      stopped: lang() === "zh" ? "已停止" : "stopped" };
    return m[s] || s;
  }
  function runHeadHTML(d) {
    var p = parseStage(d.stage), idx = p && p.idx >= 0 ? p.idx : 0, st = d.status || "running";
    // item6 — a done-but-blocking run must not wear a plain green "完成"; gate the header chip
    // on the SAME juryBlocking() the verdict banner below reads, so header + banner never
    // contradict (green "完成" over an amber "还有 N 项阻断").
    var headBlk = st === "done" ? juryBlocking() : null;
    var doneBlocking = st === "done" && headBlk != null && headBlk > 0;
    var doneWord = doneBlocking
      ? (lang() === "zh" ? statusWord("done") + " · " + headBlk + " 项阻断"
                         : statusWord("done") + " · " + headBlk + " blocking")
      : statusWord(st);
    var statusChip = TERMINAL[st]
      ? '<span class="chip ' + (st === "done" ? (doneBlocking ? "stale" : "ok") : st === "error" ? "bad" : "stale") + '">' + esc(doneWord) + '</span>'
      : '<span class="chip wait"><span class="dotb"></span>' + (st === "waiting" ? T("waiting") : T("running")) + '</span>';
    // R10 — a done run's CTAs (Open PDF / Send to Jury) now live INSIDE the verdict banner
    // below, so the header keeps only the live-run Stop control.
    var actions =
      (!TERMINAL[st] ? '<button class="btn sm ghost" id="sp-stop">' + (lang() === "zh" ? "停止" : "Stop") + '</button>' : "");
    // R13 — a terminal-but-not-done run marks WHERE it stopped (red ✕ = errored stage,
    // amber ! = halted stage), and the pulsing "now" glow is killed for every terminal run
    // so a stopped stage never masquerades as a live one.
    var bad = st === "error" || st === "stopped";
    // B — per-stage TOKEN heatmap. Drive the tint from real telemetry.per_stage when the
    // run was instrumented; otherwise leave the tape un-tinted and (below) say so honestly.
    // A genuine live run has per_stage as {stage:{in,out}}; a library run that kept no token
    // stream exposes per_stage=null / captured=false — never fabricate a number for it.
    var tel = d.telemetry || {};
    var heat = stageHeatProfile(tel.per_stage);
    var heatSource = (tel.per_stage && heat.max > 0) ? "live" : "none";
    var tape = STAGE_LABELS.map(function (n, i) {
      var cls, glyph = "";
      if (st === "done") cls = "done";
      else if (bad) {
        cls = i < idx ? "done" : i === idx ? (st === "error" ? "error" : "halt") : "todo";
        if (i === idx) glyph = st === "error" ? "✕" : "!";
      } else cls = i < idx ? "done" : i === idx ? "now" : "todo";
      // item2 — one shared node builder: focusable stage button (its aria-label carries the
      // token count + tier), a width-scaled underline heat bar, and a focus/click-pinned count.
      return stNodeHTML(cls, glyph, stageLabel(n), i, heat, heatSource);
    }).join("");
    // R1 — when the dir could not be read (or this is the built-in sample), lead with the
    // SAME sample/couldNotRead banner the sibling Spark views show, so the runs head never
    // wears a "live" look over sample data.
    var sampleTop = runIsSample(d) ? sampleBannerHTML("运行", "run") : "";
    // item31a — on a terminal run the giant folio numeral out-shouts the actual verdict word;
    // tint + shrink it (CSS .folio-wrap.terminal) and let the verdict banner below lead.
    return sampleTop + '<div class="folio-wrap' + (TERMINAL[st] ? " terminal" : "") + '">' +
        '<div class="folio">' + pad2(idx + 1) + '<span class="folio-den">/ ' + pad2(STAGE_LABELS.length) + '</span></div>' +
        '<div class="folio-meta"><span class="kick">' + T("now") + '</span>' +
          '<div class="folio-stage">' + esc(stageLabel(p && p.name ? cap1(p.name) : STAGE_LABELS[idx])) + '</div>' + statusChip + '</div>' +
        // R30 — cost + duration ride in the hero header, above the fold, next to the actions
        '<div class="run-actions">' + actions + heroMetricHTML(d) + budgetChipHTML() + liveHint(d) + '</div>' +
      '</div>' +
      '<div class="stage-tape-wrap"><div class="stage-tape' + (heatSource === "live" ? " heat-on" : "") + '">' + tape + '</div></div>' +
      heatLegendHTML(heat, heatSource) +
      // R18 — a finished run answers "is my paper OK?" loudly: a toned verdict banner
      // replaces the quiet status line when the run is terminal.
      (TERMINAL[st] ? verdictBannerHTML(d) : '<p class="run-status">' + esc(d.status_line || T("running")) + '</p>');
  }
  // B — per-stage token heatmap primitives. stageHeatProfile folds telemetry.per_stage
  // ({"<n> <stage>": {in, out}}) down to a per-node total keyed by the 0–8 stage index
  // (parseStage handles the "<n> <name>" key shape), plus the max for normalization.
  function stageHeatProfile(perStage) {
    var byIdx = {}, max = 0, total = 0;
    if (perStage && typeof perStage === "object") {
      Object.keys(perStage).forEach(function (k) {
        var v = perStage[k] || {}, t = (Number(v.in) || 0) + (Number(v.out) || 0);
        var ps = parseStage(k), i = ps ? ps.idx : -1;
        if (i < 0 || i > 8) return;
        byIdx[i] = (byIdx[i] || 0) + t;
        if (byIdx[i] > max) max = byIdx[i];
        total += t;
      });
    }
    return { byIdx: byIdx, max: max, total: total };
  }
  // The tint layer for one stage node: a sequential accent fill whose strength is the
  // node's share of the busiest stage. No data for this node (or no heatmap at all) → no
  // tint, so an un-instrumented tape stays honestly blank rather than uniformly cold.
  function heatSpanHTML(idx, heat, source) {
    if (source !== "live" && source !== "sample") return "";
    if (!heat || heat.max <= 0) return "";
    var zh = lang() === "zh";
    var t = heat.byIdx[idx];
    // item3d — captured heatmap but this stage kept no tokens → a subtle hatch marker, so a
    // missed stage reads as "no data here", not a cold zero.
    if (t == null) {
      return '<span class="st-heat st-heat-none" title="' +
        esc(zh ? "本环节无 token 记录" : "no tokens recorded for this stage") + '"></span>';
    }
    // item3d — tint floor 0.15 + 0.85·(t/max) so a captured-but-light stage still shows.
    var frac = Math.max(0, Math.min(1, t / heat.max));
    var h = 0.15 + 0.85 * frac;
    var title = (zh ? "本环节 token · " : "stage tokens · ") + tokfmt(t) + (source === "sample" ? (zh ? " · 示例" : " · sample") : "");
    return '<span class="st-heat" style="--heat:' + h.toFixed(3) + '" title="' + esc(title) + '"></span>';
  }
  // item3b — the SR string for one node: value + low/mid/high tier (or a "no record" note).
  function heatTier(frac, zh) {
    return frac >= 0.66 ? (zh ? "高" : "high") : frac >= 0.33 ? (zh ? "中" : "mid") : (zh ? "低" : "low");
  }
  function heatNodeAria(idx, heat, source, zh) {
    if ((source !== "live" && source !== "sample") || !heat || heat.max <= 0) return "";
    var t = heat.byIdx[idx];
    if (t == null) return " · " + (zh ? "无 token 记录" : "no tokens recorded");
    return " · " + (zh ? "token " : "tokens ") + tokfmt(t) + " · " + heatTier(t / heat.max, zh);
  }
  // item2b — the redundant NON-COLOR encoding: a compact token count under the node,
  // hidden at rest and revealed on hover / focus / click (the width-scaled bar carries the
  // always-on magnitude; this carries the exact number). Only when this stage kept tokens.
  function heatTokHTML(idx, heat, source) {
    if ((source !== "live" && source !== "sample") || !heat || heat.max <= 0) return "";
    var t = heat.byIdx[idx];
    if (t == null) return "";
    return '<span class="st-tok" aria-hidden="true">' + esc(tokfmt(t)) + '</span>';
  }
  // item2 — the single stage-node builder shared by the live runs head and the sample cockpit.
  // On an instrumented tape (source live/sample) each node becomes a focusable button whose
  // aria-label already carries the token count + tier (SR surfacing on focus); mouse users get
  // the same count in title= and a click pins the on-node count. Un-instrumented tapes stay
  // plain, non-focusable divs so a blank tape never fakes interactivity.
  function stNodeHTML(cls, glyph, label, idx, heat, source) {
    var zh = lang() === "zh";
    var instrumented = (source === "live" || source === "sample") && heat && heat.max > 0;
    var aria = esc(label + heatNodeAria(idx, heat, source, zh));
    var t = instrumented ? heat.byIdx[idx] : null;
    var attrs = "";
    if (instrumented) {
      attrs = ' role="button" tabindex="0"';
      if (t != null) attrs += ' title="' + esc((zh ? "本环节 token · " : "stage tokens · ") + tokfmt(t)) + '"';
    }
    return '<div class="st-node ' + cls + '"' + attrs + ' aria-label="' + aria + '">' +
      heatSpanHTML(idx, heat, source) +
      '<span class="st-dot">' + (glyph || "") + '</span>' +
      '<span class="st-lbl">' + esc(label) + '</span>' +
      heatTokHTML(idx, heat, source) +
    '</div>';
  }
  // item2e — reuse the subnav's scrollable mask-fade on the stage tape when it overflows, and
  // item2c — wire the focusable nodes to pin their per-stage token count on click / Enter / Space.
  function wireStageTape(root) {
    if (!root) return;
    var wrap = $(".stage-tape-wrap", root); if (!wrap) return;
    function sync() {
      var over = wrap.scrollWidth - wrap.clientWidth > 2;
      wrap.classList.toggle("scrollable", over);
      wrap.classList.toggle("fade-l", over && wrap.scrollLeft > 2);
      wrap.classList.toggle("fade-r", over && wrap.scrollLeft < wrap.scrollWidth - wrap.clientWidth - 2);
    }
    wrap.addEventListener("scroll", sync);
    // one live resize handler, retargeted each render and self-removing once the wrap is gone.
    if (RV._tapeResize) { try { window.removeEventListener("resize", RV._tapeResize); } catch (e) {} RV._tapeResize = null; }
    RV._tapeResize = function () {
      if (document.body.contains(wrap)) sync();
      else { window.removeEventListener("resize", RV._tapeResize); RV._tapeResize = null; }
    };
    window.addEventListener("resize", RV._tapeResize);
    sync();
    $$(".st-node[role='button']", wrap).forEach(function (nd) {
      var pin = function () { nd.classList.toggle("tok-on"); };
      nd.onclick = pin;
      nd.onkeydown = function (e) { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); pin(); } };
    });
  }
  // The legend under the tape — a low→high ramp when a heatmap is shown (flagged 示例 for
  // the sample profile), or the honest "not captured" line when a real run kept no per-stage
  // token stream. Nothing is drawn when there is simply no telemetry context at all.
  function heatLegendHTML(heat, source) {
    var zh = lang() === "zh";
    if (source === "none") {
      return '<div class="heat-legend none" role="note">' + ic("sp-warn", "sm") +
        '<span>' + (zh ? "本次运行未采集逐环节 token" : "per-stage tokens not captured for this run") + '</span></div>';
    }
    if ((source !== "live" && source !== "sample") || !heat || heat.max <= 0) return "";
    var flag = source === "sample" ? '<span class="src-hint sample">' + (zh ? "示例" : "Sample") + '</span>' : "";
    // item2d — name the busiest stage as a SHARE of total ("写作最耗 · 占 38%") so the callout
    // reads as proportion, not a raw magnitude; the exact token count rides in the tooltip.
    var topIdx = -1, topV = 0;
    Object.keys(heat.byIdx).forEach(function (k) { if (heat.byIdx[k] > topV) { topV = heat.byIdx[k]; topIdx = +k; } });
    var share = heat.total > 0 ? Math.round((topV / heat.total) * 100) : 0;
    var cap = topIdx >= 0
      ? '<span class="hl-top" title="' + esc(tokfmt(topV) + (zh ? " token" : " tokens")) + '">' +
          esc(stageLabel(STAGE_LABELS[topIdx]) + (zh ? " 最耗 · 占 " + share + "%" : " heaviest · " + share + "% of total")) + '</span>'
      : "";
    return '<div class="heat-legend" role="note"><span class="hl-lbl">' + (zh ? "token 用量" : "token use") + '</span>' +
      '<span class="hl-ends">' + (zh ? "低" : "low") + '</span><span class="hl-ramp" aria-hidden="true"></span>' +
      '<span class="hl-ends">' + (zh ? "高" : "high") + '</span>' + cap + flag + '</div>';
  }
  // R30 — compact "$4.82 · 38m" chip for the hero header. Each half is shown only when
  // its telemetry exists (honest "—"-by-omission); the raw pair sits in the tooltip.
  function heroMetricHTML(d) {
    var tel = d.telemetry || {}, card = findCard(d.id) || {};
    var cost = tel.cost_usd != null ? money(tel.cost_usd) : null;
    var dur = tel.duration_ms ? compact(tel.duration_ms / 1000)
      : (card.started && !TERMINAL[d.status] ? compact((Date.now() - (toMs(card.started) || Date.now())) / 1000) : null);
    // item3a — a total-tokens chip from the SAME per-stage heat profile (omitted when the run
    // kept no per-stage stream — heat source "none" — so we never fabricate a count).
    var heat = stageHeatProfile(tel.per_stage);
    var tok = (tel.per_stage && heat.total > 0) ? tokfmt(heat.total) : null;
    var zh = lang() === "zh";
    var parts = []; if (cost) parts.push(cost); if (dur) parts.push(dur); if (tok) parts.push(tok + " tok");
    if (!parts.length) return "";
    var raw = [cost ? (zh ? "花费 " : "cost ") + cost : "", dur ? (zh ? "用时 " : "elapsed ") + dur : "",
      tok ? (zh ? "共 " : "total ") + tok + " tok" : ""].filter(Boolean).join(" · ");
    return '<span class="hero-metric" title="' + esc(raw) + '">' + ic("sp-clock", "sm") + parts.join(" · ") + '</span>';
  }
  // item19 — the runs hero shows spend but never the ceiling a PI worries about (GPU-hours /
  // outer-round caps). Surface a compact budget chip beside cost, tinted amber near the cap and
  // red at/over it, from the SAME LEDGER.budget Governance reads. Each half shows only when its
  // pair of numbers exists (honest omission).
  function budgetTone(a, cap) {
    if (a == null || !cap) return "";
    var r = a / cap; return r >= 1 ? "over" : r >= 0.8 ? "near" : "";
  }
  function budgetChipHTML() {
    var b = LEDGER.budget || {}, zh = lang() === "zh", chips = [];
    if (b.gpu_hours_spent != null && b.gpu_hours_cap != null)
      chips.push('<span class="bud-chip ' + budgetTone(b.gpu_hours_spent, b.gpu_hours_cap) + '">' +
        esc(b.gpu_hours_spent + "/" + b.gpu_hours_cap) + " " + (zh ? "GPU 小时" : "GPU-h") + '</span>');
    if (b.outer_round != null && b.outer_rounds_cap != null)
      chips.push('<span class="bud-chip ' + budgetTone(b.outer_round, b.outer_rounds_cap) + '">' +
        esc(b.outer_round + "/" + b.outer_rounds_cap) + " " + (zh ? "轮" : "rounds") + '</span>');
    if (!chips.length) return "";
    return '<span class="budget-chips" title="' + esc(zh ? "预算(GPU 小时 · 外层轮次)" : "budget (GPU-hours · outer rounds)") + '">' + chips.join("") + '</span>';
  }
  function verdictBannerHTML(d) {
    var st = d.status || "done", zh = lang() === "zh";
    // item1 — the verdict used to key purely on status===done and stayed green even while the
    // Reader ribbon + Jury docket (both reading SB.needs.detail.jury.blocking) said "尚不可提交 ·
    // N 项阻断". Gate the tone on that SAME signal; and never assert a verdict — or fire a
    // 404-prone Open PDF — over sample / couldn't-read data.
    var sample = runIsSample(d);
    var blk = st === "done" ? juryBlocking() : null;    // null = no Jury ledger bound (unknown)
    var reviewed = provReviewed(d.id) || blk != null;   // handed to Jury (prov) or a ledger is bound

    var tone, icon, head, chip = "";
    if (sample) {
      tone = "neutral"; icon = "sp-warn";
      head = zh ? "示例运行 · 未评估结论" : "Sample run · verdict not assessed";
    } else if (st === "error") {
      tone = "err"; icon = "sp-warn"; head = zh ? "运行出错" : "Run errored";
    } else if (st !== "done") {
      tone = "halt"; icon = "sp-warn"; head = zh ? "运行已停止" : "Run halted";
    } else if (blk != null && blk > 0) {
      // pipeline finished but Jury still holds blocking issues — amber, not a green all-clear.
      tone = "halt"; icon = "sp-warn";
      head = zh ? ("流水线跑完 · 还有 " + blk + " 项阻断待清") : ("Pipeline finished · " + blk + " blocking to clear");
      chip = '<button class="rv-chip" id="sp-shield" title="' + esc(zh ? "跳到投稿护盾" : "Jump to the submission shield") + '">' +
        ic("sp-warn", "sm") + (zh ? "查看阻断项 →" : "See blocking →") + '</button>';
    } else {
      // blocking===0, or no Jury ledger bound at all → the pipeline verdict stands green.
      tone = "ok"; icon = "i-check"; head = zh ? "论文就绪" : "Paper is ready";
    }

    // R22b — pick the sub-line by language so an English head never sits over a Chinese
    // status line (or vice-versa); fall back to the single status_line the server sends.
    var line = (zh ? (d.status_line_zh || d.status_line) : (d.status_line_en || d.status_line)) || "";
    // R10 / item10 — a done, non-sample run gets a loud CTA INSIDE the verdict: solid primary
    // "Open PDF" (only when a real pdf artifact exists) + a Jury handoff. Once reviewed, the
    // ghost "Send to Jury" becomes a "Reviewed in Jury · N blocking →" chip deep-linking to the
    // shield. Sample runs get no CTA (window.open on a sample runId 404s).
    var cta = "";
    if (st === "done" && !sample) {
      var juryBtn = reviewed
        ? '<button class="btn sm ghost" id="sp-jreviewed">' + ic("sp-route", "sm") +
            (zh ? ("已评审 · Jury" + (blk != null ? (blk > 0 ? " · " + blk + " 项阻断" : " · 可提交") : "") + " →")
                : ("Reviewed in Jury" + (blk != null ? " · " + (blk > 0 ? blk + " blocking" : "clear") : "") + " →")) + '</button>'
        : '<button class="btn sm ghost" id="sp-jury">' + ic("sp-route", "sm") + (zh ? "送去评审" : "Send to Jury") + '</button>';
      cta = '<div class="rv-cta">' +
        ((d.artifacts && d.artifacts.pdf) ? '<button class="btn sm primary" id="sp-pdf">' + (zh ? "打开 PDF" : "Open PDF") + '</button>' : "") +
        juryBtn + '</div>';
    }
    // suppress the pipeline's own "all gates green" status line when Jury still holds blockers —
    // otherwise it reads as a flat contradiction beside the amber "N blocking to clear" head.
    var showLine = line && !(blk != null && blk > 0);
    return '<div class="run-verdict ' + tone + '"><span class="rv-ic">' + ic(icon) + '</span>' +
      '<div class="rv-tx"><b>' + esc(head) + '</b>' + (showLine ? '<span>' + esc(line) + '</span>' : "") + chip + '</div>' + cta + '</div>';
  }
  function waitHTML(d) {
    if (!d.needs_reply) return "";
    return '<div class="wait-line">' + ic("i-ask") +
        '<div class="wl-tx"><b>' + T("Waiting for you") + '</b> — ' + esc(d.question || "") + '</div>' +
        '<span class="wl-chip">' + T("reply in chat") + '</span></div>' +
      '<div class="reply-box"><textarea id="sp-reply" placeholder="' +
        esc(lang() === "zh" ? "你的回复…(回车发送,Shift+回车换行)" : "Your answer… (Enter sends, Shift+Enter for a new line)") + '"></textarea>' +
        '<div class="reply-actions"><button class="btn sm primary" id="sp-send">' + (lang() === "zh" ? "发送" : "Send") + '</button>' +
        '<span class="reply-note" id="sp-reply-note"></span></div></div>';
  }
  function updateChrome(d) {
    var head = $("#sp-head", RV.host); if (head) { head.innerHTML = runHeadHTML(d); wireSampleBanner(head); wireStageTape(head); }
    var stop = $("#sp-stop", RV.host); if (stop) stop.onclick = doStop;
    var pdf = $("#sp-pdf", RV.host); if (pdf) pdf.onclick = function () { window.open("/api/run/" + encodeURIComponent(RV.runId) + "/file?path=main.pdf", "_blank"); };
    // item10 — the run→charge provenance breadcrumb. Deep-link to the submission shield and,
    // where a shared-project hook exists, bind this run so Jury reads the right ledger.
    function goShield() { if (SB.project) { try { SB.project.set(RV.runId); } catch (e) {} } SB.setTool("jury"); SB.setSub("shield"); }
    // R6 / item10 — hand this run to Jury AND persist a provenance link ({reviewedFromRun})
    // so the handoff stops being a dead-end (Jury renders 'Source: run X →' from SB.prov).
    var jury = $("#sp-jury", RV.host); if (jury) jury.onclick = function () {
      try { if (SB.prov && SB.prov.link) SB.prov.link(RV.runId, { reviewedFromRun: RV.runId }); } catch (e) {}
      if (SB.project) { try { SB.project.set(RV.runId); } catch (e) {} }
      SB.setTool("jury");
    };
    var shield = $("#sp-shield", RV.host); if (shield) shield.onclick = goShield;
    var jrev = $("#sp-jreviewed", RV.host); if (jrev) jrev.onclick = goShield;
    // Rebuild the reply box ONLY when the question changes — otherwise the 1.5 s
    // poll would wipe the user's half-typed answer and steal focus each tick.
    var waitKey = d.needs_reply ? "1|" + (d.question || "") : "0";
    if (waitKey !== RV.waitKey) {
      RV.waitKey = waitKey;
      var waitwrap = $("#sp-waitwrap", RV.host);
      if (waitwrap) { waitwrap.innerHTML = waitHTML(d); wireReply(); }
    }
    var telem = $("#sp-telem", RV.host); if (telem) telem.innerHTML = telemHTML(d);
    var shelf = $("#sp-shelf", RV.host); if (shelf) shelf.innerHTML = shelfHTML(d);
    refreshApprDisclosure();   // R8 — collapse/expand the tool log to match terminal state
    refreshNarrDisclosure();   // item18 — pin the closing line + flag any open ask
  }
  function wireReply() {
    var box = $("#sp-reply", RV.host), send = $("#sp-send", RV.host);
    if (!box || !send) return;
    send.onclick = doReply;
    box.addEventListener("keydown", function (e) { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); doReply(); } });
    box.focus();
  }
  function doReply() {
    var box = $("#sp-reply", RV.host), note = $("#sp-reply-note", RV.host), id = RV.runId, token = RV.token;
    var text = box ? box.value.trim() : ""; if (!text) return;
    box.disabled = true; if (note) note.textContent = lang() === "zh" ? "正在发送…" : "Sending…";
    fetch("/api/run/" + encodeURIComponent(id) + "/reply", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text: text }) })
      .then(function (r) { if (!r.ok) throw r; return r.json(); })
      .then(function () { if (RV.token !== token) return; box.value = ""; if (note) note.textContent = lang() === "zh" ? "已发送" : "Sent"; pollRunOnce(token); })
      .catch(function () { if (note) note.textContent = lang() === "zh" ? "发送失败,文字还在框里。" : "Could not send — your text is still here."; box.disabled = false; });
  }
  function doStop() {
    var id = RV.runId, token = RV.token;
    fetch("/api/run/" + encodeURIComponent(id) + "/stop", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" })
      .then(function () { if (RV.token === token) pollRunOnce(token); });
  }
  function telemHTML(d) {
    var tel = d.telemetry || {}, tok = tel.tokens || {}, card = findCard(d.id) || {};
    var dur = tel.duration_ms ? compact(tel.duration_ms / 1000)
      : (card.started && !TERMINAL[d.status] ? compact((Date.now() - (toMs(card.started) || Date.now())) / 1000) : "—");
    // item31b — fold tokens in/out into ONE 'tokens 153.8k↓/376.3k↑' cell; keep the split in title=.
    var zh = lang() === "zh";
    var tokVal = tokfmt(tok.in) + "↓/" + tokfmt(tok.out) + "↑";
    var tokTitle = (zh ? "输入 " : "in ") + tokfmt(tok.in) + " · " + (zh ? "输出 " : "out ") + tokfmt(tok.out);
    return telCell("model", tel.model || "—", true) + telCell("turns", tel.turns == null ? "—" : String(tel.turns)) +
      telCell("tokens", tokVal, false, tokTitle) +
      telCell("cost", money(tel.cost_usd)) + telCell("duration", dur) +
      telCell("started", fmtStarted(card.started || d.started));
  }
  function shelfHTML(d) {
    var a = d.artifacts || {}, items = [];
    var figs = (a.figures || []).filter(function (p) { return /\.png$/i.test(p); });
    if (figs.length) items.push('<div class="sh-item"><span class="sh-dot ok"></span><span class="sh-lbl">' + esc(figs[figs.length - 1].split(/[\\/]/).pop()) + '</span><span class="sh-note">' + T("figure") + '</span></div>');
    if (a.pdf) items.push('<div class="sh-item"><span class="sh-dot ok"></span><span class="sh-lbl">main.pdf</span><span class="sh-note">' + (lang() === "zh" ? "已编译" : "compiled") + '</span></div>');
    (a.sections || []).slice(-4).reverse().forEach(function (p) {
      items.push('<div class="sh-item"><span class="sh-dot ok"></span><span class="sh-lbl">' + esc(p.split(/[\\/]/).pop()) + '</span><span class="sh-note">' + (lang() === "zh" ? "已写" : "written") + '</span></div>');
    });
    if (!items.length) items.push('<div class="sh-item"><span class="sh-dot"></span><span class="sh-lbl">' + (lang() === "zh" ? "尚无产物" : "no artifacts yet") + '</span></div>');
    return items.join("");
  }
  function shortArg(t) { t = String(t || ""); if (t.length > 120) t = t.slice(0, 117) + "…"; return t; }
  function appendRunEvents(list) {
    var narr = RV.$narr, appr = RV.$appr; if (!narr || !appr) return;
    list.forEach(function (e) {
      var kind = String(e.kind || "assistant").toLowerCase();
      if (kind === "tool" || kind === "tool_use" || kind === "tool_result") {
        appr.insertAdjacentHTML("beforeend", '<div class="ap-row"><span class="ap-tool">' + esc(e.label || "tool") + '</span><span class="ap-arg">' + esc(shortArg(e.text)) + '</span></div>');
      } else if (kind === "user" || kind === "reply" || kind === "human") {
        narr.insertAdjacentHTML("beforeend", '<div class="nr-line nr-user"><span class="nr-t">' + esc(clock(e.t)) + '</span><p><b>' + (lang() === "zh" ? "你:" : "You: ") + '</b>' + proseLite(e.text) + '</p></div>');
      } else if (kind === "result" || kind === "system" || kind === "status") {
        var s = (e.text || "").trim(); if (!s) return;
        narr.insertAdjacentHTML("beforeend", '<div class="nr-line nr-sys"><span class="nr-t">' + esc(clock(e.t)) + '</span><p>' + esc(s) + '</p></div>');
      } else {
        var text = (e.text || "").trim(); if (!text) return;
        narr.insertAdjacentHTML("beforeend", '<div class="nr-line"><span class="nr-t">' + esc(clock(e.t)) + '</span><p>' + proseLite(text) + '</p></div>');
      }
    });
    narr.scrollTop = narr.scrollHeight; appr.scrollTop = appr.scrollHeight;
    refreshApprDisclosure();   // R8 — recompute the summary now the full log has landed
    refreshNarrDisclosure();   // item18 — re-pin the closing line once the turn has landed
  }

  /* ---- new-paper form (POST /api/runs) ---------------------------------- */
  function selHTML(id, opts) {
    return '<select id="' + id + '">' + opts.map(function (o) { return '<option value="' + esc(o[0]) + '">' + esc(o[1]) + '</option>'; }).join("") + '</select>';
  }
  function paintNewForm(token) {
    RV.runId = null;
    function build(s) {
      if (RV.token !== token) return;
      var models = (s && s.models) || [], efforts = (s && s.efforts) || [], hosts = (s && s.ssh_hosts) || [];
      RV.host.innerHTML =
        '<div class="pane-wide reveal">' + (RV.runs.length ? runsPickerHTML() : "") +
          '<div class="new-form card">' +
            '<div class="nf-head"><h2>' + (lang() === "zh" ? "写下你的想法" : "Write down your idea") + '</h2></div>' +
            '<textarea id="nf-spark" class="nf-spark" placeholder="' + esc(lang() === "zh" ? "想法、主张、你手上的数据、想投的会议 —— 头五分钟里你会告诉合作者的,都写进来。" : "Idea, claim, the data you have, the venue you're aiming at — whatever you'd tell a collaborator in the first five minutes.") + '"></textarea>' +
            '<input id="nf-name" class="nf-name" type="text" placeholder="' + esc(lang() === "zh" ? "运行名称 —— 留空则自动生成" : "Run name — blank to auto-generate") + '">' +
            '<div class="nf-row">' +
              selHTML("nf-tpl", [["ts_iieta", "Traitement du Signal"], ["neurips_official", "NeurIPS 2025 · official"], ["neurips", "NeurIPS · approx"]]) +
              selHTML("nf-mode", [["auto", lang() === "zh" ? "自动 · 阶段 0 决定" : "auto · Stage 0 routes"], ["proposal", "proposal"], ["data_aware", "data-aware"]]) +
              selHTML("nf-review", [["lean", "review · lean"], ["cheapest", "cheapest"], ["thorough", "thorough"], ["skip", "skip"]]) +
              selHTML("nf-model", [["", lang() === "zh" ? "默认模型" : "default model"]].concat(models.map(function (m) { return [m, m]; }))) +
              selHTML("nf-effort", [["", lang() === "zh" ? "默认强度" : "default effort"]].concat(efforts.map(function (x) { return [x, x]; }))) +
              selHTML("nf-remote", [["", lang() === "zh" ? "本机" : "this machine"]].concat(hosts.map(function (h) { return [h, h]; }))) +
            '</div>' +
            '<div class="nf-go"><button class="btn primary" id="nf-start">' + (lang() === "zh" ? "开始运行" : "Start run") + '</button>' +
              '<span class="nf-note">' + (lang() === "zh" ? "约需 30–90 分钟;可关掉窗口,运行会继续。" : "~30–90 min; you can close the window and the run keeps going.") + '</span></div>' +
            '<div class="nf-err" id="nf-err"></div>' +
          '</div>' +
        '</div>';
      if (RV.runs.length) wirePicker(token);
      var sb = $("#nf-start", RV.host); if (sb) sb.onclick = function () { submitNew(token); };
      applyPendingDraft(token);   // item11 — prefill from a KB→Spark draft, if one is pending
    }
    if (RV.settings) build(RV.settings);
    else fetch("/api/settings").then(function (r) { return r.json(); }).then(function (s) { RV.settings = s; build(s); }).catch(function () { build(null); });
  }
  // item11 — fill the new-paper form from a stashed Wiki draft, then clear + focus it.
  function applyPendingDraft(token) {
    if (RV.token !== token || !RV.pendingDraft) return;
    var sp = $("#nf-spark", RV.host), nm = $("#nf-name", RV.host);
    if (!sp) return;
    sp.value = RV.pendingDraft.spark || "";
    if (nm && RV.pendingDraft.name) nm.value = RV.pendingDraft.name;
    RV.pendingDraft = null;
    try { sp.focus(); sp.setSelectionRange(sp.value.length, sp.value.length); } catch (e) {}
  }
  function val(id) { var s = $("#" + id, RV.host); return s ? s.value : ""; }
  function submitNew(token) {
    var spark = (($("#nf-spark", RV.host) || {}).value || "").trim(), err = $("#nf-err", RV.host);
    if (!spark) { if (err) err.textContent = lang() === "zh" ? "先写下想法 —— 它就是全部输入。" : "Write the idea first — it is the whole input."; return; }
    var body = { spark: spark, name: (($("#nf-name", RV.host) || {}).value || "").trim(), template: val("nf-tpl"), mode: val("nf-mode"), review: val("nf-review") };
    var model = val("nf-model"), effort = val("nf-effort"), remote = val("nf-remote");
    if (model) body.model = model; if (effort) body.effort = effort; if (remote) body.remote = remote;
    var btn = $("#nf-start", RV.host); if (btn) { btn.disabled = true; btn.textContent = lang() === "zh" ? "正在启动…" : "Starting…"; }
    fetch("/api/runs", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) })
      .then(function (r) { if (!r.ok) throw r; return r.json(); })
      .then(function (d) {
        if (RV.token !== token) return;
        RV.runs.unshift({ id: d.id, title: body.name || spark.slice(0, 40), status: "starting", stage: "", started: Date.now(), needs_reply: false });
        selectRun(d.id, token);
      })
      .catch(function () {
        if (btn) { btn.disabled = false; btn.textContent = lang() === "zh" ? "开始运行" : "Start run"; }
        if (err) err.textContent = lang() === "zh" ? "启动失败 —— 详情见服务器日志。" : "Could not start — see the server log.";
      });
  }

  // item11 — the KB→Spark edge that turns the linear spark→jury→wiki pipeline into a flywheel.
  // Wiki calls SB.sparkDraft({title,hypothesis,direction}) from a scored idea card: switch to
  // Spark's runs cockpit and prefill the new-paper form. The draft is stashed and applied once
  // the form paints (the render is async through fetchRunsState).
  SB.sparkDraft = function (idea) {
    idea = idea || {};
    var parts = [];
    if (idea.title) parts.push(String(idea.title).trim());
    if (idea.hypothesis) parts.push(String(idea.hypothesis).trim());
    if (idea.direction) parts.push(String(idea.direction).trim());
    RV.pendingDraft = { spark: parts.filter(Boolean).join("\n\n"), name: idea.title ? String(idea.title).trim() : "" };
    SB.setTool("spark");
    SB.setSub("runs");   // renderRuns → fetchRunsState → paintNewForm applies the draft
  };

  /* ---- static sample cockpit — the no-server fallback (unchanged design) - */
  function paintSampleRun(host) {
    host.innerHTML = "";
    var w = el("div", "pane-wide reveal");
    var lit = STAGE_NODES[RUN.now_index];
    var sampleHeat = stageHeatProfile(SAMPLE_PER_STAGE);   // B — flagged 示例 in the legend + tints
    var stageHead =
      '<div class="run-head card">' +
        '<div class="folio-wrap">' +
          '<div class="folio">' + pad2(RUN.now_index + 1) + '<span class="folio-den">/ ' + pad2(STAGE_NODES.length) + '</span></div>' +
          '<div class="folio-meta"><span class="kick">' + T("now") + '</span><div class="folio-stage">' + esc(stageLabel(lit)) + '</div>' +
            '<span class="chip wait"><span class="dotb"></span>' + T("running") + '</span></div>' +
          '<div class="run-actions"><span class="hero-metric" title="' + esc((lang() === "zh" ? "花费 " : "cost ") + RUN.telemetry.cost + " · " + (lang() === "zh" ? "用时 " : "elapsed ") + RUN.telemetry.duration) + '">' + ic("sp-clock", "sm") + esc(RUN.telemetry.cost) + ' · ' + esc(RUN.telemetry.duration) + '</span>' + budgetChipHTML() + srcHint(false) + '</div>' +
        '</div>' +
        '<div class="stage-tape-wrap"><div class="stage-tape heat-on">' +
          STAGE_NODES.map(function (n, i) {
            var st = i < RUN.done_through + 1 ? (i === RUN.now_index ? "now" : "done") : "todo";
            if (i === RUN.now_index) st = "now";
            // item2 — same shared focusable node builder as the live tape (sample heat profile).
            return stNodeHTML(st, "", stageLabel(n), i, sampleHeat, "sample");
          }).join("") +
        '</div></div>' +
        heatLegendHTML(sampleHeat, "sample") +
        '<p class="run-status">' + esc(RUN.status) + '</p>' +
      '</div>';
    var trip =
      '<div class="triptych">' +
        '<div class="card tri-col"><div class="card-h"><span class="kick">' + T("narration") + '</span><h3>' + T("What the agent is doing") + '</h3>' + narrTransToggleHTML() + '</div>' +
          '<div class="narration">' + RUN.narration.map(function (n) {
            return '<div class="nr-line"><span class="nr-t">' + esc(n.t) + '</span><p>' + esc(n.s) + '</p></div>';
          }).join("") + '</div></div>' +
        '<div class="card tri-col"><div class="card-h"><span class="kick">' + T("apparatus") + '</span><h3>' + T("Tool log") + '</h3></div>' +
          '<div class="apparatus">' + RUN.apparatus.map(function (a) {
            return '<div class="ap-row"><span class="ap-tool">' + esc(a.tool) + '</span><span class="ap-arg">' + esc(a.arg) + '</span><span class="ap-out">' + esc(a.out) + '</span></div>';
          }).join("") + '<div class="ap-row live"><span class="ap-cursor"></span><span class="ap-arg">reviewing §5 — verbatim anti-skim…</span></div></div></div>' +
        '<div class="card tri-col"><div class="card-h"><span class="kick">' + T("shelf") + '</span><h3>' + T("Artifacts changing") + '</h3></div>' +
          '<div class="shelf">' + RUN.shelf.map(function (s) {
            return '<div class="sh-item"><span class="sh-dot ' + s.state + '"></span><span class="sh-lbl">' + esc(s.label) + '</span><span class="sh-note">' + esc(s.note) + '</span></div>';
          }).join("") + '</div></div>' +
      '</div>';
    var wait =
      '<div class="wait-line">' + ic("i-ask") +
        '<div class="wl-tx"><b>' + T("Waiting for you") + '</b> — ' + esc(RUN.waiting) + '</div>' +
        '<span class="wl-chip">' + T("reply in chat") + '</span>' +
      '</div>';
    var tl = RUN.telemetry, zhS = lang() === "zh";
    // item31b — the two token columns fold into ONE cell (in↓/out↑); the split rides in title=.
    var telem =
      '<div class="telemetry card">' +
        telCell("model", tl.model, true) + telCell("turns", tl.turns) +
        telCell("tokens", tl.tok_in + "↓/" + tl.tok_out + "↑", false, (zhS ? "输入 " : "in ") + tl.tok_in + " · " + (zhS ? "输出 " : "out ") + tl.tok_out) +
        telCell("cost", tl.cost) + telCell("duration", tl.duration) +
        telCell("started", tl.started) +
      '</div>';
    // item10 — when a dir could not be read we degrade to this sample cockpit; lead with the
    // same couldNotRead banner the sibling views show so the sample data is honestly labelled.
    var cnrBanner = sparkCouldNotRead() ? sampleBannerHTML("运行", "run") : "";
    w.innerHTML = cnrBanner + stageHead + wait + trip + telem;
    host.appendChild(w);
    if (cnrBanner) wireSampleBanner(w);
    wireStageTape(w);   // item2 — scroll-fade + focusable stage nodes on the sample tape too
    var narrCard = $(".narration", w); narrCard = narrCard ? narrCard.closest(".tri-col") : null;
    wireNarrTranslate(narrCard);   // item20b — offer an in-place translate for the sample narration body
  }
  // item12 — the telemetry keys were esc(rawKey), so MODEL/TURNS/TOKENS… stayed English in zh.
  // Route the key through T() (zh entries below), keep the value verbatim. The .zh class drops
  // the Latin uppercase transform so "输入token" renders as written (no <html lang> is set).
  function telCell(k, v, wide, title) {
    var zh = lang() === "zh";
    return '<div class="tel-cell' + (wide ? " wide" : "") + '"' + (title ? ' title="' + esc(title) + '"' : "") + '><span class="tel-k' + (zh ? " zh" : "") + '">' + esc(T(k)) + '</span><span class="tel-v">' + esc(v) + '</span></div>';
  }

  /* =========================================================================
     SUB-VIEW 3 — FIGURES (figure-workshop gallery + lightbox)
     ========================================================================= */
  function renderFigures(main) {
    var tk = newView();
    var dir = dirOpen() ? SB.data.dir("spark") : null;
    if (!dir) {                                    // no run open → the beautiful sample gallery
      resetLive(); HYD.figures = false; paintFigures(main, false); return;
    }
    fetch("/api/spark/figures?path=" + encodeURIComponent(dir))
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (j) {
        if (tk !== VIEW_TOKEN) return;
        resetLive();
        HYD.figures = (j && !j.error) ? hydrateRichFigures(j) : false;
        paintFigures(main, HYD.figures);
      })
      .catch(function () {
        if (tk !== VIEW_TOKEN) return;
        resetLive(); HYD.figures = false; paintFigures(main, false);
      });
  }
  function figImgSrc(f) { return (f.files && (f.files.png || f.files.svg)) || null; }
  function paintFigures(main, real) {
    var pane = el("div", "pane");
    var w = el("div", "pane-wide reveal");
    var vectorN = FIGURES.filter(function (f) { return f.formats.indexOf("svg") >= 0; }).length;
    // item12 — PNG-only figures are their own honest header stat (a raster figure is normal,
    // not an audit failure); item13 — pluralize the EN 'editable vector(s)' label.
    var pngOnlyN = FIGURES.length - vectorN;
    var vecLbl = T("editable vector") + (lang() === "en" && vectorN !== 1 ? "s" : "");
    var pngSeg = pngOnlyN > 0 ? ' · ' + pngOnlyN + ' ' + T("PNG only") : "";
    // No per-figure SSIM exists anywhere in the pipeline — the summary line stays
    // honest and never carries an SSIM segment (the old empty slot is gone).
    var head =
      '<div class="pane-head fig-head"><h2>' + T("Figure workshop") + '</h2><span class="sub">' +
        FIGURES.length + ' ' + T("figures") + ' · ' + vectorN + ' ' + vecLbl + pngSeg +
        ' · ' + T("DrawAI hybrid path") + '</span>' + provChip(real) + '</div>';
    // A real dir open but no figures from the endpoint → the gallery below is sample.
    var amber = (dirOpen() && !real) ? sampleBannerHTML("图表", "figure") : "";
    // item4 — render figures in numeric order (nulls last). Sort in place so the data-i
    // indices used by the hero/lightbox/carousel/palette all stay in agreement with FIGURES.
    FIGURES.sort(function (a, b) { return (a.number == null ? 1e9 : a.number) - (b.number == null ? 1e9 : b.number); });
    var grid = '<div class="fig-grid showcase">' + FIGURES.map(figCardHTML).join("") + '</div>';
    w.innerHTML = amber + head + grid;
    pane.appendChild(w);
    main.appendChild(pane);

    wireSampleBanner(w);

    // The hero image (only) opens the lightbox — the "how it was made" strip below it
    // keeps its own interactive controls (prompt disclosure, versions carousel) that must
    // NOT bubble up into a zoom.
    $$(".fig-hero", w).forEach(function (h) {
      var open = function () { openLightbox(FIGURES[+h.dataset.i]); };
      h.onclick = open;
      h.onkeydown = function (e) { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); open(); } };
    });
    // prompt disclosure
    $$(".fm-prompt-toggle", w).forEach(function (btn) {
      btn.onclick = function () {
        var body = btn.parentNode.querySelector(".fm-prompt");
        var openNow = btn.getAttribute("aria-expanded") !== "true";
        btn.setAttribute("aria-expanded", openNow ? "true" : "false");
        if (body) body.hidden = !openNow;
      };
    });
    // versions carousel — step the redraw rounds
    $$(".fm-versions", w).forEach(function (car) {
      var card = car.closest ? car.closest(".fig-card") : null;
      var fig = card ? FIGURES[+card.dataset.i] : null;
      var slides = $$(".fv-slide", car), n = slides.length; if (!n) return;
      var zh = lang() === "zh";
      var idx = 0, cnt = $(".fv-count", car);
      var prev = $(".fv-prev", car), next = $(".fv-next", car);
      if (cnt) cnt.setAttribute("aria-live", "polite");   // item16 — announce the round change
      function show(k) {
        idx = (k + n) % n;
        slides.forEach(function (s, j) { s.classList.toggle("on", j === idx); });
        if (cnt) { cnt.textContent = (idx + 1) + " / " + n;
          cnt.setAttribute("aria-label", (zh ? "重绘轮次 " : "redraw round ") + (idx + 1) + " / " + n); }
        if (prev) prev.disabled = n < 2; if (next) next.disabled = n < 2;
      }
      if (prev) prev.onclick = function () { show(idx - 1); };
      if (next) next.onclick = function () { show(idx + 1); };
      // item16 — a slide carrying a real round image is clickable/Enter → lightbox that round.
      slides.forEach(function (s) {
        var url = s.getAttribute("data-svg"); if (!url || !fig) return;
        var rd = $(".fv-round", s), rlbl = rd ? rd.textContent : "";
        s.classList.add("fv-zoomable"); s.tabIndex = 0; s.setAttribute("role", "button");
        s.setAttribute("aria-label", (zh ? "放大 " : "Zoom ") + rlbl);
        var openR = function () { openLightbox(fig, { imgSrc: url, titleSuffix: rlbl }); };
        s.onclick = openR;
        s.onkeydown = function (e) { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); openR(); } };
      });
      show(0);
    });
  }
  function figCardHTML(f, i) {
    var zh = lang() === "zh";
    var vector = f.formats.indexOf("svg") >= 0;
    var warns = (f.audit && f.audit.warnings && f.audit.warnings.length) || 0;
    var fmtChips = f.formats.map(function (x) { return '<span class="chip mono">' + x.toUpperCase() + '</span>'; }).join("") +
      (vector ? '<span class="chip ok"><span class="dotb"></span>' + T("vector") + '</span>' : '<span class="chip stale"><span class="dotb"></span>' + T("PNG only") + '</span>');
    // item4 — four honest states; null ≠ false, and a green pass must not hide warnings:
    //   true + warnings>0 → amber "审核 · N 警告" (never a clean green over warnings)
    //   true             → green pass (✓)
    //   false            → a real vector-audit FAILURE (amber)
    //   null + has-svg   → NEUTRAL "审核未采集" (audit not captured — NOT the raster N/A, which
    //                      would contradict the green 'vector' chip beside it)
    //   null + no-svg    → N/A raster (a raster / qualitative figure, not vector-audited)
    var auditChip;
    if (f.audit_ok === true && warns > 0)
      auditChip = '<span class="chip stale" title="' + esc((f.audit.warnings || []).join(" · ")) + '" aria-label="' +
        esc(zh ? "矢量审核 · " + warns + " 条警告" : "vector audit · " + warns + (warns === 1 ? " warning" : " warnings")) + '">' +
        ic("sp-warn", "sm") + (zh ? "审核 · " + warns + " 警告" : "audit · " + warns + (warns === 1 ? " warning" : " warnings")) + '</span>';
    else if (f.audit_ok === true) auditChip = '<span class="chip ok">' + ic("i-check", "sm") + T("audit") + '</span>';
    else if (f.audit_ok === false) auditChip = '<span class="chip stale">' + ic("sp-warn", "sm") + T("audit failed") + '</span>';
    else if (vector) auditChip = '<span class="chip fig-na" title="' + esc(zh ? "本图未采集矢量审核结果" : "vector audit not captured for this figure") + '" aria-label="' +
      esc(zh ? "审核未采集" : "audit not captured") + '">' + (zh ? "审核未采集" : "audit not captured") + '</span>';
    else auditChip = '<span class="chip fig-na" title="' + esc(zh ? "栅格/定性图,不做矢量审核 —— 正常" : "raster / qualitative figure — not vector-audited (normal)") + '" aria-label="' +
      esc(zh ? "不适用:栅格图不做矢量审核" : "N/A — raster figure, not vector-audited") + '">N/A</span>';
    // item4 — an amber corner badge flags a non-vector, a failed, OR a passed-with-warnings card.
    var cornerBadge = (!vector || f.audit_ok === false || (f.audit_ok === true && warns > 0))
      ? '<span class="fig-corner" title="' + esc(
          !vector ? (zh ? "仅 PNG · 无可编辑矢量" : "PNG only · no editable vector")
            : f.audit_ok === false ? (zh ? "矢量审核未过" : "vector audit failed")
              : (zh ? "矢量审核有 " + warns + " 条警告" : "vector audit has " + warns + (warns === 1 ? " warning" : " warnings"))
        ) + '">' + ic("sp-warn", "sm") + '</span>'
      : "";
    var src = figImgSrc(f);
    var hero = src ? '<img class="fig-img" src="' + esc(src) + '" alt="' + esc(f.caption || f.label) + '" loading="lazy">' : figThumb(f.type);
    var figN = f.number != null ? (T("Fig") + " " + f.number) : f.label;   // raw — esc() at each use
    return '<figure class="fig-card showcase" data-i="' + i + '">' + cornerBadge +
      '<button class="fig-hero" type="button" data-i="' + i + '" aria-label="' + esc((zh ? "放大 " : "Zoom ") + (f.number != null ? "Fig " + f.number : f.label)) + '">' +
        hero +
        '<span class="fig-type" title="' + esc(f.type) + '">' + esc(figTypeLabel(f.type)) + '</span>' +
        '<span class="fig-folio">' + esc(figN) + '</span>' +
        '<span class="fig-zoom" aria-hidden="true">' + ic("sp-image", "sm") + '</span>' +
      '</button>' +
      '<figcaption class="fig-cap"><b>' + esc(figN) + '</b>' + (f.caption ? ' · ' + esc(f.caption) : '') + '</figcaption>' +
      // item4 — the format + audit chips read as one labelled group to assistive tech.
      '<div class="fig-chips" role="group" aria-label="' + esc(zh ? "图 " + (f.number != null ? f.number : f.label) + " · 格式与审核" : "Figure " + (f.number != null ? f.number : f.label) + " — formats & audit") + '">' + fmtChips + auditChip + '</div>' +
      figMadeHTML(f) +
    '</figure>';
  }
  // The "生成过程 / How it was made" strip: provenance badges, SVG-audit chips, a
  // collapsible prompt excerpt, and the redraw-round carousel. Only the parts that
  // carry data are drawn; a raster-only figure (no vector, no rounds) shows just badges.
  function figMadeHTML(f) {
    var zh = lang() === "zh";
    var badges = [];
    if (f.critic_rounds != null) badges.push(madeBadge(ic("sp-image", "sm") + (zh ? "评审轮 ×" : "critic ×") + f.critic_rounds, zh ? "评审轮数" : "critic rounds"));
    if (f.svg_rounds != null) badges.push(madeBadge(ic("sp-undo", "sm") + (zh ? "重绘轮 ×" : "redraw ×") + f.svg_rounds, zh ? "SVG 重绘轮数" : "SVG redraw rounds"));
    // item4 — engine/grounding badges carry real, localized tooltip + aria text (not the bare
    // English word "engine"/"grounding").
    if (f.engine) badges.push(madeBadge((zh ? "引擎 " : "engine ") + esc(f.engine), (zh ? "生成引擎:" : "generation engine: ") + f.engine));
    if (f.grounding) badges.push(madeBadge((zh ? "依据 " : "grounding ") + esc(f.grounding), (zh ? "作图依据:" : "figure grounding: ") + f.grounding));
    var badgeRow = '<div class="fm-badges">' + badges.join("") + '</div>';

    var a = f.audit, auditRow = "";
    if (a) {
      var chips = [];
      if (a.cleanliness != null) chips.push('<span class="chip mono" title="' + esc(zh ? "整洁度" : "cleanliness") + '">' + (zh ? "整洁 " : "clean ") + Math.round(a.cleanliness * 100) + '%</span>');
      if (a.min_text_px != null) chips.push('<span class="chip mono" title="' + esc(zh ? "最小文字像素" : "min text px") + '">' + (zh ? "最小字 " : "min-text ") + (Math.round(a.min_text_px * 10) / 10) + 'px</span>');
      if (a.texts != null) chips.push('<span class="chip mono">' + a.texts + (zh ? " 文本" : " texts") + '</span>');
      if (a.shapes != null) chips.push('<span class="chip mono">' + a.shapes + (zh ? " 形状" : " shapes") + '</span>');
      var warns = (a.warnings && a.warnings.length) || 0;
      chips.push(warns
        ? '<span class="chip stale" title="' + esc((a.warnings || []).join(" · ")) + '">' + ic("sp-warn", "sm") + warns + (zh ? " 警告" : (warns === 1 ? " warning" : " warnings")) + '</span>'
        : '<span class="chip ok">' + ic("i-check", "sm") + (zh ? "无警告" : "no warnings") + '</span>');
      auditRow = '<div class="fm-audit">' + chips.join("") + '</div>';
    }

    var promptRow = "";
    if (f.prompt) {
      promptRow = '<div class="fm-prompt-wrap">' +
        '<button class="fm-prompt-toggle" type="button" aria-expanded="false">' + ic("sp-quote", "sm") + (zh ? "生成提示词" : "Generation prompt") + '</button>' +
        '<pre class="fm-prompt" hidden>' + esc(f.prompt) + (f.prompt.length >= 1200 ? " …" : "") + '</pre>' +
      '</div>';
    }

    var versionRow = figVersionsHTML(f);

    return '<div class="fig-made">' +
      '<div class="fm-head"><span class="kick">' + (zh ? "生成过程" : "How it was made") + '</span></div>' +
      badgeRow + auditRow + promptRow + versionRow +
    '</div>';
  }
  function madeBadge(inner, title) {
    // item4 — mirror the tooltip into aria-label so the badge is legible to assistive tech too.
    var attrs = title ? ' title="' + esc(title) + '" aria-label="' + esc(title) + '"' : "";
    return '<span class="fm-badge"' + attrs + '>' + inner + '</span>';
  }
  // The redraw-round carousel: one round_*.svg per slide, stepped by prev/next. A real
  // round carries an svg_url (an /api/file URL) shown as an <img>; the sample carries
  // null URLs and falls back to an on-brand placeholder panel flagged 示例.
  function figVersionsHTML(f) {
    var zh = lang() === "zh";
    var vs = f.versions || []; if (!vs.length) return "";
    var slides = vs.map(function (v, k) {
      var rn = v.round != null ? v.round : (k + 1);
      var inner = v.svg_url
        ? '<img class="fv-img" src="' + esc(v.svg_url) + '" alt="round ' + rn + '" loading="lazy">'
        : '<div class="fv-ph">' + figThumb(f.type) + '<span class="fv-ph-tag">' + (zh ? "示例" : "sample") + '</span></div>';
      return '<div class="fv-slide' + (k === 0 ? " on" : "") + '"' + (v.svg_url ? ' data-svg="' + esc(v.svg_url) + '"' : "") + '><span class="fv-round">' + (zh ? "第 " : "round ") + rn + '</span>' + inner + '</div>';
    }).join("");
    return '<div class="fm-versions" role="group" aria-label="' + esc(zh ? "重绘轮次" : "redraw rounds") + '">' +
      '<div class="fv-bar"><span class="fv-h">' + (zh ? "重绘轮次" : "Redraw rounds") + '</span>' +
        '<div class="fv-nav"><button class="fv-prev" type="button" aria-label="' + esc(zh ? "上一轮" : "previous round") + '">‹</button>' +
        '<span class="fv-count mono"></span>' +
        '<button class="fv-next" type="button" aria-label="' + esc(zh ? "下一轮" : "next round") + '">›</button></div></div>' +
      '<div class="fv-stage">' + slides + '</div></div>';
  }
  // Distinct, on-brand schematic per figure type (self-contained; no external assets).
  function figThumb(type) {
    var A = 'var(--accent)', I = 'var(--paper-ink)';
    var box = function (x, y, w, h, fill) { return '<rect x="' + x + '" y="' + y + '" width="' + w + '" height="' + h + '" rx="4" fill="' + (fill || "none") + '" stroke="currentColor" stroke-width="1.6"/>'; };
    var ln = function (x1, y1, x2, y2, a) { return '<path d="M' + x1 + ' ' + y1 + 'L' + x2 + ' ' + y2 + '" stroke="' + (a ? A : "currentColor") + '" stroke-width="1.6" fill="none"/>'; };
    var g;
    if (type === "architecture") g = box(10, 14, 200, 92, "none") + box(24, 30, 78, 26) + box(24, 66, 78, 26) + box(130, 46, 66, 34, "color-mix(in oklab,var(--accent) 16%,transparent)") + ln(102, 43, 130, 58, 1) + ln(102, 79, 130, 68, 1);
    else if (type === "flow") g = box(16, 44, 46, 30) + '<path d="M96 59l22-18 22 18-22 18z" fill="none" stroke="currentColor" stroke-width="1.6"/>' + box(168, 22, 46, 26, "color-mix(in oklab,var(--accent) 16%,transparent)") + box(168, 70, 46, 26) + ln(62, 59, 96, 59) + ln(140, 59, 168, 35, 1) + ln(140, 59, 168, 83, 1);
    else if (type === "pipeline") g = [0, 1, 2, 3].map(function (k) { var x = 16 + k * 50; return '<path d="M' + x + ' 44h34l10 15-10 15h-34l10-15z" fill="' + (k === 3 ? "color-mix(in oklab,var(--accent) 16%,transparent)" : "none") + '" stroke="currentColor" stroke-width="1.5"/>'; }).join("") + ln(60, 59, 66, 59, 1) + ln(110, 59, 116, 59, 1) + ln(160, 59, 166, 59, 1);
    else if (type === "diagram") g = box(90, 12, 44, 24) + '<path d="M112 44l18 16-18 16-18-16z" fill="none" stroke="var(--accent)" stroke-width="1.6"/>' + box(20, 84, 56, 22) + box(148, 84, 56, 22, "color-mix(in oklab,var(--accent) 16%,transparent)") + ln(112, 36, 112, 44) + ln(96, 66, 48, 84, 1) + ln(128, 66, 176, 84, 1);
    else if (type === "concept") g = [0, 1, 2, 3].map(function (k) { var y = 24 + k * 20; return '<rect x="34" y="' + y + '" width="152" height="14" rx="3" fill="' + (k === 0 ? "color-mix(in oklab,var(--accent) 18%,transparent)" : "none") + '" stroke="currentColor" stroke-width="1.4"/>'; }).join("") + ln(110, 20, 110, 106);
    else if (type === "qualitative") g = box(14, 20, 88, 80) + box(118, 20, 88, 80, "color-mix(in oklab,var(--accent) 12%,transparent)") + '<path d="M110 16v88" stroke="currentColor" stroke-width="1.2" stroke-dasharray="3 3"/>' + '<circle cx="58" cy="60" r="16" fill="none" stroke="currentColor" stroke-width="1.5"/>' + '<circle cx="162" cy="60" r="16" fill="none" stroke="var(--accent)" stroke-width="1.8"/>';
    else g = box(30, 24, 160, 72);
    return '<svg class="fig-svg" viewBox="0 0 220 120" preserveAspectRatio="xMidYMid meet" aria-hidden="true">' + g + '</svg>';
  }
  function openLightbox(f, opts) {
    $$(".fig-lightbox,.fig-scrim").forEach(function (n) { n.remove(); });
    var vector = f.formats.indexOf("svg") >= 0;
    var opener = document.activeElement;   // item9 — restore focus to the opener on close
    var scrim = el("div", "fig-scrim"); document.body.appendChild(scrim);
    var lb = el("div", "fig-lightbox");
    // item16 — a caller can pass a specific image (a redraw round) to zoom instead of the hero.
    var src = (opts && opts.imgSrc) || figImgSrc(f);
    var title = (f.number != null ? ("Fig " + f.number + " · " + f.label) : f.label) + (opts && opts.titleSuffix ? " · " + opts.titleSuffix : "");
    // Honest metadata only — there is NO per-figure SSIM, so no SSIM row is shown.
    var rows = [
      ["label", f.label], ["type", figTypeLabel(f.type)], ["engine", f.engine || "—"], ["grounding", f.grounding || "—"],
      ["ref", f.ref || "—"], ["critic_rounds", String(f.critic_rounds)],
      ["svg_rounds", f.svg_rounds == null ? "—" : String(f.svg_rounds)],
      ["formats", (f.formats.length ? f.formats.map(function (x) { return x.toUpperCase(); }).join(" · ") : "—") + (vector ? " — vector" : " — PNG only")],
      // item12 — 3-state audit row (null → n/a, false → failed, true → ok)
      ["audit", f.audit_ok === true ? "✓ ok" : f.audit_ok === false ? "failed" : "n/a"]
    ];
    if (f.audit) {
      if (f.audit.cleanliness != null) rows.push(["cleanliness", Math.round(f.audit.cleanliness * 100) + "%"]);
      if (f.audit.min_text_px != null) rows.push(["min_text_px", (Math.round(f.audit.min_text_px * 10) / 10) + "px"]);
      if (f.audit.texts != null) rows.push(["texts / shapes", f.audit.texts + " / " + (f.audit.shapes != null ? f.audit.shapes : "—")]);
    }
    if (f.caption) rows.push(["caption", f.caption]);
    // open-in-tab links for whichever real files exist (none for the sample)
    var links = ["png", "svg", "pdf"].filter(function (x) { return f.files && f.files[x]; })
      .map(function (x) { return '<a class="lb-file" href="' + esc(f.files[x]) + '" target="_blank" rel="noopener">' + x.toUpperCase() + '</a>'; }).join("");
    // item9 — the lightbox is a real modal dialog: role/aria-modal/labelledby, a Tab focus
    // trap, focus moved to the close button on open, and focus restored to the opener on close.
    lb.setAttribute("role", "dialog");
    lb.setAttribute("aria-modal", "true");
    lb.setAttribute("aria-labelledby", "sp-lb-h");
    lb.innerHTML =
      '<div class="lb-head"><h3 id="sp-lb-h">' + esc(title) + '</h3>' +
        '<button class="iconbtn" data-close aria-label="' + esc(lang() === "zh" ? "关闭" : "close") + '">' + ic("i-close") + '</button></div>' +
      '<div class="lb-stage">' + (src ? '<img class="fig-img" src="' + esc(src) + '" alt="' + esc(f.caption || f.label) + '">' : figThumb(f.type)) + '</div>' +
      (links ? '<div class="lb-files">' + links + '</div>' : "") +
      '<table class="lb-table">' + rows.map(function (r) {
        return '<tr><td class="lk">' + esc(r[0]) + '</td><td class="lv">' + esc(r[1]) + '</td></tr>';
      }).join("") + '</table>';
    document.body.appendChild(lb);
    function close() {
      lb.remove(); scrim.remove(); document.removeEventListener("keydown", onKey, true);
      try { opener && opener.focus && opener.focus(); } catch (e) {}
    }
    function onKey(e) {
      if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); close(); }
      else if (e.key === "Tab") {
        var fs = $$("button,[href],[tabindex]:not([tabindex='-1'])", lb).filter(function (n) { return !n.disabled; });
        if (!fs.length) return;
        var first = fs[0], last = fs[fs.length - 1];
        if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
        else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
        else if (!lb.contains(document.activeElement)) { e.preventDefault(); first.focus(); }
      }
    }
    scrim.onclick = close; $("[data-close]", lb).onclick = close; document.addEventListener("keydown", onKey, true);
    var cb = $("[data-close]", lb); if (cb) { try { cb.focus(); } catch (e) {} }
  }

  /* =========================================================================
     SUB-VIEW 4 — GOVERNANCE (unique-Spark telemetry as native cards)
     ========================================================================= */
  function renderGovernance(main) {
    var tk = newView();
    Promise.all([
      SB.data.getOr("spark", "governance", null),
      SB.data.getOr("spark", "facts", null),
      SB.data.getOr("spark", "report", null)
    ]).then(function (r) {
      if (tk !== VIEW_TOKEN) return;
      resetLive();
      HYD.gov = hydrateGovernance(r[0]);
      // FLAT contract: a real, readable linear run (no .research/) returns a DISTINCT
      // {found:false, not_applicable:true, variant:"flat"} — different from couldNotRead.
      // Guarded: absent flags → GOV_FLAT stays false → today's sample/amber behavior.
      GOV_FLAT = !!(r[0] && (r[0].not_applicable === true || r[0].variant === "flat"));
      HYD.facts = hydrateFacts(r[1]);
      HYD.gates = hydrateGates(r[2]);
      paintGovernance(main, HYD.gov);
    });
  }
  function paintGovernance(main, real) {
    var pane = el("div", "pane");
    var w = el("div", "pane-wide reveal");

    // FLAT spark: a real, readable linear run that simply never had a research engine.
    // Render ONE honest line where the sample budget/GPU/seals/decisions dashboard would go —
    // do NOT fabricate a governance dashboard. The tab stays present. This is distinct from
    // couldNotRead (an unreadable dir), which still gets the amber "showing sample" banner below.
    if (GOV_FLAT) {
      var zhf = lang() === "zh";
      // dir WAS read (not_applicable, not couldNotRead) → honest "reading <dir>", never "Sample".
      w.innerHTML = '<div class="gov-stathead">' + srcHint(dirOpen()) + '</div>' +
        '<p class="honest-note" role="status">' + ic("sp-warn", "sm") +
        (zhf ? "本次运行没有治理数据"
             : "No governance data for this run") + '</p>';
      pane.appendChild(w); main.appendChild(pane);
      return;
    }

    var bud = LEDGER.budget || {};
    var bestTier = (GOV_TIER && GOV_TIER.best_tier) ? GOV_TIER.best_tier : "FULL_PAPER";
    function slash(a, b) { return (a != null ? a : "—") + " / " + (b != null ? b : "—"); }

    // R1 — a real dir open but no governance ledger → the ledger cards below are sample.
    // Replace the tiny corner pill with a full-width amber banner; the two cards that DID
    // hydrate from this run (facts / gates) keep their own green "this run" chip.
    var amber = (dirOpen() && !real) ? sampleBannerHTML("治理", "governance") : "";
    var head = amber || ('<div class="gov-stathead">' + provChip(real) + '</div>');

    // R16 — the decision hero: alert-red and click-to-scroll when this run really has
    // open decisions (never red for sample counts under the amber banner).
    var decN = DQ.open.length, decAlert = HYD.gov && decN > 0;
    var decCard = '<div class="card stat-card click' + (decAlert ? " alert" : "") + '" id="gov-decstat" role="button" tabindex="0" title="' +
      esc(lang() === "zh" ? "滚动到决策队列" : "Scroll to the decision queue") + '">' +
      '<div class="stat"><span class="v">' + esc(decN) + '</span><span class="k">' + esc(T("open decisions")) + '</span></div>' +
      '<span class="sc-chip chip ' + (decAlert ? "bad" : "wait") + '"></span></div>';

    var stats =
      head +
      // R28a — a count class + pinned columns so the KPI tiles lay out as one clean row
      // (or 2×2 / 1-col on narrower widths) instead of auto-fill leaving an orphan.
      '<div class="grid grid-auto gov-stats gov-stats-4">' +
        decCard +
        // R18 — the tier is a categorical enum, not a numeral: localize it (raw enum → title=)
        // and render it as a categorical pill (see .accent-v in spark.css), not a serif number.
        statCard(tierLabel(bestTier), T("best tier"), "accent", bestTier) +
        statCard(slash(bud.gpu_hours_spent, bud.gpu_hours_cap), T("GPU-hours"), "") +
        // item18 — the OUTER ROUNDS stat now carries a hover gloss (matched in the term strip below).
        statCard(slash(bud.outer_round, bud.outer_rounds_cap), T("outer rounds"), "",
          lang() === "zh" ? "外层轮次 —— 一次完整的自动跑(起草→评审→修订);上限约束这次运行能跑几轮"
                          : "outer round — one full autopilot pass (draft→review→revise); the cap bounds how many the run may spend") +
      '</div>';

    var body =
      stats +
      govGlossHTML() +   // R9 — a one-line newcomer glossary for the densest insider vocab
      '<div class="gov-grid">' +
        // R16 — the decision queue leads, full width, above the seal timeline
        card("Decision queue", T("Answer me"), dqHTML(), "gov-wide", "", "gov-dq") +
        // stage seals (full width)
        card("Stage seals", T("Run timeline"), sealsHTML(), "gov-wide") +
        // tier ladder + budget
        card("Tier ladder", T("Shippable tier"), tierHTML(), "") +
        // negative results
        card("Negative results", T("Dead-ends & lessons"), deadEndHTML(), "") +
        // claim ledger (full width)
        card("Claim ledger", T("Evidence × status"), claimHTML(), "gov-wide") +
        // facts panel — real when the facts family hydrated
        card("Results / facts", T("The verified numbers"), factsHTML(), "gov-wide", cardRealChip(HYD.facts)) +
        // gates / latex — often real even when the ledger is not
        card("Gates & LaTeX QA", T("Build integrity"), gatesHTML(), "", cardRealChip(HYD.gates)) +
        // E14 trends (full width)
        card("E14 cross-run trends", T("Is the pipeline behaving?"), e14HTML(), "gov-wide") +
      '</div>';

    w.innerHTML = body;
    pane.appendChild(w); main.appendChild(pane);

    wireSampleBanner(w);
    wireGloss(w);   // item21 — '知道了 / Got it' dismiss on the governance gloss strip
    // R16 — the hero decision tile scrolls to the queue (click + keyboard).
    var ds = $("#gov-decstat", w);
    if (ds) { var goDq = function () { scrollToCard("gov-dq"); };
      ds.onclick = goDq; ds.onkeydown = function (e) { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); goDq(); } }; }
    // wire expandable seal roll-calls + decision buttons
    $$(".seal-node", w).forEach(function (n) {
      n.onclick = function () { n.classList.toggle("open"); };
    });
    $$("[data-dq-act]", w).forEach(function (b) {
      // R14 — a decision command is now actionable: copy it to the clipboard to run in a terminal
      b.onclick = function (e) { e.stopPropagation(); copyCmd(b.dataset.dqAct); };
    });
  }

  // R9 — governance carries the most un-glossed insider vocabulary; a compact strip names
  // the four terms a newcomer stumbles on. Kept to one line, calm, and theme-token styled.
  function govGlossHTML() {
    if (glossDismissed("gov")) return "";                   // item21 — remembered dismissal
    var zh = lang() === "zh";
    var items = zh ? [
      ["档位", "论文成熟度四级阶梯,最高一级为 FULL_PAPER"],
      ["封章", "阶段通过点名后的不可逆印记"],
      ["处置", "对一项待决策的了结(继续 / 撤销)"],
      ["撤销率", "自动判断被人工翻案的比例"],
      // item18 — the OUTER ROUNDS budget stat had no gloss anywhere; name it here too.
      ["外层轮次", "一次完整的自动跑(起草→评审→修订);上限约束能跑几轮"]
    ] : [
      ["tier", "4-rung maturity ladder, tops out at FULL_PAPER"],
      ["seal", "irreversible stamp a passed stage earns"],
      ["disposition", "a pending decision resolved (resume / reverse)"],
      ["reversal rate", "how often an auto-call was overturned by a human"],
      ["outer round", "one full autopilot pass (draft→review→revise); the cap bounds how many the run may spend"]
    ];
    return '<div class="gov-gloss" role="note"><span class="gg-h">' + (zh ? "术语速览" : "New here?") + '</span>' +
      items.map(function (it) {
        return '<span class="gg-item"><b>' + esc(it[0]) + '</b>' + esc(it[1]) + '</span>';
      }).join("") + glossDismissBtn("gov") + '</div>';
  }

  function sealsHTML() {
    return '<div class="seals">' + SEALS.map(function (s) {
      var cls = s.state === "sealed" ? "ok" : s.state === "halt" ? "warn" : "";
      var badge = s.state === "sealed" ? '<span class="chip ok">' + ic("sp-seal", "sm") + T("sealed") + '</span>'
        : s.state === "halt" ? '<span class="chip stale">' + ic("sp-warn", "sm") + T("halt") + '</span>'
          : '<span class="chip">' + T("unsealed") + '</span>';
      var rc = s.rollcall.length
        ? '<div class="rollcall">' + s.rollcall.map(function (r) {
          var m = r.status === "present" ? "ok" : r.status === "waived" ? "waived" : "missing";
          var glyph = r.status === "present" ? ic("i-check", "sm") : r.status === "waived" ? "⊘" : "✕";
          return '<div class="rc-row ' + m + '"><span class="rc-g">' + glyph + '</span>' +
            '<span class="rc-id">' + esc(r.id) + '</span>' +
            '<span class="rc-cls">' + esc(r.cls) + '</span>' +
            '<span class="rc-art">' + esc(r.artifact) + '</span></div>';
        }).join("") + '</div>'
        : '<div class="rollcall"><div class="rc-empty">' + T("no roll-call yet — stage not run") + '</div></div>';
      return '<div class="seal-node ' + cls + '">' +
        '<div class="seal-head"><span class="seal-nn badge">' + s.nn + '</span>' +
          '<span class="seal-stage">' + esc(s.stage) + '</span>' + badge +
          '<span class="seal-ts"' + (s.ts ? ' title="' + esc(s.ts) + '"' : "") + '>' + (s.ts ? esc(fmtStamp(s.ts)) : "—") + '</span>' +
          '<span class="seal-chev">' + ic("i-chev", "sm") + '</span></div>' +
        rc + '</div>';
    }).join("") + '</div>';
  }

  function dqHTML() {
    var rows = DQ.open.map(function (d) {
      var cost = d.reversal_cost === "cheap" ? "ok" : "stale";
      return '<div class="dq-row">' +
        '<div class="dq-top"><span class="badge">' + esc(d.id) + '</span>' +
          '<span class="chip" title="' + esc(d.type) + '">' + esc(glossEnum(d.type)) + '</span>' +
          // R22a — the reversal-cost enum was raw; localize it, keep the token in title=.
          '<span class="chip ' + cost + '" title="' + esc(d.reversal_cost) + '">' + esc(costLabel(d.reversal_cost)) + '</span></div>' +
        '<p class="dq-find">' + esc(d.finding) + '</p>' +
        '<div class="dq-ptr">' + ic("sp-quote", "sm") + '<code>' + esc(d.pointer) + '</code></div>' +
        // R14 — these buttons only COPY a CLI command to run in a terminal — they are not
        // in-app actions. Say so (copy glyph + "Copy resume/reverse cmd") and print the exact
        // /ts-run string as muted <code> below, so it is readable without clicking.
        '<div class="dq-acts">' +
          '<button class="btn sm primary" data-dq-act="' + esc(d.resume) + '">' + ic("sp-copy", "sm") + T("Copy resume cmd") + '</button>' +
          '<button class="btn sm ghost" data-dq-act="' + esc(d.reverse) + '">' + ic("sp-copy", "sm") + T("Copy reverse cmd") + '</button>' +
        '</div>' +
        '<div class="dq-cmds">' +
          (d.resume ? '<code>' + esc(d.resume) + '</code>' : "") +
          (d.reverse ? '<code>' + esc(d.reverse) + '</code>' : "") +
        '</div></div>';
    }).join("");
    var pct = Math.round(DQ.dispositioned / DQ.total * 100);
    var gauge =
      '<div class="dq-gauge"><div class="meter"><i style="width:' + pct + '%"></i></div>' +
        '<div class="dq-gauge-tx"><code title="' + esc(DQ.state) + '">' + esc(dqStateLabel(DQ.state)) + '</code> → ' +
        esc(dqStateLabel("SUBMITTABLE")) + ' · ' +
        DQ.dispositioned + '/' + DQ.total + ' ' + T("dispositioned") + '</div></div>';
    return '<div class="dq">' + rows + gauge + '</div>';
  }

  function tierHTML() {
    var rungs = ["NEGATIVE_RESULT", "TECHNICAL_REPORT", "PRELIMINARY_STUDY", "FULL_PAPER"];
    var bt = (GOV_TIER && GOV_TIER.best_tier) ? GOV_TIER.best_tier : "FULL_PAPER";
    var best = rungs.indexOf(bt);
    var offLead = best < 0 ? '<div class="tier-off-lead"><span class="chip accent">' + esc(bt) + '</span>' +
      '<span class="tol-t">' + (lang() === "zh" ? "当前档位(不在四级阶梯上)" : "current tier (off the 4-rung ladder)") + '</span></div>' : "";
    var ladder = '<div class="tier-ladder">' + rungs.map(function (r, i) {
      var st = best < 0 ? "todo" : i < best ? "passed" : i === best ? "current" : "todo";
      return '<div class="tier-rung ' + st + '"><span class="tr-dot"></span><span class="tr-name" title="' + esc(r) + '">' + esc(tierLabel(r)) + '</span>' +
        (i === best ? '<span class="chip accent">' + T("current") + '</span>' : "") + '</div>';
    }).join("") + '</div>';
    var floors = GOV_TIER
      ? '<div class="tier-floors"><div class="tf-h">' + (lang() === "zh" ? "阻断门槛" : "blocking floors") + '</div>' +
          '<div class="tf-note">' + (lang() === "zh" ? "每级阻断门槛需 sr5_render 计算,未在此处展示。" : "per-tier blocking floors require sr5_render — not surfaced here.") + '</div></div>'
      : '<div class="tier-floors"><div class="tf-h">' + T("FULL_PAPER floors") + ' · ' + T("all green") + '</div>' +
          ['menu ≥ 5/7', 'terminal council', 'direction terminal', 'gates green', 'export-receipt'].map(function (x) {
            return '<span class="chip ok">' + ic("i-check", "sm") + esc(x) + '</span>';
          }).join("") + '</div>';
    var bud = LEDGER.budget || {};
    function pct(a, b) { return (a != null && b) ? Math.max(0, Math.min(100, a / b * 100)) : 0; }
    var meter =
      '<div class="tier-budget"><div class="tb-row"><span>' + T("GPU-h") + '</span><span class="mono">' + (bud.gpu_hours_spent != null ? bud.gpu_hours_spent : "—") + ' / ' + (bud.gpu_hours_cap != null ? bud.gpu_hours_cap : "—") + '</span></div>' +
        '<div class="meter"><i style="width:' + pct(bud.gpu_hours_spent, bud.gpu_hours_cap) + '%"></i></div>' +
        '<div class="tb-row" style="margin-top:8px"><span>' + T("rounds") + '</span><span class="mono">' + (bud.outer_round != null ? bud.outer_round : "—") + ' / ' + (bud.outer_rounds_cap != null ? bud.outer_rounds_cap : "—") + '</span></div>' +
        '<div class="meter"><i style="width:' + pct(bud.outer_round, bud.outer_rounds_cap) + '%"></i></div></div>';
    var off = '<div class="tier-off">' + T("off-ladder") + ': <span class="chip">NEGATIVE_RESULT_PAPER</span><span class="chip">PROVISIONAL_DRAFT</span></div>';
    return offLead + ladder + floors + meter + off;
  }

  function claimHTML() {
    var counts = { supported: 0, refuted: 0, inconclusive: 0 };
    CLAIMS.forEach(function (c) { if (counts[c.status] != null) counts[c.status]++; });
    var head =
      '<div class="claim-counts">' +
        '<span class="chip ok">' + counts.supported + ' ' + T("supported") + '</span>' +
        '<span class="chip bad">' + counts.refuted + ' ' + T("refuted") + '</span>' +
        '<span class="chip stale">' + counts.inconclusive + ' ' + T("inconclusive") + '</span></div>';
    var rows = CLAIMS.map(function (c) {
      var sc = c.status === "supported" ? "ok" : c.status === "refuted" ? "bad" : "stale";
      return '<tr>' +
        '<td class="cl-id"><span class="badge">' + esc(c.id) + '</span></td>' +
        '<td><span class="chip ' + sc + '">' + esc(T(c.status)) + '</span></td>' +
        '<td class="cl-note">' + esc(c.note) + '</td>' +
        '<td class="cl-margin mono">' + esc(c.margin) + '</td>' +
        '<td class="cl-prov"><code>' + esc(c.provenance) + '</code></td>' +
        '</tr>';
    }).join("");
    return head + '<div class="tbl-scroll"><table class="claim-table">' +
      '<thead><tr><th>C-id</th><th>' + T("status") + '</th><th>' + T("belief") + '</th><th>' + T("margin") + '</th><th>' + T("provenance") + '</th></tr></thead>' +
      '<tbody>' + rows + '</tbody></table></div>';
  }

  function factsHTML() {
    // Proposal-mode run with no measured results yet → label the card honestly instead of
    // showing SAMPLE RQ numbers. data_aware runs with a real facts.json still show real numbers;
    // a genuine couldNotRead dir still falls through to the sample below under its amber banner.
    if (FACTS_PROPOSAL) {
      var zhp = lang() === "zh";
      return '<p class="honest-note" role="status">' + ic("sp-warn", "sm") +
        (zhp ? "提案模式 · 暂无实测结果" : "Proposal mode — no measured results yet") + '</p>';
    }
    var s = FACTS.rq1_figure_engine_ssim, g = FACTS.rq2_integrity_gates, e = FACTS.rq3_end_to_end;
    function grp(title, ptr, inner) { return '<div class="facts-grp"><div class="fg-h"><span class="kick">' + esc(title) + '</span><code>' + esc(ptr) + '</code></div>' + inner + '</div>'; }
    function stat(v, k, tone) { return '<div class="fnum' + (tone ? " " + tone : "") + '"><span class="fv">' + esc(v) + '</span><span class="fk">' + esc(k) + '</span></div>'; }
    var rq1 = grp("RQ1 · figure engine", "rq1_figure_engine_ssim",
      '<div class="facts-row">' + stat(s.mean.toFixed(3), "SSIM mean") + stat(s.min + "–" + s.max, "SSIM range") +
        stat(FACTS.rq1_editable_text_boxes.mean, "text boxes (mean)") + stat(FACTS.rq1_runtime_seconds.mean + "s", "runtime (mean)") + '</div>');
    var rq2 = grp("RQ2 · integrity gates", "rq2_integrity_gates",
      '<div class="facts-row">' +
        stat(g.fabricated_numbers_caught_full_stack + "/" + g.fabricated_numbers_injected, "fabrications caught", "ok") +
        stat(g.fabricated_numbers_caught_without_audit + "/" + g.fabricated_numbers_injected, "without audit", "bad") +
        stat(g.citation_probes_caught_full_stack + "/" + g.citation_probes_injected, "cite probes caught", "ok") +
        stat(g.false_alarms_on_clean_manuscript, "false alarms", "ok") + '</div>');
    var rq3 = grp("RQ3 · end-to-end", "rq3_end_to_end",
      '<div class="facts-row">' +
        stat(e.pages, "pages") + stat(e.references_resolved + "/" + e.references, "refs resolved", "ok") +
        stat(e.editable_vector_figures + "/" + e.figures, "vector figs") + stat(e.latex_error_count, "LaTeX errors", "ok") +
        stat(e.gates_green ? "✓" : "✗", "gates green", e.gates_green ? "ok" : "bad") + '</div>');
    var note = '<p class="facts-note">' + ic("sp-warn", "sm") + esc(FACTS.notes) + '</p>';
    return rq1 + rq2 + rq3 + note;
  }

  function deadEndHTML() {
    return '<div class="deadends">' + DEADENDS.map(function (d) {
      return '<div class="de-row">' +
        '<div class="de-top"><span class="badge">' + esc(d.id) + '</span>' +
          '<span class="chip">' + esc(d.dir) + '</span><span class="chip">' + esc(d.run) + '</span>' +
          '<span class="chip ' + (d.support === "explicit" ? "bad" : "stale") + '">' + esc(d.support) + '</span></div>' +
        '<div class="de-line"><span class="de-lbl">' + T("hypothesis") + '</span>' + esc(d.hypothesis) + '</div>' +
        '<div class="de-line"><span class="de-lbl">' + T("failure mode") + '</span>' + esc(d.failure_mode) + '</div>' +
        '<div class="de-line de-lesson"><span class="de-lbl">' + T("lesson") + '</span>' + esc(d.lesson) + '</div>' +
        '</div>';
    }).join("") + '</div>';
  }

  function gatesHTML() {
    var g = GATES;
    var checks = '<div class="gate-list">' + g.checks.map(function (c) {
      return '<div class="gate-row"><span class="chip ' + (c.status === "ok" ? "ok" : "bad") + '">' + ic("i-check", "sm") + '</span>' +
        '<span class="gate-name">' + esc(c.check) + '</span><span class="gate-cls">' + esc(c.cls) + '</span></div>';
    }).join("") + '</div>';
    var lx = g.latex;
    var latex =
      '<div class="latex-build"><div class="lx-verdict"><span class="chip ' + (lx.verdict === "ok" ? "ok" : "bad") + '">' + esc(lx.verdict) + '</span>' +
        '<span class="lx-sum mono">' + lx.pages + ' pp · ' + lx.errors + ' err · ' + lx.undefined + ' undef · ' + lx.overfull + ' overfull · ' + lx.bib_entries + ' bib</span></div>' +
        '<div class="lx-lints"><span class="chip">draft_lint ' + (g.draft_lint.ok ? "ok" : "fail") + ' · ' + g.draft_lint.n_warnings + 'w</span>' +
        '<span class="chip">citations_lint ' + g.citations_lint.n_cited + ' cited · ' + g.citations_lint.n_issues + ' issues</span></div></div>';
    return checks + latex;
  }

  function e14HTML() {
    // reversal-rate-by-class bars + integrity/ceremony sparklines + tier history
    var bars = '<div class="e14-block"><div class="e14-h">' + T("reversal rate by class") + '<span class="e14-sub">' + T("did the agent freelance?") + '</span></div>' +
      E14.reversal_rate_by_class.map(function (r) {
        return '<div class="rev-row"><span class="rev-cls">' + esc(r.cls) + '</span>' +
          '<div class="meter ' + (r.rate === 0 ? "ok" : "") + '"><i style="width:' + Math.max(3, r.rate * 100 * 6) + '%"></i></div>' +
          '<span class="rev-v mono">' + (r.rate * 100).toFixed(0) + '% · ' + r.reversals + '/' + r.delegated + '</span></div>';
      }).join("") + '</div>';
    var spark = '<div class="e14-block"><div class="e14-h">' + T("postproc trend") + '<span class="e14-sub">integrity · ceremony</span></div>' +
      '<div class="spark-row"><span class="sp-lbl">integrity</span>' + sparkline(E14.postproc_trend.integrity, "var(--ok)") + '<span class="mono sp-last">' + last(E14.postproc_trend.integrity) + '</span></div>' +
      '<div class="spark-row"><span class="sp-lbl">ceremony</span>' + sparkline(E14.postproc_trend.ceremony, "var(--accent)") + '<span class="mono sp-last">' + last(E14.postproc_trend.ceremony) + '</span></div></div>';
    var hist = '<div class="e14-block"><div class="e14-h">' + T("run history") + '<span class="e14-sub">ended_by · best_tier</span></div>' +
      '<div class="e14-hist">' + E14.runs.map(function (r) {
        var tone = r.best_tier === "FULL_PAPER" ? "ok" : r.best_tier === "TECHNICAL_REPORT" ? "stale" : "";
        return '<div class="eh-row"><span class="mono eh-id">' + esc(r.run_id) + '</span>' +
          '<span class="chip" title="' + esc(r.ended_by) + '">' + esc(glossEnum(r.ended_by)) + '</span>' +
          '<span class="chip ' + tone + '" title="' + esc(r.best_tier) + '">' + esc(tierLabel(r.best_tier)) + '</span></div>';
      }).join("") + '</div></div>';
    return '<div class="e14-grid">' + bars + spark + hist + '</div>';
  }
  function sparkline(arr, color) {
    var w = 120, h = 26, max = Math.max.apply(null, arr), min = Math.min.apply(null, arr);
    var rng = max - min || 1;
    var pts = arr.map(function (v, i) { return [i / (arr.length - 1) * w, h - 3 - (v - min) / rng * (h - 6)]; });
    var d = pts.map(function (p, i) { return (i ? "L" : "M") + p[0].toFixed(1) + " " + p[1].toFixed(1); }).join("");
    var dots = pts.map(function (p, i) { return '<circle cx="' + p[0].toFixed(1) + '" cy="' + p[1].toFixed(1) + '" r="' + (i === pts.length - 1 ? 2.4 : 1.4) + '" fill="' + color + '"/>'; }).join("");
    return '<svg class="spark-svg" viewBox="0 0 ' + w + ' ' + h + '" preserveAspectRatio="none"><path d="' + d + '" fill="none" stroke="' + color + '" stroke-width="1.6"/>' + dots + '</svg>';
  }

  /* ---- small shared builders --------------------------------------------- */
  function card(kick, h3, inner, extra, prov, id) {
    // R5 — the card eyebrow localizes too (was raw English, leaking into zh); T() is a no-op in en
    // prov (optional) = a per-card provenance chip; id (optional) = a scroll anchor (R16).
    return '<div class="card ' + (extra || "") + '"' + (id ? ' id="' + esc(id) + '"' : "") + '>' +
      '<div class="card-h"><span class="kick">' + esc(T(kick)) + '</span><h3>' + esc(h3) + '</h3>' + (prov || "") + '</div>' + inner + '</div>';
  }
  function statCard(v, k, tone, title) {
    return '<div class="card stat-card"' + (title ? ' title="' + esc(title) + '"' : "") + '><div class="stat"><span class="v' + (tone === "accent" ? " accent-v" : "") + '">' + esc(v) + '</span><span class="k">' + esc(k) + '</span></div>' +
      (tone && tone !== "accent" ? '<span class="sc-chip chip ' + tone + '"></span>' : "") + '</div>';
  }
  function sec(title, rowEls) {
    // rowEls is an array of side-row ELEMENTS (with their click handlers attached)
    var d = el("div", "side-sec");
    d.appendChild(el("div", "side-h", esc(title)));
    rowEls.forEach(function (r) { d.appendChild(r); });
    return d;
  }
  function sideRow(ico, label, cnt, sel, onClick, title) {
    // return a real element so click handlers survive (sec() appends nodes, not strings)
    var r = el("div", "side-row" + (sel ? " sel" : ""));
    if (title) r.setAttribute("title", title);
    r.innerHTML = '<svg class="i ico"><use href="#' + ico + '"/></svg><span class="lbl">' + esc(label) + '</span>' + (cnt ? '<span class="cnt">' + cnt + '</span>' : "");
    if (onClick) { r.onclick = onClick; r.setAttribute("role", "button"); r.setAttribute("tabindex", "0"); r.onkeydown = function (e) { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onClick(); } }; }
    return r;
  }
  function entryHTML(r) {
    // item11 — append the shell's relative-time ('· N 天前' / '· Nd ago') when SB.relTime is exposed.
    var rel = ""; try { if (SB.relTime && r.date) { var rr = SB.relTime(r.date); if (rr) rel = rr; } } catch (e) {}
    return '<div class="entry' + (r.sel ? " sel" : (r.unread ? "" : " read")) + '" role="option" aria-selected="' + (r.sel ? "true" : "false") + '" tabindex="-1"><span class="dot"></span><div class="body">' +
      '<div class="etitle">' + esc(r.title) + '</div><div class="eprev">' + esc(r.prev) + '</div>' +
      '<div class="efoot"><span class="src">' + esc(r.src) + '</span>' +
      (r.star ? '<svg class="i star" style="width:12px;height:12px"><use href="#i-spark"/></svg>' : "") +
      '<span class="date">' + esc(r.date) + (rel ? ' · ' + esc(rel) : "") + '</span></div></div></div>';
  }
  function b(x) { return '<strong>' + esc(x) + '</strong>'; }
  function pad2(n) { return n < 10 ? "0" + n : String(n); }
  function last(a) { return a[a.length - 1]; }
  // pull the "forbidden:" clauses out of a gap_pattern string → a compact summary
  function shortGap(g) {
    var fs = g.split("·").map(function (p) { var m = p.match(/forbidden:\s*([^|]+)/); return m ? m[1].trim() : null; }).filter(Boolean);
    return fs.length ? fs.join("; ") : g.split("|")[0].replace(/^forbidden:\s*/, "").trim();
  }
  function scrollToCard(id) { var n = document.getElementById(id); if (n) n.scrollIntoView({ behavior: "smooth", block: "start" }); }
  function lang() { return SB.state && SB.state.lang === "en" ? "en" : "zh"; }

  // R4 — route content-swaps through the shell's aria-live region so screen-reader users
  // hear the swap instead of silence. Prefer a shell hook (SB.announce) if reader.js grows
  // one; otherwise write the #sb-live span reader.js already renders.
  function announce(msg) {
    if (!msg) return;
    try { if (typeof SB.announce === "function") { SB.announce(msg); return; } } catch (e) {}
    var lv = document.getElementById("sb-live"); if (lv) lv.textContent = msg;
  }

  // R5 — localize the shippable-tier token for the reading eyebrow ONLY. The governance
  // ladder keeps raw enum tokens as identity; venue/format terms-of-art stay English.
  function tierLabel(t) {
    if (lang() !== "zh") return t;
    var m = { FULL_PAPER: "完整论文", PRELIMINARY_STUDY: "初步研究", TECHNICAL_REPORT: "技术报告",
      NEGATIVE_RESULT: "负面结果", NEGATIVE_RESULT_PAPER: "负面结果论文", PROVISIONAL_DRAFT: "临时草稿" };
    return m[t] || t;
  }

  // R5(round5) item12 — the run stage rail + hero title are the two loudest "where am I"
  // elements; localize each node so a zh user never reads an English stepper. Values verbatim
  // from the backlog. Off-list / server-custom stage names pass through unchanged.
  function stageLabel(n) {
    if (lang() !== "zh") return n;
    var m = { Route: "路由", Plan: "规划", Cite: "引用", Write: "写作", Refine: "精修",
      Review: "评审", Figures: "配图", LaTeX: "LaTeX", Experiment: "实验" };
    return m[n] || n;
  }
  // R29e — the figure-type kicker was raw English in zh; localize the categorical kind.
  function figTypeLabel(t) {
    if (lang() !== "zh") return t;
    var m = { concept: "概念图", architecture: "架构图", schematic: "示意图",
      diagram: "图解", flow: "流程图", pipeline: "流水线图", qualitative: "定性图" };
    return m[String(t == null ? "" : t).toLowerCase()] || t;
  }
  // item1/item10 — read the SAME Jury blocking signal the Reader ribbon uses so the Runs
  // verdict can never contradict it. null = no Jury ledger bound for this paper (unknown).
  function juryBlocking() {
    var nd = (SB.needs && SB.needs.detail) ? SB.needs.detail.jury : null;
    var juryDir = (SB.needs && SB.needs.dirs) ? SB.needs.dirs.jury : "";
    if (!nd || !juryDir) return null;
    return nd.blocking || 0;
  }
  // item10 — has this run already been handed to Jury? (localStorage provenance, guarded)
  function provReviewed(runId) {
    if (!runId) return false;
    try { if (SB.prov && SB.prov.get) { var p = SB.prov.get(runId) || {}; return p.reviewedFromRun === runId; } } catch (e) {}
    return false;
  }
  function prefersReduced() {
    try { return !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches); } catch (e) { return false; }
  }

  /* ---- R24 — gloss machine enums / modes / ISO timestamps into human text.
     Every gloss keeps the raw token available in a title tooltip at the call site,
     so nothing that used to be readable becomes un-inspectable. */
  function fmtStamp(v) {
    var ms = toMs(v); if (!ms) return "—";
    var d = new Date(ms);
    return d.getFullYear() + "-" + pad2(d.getMonth() + 1) + "-" + pad2(d.getDate()) + " " + pad2(d.getHours()) + ":" + pad2(d.getMinutes());
  }
  function titleCase(s) { return String(s || "").replace(/[_-]+/g, " ").replace(/\b\w/g, function (c) { return c.toUpperCase(); }); }
  function glossEnum(s) {
    s = String(s == null ? "" : s); if (!s) return "—";
    var zh = lang() === "zh";
    var map = {
      "ask-baseline-parity": zh ? "待确认:基线口径" : "confirm baseline parity",
      "ask-citation": zh ? "待确认:引用" : "confirm citation",
      "auto-terminal": zh ? "自动终止" : "auto-terminal",
      "principal-collect": zh ? "主理收束" : "principal collect",
      "export-complete": zh ? "导出完成" : "export complete",
      "stall": zh ? "停滞" : "stalled"
    };
    return map[s] || titleCase(s);
  }
  function modeLabel(m) {
    var zh = lang() === "zh";
    var map = { data_aware: zh ? "数据核验" : "data-aware", proposal: zh ? "提案模式" : "proposal" };
    return map[m] || String(m || "").replace(/_/g, "-");
  }
  // R22a — the reversal-cost enum, glossed (English keeps the plain word; raw token → title=).
  function costLabel(c) {
    var zh = lang() === "zh";
    var map = { expensive: zh ? "撤销代价高" : "expensive", cheap: zh ? "易撤销" : "cheap" };
    return map[c] || String(c == null ? "" : c);
  }
  function dqStateLabel(s) {
    var zh = lang() === "zh";
    var map = { PENDING_REVIEW: zh ? "待复核" : "pending review", SUBMITTABLE: zh ? "可提交" : "submittable", BLOCKED: zh ? "受阻" : "blocked" };
    return map[s] || glossEnum(s);
  }

  // R14 — copy a decision command to the clipboard and confirm, so a stubbed button
  // becomes something the user can actually run in their terminal.
  function copyCmd(cmd) {
    if (!cmd) return;
    var ok = (lang() === "zh" ? "已复制,在终端里运行:" : "Copied — run in your terminal: ") + cmd;
    function fallback() {
      try {
        var ta = document.createElement("textarea");
        ta.value = cmd; ta.setAttribute("readonly", "");
        ta.style.position = "fixed"; ta.style.top = "-1000px"; ta.style.opacity = "0";
        document.body.appendChild(ta); ta.select();
        var done = document.execCommand("copy"); ta.remove();
        SB.toast(done ? ok : cmd);
      } catch (_) { SB.toast(cmd); }
    }
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(cmd).then(function () { SB.toast(ok); }, fallback);
      else fallback();
    } catch (_) { fallback(); }
  }

  /* ---- tiny i18n for the workspace body (chrome-adjacent labels only) ------ */
  var L = {
    zh: {
      "now": "当前", "running": "运行中", "narration": "叙述", "apparatus": "器械", "shelf": "货架",
      "What the agent is doing": "智能体在做什么", "Tool log": "工具日志", "Artifacts changing": "变动的产物",
      "Waiting for you": "等你答复", "reply in chat": "在对话里回复",
      "The spark": "一句话火种", "gap pattern": "空白模式", "solution": "解法", "provenance": "来源",
      "PDF out of date": "PDF 已过期", "sections/pipeline.tex changed after main.pdf was built — recompile to trust the reading below.": "main.pdf 生成后 sections/pipeline.tex 又改过 —— 重新编译后下面的正文才可信。",
      "Recompile": "重新编译", "Recompiling main.pdf…": "正在重新编译 main.pdf…", "PDF is fresh": "PDF 已是最新", "20 pp · 0 errors · rebuilt just now": "20 页 · 0 错误 · 刚刚重建",
      "Figure workshop": "图表工坊", "figures": "张图", "editable vector": "可编辑矢量", "DrawAI hybrid path": "DrawAI 混合路径", "Fig": "图",
      "vector": "矢量", "PNG only": "仅 PNG", "audit": "审核", "audit waived": "审核豁免", "audit failed": "审核未过", "critic": "评审", "critic rounds": "评审轮数", "editable text boxes": "可编辑文本框",
      "best tier": "最高档位", "GPU-hours": "GPU 小时", "outer rounds": "外层轮次", "open decisions": "待决策",
      // item12 — telemetry strip keys (values verbatim from the backlog)
      "model": "模型", "turns": "轮次", "tokens in": "输入token", "tokens out": "输出token", "tokens": "token", "cost": "花费", "duration": "用时", "started": "开始于",
      "Run timeline": "运行时间线", "sealed": "已封章", "halt": "停摆", "unsealed": "未封章", "no roll-call yet — stage not run": "尚无点名 —— 该阶段未运行",
      "Answer me": "等你处置", "Resume": "继续", "Reverse": "撤销", "dispositioned": "已处置",
      "Copy resume cmd": "复制继续命令", "Copy reverse cmd": "复制撤销命令",
      "Shippable tier": "可交付档位", "current": "当前", "FULL_PAPER floors": "FULL_PAPER 门槛", "all green": "全绿", "GPU-h": "GPU 小时", "rounds": "轮次", "off-ladder": "阶梯外",
      "Evidence × status": "证据 × 状态", "supported": "支持", "refuted": "证伪", "inconclusive": "未定", "status": "状态", "belief": "信念", "margin": "余量",
      "The verified numbers": "核实过的数字", "Dead-ends & lessons": "死胡同与教训", "hypothesis": "假设", "failure mode": "失败方式", "lesson": "教训",
      "Build integrity": "构建完整性", "Is the pipeline behaving?": "流水线守规矩吗?", "reversal rate by class": "按类别的撤销率", "did the agent freelance?": "智能体擅自行动了吗?",
      "postproc trend": "后处理趋势", "run history": "运行历史",
      // R5 — reading nav rail (left) + section headers
      "Runs": "运行", "This paper": "本篇论文",
      "Story": "故事", "Proposal": "提案", "Compiled PDF": "编译好的 PDF",
      "Claims ledger": "主张台账", "Facts": "事实", "Decisions": "决策", "official": "官方",
      // R5 — governance card eyebrows (were leaking English in zh)
      "Stage seals": "阶段封章", "Decision queue": "决策队列", "Tier ladder": "档位阶梯",
      "Claim ledger": "主张台账", "Results / facts": "结果 / 事实", "Negative results": "负面结果",
      "Gates & LaTeX QA": "闸门与 LaTeX 质检", "E14 cross-run trends": "E14 跨运行趋势",
      "waiting": "等待中", "figure": "图",
      "newer than every source file — the reading below is trustworthy.": "比所有源文件都新 —— 下面的正文可信。"
    },
    en: {}
  };
  function T(k) { var m = L[lang()]; return (m && m[k]) || k; }

  /* =========================================================================
     REGISTER — the workspace title, sub-views, and dispatch
     ========================================================================= */
  ensureSparkSprite();
  SB.registerTool("spark", {
    title: BLUEPRINT.method_name,
    sub: [
      { id: "reading", label: lang() === "zh" ? "阅读" : "Reading" },
      { id: "runs", label: lang() === "zh" ? "运行" : "Runs" },
      { id: "figures", label: lang() === "zh" ? "图表" : "Figures" },
      { id: "manuscript", label: lang() === "zh" ? "稿件" : "Manuscript" },
      { id: "governance", label: lang() === "zh" ? "治理" : "Governance" }
    ],
    onTitle: openRunSwitcher,
    render: function (main, sub) {
      ensureSparkSprite();
      fitMain(main);
      if (sub === "runs") return renderRuns(main);
      if (sub === "figures") return renderFigures(main);
      // Manuscript is implemented in a separate manuscript.js loaded by the shell;
      // dispatch to it when present, else fail soft with a toast (never a blank view).
      if (sub === "manuscript") return SB.sparkManuscript ? SB.sparkManuscript(main) : (main.innerHTML = "", SB.toast && SB.toast("Manuscript 模块未加载"));
      if (sub === "governance") return renderGovernance(main);
      return renderReading(main);
    }
  });

  // ---- SHARED-SHELL WORKAROUND -------------------------------------------
  // The shell's CSS targets #app / main#main, but reader.js actually creates
  // #sb-app / #sb-main — so #sb-main never gets `flex:1;overflow:hidden` and is
  // content-height driven. With body{overflow:hidden} that clips tall content
  // with no scroll. We cannot edit the shared shell, so we bound the received
  // <main> at runtime: a real height lets ReaderShell's height:100% columns and
  // our .pane's overflow:auto actually scroll. (Reported as a shell gap.)
  function fitMain(main) {
    main.style.height = "calc(100vh - 53px)"; // 52px strip + 1px border
    main.style.minHeight = "0";
    main.style.overflow = "hidden";
    main.style.position = "relative";
  }

  // run switcher popover (workspace title dropdown)
  function openRunSwitcher() {
    $$(".pop.run-switch,.scrim").forEach(function (n) { n.remove(); });
    var sc = el("div", "scrim"); sc.onclick = close; document.body.appendChild(sc);
    var pop = el("div", "pop run-switch");
    pop.style.cssText = "left:96px;top:58px;width:min(380px,92vw);padding:10px";
    pop.innerHTML = '<div class="rs-h">' + (lang() === "zh" ? "选择运行" : "Open a run") + '</div>' +
      FEED.map(function (r, i) {
        return '<div class="rs-row' + (r.sel ? " sel" : "") + '"><span class="rs-dot ' + (r.sel ? "on" : "") + '"></span>' +
          '<div class="rs-body"><div class="rs-t">' + esc(r.title) + '</div><div class="rs-s">' + esc(r.src) + '</div></div></div>';
      }).join("");
    document.body.appendChild(pop);
    // R5 — the switcher actually switches now (was a "demo" toast).
    $$(".rs-row", pop).forEach(function (row, i) { row.onclick = function () { close(); loadRun(FEED[i].id); }; });
    function close() { pop.remove(); sc.remove(); }
  }

  // R3/R5 — expose Spark's runs to the ⌘K palette when the shell supports extra
  // sources (guarded: a no-op until reader.js grows SB.registerPaletteSource).
  if (SB.registerPaletteSource) {
    SB.registerPaletteSource(function () {
      var rs = (RV.runs && RV.runs.length) ? RV.runs : FEED;
      return rs.map(function (r) {
        return { id: r.id, label: r.title, type: "run", run: function () { SB.setTool("spark"); loadRun(r.id); } };
      });
    });
    // item23 — one ⌘K entry per figure → jump to the figures view and zoom it. Guarded on
    // dirOpen so the sample gallery doesn't flood the palette; late-bound to the live FIGURES.
    SB.registerPaletteSource(function () {
      if (!dirOpen()) return [];
      var zh = lang() === "zh";
      return FIGURES.map(function (f) {
        var figN = f.number != null ? (T("Fig") + " " + f.number) : f.label;
        return { id: "fig:" + (f.number != null ? f.number : f.label), label: (zh ? "图表 ▸ " : "Figures ▸ ") + figN, type: (zh ? "图表" : "figure"),
          run: function () { SB.setTool("spark"); SB.setSub("figures"); openLightbox(f); } };
      });
    });
  }
})();
