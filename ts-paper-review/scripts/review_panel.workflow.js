// review_panel.workflow.js — adversarial peer-review for a ts-paper draft.
// Distilled from PaperJury's review-panel.workflow.js (the lean fast-path): N isolated
// reviewers read the WHOLE paper -> merge/dedupe vs everything seen -> perspective-diverse
// skeptics try to refute each new issue -> loop-until-dry. The heavy courtroom (trial/jury/
// ledger/recall) is intentionally NOT ported — this lean panel captures ~80% of the value.
//
// THIS IS TIER 1 of THREE interchangeable backends (see SKILL.md "THE REVIEW ALGORITHM").
// It runs ONLY when the Workflow tool is available. Tiers 2 (Task/Agent subagents) and 3
// (in-context sequential) reproduce this EXACT algorithm and return shape by instruction, with
// no quality loss (Tier 2 gets true isolation from separate subagent contexts). Anyone editing
// the algorithm here MUST keep all tiers in lockstep: the return object
// { issues, refuted, dropped_no_criterion, rounds_run, per_round }, the survive rule
// (refutedCount < ceil(ANGLES.length/2) => survives, i.e. drop on >=2 of 3 refutes), and the
// final severity sort + 'I-NN' id assignment.
//
// Invoke from the orchestrator:
//   Workflow({ scriptPath: ".../review_panel.workflow.js", args: {
//     paperText: "<the whole drafted paper as readable text, leakage-stripped>",
//     venueProfile: "<one-line venue/style note, e.g. 'Traitement du Signal journal: rigor, well-read, signal-processing'>",
//     resultsMode: "proposal" | "data_aware",
//     personas: [ {id:"R1", lensName:"Theory / Foundations", focus:"..."}, ... ],  // optional; defaults to 3 generic lenses
//     maxRounds: 2, dryStop: 1, verify: true   // lean defaults; cheapest = {maxRounds:1, verify:false}; thorough = {maxRounds:4, dryStop:2}
//   }})
// Returns { issues, refuted, dropped_no_criterion, rounds_run, per_round }. The orchestrator
// triages `issues` by verdict-of-severity, fixes the valid ones via the refine stage (binding
// each fix to its close_criterion), and lists author-required ones for the user.

export const meta = {
  name: 'ts-paper-review',
  description: 'Adversarial N-reviewer panel over a drafted paper, with loop-until-dry re-runs and perspective-diverse refutation of each issue. Distilled from PaperJury.',
  phases: [
    { title: 'Review', detail: 'N isolated reviewers per pass; each returns a schema-validated issue table' },
    { title: 'Merge', detail: 'dedupe within the pass and against everything seen so far' },
    { title: 'Verify', detail: 'perspective-diverse skeptics try to refute each new issue; keep survivors' },
  ],
}

const A = (typeof args === 'string' ? JSON.parse(args) : args) || {}
const paperText = A.paperText || ''
const venueProfile = A.venueProfile || 'a top venue: rigor, clarity, well-read, fair baselines'
const resultsMode = A.resultsMode === 'data_aware' ? 'data_aware' : 'proposal'
const maxRounds = A.maxRounds ?? 2
const dryStop = A.dryStop ?? 1
const doVerify = A.verify !== false

// The three full-surface lenses (PaperJury's degrade fallback; a tendency, not a fence).
const DEFAULT_PERSONAS = [
  { id: 'R1', lensName: 'Theory / Foundations', focus: 'definitions vs use, notation consistency, whether the formalism actually supports the contribution, proof/derivation gaps, over-general claims.' },
  { id: 'R2', lensName: 'Empirical / Benchmark', focus: 'evaluation design soundness, baseline fairness and vintage, metric correctness, ablation coverage of the key design decisions, whether the planned experiments would actually validate the claims.' },
  { id: 'R3', lensName: 'Applied / Systems', focus: 'practicality, efficiency/latency/memory claims, reproducibility, deployment realism, whether the problem matches a real use case.' },
]
const personas = (A.personas && A.personas.length) ? A.personas : DEFAULT_PERSONAS

const GATEKEEPER_CORE = [
  'You are a senior reviewer for a top venue, known for being harsh, precise, and constructive.',
  'Your job is to find what is actually WRONG, not to be agreeable. You separate fatal flaws from',
  'fixable nits and weight them accordingly. You do not pad with compliments, you do not invent',
  'problems to look thorough, and you do not soften a real flaw. You MUST reason across sections',
  '(abstract-vs-method, a symbol reused inconsistently, a contribution the paper does not actually',
  'support). Two passes: (1) a blunt fatal-flaw diagnostic; (2) a forensic interrogation per flaw',
  '(where exactly, why, what would settle it, fatal vs fixable within a revision).',
].join('\n')

