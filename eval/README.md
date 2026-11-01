# Evaluation

| Script | Purpose |
|---|---|
| `evaluate.py <folder>` | Runs the full pipeline on `folder/real/*` and `folder/ai/*`. Writes `report.md`, `results.json` and `results.csv` (default `eval/reports/`). Images and text are reported separately: accuracy, precision, recall, false-positive rate, F1, confusion matrix, label distribution and per-detector results. |
| `calibrate_binoculars.py <folder>` | Prints Binoculars raw scores for `real/*.txt` and `ai/*.txt` and suggests `BINOCULARS_THRESHOLD` / `BINOCULARS_SCALE`. |

Quick smoke test with the bundled samples (seconds, needs models):

```bash
mkdir -p /tmp/smoke/real /tmp/smoke/ai
cp tests/samples/human.txt tests/samples/sample.jpg /tmp/smoke/real/
cp tests/samples/ai.txt tests/samples/c2pa_ai.jpg /tmp/smoke/ai/
python eval/evaluate.py /tmp/smoke
```

## Results recorded in docs/LIMITATIONS.md (November 2026)

The test data was public and is **not** stored in this repository. To reproduce:

* **Text:** Hello-SimpleAI/HC3 (human vs ChatGPT answers). Calibration used
  rows 0–39 of `open_qa`, `finance` and `wiki_csai`. Evaluation used different
  rows/subsets (`reddit_eli5` from 500, `medicine` from 300, `open_qa` from
  200, `finance` from 600): 40 human and 40 AI answers of 80+ words.
* **Images A:** elsaEU/ELSA_D3 validation split. Generated images from SD 1.4,
  SD 2.1 or SDXL (40), and the original web photos they were made from
  (35 that could still be downloaded).
* **Images B:** Hemg/AI-Generated-vs-Real-Images-Datasets (AI art vs. real
  art). Many AI items are 32×32 thumbnails, which the tool now refuses to
  score. On the larger items the image models found almost no AI artwork.

Public datasets are only a first check. Before go-live, build a local set as
described in docs/LIMITATIONS.md, section 6.
