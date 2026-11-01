"""Builds small sample files used by the tests (run once; outputs are committed).

python tests/make_samples.py
"""

from pathlib import Path

from docx import Document
from PIL import Image, ImageDraw
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

OUT = Path(__file__).parent / "samples"

HUMAN_TEXT = (
    "Went to the market on Tuesday with my uncle. The fish seller near the bus stand had run out of "
    "sardines by nine, so we bought mackerel instead, which my aunt grumbled about all evening. "
    "Rain started around four. The roof over the back verandah still leaks in the same corner it "
    "always has, and nobody has called the carpenter even though we said we would after Onam. "
    "Tomorrow I need to renew the bike insurance before the office closes at five."
)
AI_TEXT = (
    "Artificial intelligence is transforming the way governments deliver public services. By "
    "leveraging advanced machine learning algorithms, agencies can streamline processes, enhance "
    "decision-making, and improve citizen engagement. Furthermore, AI-driven solutions enable "
    "data-driven insights that foster transparency and accountability. However, it is important "
    "to address challenges such as data privacy, algorithmic bias, and the need for robust "
    "governance frameworks. In conclusion, a balanced approach that combines innovation with "
    "ethical considerations will be essential for maximizing the benefits of AI in the public sector."
)


def make_image(path: Path, fmt: str) -> None:
    img = Image.new("RGB", (256, 256), (200, 220, 240))
    d = ImageDraw.Draw(img)
    d.rectangle((40, 40, 200, 200), outline=(20, 40, 90), width=6)
    d.ellipse((90, 90, 160, 160), fill=(240, 120, 60))
    img.save(path, fmt)


def make_photo(path: Path, seed: int) -> None:
    """A busy, colourful 'photo' (stands in for e.g. a flood-damage picture)."""
    import random

    r = random.Random(seed)
    img = Image.new("RGB", (1024, 768), (r.randint(0, 120),) * 3)
    d = ImageDraw.Draw(img)
    for _ in range(80):
        x, y = r.randint(-100, 1000), r.randint(-100, 740)
        colour = tuple(r.randint(0, 255) for _ in range(3))
        d.ellipse((x, y, x + r.randint(30, 400), y + r.randint(30, 300)), fill=colour)
    img.save(path, "JPEG", quality=90)


def make_marksheet(path: Path, name: str, marks: list[int]) -> None:
    """A simple marksheet-like document image: same layout, different contents."""
    img = Image.new("RGB", (1240, 1754), "white")
    d = ImageDraw.Draw(img)
    d.rectangle((40, 40, 1200, 1714), outline="black", width=4)
    d.text((380, 90), "BOARD OF HIGHER SECONDARY EXAMINATIONS", fill="black")
    d.text((480, 140), "STATEMENT OF MARKS 2026", fill="black")
    d.text((80, 240), f"Name: {name}", fill="black")
    y = 380
    for subject, mark in zip(
        ["English", "Malayalam", "Physics", "Chemistry", "Mathematics", "Biology"], marks, strict=True
    ):
        d.rectangle((80, y, 1160, y + 70), outline="black", width=2)
        d.text((100, y + 25), subject, fill="black")
        d.text((900, y + 25), str(mark), fill="black")
        y += 70
    d.text((700, y + 40), f"TOTAL: {sum(marks)}", fill="black")
    img.save(path, "PNG")


def main() -> None:
    OUT.mkdir(exist_ok=True)
    make_image(OUT / "sample.png", "PNG")
    make_image(OUT / "sample.jpg", "JPEG")
    make_image(OUT / "sample.webp", "WEBP")
    make_photo(OUT / "photo1.jpg", seed=1)
    make_photo(OUT / "photo2.jpg", seed=2)
    make_marksheet(OUT / "marksheet1.png", "Anu Joseph", [78, 85, 62, 70, 91, 66])
    make_marksheet(OUT / "marksheet2.png", "Rahul K", [55, 60, 48, 52, 40, 58])

    doc = Document()
    doc.add_heading("Field report", level=1)
    doc.add_paragraph(HUMAN_TEXT)
    doc.add_paragraph(AI_TEXT)
    doc.add_picture(str(OUT / "sample.png"))
    doc.save(OUT / "sample.docx")

    c = canvas.Canvas(str(OUT / "sample.pdf"), pagesize=A4)
    y = 800
    for para in (HUMAN_TEXT, AI_TEXT):
        words, line = para.split(), ""
        for w in words:
            if len(line) + len(w) > 90:
                c.drawString(40, y, line)
                y, line = y - 14, ""
            line += w + " "
        c.drawString(40, y, line)
        y -= 28
    c.drawImage(str(OUT / "sample.png"), 40, 300, width=128, height=128)
    c.save()

    # A file that pretends to be an image but is an executable.
    (OUT / "fake.png").write_bytes(b"MZ\x90\x00" + b"\x00" * 200)
    print("samples written to", OUT)


if __name__ == "__main__":
    main()
