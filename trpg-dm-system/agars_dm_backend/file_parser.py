from __future__ import annotations

import re
from pathlib import Path


SUPPORTED_EXTENSIONS = {".txt", ".md", ".markdown", ".pdf"}
_SECTION_HEADING_RE = re.compile(
    r"^(?:#{1,6}\s+\S.*|第[零一二三四五六七八九十百千万\d]+[章节卷幕回篇部]\s*\S*|Chapter\s+\d+\b.*)$",
    flags=re.IGNORECASE,
)


def extract_text(file_path: str | Path) -> str:
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"file not found: {path}")

    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"unsupported file type: {suffix}")

    if suffix == ".pdf":
        try:
            import fitz
        except ImportError as exc:
            raise RuntimeError("PyMuPDF is required to ingest PDF files") from exc
        text_parts: list[str] = []
        with fitz.open(path) as doc:
            for page in doc:
                text = page.get_text().strip()
                if text:
                    text_parts.append(text)
        return "\n\n".join(text_parts)

    raw = path.read_bytes()
    for encoding in ("utf-8", "utf-8-sig", "gb18030", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def split_snippets(text: str, *, target_size: int = 1800) -> list[str]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        return []

    sections = _split_by_headings(normalized)
    if len(sections) <= 1:
        sections = _split_by_paragraphs(normalized, target_size=target_size)

    return _normalize_sections(sections, target_size=target_size)


def _split_by_headings(text: str) -> list[str]:
    lines = text.split("\n")
    sections: list[str] = []
    current: list[str] = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            current.append("")
            continue
        if _SECTION_HEADING_RE.match(stripped) and current:
            section = "\n".join(current).strip()
            if section:
                sections.append(section)
            current = [stripped]
            continue
        current.append(stripped)

    if current:
        section = "\n".join(current).strip()
        if section:
            sections.append(section)
    return sections


def _split_by_paragraphs(text: str, *, target_size: int) -> list[str]:
    paragraphs = [item.strip() for item in re.split(r"\n{2,}", text) if item.strip()]
    if not paragraphs:
        return [text]

    sections: list[str] = []
    current: list[str] = []
    current_len = 0
    for paragraph in paragraphs:
        projected = current_len + len(paragraph)
        if current and projected > target_size:
            sections.append("\n\n".join(current))
            current = [paragraph]
            current_len = len(paragraph)
            continue
        current.append(paragraph)
        current_len = projected

    if current:
        sections.append("\n\n".join(current))
    return sections


def _normalize_sections(sections: list[str], *, target_size: int) -> list[str]:
    normalized: list[str] = []
    for section in sections:
        stripped = section.strip()
        if not stripped:
            continue
        if len(stripped) > target_size * 2:
            normalized.extend(_split_by_paragraphs(stripped, target_size=target_size))
            continue
        normalized.append(stripped)

    return normalized
