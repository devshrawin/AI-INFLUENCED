# What this tool can and cannot do

*A note for leadership and reviewing officers.*

## 1. The short version

The tool raises a flag in two situations:
1. **The file itself says it was made or edited with AI** (in its metadata).
2. **The same image was already uploaded by a different applicant.**

When the tool flags something, the evidence is usually solid. **When it does
not flag, that proves nothing.** Many AI-edited or copied files carry no
traces. A flag is a reason for an officer to look, never a decision on its own.

## 2. AI influence from metadata

| Evidence | How reliable | How often present |
|---|---|---|
| **Signed content credential (C2PA)** saying "made/edited with AI" | Very reliable: it is a digital signature; changing the file breaks it | Only when the file comes **straight** from tools that add it (ChatGPT/OpenAI images, Google Gemini, Adobe Firefly / Photoshop generative fill, Microsoft Designer…) |
| **AI tool named in plain metadata** (EXIF Software, XMP, PNG prompt text) | Medium: anyone can add or remove it | Midjourney, Stable Diffusion tools, some phone AI editors |
| **Editing software** (Photoshop, Canva, PicsArt…) | Only a note: most edits are innocent | Common |

**The metadata is lost when:**
* the image is **screenshotted**, or forwarded on **WhatsApp / Telegram / social media**
* the citizen **prints and re-scans** or **photographs** the AI-edited file
* the image is re-saved by many editing apps
* **the scheme platform itself resizes or compresses uploads** before checking them

So an AI-edited marksheet that was screenshotted before upload **will not be
flagged**. For marksheets, the only near-certain check is **verifying the
marks with the issuing board** (DigiLocker or the board's verification
service). This tool is a quick first filter, not a replacement for that.

**Can someone fake a flag?** Plain metadata, yes: someone could add
"Midjourney" to a genuine photo. That is why unsigned metadata only gives a
**review** flag. A signed credential cannot be forged without breaking its
signature.

## 3. Same image uploaded before

**Photos** (damage, house, crop):

| Situation | Result (measured on real photos, Nov 2026) |
|---|---|
| Exact same file | Always caught (high) |
| Same photo resized, re-compressed, brightened or forwarded on WhatsApp | Caught (high) |
| Same photo cropped by 2–5% | Usually caught (high or review) |
| Heavily cropped, rotated, mirrored, or with stickers / text added | Often missed |
| Different photo of the same scene (e.g. two neighbours photograph the same flooded road) | Usually not flagged; occasionally "very similar" (review). That may be legitimate |
| Unrelated photos | No false matches in testing (closest pair was well beyond the threshold) |

**Documents** (marksheets, certificates, scanned pages): different
students' marksheets with the same printed layout look identical to a
visual fingerprint. So documents are only matched as **exact** files. The
same marksheet file re-uploaded is caught, but a re-scan or a photo of the
same marksheet is **not**.

**Same applicant**: a citizen re-uploading their own photo in a new
application is never flagged.

**Not covered**: photos copied from the internet that nobody else has
uploaded, old photos re-used by the same person, and photos taken at a
different place or time than claimed.

## 4. How to keep false flags low
* `high` is used only for strong evidence: a signed credential, an identical
  file, or a near-identical photo from a different applicant.
* Thresholds can be adjusted in `.env` (`SAME_PHOTO_MAX_DISTANCE`,
  `SIMILAR_PHOTO_MAX_DISTANCE`).
* Every flag lists its evidence (e.g. the matching application numbers) so
  the officer can open both applications and compare.

**Rule for officers:** a flag means *look at this*. Compare the matching
applications, or ask the citizen for the original. Never reject on the flag alone.

## 5. What is recorded
For every check: who checked (officer or platform API key), when,
application and applicant ID, the file's SHA-256 fingerprint, the photo
fingerprint, and the flags. **File contents are not stored.** Uploaded files
are discarded after the check unless storage is switched on.

## 6. Ideas to strengthen it later
* **Capture photos inside the platform's mobile app** (camera only, not
  gallery). The app then records time and GPS itself, which also catches old
  photos and photos from other places.
* **Verify marksheets with the board / DigiLocker** instead of trusting uploads.
* Bring back the **AI image detector models** (kept on branch
  `archive/full-ml-detector`) as an extra, weaker signal.
