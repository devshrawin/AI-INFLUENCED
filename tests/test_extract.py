from app.pipeline.extract import extract_document


def test_pdf_images_and_meta(sample):
    doc = extract_document("pdf", sample("sample.pdf"))
    assert len(doc.images) == 1
    assert isinstance(doc.metadata, dict)


def test_docx_images_and_meta(sample):
    doc = extract_document("docx", sample("sample.docx"))
    assert len(doc.images) == 1
    assert "creator" in doc.metadata or "Application" in doc.metadata


def test_max_images_respected(sample):
    assert extract_document("pdf", sample("sample.pdf"), max_images=0).images == []
