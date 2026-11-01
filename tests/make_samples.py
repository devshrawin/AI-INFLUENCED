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


def main() -> None:
    OUT.mkdir(exist_ok=True)
    make_image(OUT / "sample.png", "PNG")
    make_image(OUT / "sample.jpg", "JPEG")
    make_image(OUT / "sample.webp", "WEBP")
    (OUT / "human.txt").write_text(HUMAN_TEXT, encoding="utf-8")
    (OUT / "ai.txt").write_text(AI_TEXT, encoding="utf-8")
    (OUT / "malayalam.txt").write_text(
        "കേരളം ഇന്ത്യയുടെ തെക്കുപടിഞ്ഞാറൻ തീരത്തുള്ള ഒരു സംസ്ഥാനമാണ്. ഇവിടെ മലയാളമാണ് പ്രധാന ഭാഷ. "
        "സംസ്ഥാനത്തിന്റെ തലസ്ഥാനം തിരുവനന്തപുരം ആണ്. കേരളം പ്രകൃതി സൗന്ദര്യത്തിന് പ്രശസ്തമാണ്.",
        encoding="utf-8",
    )

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
