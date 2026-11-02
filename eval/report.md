# Accuracy report

Sources sampled: 40 photos (seed 7). Edited copies of the first photo are in the work folder for eyeballing.

## Part A: duplicate detection

Source photos: **40** (pipeline treated 22 as *photo*, 18 as *document*). Thresholds: same photo <= 10/64, similar <= 16/64.

> 18 real photos were classed as *document* by the layout heuristic, so only exact copies of them can ever be matched. These rows are scored separately below.

### Recall per edit (photo-class sources)

| Edit | Caught high | Caught review | Missed | Median bit-distance | Wrong match |
|---|---:|---:|---:|---:|---:|
| re-save jpeg q92 | 100% | 0% | 0% | 0.0 | 12 |
| jpeg q70 | 100% | 0% | 0% | 0.0 | 12 |
| jpeg q40 | 95% | 0% | 5% | 0 | 12 |
| jpeg q20 | 95% | 0% | 5% | 0 | 12 |
| png copy | 100% | 0% | 0% | 0.0 | 12 |
| webp q75 | 100% | 0% | 0% | 0.0 | 12 |
| resize 75% | 100% | 0% | 0% | 0.0 | 12 |
| resize 50% | 100% | 0% | 0% | 0.0 | 12 |
| resize 25% | 100% | 0% | 0% | 0.0 | 12 |
| WhatsApp (1600px q70) | 95% | 0% | 5% | 0 | 12 |
| WhatsApp heavy (1024px q55) | 95% | 0% | 5% | 0 | 12 |
| brightness +30% | 50% | 5% | 45% | 4.0 | 3 |
| brightness -30% | 100% | 0% | 0% | 0.0 | 12 |
| contrast +40% | 95% | 0% | 5% | 2 | 12 |
| greyscale | 100% | 0% | 0% | 0.0 | 12 |
| saturation +60% | 95% | 5% | 0% | 0.0 | 12 |
| warm tint | 86% | 0% | 14% | 2 | 10 |
| gamma 0.6 | 86% | 0% | 14% | 4 | 10 |
| blur r2 | 100% | 0% | 0% | 0.0 | 12 |
| blur r5 | 100% | 0% | 0% | 0.0 | 12 |
| sharpen x2 | 100% | 0% | 0% | 0.0 | 12 |
| noise s10 | 95% | 0% | 5% | 0 | 12 |
| noise s25 | 95% | 0% | 5% | 0 | 12 |
| crop centre 98% | 95% | 0% | 5% | 2 | 12 |
| crop centre 95% | 82% | 9% | 9% | 5.0 | 10 |
| crop centre 90% | 41% | 36% | 23% | 12 | 8 |
| crop centre 80% | 5% | 14% | 82% | 22 | 1 |
| crop centre 70% | 0% | 5% | 95% | 26 | 0 |
| crop centre 50% | 0% | 5% | 95% | 27.0 | 1 |
| crop top-left 85% | 0% | 14% | 86% | 22 | 2 |
| crop bottom-right 85% | 0% | 9% | 91% | 28 | 3 |
| crop to 16:9 | 59% | 0% | 41% | 0.0 | 10 |
| crop to square | 0% | 18% | 82% | 20 | 2 |
| white border 5% | 0% | 36% | 64% | 18 | 2 |
| black border 10% | 9% | 9% | 82% | 22 | 1 |
| phone screenshot of photo | 5% | 27% | 68% | 20.0 | 4 |
| caption bar bottom | 45% | 9% | 45% | 7.0 | 3 |
| sticker 10% area | 64% | 18% | 18% | 8 | 11 |
| repeating watermark | 100% | 0% | 0% | 0.0 | 12 |
| rotate 5 deg | 9% | 18% | 73% | 16.0 | 1 |
| rotate 15 deg | 0% | 9% | 91% | 28 | 0 |
| rotate 90 deg | 0% | 0% | 100% | 32.0 | 0 |
| rotate 180 deg | 0% | 0% | 100% | 32.0 | 0 |
| mirror left-right | 0% | 0% | 100% | 32.0 | 1 |
| mirror top-bottom | 0% | 0% | 100% | 32.0 | 0 |
| WhatsApp + crop 90% | 41% | 36% | 23% | 12 | 8 |
| crop 90% + bright + q60 | 23% | 27% | 50% | 12.0 | 4 |
| resize 50% + caption + q60 | 45% | 9% | 45% | 8.0 | 3 |
| print + re-scan | 32% | 23% | 45% | 8.0 | 2 |

### Recall by category

| Category | Flagged (high+review) | High only | Missed |
|---|---:|---:|---:|
| recompress | 98% | 98% | 2% |
| resize | 100% | 100% | 0% |
| messenger | 95% | 95% | 5% |
| colour | 89% | 88% | 11% |
| filter | 98% | 98% | 2% |
| crop | 39% | 28% | 61% |
| frame | 29% | 5% | 71% |
| overlay | 79% | 70% | 21% |
| geometry | 6% | 2% | 94% |
| combo | 59% | 35% | 41% |
| **all edits** | **65%** | **58%** | **35%** |

Doc-class sources (heuristic called them documents): {'miss': 882}

### False positives (unrelated photos)

