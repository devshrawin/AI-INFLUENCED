# Accuracy report

Sources sampled: 40 photos (seed 7). Edited copies of the first photo are in the work folder for eyeballing.

## Part A: duplicate detection

Source photos: **40** (pipeline treated 25 as *photo*, 15 as *document*). Thresholds: same photo <= 10/64, similar <= 16/64.

> 15 real photos were classed as *document* by the layout heuristic, so only exact copies of them can ever be matched. These rows are scored separately below.

### Recall per edit (photo-class sources)

| Edit | Caught high | Caught review | Missed | Median bit-distance | Wrong match |
|---|---:|---:|---:|---:|---:|
| re-save jpeg q92 | 100% | 0% | 0% | 0.0 | 13 |
| jpeg q70 | 100% | 0% | 0% | 0.0 | 13 |
| jpeg q40 | 100% | 0% | 0% | 0.0 | 13 |
| jpeg q20 | 100% | 0% | 0% | 0.0 | 13 |
| png copy | 100% | 0% | 0% | 0.0 | 14 |
| webp q75 | 100% | 0% | 0% | 0.0 | 13 |
| resize 75% | 100% | 0% | 0% | 0.0 | 13 |
| resize 50% | 100% | 0% | 0% | 0.0 | 13 |
| resize 25% | 100% | 0% | 0% | 0.0 | 13 |
| WhatsApp (1600px q70) | 100% | 0% | 0% | 0.0 | 13 |
| WhatsApp heavy (1024px q55) | 100% | 0% | 0% | 0.0 | 13 |
| brightness +30% | 76% | 24% | 0% | 6.0 | 10 |
| brightness -30% | 100% | 0% | 0% | 0.0 | 14 |
| contrast +40% | 100% | 0% | 0% | 2.0 | 13 |
| greyscale | 100% | 0% | 0% | 0.0 | 13 |
| saturation +60% | 96% | 4% | 0% | 0.0 | 13 |
| warm tint | 100% | 0% | 0% | 2.0 | 12 |
| gamma 0.6 | 100% | 0% | 0% | 2.0 | 12 |
| blur r2 | 100% | 0% | 0% | 0.0 | 13 |
| blur r5 | 100% | 0% | 0% | 0.0 | 14 |
| sharpen x2 | 100% | 0% | 0% | 0.0 | 13 |
| noise s10 | 100% | 0% | 0% | 0.0 | 13 |
| noise s25 | 100% | 0% | 0% | 2.0 | 13 |
| crop centre 98% | 100% | 0% | 0% | 2.0 | 12 |
| crop centre 95% | 92% | 8% | 0% | 6.0 | 11 |
| crop centre 90% | 44% | 48% | 8% | 12.0 | 10 |
| crop centre 80% | 4% | 16% | 80% | 22.0 | 1 |
| crop centre 70% | 0% | 4% | 96% | 28.0 | 1 |
| crop centre 50% | 0% | 4% | 96% | 30.0 | 1 |
| crop top-left 85% | 0% | 12% | 88% | 24.0 | 3 |
| crop bottom-right 85% | 0% | 8% | 92% | 28.0 | 3 |
| crop to 16:9 | 56% | 0% | 44% | 2.0 | 10 |
| crop to square | 8% | 16% | 76% | 21.0 | 2 |
| white border 5% | 8% | 36% | 56% | 16.0 | 2 |
| black border 10% | 8% | 8% | 84% | 24.0 | 2 |
| phone screenshot of photo | 4% | 24% | 72% | 22.0 | 4 |
| caption bar bottom | 80% | 20% | 0% | 8.0 | 5 |
| sticker 10% area | 64% | 20% | 16% | 10.0 | 11 |
| repeating watermark | 100% | 0% | 0% | 0.0 | 13 |
| rotate 5 deg | 8% | 36% | 56% | 18.0 | 3 |
| rotate 15 deg | 0% | 8% | 92% | 29.0 | 0 |
| rotate 90 deg | 0% | 0% | 100% | 30.0 | 1 |
| rotate 180 deg | 0% | 0% | 100% | 32.0 | 0 |
| mirror left-right | 0% | 0% | 100% | 32.0 | 1 |
| mirror top-bottom | 0% | 0% | 100% | 32.0 | 0 |
| WhatsApp + crop 90% | 44% | 48% | 8% | 12.0 | 10 |
| crop 90% + bright + q60 | 32% | 48% | 20% | 14.0 | 8 |
| resize 50% + caption + q60 | 80% | 20% | 0% | 8.0 | 6 |
| print + re-scan | 52% | 48% | 0% | 12.0 | 5 |

