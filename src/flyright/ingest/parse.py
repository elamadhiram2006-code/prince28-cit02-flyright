"""Turn one raw file into clean, structured pages."""

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf
import trafilatura
from pypdf import PdfReader

TEXT_TYPES = {".md", ".mdx", ".markdown", ".txt", ".rst", ".adoc", ".sgml", ".py"}
DATA_TYPES = {".json", ".yaml", ".yml", ".csv", ".xml"}

PAGE_CHARS = 3000
MIN_CHARS_PER_PAGE = 50

HEADING = re.compile(r"^(#{1,6}) +(.+?)\s*$")
FENCE = re.compile(r"^\s*(```|~~~)")
ANCHOR = re.compile(r"\s*\{\s*[#.]?[^}]+\}\s*$")

RST_MARKS = {"=": 1, "-": 2, "~": 3, "^": 3, '"': 3}


@dataclass
class ParsedPage:
    page_no: int
    text: str
    headings: list[str] = field(default_factory=list)
    tables: int = 0


@dataclass
class ParsedDoc:
    parser: str
    kind: str
    title: str
    pages: list[ParsedPage]


class ParseError(Exception):
    """A file we could not parse, with a short machine-readable reason."""

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason
        self.detail = detail[:500]


def clean_text(text: str) -> str:
    """Normalize Unicode and whitespace while preserving paragraphs."""
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\x00", "").replace("\u00ad", "")
    text = re.sub(r"(?<=[a-z])-\n(?=[a-z])", "", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" ?\n ?", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def drop_repeated_lines(pages: list[str]) -> list[str]:
    """Remove headers and footers repeated on most pages."""

    if len(pages) < 4:
        return pages

    def key(line: str) -> str:
        return re.sub(r"\d+", "#", line.strip().lower())

    seen: Counter[str] = Counter()

    for page in pages:
        lines = [line for line in page.splitlines() if line.strip()]
        seen.update({key(line) for line in lines[:2] + lines[-2:] if not line.startswith("#")})

    repeated = {value for value, count in seen.items() if count >= 0.6 * len(pages)}

    cleaned = []

    for page in pages:
        lines = page.splitlines()
        nonempty = [i for i, line in enumerate(lines) if line.strip()]
        edges = set(nonempty[:2] + nonempty[-2:])

        cleaned.append(
            "\n".join(
                line
                for index, line in enumerate(lines)
                if not (index in edges and key(line) in repeated)
            )
        )

    return cleaned


def heading_title(raw: str) -> str:
    """Remove optional heading anchors."""
    return ANCHOR.sub("", raw).strip()


def headings_in(
    text: str,
    in_code: bool = False,
) -> tuple[list[tuple[int, str]], bool]:
    """Find Markdown headings without treating code comments as headings."""
    found = []

    for line in text.splitlines():
        if FENCE.match(line):
            in_code = not in_code
        elif not in_code and (match := HEADING.match(line)):
            title = heading_title(match.group(2))
            if title:
                found.append((len(match.group(1)), title))

    return found, in_code


def with_heading_paths(texts: list[str]) -> list[ParsedPage]:
    """Number pages and record the section path each page starts in."""
    pages = []
    path: list[str] = []
    in_code = False

    for number, text in enumerate(texts, start=1):
        pages.append(
            ParsedPage(
                page_no=number,
                text=text,
                headings=list(path),
                tables=text.count("\n|---"),
            )
        )

        found, in_code = headings_in(text, in_code)

        for level, title in found:
            path = path[: level - 1] + [title]

    return pages


def finish(
    parser: str,
    kind: str,
    title: str,
    texts: list[str],
) -> ParsedDoc:
    """Clean extracted text and construct the final parsed document."""
    texts = drop_repeated_lines([clean_text(text) for text in texts])
    texts = [clean_text(text) for text in texts]

    if not any(texts):
        raise ParseError("empty", "no text after cleaning")

    found, _ = headings_in("\n".join(texts))
    final_title = found[0][1] if found else title

    return ParsedDoc(
        parser=parser,
        kind=kind,
        title=(final_title or "Untitled document")[:500],
        pages=with_heading_paths(texts),
    )


def _body_size(doc: pymupdf.Document) -> float:
    """Find the most common PDF font size, weighted by characters."""
    sizes: Counter[float] = Counter()

    for page in list(doc)[:30]:
        for block in page.get_text("dict").get("blocks", []):
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    sizes[round(span["size"], 1)] += len(span["text"])

    return float(sizes.most_common(1)[0][0]) if sizes else 10.0


def _heading_level(
    text: str,
    size: float,
    bold: bool,
    body: float,
) -> int:
    """Infer a heading level from text length, font size, and weight."""
    if not 2 < len(text) <= 120 or not any(char.isalpha() for char in text):
        return 0

    if size >= body * 1.6:
        return 1

    if size >= body * 1.3:
        return 2

    if size >= body * 1.12 or (bold and len(text) <= 80 and not text.endswith((".", ",", ";"))):
        return 3

    return 0


def _open_pdf(path: Path) -> pymupdf.Document:
    """Open a PDF and report common document errors."""
    try:
        doc = pymupdf.open(path)
    except Exception as exc:
        raise ParseError("corrupt", str(exc)) from exc

    if doc.needs_pass and not doc.authenticate(""):
        doc.close()
        raise ParseError("encrypted", "the PDF needs a password")

    if doc.page_count == 0:
        doc.close()
        raise ParseError("empty", "the PDF has no pages")

    return doc


def parse_pdf_pymupdf(path: Path) -> ParsedDoc:
    """Extract PDF text, headings, and ruled tables using PyMuPDF."""
    doc = _open_pdf(path)

    try:
        body = _body_size(doc)
        texts = []
        chars = 0

        for page in doc:
            tables = list(page.find_tables().tables) if len(page.get_cdrawings()) >= 4 else []

            used: set[int] = set()
            output: list[str] = []

            for block in page.get_text("dict").get("blocks", []):
                if block.get("type") != 0:
                    continue

                rect = pymupdf.Rect(block["bbox"])
                inside = next(
                    (index for index, table in enumerate(tables) if rect.intersects(table.bbox)),
                    None,
                )

                if inside is not None:
                    if inside not in used:
                        used.add(inside)
                        markdown = tables[inside].to_markdown()
                        if markdown:
                            output.append("\n" + markdown.strip() + "\n")
                    continue

                for line in block.get("lines", []):
                    spans = line.get("spans", [])
                    text = "".join(span.get("text", "") for span in spans).strip()

                    if not text:
                        continue

                    size = max(
                        (span.get("size", 0) for span in spans),
                        default=body,
                    )
                    bold = all(span.get("flags", 0) & 16 for span in spans)

                    level = _heading_level(text, size, bold, body)

                    output.append(f"{'#' * level} {text}" if level else text)
                    chars += len(text)

                output.append("")

            texts.append("\n".join(output))

        if chars < MIN_CHARS_PER_PAGE * len(texts):
            raise ParseError(
                "no_text_layer",
                f"{chars} characters on {len(texts)} pages: needs OCR",
            )

        title = (doc.metadata or {}).get("title") or ""
        return finish("pymupdf", "pdf", title, texts)

    finally:
        doc.close()


def parse_pdf_ocr(
    path: Path,
    language: str = "eng",
) -> ParsedDoc:
    """Extract scanned PDF text using Tesseract OCR."""
    doc = _open_pdf(path)

    try:
        try:
            texts = [
                page.get_text(
                    textpage=page.get_textpage_ocr(
                        language=language,
                        dpi=200,
                        full=True,
                    )
                )
                for page in doc
            ]
        except Exception as exc:
            raise ParseError("ocr_unavailable", str(exc)) from exc

        return finish(
            f"ocr-{language}",
            "pdf",
            (doc.metadata or {}).get("title") or "",
            texts,
        )
    finally:
        doc.close()


def parse_pdf_pypdf(path: Path) -> ParsedDoc:
    """Extract PDF text using pypdf."""
    try:
        reader = PdfReader(path, strict=False)

        if reader.is_encrypted and not reader.decrypt(""):
            raise ParseError("encrypted", "the PDF needs a password")

        texts = [page.extract_text() or "" for page in reader.pages]

    except ParseError:
        raise
    except Exception as exc:
        raise ParseError("corrupt", str(exc)) from exc

    if not texts:
        raise ParseError("empty", "the PDF has no pages")

    total_chars = sum(len(text) for text in texts)

    if total_chars < MIN_CHARS_PER_PAGE * len(texts):
        raise ParseError(
            "no_text_layer",
            f"almost no text on {len(texts)} pages: needs OCR",
        )

    metadata = reader.metadata or {}
    title = metadata.get("/Title", "") or ""

    return finish("pypdf", "pdf", str(title), texts)


def parse_html(path: Path) -> ParsedDoc:
    """Extract the main article from an HTML file."""
    try:
        html = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise ParseError("read_error", str(exc)) from exc

    markdown = trafilatura.extract(
        html,
        output_format="markdown",
        include_tables=True,
    )

    if not markdown or len(markdown) < 40:
        raise ParseError(
            "empty",
            "no main content found (possibly a JavaScript-built page)",
        )

    metadata = trafilatura.extract_metadata(html)
    title = metadata.title if metadata else ""

    return finish(
        "trafilatura",
        "html",
        title or "",
        split_pages(markdown),
    )


def markup_to_markdown(text: str, suffix: str) -> str:
    """Convert reStructuredText and AsciiDoc headings to Markdown."""
    lines = text.splitlines()

    if suffix == ".adoc":
        return "\n".join(
            re.sub(
                r"^(=+) ",
                lambda match: "#" * len(match.group(1)) + " ",
                line,
            )
            for line in lines
        )

    if suffix not in {".rst", ".txt"}:
        return text

    output: list[str] = []

    for index, line in enumerate(lines):
        underline = lines[index + 1] if index + 1 < len(lines) else ""

        is_rule = len(underline) >= 3 and len(set(underline)) == 1 and underline[0] in RST_MARKS

        if line.strip() and is_rule and len(underline) >= len(line.rstrip()):
            level = RST_MARKS[underline[0]]
            output.append("#" * level + " " + line.strip())
        elif not (output and len(line) >= 3 and len(set(line)) == 1 and line[0] in RST_MARKS):
            output.append(line)

    return "\n".join(output)


def split_pages(
    text: str,
    size: int = PAGE_CHARS,
) -> list[str]:
    """Split text at blank lines into pieces of approximately size characters."""
    pages: list[str] = []
    current: list[str] = []
    length = 0

    for paragraph in re.split(r"\n\s*\n", text):
        if current and length + len(paragraph) > size:
            pages.append("\n\n".join(current))
            current = []
            length = 0

        current.append(paragraph)
        length += len(paragraph)

    if current:
        pages.append("\n\n".join(current))

    return pages


def parse_text(path: Path) -> ParsedDoc:
    """Parse a supported plain-text, markup, or data file."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise ParseError("read_error", str(exc)) from exc

    suffix = path.suffix.lower()

    if suffix in DATA_TYPES:
        return finish("plain", "data", path.stem, split_pages(text))

    converted = markup_to_markdown(text, suffix)
    return finish("plain", "text", "", split_pages(converted))


PDF_PARSERS = {
    "pymupdf": parse_pdf_pymupdf,
    "pypdf": parse_pdf_pypdf,
}


def parse_file(
    path: Path,
    pdf_parser: str = "pymupdf",
) -> ParsedDoc:
    """Select a parser by file type. Always report failures as ParseError."""
    path = Path(path)
    suffix = path.suffix.lower()

    try:
        if suffix == ".pdf":
            parser = PDF_PARSERS.get(pdf_parser)
            if parser is None:
                raise ParseError(
                    "unsupported_parser",
                    f"Unknown PDF parser: {pdf_parser}",
                )
            return parser(path)

        if suffix in {".html", ".htm"}:
            return parse_html(path)

        if suffix in TEXT_TYPES | DATA_TYPES:
            return parse_text(path)

        raise ParseError(
            "unsupported_type",
            suffix or "no file extension",
        )

    except ParseError:
        raise
    except Exception as exc:
        raise ParseError(
            "crash",
            f"{type(exc).__name__}: {exc}",
        ) from exc