* Original vs original pairs: **231**. Closest pair: **12**/64, median **30**/64.
* Pairs <= 10 (would be 'same photo'): **0**; <= 16 (would be 'similar'): **12**.
* Edited copy vs a *different* original: **20475** comparisons, <= 10: **13** (0.063%), <= 16: **675** (3.297%).

### Threshold sweep

Recall = share of edited copies (all edits except rotate/mirror/re-scan) within the distance of their own original. False-positive rate = share of edited-copy-vs-different-photo pairs within it.

| Distance <= | Recall | False-positive rate |
|---:|---:|---:|
| 4 | 65.6% | 0.000% |
| 6 | 68.2% | 0.000% |
| 8 | 70.7% | 0.000% |
| 10 | 73.2% | 0.063% |
| 12 | 76.2% | 1.035% |
| 14 | 78.4% | 2.349% |
| 16 | 80.8% | 3.297% |
| 18 | 83.4% | 3.922% |
| 20 | 86.6% | 5.153% |
| 24 | 92.8% | 14.940% |

## Part B: AI-influence metadata

### B1. Real, non-AI files from this machine (should all be `none`)

40 files -> {'none': 40}; flag codes seen: {'(no flags)': 39, 'EDITING_SOFTWARE': 1}

### B2. Injected tags (images are real photos; tag added)

| Case | n | Detected as expected | Levels | Missed |
|---|---:|---:|---|---|
| EXIF Software = AI tool | 18 | 15/18 (83%) | {'review': 15, 'none': 3} | DALL·E 2, Imagen 3, Runway ML |
| EXIF Artist = AI tool | 18 | 15/18 (83%) | {'review': 15, 'none': 3} | DALL·E 2, Imagen 3, Runway ML |
| EXIF ImageDescription 'made with X' | 18 | 15/18 (83%) | {'review': 15, 'none': 3} | DALL·E 2, Imagen 3, Runway ML |
| XMP CreatorTool = AI tool | 18 | 16/18 (89%) | {'review': 16, 'none': 2} | Imagen 3, Runway ML |
| XMP DigitalSourceType trainedAlgorithmicMedia | 2 | 2/2 (100%) | {'review': 2} | - |
| PNG text (SD / Comfy / Invoke keys) | 6 | 6/6 (100%) | {'review': 6} | - |
| Editing software only (expect `none`, info note) | 8 | 8/8 (100%) | {'none': 8} | - |

### B3. Does the AI tag survive edits? (EXIF `Software = Midjourney`)

`strip` = the editing app drops metadata (Pillow default, WhatsApp, screenshots). `keep` = the app copies EXIF across.

| Edit | Detected if metadata stripped | Detected if metadata kept |
|---|---|---|
| none (straight from tool) | none | review |
| re-save jpeg q70 | none | review |
| resize 50% | none | review |
| crop 90% | none | review |
| brightness +30% | none | review |
| WhatsApp (1600px q70) | none | review |
| phone screenshot (PNG) | none | n/a (screenshots carry no EXIF) |

### B4. Signed C2PA credential (test-signed sample)

| Case | Result | Flags |
|---|---|---|
| file straight from the AI tool | high | AI_CREDENTIAL |
| renamed .png (content is jpeg) | high | AI_CREDENTIAL |
| re-saved with Pillow (drops credential) | none | - |
| resized 50% | none | - |
| WhatsApp style (1600px q70) | none | - |
| converted to PNG | none | - |
| phone screenshot | none | - |
| one pixel-data byte flipped after signing (tamper) | review | AI_CREDENTIAL_BROKEN |
| manifest cut off (truncated file) | rejected | - |

### B5. PDF and DOCX metadata

| Case | Result | Flags |
|---|---|---|
| PDF Producer = Adobe Firefly | review | AI_METADATA |
| PDF Producer = ChatGPT | review | AI_METADATA |
| PDF Producer = Microsoft Word | none | - |
| PDF Producer = Canva | none | EDITING_SOFTWARE |
| PDF Producer = iLovePDF | none | EDITING_SOFTWARE |
| DOCX creator = ChatGPT | review | AI_METADATA |
| DOCX creator = John Smith | none | - |

### B6. Real AI images

**Not tested.** No genuine ChatGPT / Gemini / Firefly / Midjourney files were available. Re-run with `--ai-dir <folder of real AI images>`.

## Part C: false-positive probes (innocent metadata that contains an AI-marker word)

| Metadata text | Result | Why it is innocent |
|---|---|---|
| Artist = Gemini Photo Studio | review | a business name |
| Artist = Dalle Nogare | review | a surname |
| Artist = Rajesh Dallesandro | review | a surname containing 'dalle' |
| ImageDescription = Visit to the OpenAI office, Mumbai | review | a caption about a place |
| ImageDescription = Photo of the Gemini constellation | review | astronomy |
| ImageDescription = ideogram of Chinese character 'tree' | review | linguistics |
| ImageDescription = Flooded road near Fooocus Hotel | review | contrived name |
| Software = Samsung SM-S918B | none | phone firmware |
| Software = Google Pixel 8 Pro | none | phone firmware |
| Software = Windows Photo Editor 10 | none | OS viewer |
| Software = Microsoft Photos | none | OS viewer |
| Software = Adobe Lightroom Mobile | none | plain edit, not AI |
| PNG text key `prompt` = 'Please enter your name' | review | generic key used by non-AI tools |
| PNG Description = 'Screenshot taken with Snipping Tool' | none | screenshot tool |
