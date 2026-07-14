from config import settings
from models import ReadFileInput
from tools.files import read_file


def setup_docs(tmp_path, monkeypatch):
    docs = tmp_path / "docs"
    docs.mkdir()
    monkeypatch.setattr(settings, "docs_dir", docs)
    return docs


def test_reads_txt(tmp_path, monkeypatch):
    docs = setup_docs(tmp_path, monkeypatch)
    (docs / "note.txt").write_text("hello world", encoding="utf-8")
    result = read_file(ReadFileInput(path="note.txt"))
    assert result.ok and result.data["content"] == "hello world"


def test_blocks_path_traversal(tmp_path, monkeypatch):
    setup_docs(tmp_path, monkeypatch)
    (tmp_path / "secret.txt").write_text("secret", encoding="utf-8")
    result = read_file(ReadFileInput(path="../secret.txt"))
    assert not result.ok and "outside the docs/ folder" in result.error


def test_blocks_absolute_path(tmp_path, monkeypatch):
    setup_docs(tmp_path, monkeypatch)
    outside = tmp_path / "outside.txt"
    outside.write_text("x", encoding="utf-8")
    result = read_file(ReadFileInput(path=str(outside)))
    assert not result.ok and "outside the docs/ folder" in result.error


def test_rejects_unsupported_extension(tmp_path, monkeypatch):
    docs = setup_docs(tmp_path, monkeypatch)
    (docs / "app.exe").write_bytes(b"MZ")
    result = read_file(ReadFileInput(path="app.exe"))
    assert not result.ok and "only .txt and .pdf" in result.error


def test_missing_file_lists_available(tmp_path, monkeypatch):
    docs = setup_docs(tmp_path, monkeypatch)
    (docs / "real.txt").write_text("x", encoding="utf-8")
    result = read_file(ReadFileInput(path="ghost.txt"))
    assert not result.ok and "real.txt" in result.error


def test_size_cap(tmp_path, monkeypatch):
    docs = setup_docs(tmp_path, monkeypatch)
    monkeypatch.setattr(settings, "file_max_mb", 0.0001)  # ~100 bytes
    (docs / "big.txt").write_text("x" * 1000, encoding="utf-8")
    result = read_file(ReadFileInput(path="big.txt"))
    assert not result.ok and "over the" in result.error


def test_truncation(tmp_path, monkeypatch):
    docs = setup_docs(tmp_path, monkeypatch)
    monkeypatch.setattr(settings, "file_max_chars", 50)
    (docs / "long.txt").write_text("a" * 200, encoding="utf-8")
    result = read_file(ReadFileInput(path="long.txt"))
    assert result.ok and result.data["content"].endswith("[truncated]")
    assert len(result.data["content"]) < 100


def test_corrupt_pdf_readable_error(tmp_path, monkeypatch):
    docs = setup_docs(tmp_path, monkeypatch)
    (docs / "bad.pdf").write_bytes(b"this is not a pdf")
    result = read_file(ReadFileInput(path="bad.pdf"))
    assert not result.ok
    assert "bad.pdf" in result.error
