from app.pipeline.extract import extract_document


def test_pdf_text_and_image(sample):
    doc = extract_document("pdf", sample("sample.pdf"))
    assert "mackerel" in doc.text and "Artificial intelligence" in doc.text
    assert len(doc.images) == 1


def test_docx_text_image_meta(sample):
    doc = extract_document("docx", sample("sample.docx"))
    assert "Field report" in doc.text and "mackerel" in doc.text
    assert len(doc.images) == 1
    assert isinstance(doc.metadata, dict)


def test_txt_and_truncation(sample):
    doc = extract_document("txt", sample("human.txt"), max_chars=50)
    assert len(doc.text) == 50 and doc.notes


def test_max_images_respected(sample):
    assert extract_document("pdf", sample("sample.pdf"), max_images=0).images == []
