import io
from pathlib import Path

from PIL import Image
from PIL.PngImagePlugin import PngInfo

from app.pipeline.provenance import check_document_metadata, check_provenance
from app.pipeline.types import ProvenanceResult

TEST_CA = Path(__file__).parent / "fixtures_c2pa" / "ca.pem"


def test_plain_image_has_no_provenance(sample):
    res, _ = check_provenance(sample("sample.jpg"), "image/jpeg")
    assert not res.c2pa_present and not res.confirmed_ai and not res.ai_hints


def test_c2pa_ai_credential_is_confirmed(sample):
    res, _ = check_provenance(sample("c2pa_ai.jpg"), "image/jpeg")
    assert res.c2pa_present and res.c2pa_state == "Valid"
    assert res.ai_declared_type == "trainedAlgorithmicMedia"
    assert res.confirmed_ai
    assert not res.c2pa_trusted  # test CA is not on any trust list
    assert "TestDiffusion" in (res.generator or "")


def test_c2pa_trusted_with_local_trust_anchor(sample):
    res, _ = check_provenance(sample("c2pa_ai.jpg"), "image/jpeg", trust_anchors_file=TEST_CA)
    assert res.c2pa_state == "Trusted" and res.c2pa_trusted and res.confirmed_ai


def test_tampered_c2pa_is_not_confirmed(sample):
    data = bytearray(sample("c2pa_ai.jpg"))
    data[-200] ^= 0xFF  # flip bits inside the image data (after the manifest)
    res, _ = check_provenance(bytes(data), "image/jpeg")
    assert res.c2pa_present
    assert not res.confirmed_ai
    assert res.c2pa_state not in ("Valid", "Trusted")


def test_png_stable_diffusion_parameters_hint():
    info = PngInfo()
    info.add_text("parameters", "a cat, Steps: 20, Sampler: Euler a, Model: sdxl")
    buf = io.BytesIO()
    Image.new("RGB", (64, 64)).save(buf, "PNG", pnginfo=info)
    res, meta = check_provenance(buf.getvalue(), "image/png")
    assert any("parameters" in h for h in res.ai_hints)
    assert "PNG:parameters" in meta
    assert not res.confirmed_ai  # unsigned metadata never "confirms"


def test_exif_software_and_camera():
    img = Image.new("RGB", (64, 64))
    exif = img.getexif()
    exif[0x0131] = "Midjourney v6"  # Software
    exif[0x010F] = "Canon"  # Make
    buf = io.BytesIO()
    img.save(buf, "JPEG", exif=exif)
    res, _ = check_provenance(buf.getvalue(), "image/jpeg")
    assert any("midjourney" in h for h in res.ai_hints)
    assert res.camera_hints


def test_document_metadata_hint():
    res = ProvenanceResult()
    check_document_metadata({"Producer": "ChatGPT export"}, res)
    assert res.ai_hints


def test_editing_software_hint():
    img = Image.new("RGB", (64, 64))
    exif = img.getexif()
    exif[0x0131] = "Adobe Photoshop 25.1 (Windows)"
    buf = io.BytesIO()
    img.save(buf, "JPEG", exif=exif)
    res, _ = check_provenance(buf.getvalue(), "image/jpeg")
    assert any("photoshop" in h for h in res.edit_hints) and not res.ai_hints


def test_xmp_iptc_ai_source_type_hint():
    """Google/Meta tools write IPTC DigitalSourceType=trainedAlgorithmicMedia into XMP (unsigned)."""
    xmp = (b'<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
           b'<rdf:Description Iptc4xmpExt:DigitalSourceType="http://cv.iptc.org/newscodes/digitalsourcetype/'
           b'compositeWithTrainedAlgorithmicMedia"/></rdf:RDF></x:xmpmeta>')  # fmt: skip
    buf = io.BytesIO()
    Image.new("RGB", (64, 64)).save(buf, "JPEG", xmp=xmp)
    res, _ = check_provenance(buf.getvalue(), "image/jpeg")
    assert any("trainedalgorithmicmedia" in h for h in res.ai_hints)
