from app.pipeline.chunking import chunk_text
from app.pipeline.language import detect_language


def test_english(sample):
    res = detect_language(sample("ai.txt").decode())
    assert res.is_english and res.warning is None


def test_malayalam_warns(sample):
    res = detect_language(sample("malayalam.txt").decode())
    assert not res.is_english and res.name == "Malayalam"
    assert "NOT reliable" in res.warning


def test_hindi_warns():
    res = detect_language("भारत एक विशाल देश है। यहाँ अनेक भाषाएँ बोली जाती हैं और लोग विभिन्न त्योहार मनाते हैं।")
    assert not res.is_english and "Devanagari" in res.name


def test_french_warns():
    res = detect_language(
        "Le gouvernement a annoncé de nouvelles mesures pour soutenir les agriculteurs de la région."
    )
    assert not res.is_english and res.warning


def test_empty_text():
    assert not detect_language("1234 ... !!").is_english


def test_chunking_respects_limits():
    text = " ".join(f"Sentence number {i} is here." for i in range(400))  # 2000 words
    chunks = chunk_text(text, max_words=300, max_chunks=50)
    assert all(c.word_count <= 300 for c in chunks)
    assert sum(c.word_count for c in chunks) == 2000
    assert [c.index for c in chunks] == list(range(len(chunks)))


def test_chunking_merges_short_tail_and_caps_count():
    text = ("word " * 100 + ". ") * 3 + "tiny tail."
    chunks = chunk_text(text, max_words=100, min_words=40)
    assert chunks[-1].text.endswith("tiny tail.")
    assert len(chunk_text("a b c. " * 2000, max_words=10, max_chunks=5)) == 5


def test_chunking_splits_unpunctuated_text():
    chunks = chunk_text("word " * 1000, max_words=384)
    assert len(chunks) == 3 and chunks[0].word_count == 384


def test_chunk_start_offsets():
    text = "First para one. First para two.\nSecond para here."
    chunks = chunk_text(text, max_words=4, min_words=1)
    for c in chunks:
        assert text[c.start_char :].startswith(c.text.split(".")[0])
