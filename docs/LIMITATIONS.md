# What this tool can and cannot do

*A note for leadership and reviewing officers. Please read before relying on any result.*

## 1. The short version

1. The tool gives an **indicator, not proof**. A score is a statistical guess.
   It must never be the only basis for a decision about a person.
2. It is **good at spotting typical chatbot text in English**. It is **weak on
   images**, especially AI artwork and edited photos.
3. It **cannot judge text in Malayalam, Hindi or other Indian languages**. It
   says so and does not give a label for that text.
4. People can **defeat it on purpose**. Light editing, paraphrasing tools,
   screenshots or re-saving an image can hide AI origin.
5. **"Likely Human" does not mean "certainly human".** It means the tool found
   no strong AI signal.

## 2. How accurate is it? (measured November 2026)

We tested on public, labelled examples the models had not been tuned on.
Accuracy on department documents will differ. **Test on local samples before
wide use** with `eval/evaluate.py`; see section 6.

### Text (English): good on typical chatbot text

80 texts: 40 human answers and 40 ChatGPT answers (public HC3 dataset,
medicine, finance, open questions, Reddit).

| | Result |
|---|---|
| Correct overall (score ≥ 50 = AI) | **98.8 %** (79 of 80) |
| Human texts wrongly scored ≥ 50 (false positives) | **2.5 %** (1 of 40) |
| Human texts labelled "Likely AI" (score ≥ 70) | **0 %** |
| AI texts labelled "Likely AI" | 82.5 % (the rest were "Not sure") |
| Results in the "Not sure" band | 14 % |

**Why real-world accuracy will be lower:**
* The test texts come from an older ChatGPT (2023). Newer models, and texts that
  a person has edited, are harder to detect.
* Text from paraphrasing tools (e.g. "humanisers") is often missed.
* **Short texts** (under about 150 words) are unreliable. Under 40 words, no text score is given.
* **Formal, formulaic human writing** (government orders, legal notices,
  standard reports, translations) can look "AI-like" because it is predictable.
  This is the main source of false positives. Treat "Likely AI" on such
  documents with extra care.
* Writing by non-native English speakers is known to be flagged more often by
  all AI-text detectors.

### Images: limited

**Test A: photo-style images from Stable Diffusion 1.4 / 2.1 / XL vs. real web photos**
(75 images, ELSA D3 dataset):

| | Result |
|---|---|
| Correct overall (score ≥ 50 = AI) | **76 %** |
| Real photos wrongly scored ≥ 50 | **8.6 %** (3 of 35) |
| AI images labelled "Likely AI" | 47.5 % |
| Results in the "Not sure" band | 43 % |

**Test B: AI-generated artwork vs. human artwork** (Hemg dataset):
the image models found **almost none** of the AI artworks (recall near 0 %).
They are trained on photo-like images and **do not work for illustrations,
paintings, logos, cartoons or posters**.

**Other image limits:**
* Images smaller than 128 pixels are not scored. The screen says so.
* Screenshots, heavy compression, resizing, cropping or photos of a screen
  remove the traces the models look for.
* New image generators appear every few months. Models trained on older
  generators miss them. The models need periodic replacement (section 7).
* **Edited real photos** (a face swapped, an object added) are often scored as human.

### Provenance (C2PA content credentials): reliable when present, usually absent

Some AI tools (e.g. Adobe Firefly, OpenAI image tools, some Google and
Microsoft tools) attach a **signed content credential** saying "made with
AI". If it is present and the signature is intact, the tool shows
**"AI (provenance-confirmed)"**. This is the strongest evidence the tool can
give.

But: most files **do not carry credentials**. Credentials are removed by
screenshots, WhatsApp/social-media forwarding and most editing. **No
credential tells you nothing.** A credential whose signature is broken is
reported but not trusted.

Metadata hints (e.g. "Software: Midjourney" in the file) are easily added or
removed. They only add a small amount (+15) to the score.

## 3. Language limits

The text detectors are trained and tuned for **English only**.

* For Malayalam, Hindi, Tamil and other Indian languages, the tool **detects
  the language, shows a warning, and does not use the text score for the
  label**. The result is usually "Cannot assess" unless images can be scored.
* For **mixed English + Indian-language text** a warning is shown. Accuracy is reduced.
* **Transliterated text** (e.g. Malayalam written in English letters) is
  usually detected as non-English and is not scored.

Supporting Indian languages properly would need models trained on those
languages, plus a local evaluation set. Neither exists today in a form we
could validate.

## 4. False positives: the most important risk

A false positive means **a person's genuine work is flagged as AI**. To limit this:

* The label "Likely AI" needs a score of **70 or more**, not 50.
* The text threshold was set so that about 5 % or fewer of human test texts score above 50.
* The screen shows **every signal**, warns when detectors **disagree strongly**,
  and always shows the disclaimer.

**Recommended rule for officers:** a "Likely AI" result is a reason to *look
more closely*, e.g. ask the author for drafts or sources, or compare with
their other work. It is never a finding by itself.

## 5. What is recorded

For every check the audit log keeps who, when, the file's SHA-256
fingerprint, the file type, every score, the model versions and the label.
**The content of documents is not stored.** Uploaded files are deleted
immediately unless the administrator turns on storage (then they are deleted
after 24 hours by default).

## 6. Before going live: test on local data

1. Collect at least 100 local examples: officer-written documents (`real/`)
   and documents produced with common AI tools (`ai/`). Include formal
   government text and Indian-English writing.
2. Run `python eval/evaluate.py <folder>` and read `eval/reports/report.md`.
3. If the false-positive rate on `real/` is too high, raise `THRESHOLD_AI`
   in `.env`. Text calibration can also be redone with `eval/calibrate_binoculars.py`.

## 7. Keeping it useful

* **Re-evaluate every 6 months.** AI generators improve quickly and detector
  accuracy decays.
* Replace or add models through `scripts/download_models.py` on an
  internet machine, then re-package and re-verify (see SDC_DEPLOYMENT.md).
* Keep the C2PA trust list (`C2PA_TRUST_ANCHORS_FILE`) up to date if used.

## Models used (all open licences that allow government use)

| Purpose | Model | Licence |
|---|---|---|
| Image | haywoodsloan/ai-image-detector-deploy (SwinV2) | Apache-2.0 |
| Image | Ateeqq/ai-vs-human-image-detector (SigLIP) | Apache-2.0 |
| Text | Binoculars method with Qwen/Qwen2.5-1.5B + Qwen2.5-1.5B-Instruct | Apache-2.0 |
| Text | desklib/ai-text-detector-v1.01 (DeBERTa-v3) | MIT |
| Provenance | c2pa-python (Content Authenticity Initiative) | Apache-2.0 / MIT |

The exact model versions (commit hashes) and file checksums are in
`models/MANIFEST.json`. Each check records the versions in the audit log.