### Recall by category

| Category | Flagged (high+review) | High only | Missed |
|---|---:|---:|---:|
| recompress | 100% | 100% | 0% |
| resize | 100% | 100% | 0% |
| messenger | 100% | 100% | 0% |
| colour | 100% | 96% | 0% |
| filter | 100% | 100% | 0% |
| crop | 42% | 30% | 58% |
| frame | 29% | 7% | 71% |
| overlay | 95% | 81% | 5% |
| geometry | 9% | 1% | 91% |
| combo | 93% | 52% | 7% |
| **all edits** | **72%** | **62%** | **28%** |

Doc-class sources (heuristic called them documents): {'miss': 735}

### False positives (unrelated photos)

* Original vs original pairs: **780**. Closest pair: **12**/64, median **30.0**/64.
* Pairs <= 10 (would be 'same photo'): **0**; <= 16 (would be 'similar'): **14**.
* Edited copy vs a *different* original: **76440** comparisons, <= 10: **16** (0.021%), <= 16: **803** (1.050%).

### Threshold sweep

Recall = share of edited copies (all edits except rotate/mirror/re-scan) within the distance of their own original. False-positive rate = share of edited-copy-vs-different-photo pairs within it.

| Distance <= | Recall | False-positive rate |
|---:|---:|---:|
| 4 | 60.5% | 0.000% |
| 6 | 64.7% | 0.000% |
| 8 | 67.7% | 0.001% |
| 10 | 71.0% | 0.021% |
| 12 | 74.3% | 0.288% |
| 14 | 76.9% | 0.657% |
| 16 | 79.5% | 1.050% |
| 18 | 81.6% | 1.486% |
| 20 | 84.4% | 2.318% |
| 24 | 90.2% | 9.243% |

## Part B: AI-influence metadata

### B1. Real, non-AI files from this machine (should all be `none`)

40 files -> {'none': 40}; flag codes seen: {'(no flags)': 39, 'EDITING_SOFTWARE': 1}

### B2. Injected tags (images are real photos; tag added)

| Case | n | Detected as expected | Levels | Missed |
|---|---:|---:|---|---|
| EXIF Software = AI tool | 18 | 18/18 (100%) | {'review': 18} | - |
| EXIF Artist = AI tool | 18 | 14/18 (78%) | {'review': 14, 'none': 4} | Google Gemini, ChatGPT, Ideogram, Imagen 3 |
| EXIF ImageDescription 'made with X' | 18 | 18/18 (100%) | {'review': 18} | - |
| XMP CreatorTool = AI tool | 18 | 18/18 (100%) | {'review': 18} | - |
| XMP DigitalSourceType trainedAlgorithmicMedia | 2 | 2/2 (100%) | {'review': 2} | - |
| PNG text (SD / Comfy / Invoke keys) | 6 | 5/6 (83%) | {'review': 5, 'none': 1} | PNG workflow |
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
| DOCX creator = ChatGPT | none | - |
| DOCX creator = John Smith | none | - |

### B6. Real AI images

**Not tested.** No genuine ChatGPT / Gemini / Firefly / Midjourney files were available. Re-run with `--ai-dir <folder of real AI images>`.

## Part C: false-positive probes (innocent metadata that contains an AI-marker word)

| Metadata text | Result | Why it is innocent |
|---|---|---|
| Artist = Gemini Photo Studio | none | a business name |
| Artist = Dalle Nogare | none | a surname |
| Artist = Rajesh Dallesandro | none | a surname containing 'dalle' |
| ImageDescription = Visit to the OpenAI office, Mumbai | none | a caption about a place |
| ImageDescription = Photo of the Gemini constellation | none | astronomy |
| ImageDescription = ideogram of Chinese character 'tree' | none | linguistics |
| ImageDescription = Flooded road near Fooocus Hotel | review | contrived name |
| Software = Samsung SM-S918B | none | phone firmware |
| Software = Google Pixel 8 Pro | none | phone firmware |
| Software = Windows Photo Editor 10 | none | OS viewer |
| Software = Microsoft Photos | none | OS viewer |
| Software = Adobe Lightroom Mobile | none | plain edit, not AI |
| PNG text key `prompt` = 'Please enter your name' | none | generic key used by non-AI tools |
| PNG Description = 'Screenshot taken with Snipping Tool' | none | screenshot tool |
