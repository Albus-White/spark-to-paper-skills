# Text & formula rules

## Text
- All ordinary text is recreated as **real editable** text. DrawAI emits every label/title/legend as
  native `<text>`/`<tspan>` (its `text_rendering=model_text` contract) which the native-shapes converter
  maps to PowerPoint text boxes. Text is **never** rasterized.
- Do **not** preserve AI-generated malformed text: DrawAI uses OCR as a hint and verifies against the
  source image; this skill additionally compares source-OCR tokens to rendered-output text every round.
- Preserve exact wording, capitalization, punctuation, and meaningful line breaks; preserve font size,
  weight, alignment, and color as closely as DrawAI's profile allows.
- Every detected text region should map to an editable text object. Critical-label mismatch **fails the
  quality gate** (`critical_label_recall` must be 1.0 for PASS).
- `verify_text_and_formulas.py` computes OCR token recall/precision and critical-label recall. Critical
  labels can be supplied via `--critical-labels "Title A,Title B,..."`; otherwise they are inferred from
  longer/capitalized OCR strings. Provide them explicitly for important figures.

## Formulas
Per the contract, formulas are **not** approximated as plain Unicode and **never** kept as low-res raster.

For every detected formula `verify_text_and_formulas.py`:
1. detects candidate formula strings (OCR math-like tokens + SVG `data-pb-role="formula"`);
2. (with `--transcribe`) transcribes to **LaTeX** via an available agent CLI (`codex`/`claude`), saved to
   `formulas/formula_NNN.tex`;
3. verification of the LaTeX against the source image is a **human-review** step (every formula is flagged
   `needs_review: true`);
4. converts LaTeX to a **vector** SVG via matplotlib mathtext when it parses (`formulas/formula_NNN.svg`);
5. **OMML / native Office Math insertion is not implemented** in this skill version. Per spec item 6 the
   documented fallback is: insert the vector SVG generated from LaTeX and **preserve the `.tex` source**
   beside the PPTX. `formulas/formula_NNN.json` records `omml_inserted: false` and the fallback used.
6. low-resolution raster formulas are never produced.

Artifacts per formula:
```text
formulas/
  formula_001.tex     LaTeX source (when transcribed)
  formula_001.svg     vector rendering from LaTeX (when it parses)
  formula_001.json    { detected_text, latex, vector_svg_file, omml_inserted:false, needs_review:true, rasterized:false }
```

> Honesty: if no agent CLI is available, `latex` is `null` and the formula is flagged for manual
> transcription — the skill does not invent a LaTeX string. OMML support is a documented TODO; until then
> formulas in the PPTX come from DrawAI's editable `<text>`+`<tspan>` (Unicode + baseline-shift) and the
> `.tex`/`.svg` fallback is preserved beside the output for a faithful vector version.
