# Experiment Templates

Minimal templates per paper type. Use them in Step 3 to pick **required** vs **recommended**
experiments. Run only what is feasible with the available data/code (Step 4). These are
starting points — adapt to the specific paper, and never run an experiment just to fill a
template slot.

---

## 1. Machine learning classification papers

- **Required experiments:** main classification on the target dataset(s); comparison against
  at least one credible baseline; standard train/val/test split.
- **Recommended:** ablation of key components; sensitivity to main hyperparameters; multiple
  seeds for variance.
- **Common metrics:** accuracy, precision, recall, F1, AUROC/AUPRC (for imbalance).
- **Common baselines:** logistic regression / SVM / random forest / gradient boosting; a
  simple neural baseline; the most relevant prior method.
- **Typical tables/figures:** main results table; ablation table; confusion matrix; learning
  curve.
- **Common risks:** data leakage, class imbalance ignored, single-seed results, tuning on test.

## 2. Image classification / detection papers

- **Required experiments:** main accuracy/mAP on standard benchmark; comparison to a published
  baseline under the same protocol.
- **Recommended:** ablations (backbone, augmentation, loss); efficiency (params, FLOPs,
  latency); qualitative examples.
- **Common metrics:** top-1/top-5 accuracy; mAP / AP50 / AP75; IoU; FPS.
- **Common baselines:** ResNet/ViT backbones; Faster R-CNN / YOLO / DETR families; the
  paper's stated prior art.
- **Typical tables/figures:** benchmark table; ablation table; qualitative detections;
  accuracy-vs-compute plot.
- **Common risks:** inconsistent input sizes/protocols, cherry-picked qualitative samples,
  unfair compute comparison.

## 3. NLP classification / generation papers

- **Required experiments:** task metric on standard dataset(s); comparison to a relevant
  baseline/LLM under a fixed prompt/protocol.
- **Recommended:** ablations (prompt, components); robustness to input perturbation; human or
  reference-based evaluation for generation.
- **Common metrics:** accuracy/F1 (classification); BLEU/ROUGE/METEOR/BERTScore (generation);
  exact match; perplexity; human ratings.
- **Common baselines:** fine-tuned encoder (BERT/RoBERTa); strong zero/few-shot LLM; prior SOTA.
- **Typical tables/figures:** main metric table; ablation table; example outputs; error
  analysis.
- **Common risks:** contamination/leakage, metric gaming, single prompt, no significance/
  variance reporting.

## 4. Time-series prediction papers

- **Required experiments:** forecasting on target series with proper temporal split (no
  look-ahead); comparison to naive and classical baselines.
- **Recommended:** multiple horizons; rolling-origin evaluation; sensitivity to window length.
- **Common metrics:** MAE, RMSE, MAPE/sMAPE, MASE; coverage for intervals.
- **Common baselines:** naive/seasonal-naive; ARIMA/ETS; a simple ML/DL forecaster.
- **Typical tables/figures:** error table by horizon; forecast-vs-actual plot; residual
  diagnostics.
- **Common risks:** data leakage via shuffling, non-stationarity ignored, single split.

## 5. Engineering system papers

- **Required experiments:** end-to-end evaluation on a realistic workload/scenario; comparison
  to a baseline system or prior approach.
- **Recommended:** scalability/throughput/latency; resource usage; ablation of design choices;
  failure/stress cases.
- **Common metrics:** throughput, latency (p50/p95/p99), success rate, cost, energy,
  utilization.
- **Common baselines:** existing system, default configuration, or a simplified variant.
- **Typical tables/figures:** performance table; scalability curve; latency distribution;
  resource breakdown.
- **Common risks:** unrepresentative workload, warm-up effects, single run, untuned baseline.

## 6. Survey / bibliometric papers

- **Required experiments:** explicit search strategy and inclusion/exclusion criteria;
  reproducible corpus; structured taxonomy.
- **Recommended:** trend analysis over time; coverage/quality assessment; gap analysis.
- **Common metrics:** counts by category/year; coverage; inter-rater agreement (if coded).
- **Common baselines:** prior surveys (scope comparison).
- **Typical tables/figures:** PRISMA-style flow diagram; taxonomy table; trend charts.
- **Common risks:** opaque selection, missing search terms, no reproducibility, vote-counting
  passed off as synthesis. (Route to **PRISMA** for systematic reviews.)
