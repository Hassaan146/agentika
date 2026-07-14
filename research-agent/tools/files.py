"""File-read plugin: .txt and .pdf, hardened.

- Path is resolved and must stay inside docs/ (blocks ../ traversal and
  absolute paths).
- Extension allowlist, size cap, output truncation.
- PDF parse failures come back as readable ToolResult errors.
"""

from pypdf import PdfReader

from config import settings
from models import ReadFileInput, ToolResult

ALLOWED_EXTENSIONS = {".txt", ".pdf"}


def read_file(args: ReadFileInput) -> ToolResult:
    docs = settings.docs_dir.resolve()
    target = (docs / args.path).resolve()

    if not target.is_relative_to(docs):
        return ToolResult(ok=False, error=f"Access denied: '{args.path}' is outside the docs/ folder")

    if target.suffix.lower() not in ALLOWED_EXTENSIONS:
        return ToolResult(
            ok=False, error=f"Unsupported file type '{target.suffix}' - only .txt and .pdf are allowed"
        )

    if not target.is_file():
        available = (
            sorted(f.name for f in docs.iterdir() if f.suffix.lower() in ALLOWED_EXTENSIONS)
            if docs.is_dir()
            else []
        )
        return ToolResult(ok=False, error=f"File '{args.path}' not found. Available files: {available}")

    size_mb = target.stat().st_size / (1024 * 1024)
    if size_mb > settings.file_max_mb:
        return ToolResult(
            ok=False, error=f"File is {size_mb:.1f} MB, over the {settings.file_max_mb} MB limit"
        )

    if target.suffix.lower() == ".pdf":
        try:
            reader = PdfReader(target)
            text = "\n".join(page.extract_text() or "" for page in reader.pages).strip()
        except Exception as exc:
            return ToolResult(ok=False, error=f"Could not parse PDF '{args.path}': {exc}")
        if not text:
            return ToolResult(ok=False, error=f"PDF '{args.path}' contains no extractable text")
    else:
        text = target.read_text(encoding="utf-8", errors="replace")

    if len(text) > settings.file_max_chars:
        text = text[: settings.file_max_chars] + "\n[truncated]"

    return ToolResult(ok=True, data={"path": args.path, "content": text})