// What "wrong" means depends on whether the paper reports real results.
const MODE_NOTE = resultsMode === 'data_aware'
  ? ['This paper reports REAL experimental results. Scrutinize: claims-vs-evidence (does each number',
     'support the claim it is attached to?), baseline fairness, ablation coverage, statistical care,',
     'over-claiming beyond what the data shows, and abstract numbers matching the tables.'].join('\n')
  : ['This is a research PROPOSAL with NO real experimental results yet (result tables are intentionally',
     'blank and prose is forward-looking — do NOT file "results are missing/blank" as a flaw). Judge the',
     'PROPOSAL on: method soundness and completeness (is it fully specified?), novelty/positioning vs prior',
     'work, clarity, whether the EVALUATION PLAN (datasets/metrics/baselines/ablations) would actually',
     'validate the stated contributions, internal consistency, and unsupported or overreaching claims.'].join('\n')

const ANGLES = [
  'misreading: the issue claims something is wrong or missing that is actually present or correct in the paper text',
  'already-addressed: the concern is already handled elsewhere in the paper, so the issue does not stand',
  'scope-or-severity: the concern is real but out of scope for this venue/paper-stage, or its severity is materially overstated',
]

const ISSUE_TABLE = {
  type: 'object', additionalProperties: false,
  properties: {
    reviewer_id: { type: 'string' },
    pass1_fatal_flaws: { type: 'array', items: { type: 'string' } },
    issues: {
      type: 'array',
      items: {
        type: 'object', additionalProperties: false,
        properties: {
          id_local: { type: 'string' },
          severity: { type: 'string', enum: ['blocker', 'major', 'minor', 'nit'] },
          section: { type: 'string' },
          summary: { type: 'string' },
          evidence_quote: { type: 'string', description: 'EXACT verbatim quote from the paper the issue rests on; cannot quote => do not file' },
          close_criterion: { type: 'string', description: 'one sentence describing what an edit must satisfy to resolve it' },
        },
        required: ['id_local', 'severity', 'section', 'summary', 'evidence_quote', 'close_criterion'],
      },
    },
  },
  required: ['reviewer_id', 'pass1_fatal_flaws', 'issues'],
}

const ROUND_MERGE = {
  type: 'object', additionalProperties: false,
  properties: {
    new_issues: {
      type: 'array',
      items: {
        type: 'object', additionalProperties: false,
        properties: {
          severity: { type: 'string', enum: ['blocker', 'major', 'minor', 'nit'] },
          section: { type: 'string' },
          summary: { type: 'string' },
          evidence_quote: { type: 'string' },
          close_criterion: { type: 'string' },
          raised_by: { type: 'array', items: { type: 'string' } },
        },
        required: ['severity', 'section', 'summary', 'evidence_quote', 'close_criterion', 'raised_by'],
      },
    },
    dropped_no_criterion: {
      type: 'array',
      items: {
        type: 'object', additionalProperties: false,
        properties: { summary: { type: 'string' }, reason: { type: 'string' } },
        required: ['summary', 'reason'],
      },
    },
  },
  required: ['new_issues', 'dropped_no_criterion'],
}

const VERIFY = {
  type: 'object', additionalProperties: false,
  properties: {
    refuted: { type: 'boolean' },
    angle: { type: 'string' },
    reason: { type: 'string' },
  },
  required: ['refuted', 'angle', 'reason'],
}

function reviewerPrompt(p) {
  return [
    GATEKEEPER_CORE,
    '',
    `Your lens: ${p.lensName} — ${p.focus || ''} (the lens is a tendency; cover the whole paper).`,
    `Venue / style profile: ${venueProfile}`,
    '',
    MODE_NOTE,
    '',
    'Return: (1) pass1_fatal_flaws (a blunt list), then (2) the structured issue table. Every issue',
    'MUST carry an EXACT verbatim evidence_quote from the paper (if you cannot quote the supporting',
    'text, you did not actually find it — do not file it) and a concrete close_criterion (one sentence',
    'an edit must satisfy). Anchor each issue to a precise section. Do not be agreeable; do not invent',
    'problems; name real flaws exactly.',
    '',
    'ISOLATION (hard rule): judge ONLY the paper quoted below. Do not read files, search, or use any',
    'tool; you cannot see other reviewers or prior passes — everything you may consider is here.',
    '',
    'THE PAPER:',
    '"""',
    paperText,
    '"""',
  ].join('\n')
}

