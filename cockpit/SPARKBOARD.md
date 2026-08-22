# SparkBoard — the paper-first reader for Spark · Jury · Wiki

SparkBoard is the local control room for the Spark-to-Paper tool suite, reimagined
as a warm, **paper-first three-column reader** in the spirit of the macOS RSS reader
*PaperRss* ("Reading First, AI Second"). One shell hosts three switchable **tool
workspaces**, each with its own content and its own ink, sharing one reading surface
and one restrained on-demand AI.

- **Spark** (terracotta) — turn one sentence into a full paper: launch + monitor runs,
  read the produced paper, and inspect the run's governance (seals, decisions, tiers,
  claims, negative results).
- **Jury** (judicial indigo) — a pre-submission adversarial peer-review *courtroom*:
  a verdict board, a revision inbox of before/after diffs, reviewer panels, a
  submission shield.
- **Wiki** (field sage) — a reverse-linked LLM knowledge corpus you read entry-by-entry,
  with the signature backlinks rail, a concept graph, and a research-ideation inbox.

## Run it

```
python -m cockpit            # serves 127.0.0.1:8765 and opens an app window
python -m cockpit --no-browser --port 8790
```

`/` is the SparkBoard shell; `/legacy` is the original single-tool Spark cockpit
(`ui.html`), kept intact. The server OWNS the run subprocesses (see `runner.py`), so
closing the window never kills a three-hour run.

## Architecture (no build step, stdlib server, vanilla JS)

```
cockpit/
  serve.py            # stdlib http.server: run API + static /ui,/assets + /api/ai + settings
  runner.py           # one headless `claude` subprocess per run (bidirectional stream-json)
  ui/
    index.html        # the modular shell page (served at /)
    sparkboard.css    # design system: tokens, the reader surface, shared primitives
    reader.js         # SB shell: tool switcher, 3-column reader, rail, keyboard, restrained AI
    ai.js             # SB.aiTransport -> /api/ai (real streaming model)
    settings.js       # the .env editor overlay (incl. the Reading assistant key)
    spark.js/.css     # Spark workspace (reading + runs + figures + governance)
    jury.js/.css      # Jury workspace (docket + revisions + panel + shield + example)
    wiki.js/.css      # Wiki workspace (library + ideas + graph + coverage + sources + inbox + ask)
  assets/fonts/       # Fraunces (reading headers / editorial display)
  workspaces/         # stdlib data adapters: on-disk artifacts -> JSON the reader fetches
    ai.py             # the reading-AI proxy (OpenAI-compatible, streaming)
    spark_read.py     # build_report collectors + .research governance readers
    jury.py           # .paper-review/LEDGER.json, journal, spine, compile, compliance
    wiki.py           # wiki/ notes, computed backlinks, concept graph, ideas, coverage
```

### The shared shell (`reader.js`, exposed as `window.SB`)
- `SB.registerTool(name, {title, sub, render})` — each workspace module self-registers.
- `SB.ReaderShell(main, {sidebar, list, rail, reader:{kicker,title,meta,bodyHTML,backlinks}})`
  — the PaperRss three-column reader: sidebar 240–340 / list 280+ / reader (820px serif
  column), a draggable split, Zen mode, a floating overlay scrollbar, and the polymorphic
  right rail (`toc` ticks, or the `dock` = section-TOC + **computed backlinks**).
- Restrained AI: on-demand summary (**V**), a text-selection action bar → explain /
  translate / ask popover, inline translation (**C**). One request at a time; nothing is
  sent to a model until you act. Backed by `/api/ai`.
- Keyboard: `V` summary · `C` translate · `B,B`/`N,N` prev/next · `M` star · `Z` zen ·
  `1/2/3` switch tool · `⌘±/0` font · `⌘/` help · `Esc`.
- Theme (system/light/dark) and language (中/EN) persist; `?tool=&theme=&lang=` force a
  state for deterministic screenshots.

### The design system (`sparkboard.css`) — "Editorial Press / Paper Desk"
- **Fraunces** serif for reading headers + editorial display; **IBM Plex Sans** body/UI;
  **IBM Plex Mono** apparatus. A hair of paper grain over warm desk/sheet/raise surfaces.
- One accent switches per tool via `html[data-tool]`: Spark `#C0552A`, Jury `#4B4FA6`,
  Wiki `#5F7355` (each with a dark-mode variant). Reusable primitives: cards, chips,
  badges, meters, kanban, diffs, vote bars, persona cards, heatmaps, timelines.

### Server (`serve.py`) — additions over the base cockpit
- `GET /ui/*`, `GET /assets/*` — static modules + fonts, path-jailed to their roots.
- `POST /api/ai {op,text,context,target_lang}` — SSE stream from the configured
  reading model (DeepSeek / OpenAI-compatible). The **one** place user text reaches a model.
- Settings gains a **Reading assistant** group (`SPARKBOARD_AI_BASE_URL/KEY/MODEL`,
  falling back to `OPENAI_API_KEY`).
- Everything else (runs, figures, tree, file, report, settings) is unchanged; the path
  jail on `/api/run/<id>/file` still holds.

## Configure the reading AI
Settings → **Reading assistant**: a Base URL (DeepSeek `https://api.deepseek.com` is a
cheap default), an API key (stored only in the plugin `.env`, never synced), and a model
(`deepseek-chat`, `gpt-4o-mini`, …). Text is sent only when you press **V** or pick a
selection action — never on its own.

## Design provenance
See `.../scratchpad/DESIGN-CONTRACT.md` and the subsystem maps (PaperRss UX, the base
cockpit, and the spark/jury/wiki data models) for the full derivation.