function mergePrompt(reviews, seen) {
  return [
    'You are merging one pass of an adversarial review panel over a paper draft.',
    'Input: each reviewer\'s issue table (JSON), plus a SEEN list of issue summaries from earlier passes.',
    'Rules:',
    '- Dedupe within this pass: an issue raised by >=2 reviewers collapses into ONE row whose raised_by',
    '  lists every source reviewer (same issue only when the section anchor matches AND the summaries',
    '  genuinely overlap; when unsure keep separate).',
    '- Exclude anything already in SEEN (judge by MEANING, not string match) — return only genuinely NEW issues.',
    '- Drop any issue missing a usable close_criterion into dropped_no_criterion.',
    '- Carry each issue\'s evidence_quote through unchanged. Do NOT invent issues.',
    '',
    'SEEN (already captured, do not re-report):',
    JSON.stringify(seen, null, 2),
    '',
    'Reviewer issue tables this pass:',
    JSON.stringify(reviews, null, 2),
  ].join('\n')
}

function verifyPrompt(issue, angle) {
  return [
    'You are an ADVERSARIAL verifier. Try to REFUTE the issue below, judged ONLY from this angle:',
    angle,
    '',
    'Set refuted=true ONLY if, from this angle, the issue does not hold (reason grounded in the paper',
    'text). Otherwise refuted=false. Be skeptical but fair: do not refute a genuine flaw to look',
    'decisive, and do not rubber-stamp. Judge ONLY the paper quoted below; use no tools.',
    '',
    `ISSUE:\n  severity: ${issue.severity}\n  section: ${issue.section}\n  summary: ${issue.summary}`,
    `  evidence_quote: ${issue.evidence_quote}\n  close_criterion: ${issue.close_criterion}`,
    '',
    'THE PAPER:',
    '"""',
    paperText,
    '"""',
  ].join('\n')
}

const confirmed = []
const seen = []
const refutedLog = []
const droppedNoCriterion = []
const perRound = []
let dry = 0
let round = 0

while (dry < dryStop && round < maxRounds) {
  round++
  if (budget.total && budget.remaining() < 40000) {
    log(`budget low (${Math.round(budget.remaining() / 1000)}k left); stopping the review loop early`)
    break
  }

  const reviews = (await parallel(
    personas.map((p) => () => agent(reviewerPrompt(p), { label: `r${round}:review:${p.id}`, phase: 'Review', schema: ISSUE_TABLE }))
  )).filter(Boolean)

  const merge = await agent(mergePrompt(reviews, seen), { label: `r${round}:merge`, phase: 'Merge', schema: ROUND_MERGE })
  droppedNoCriterion.push(...(merge.dropped_no_criterion || []))
  const candidates = merge.new_issues || []

  if (candidates.length === 0) {
    dry++; perRound.push({ round, candidates: 0, survived: 0, dry })
    log(`pass ${round}: no new issues (dry ${dry}/${dryStop})`); continue
  }
  candidates.forEach((c) => seen.push(c.summary))

  let survivors = candidates
  if (doVerify) {
    const judged = await parallel(candidates.map((c) => () =>
      parallel(ANGLES.map((a) => () => agent(verifyPrompt(c, a), { label: `r${round}:verify:${(c.section || '').slice(0, 16)}`, phase: 'Verify', schema: VERIFY })))
        .then((vs) => {
          const v = vs.filter(Boolean)
          const refuted = v.filter((x) => x.refuted).length
          return { issue: c, survived: refuted < Math.ceil(ANGLES.length / 2), verdicts: v, refutedCount: refuted }
        })
    ))
    survivors = judged.filter((j) => j && j.survived).map((j) => j.issue)
    judged.filter((j) => j && !j.survived).forEach((j) => refutedLog.push({ issue: j.issue, refutedCount: j.refutedCount, verdicts: j.verdicts }))
  }

  if (survivors.length === 0) { dry++ } else { dry = 0; confirmed.push(...survivors) }
  perRound.push({ round, candidates: candidates.length, survived: survivors.length, dry })
  log(`pass ${round}: ${candidates.length} new, ${survivors.length} survived verify, total ${confirmed.length} (dry ${dry}/${dryStop})`)
}

const rank = { blocker: 0, major: 1, minor: 2, nit: 3 }
const issues = confirmed
  .slice()
  .sort((a, b) => (rank[a.severity] ?? 9) - (rank[b.severity] ?? 9))
  .map((iss, i) => ({ ...iss, id: 'I-' + String(i + 1).padStart(2, '0') }))

return { issues, refuted: refutedLog, dropped_no_criterion: droppedNoCriterion, rounds_run: round, per_round: perRound }
