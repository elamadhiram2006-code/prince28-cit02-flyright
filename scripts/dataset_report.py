"""Measure the corpus and generate DATASET.md and docs/CAPACITY.md.

Examples:
    uv run python scripts/dataset_report.py --full-pages 1200
    uv run python scripts/dataset_report.py --full-files 2500

PDF page counts are measured independently from text extraction so that
malformed font encodings cannot prevent a document from being counted.
Only the content between generated markers is replaced.
"""

import argparse
import hashlib
import json
import logging
import re
import sys
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "data" / "manifest.jsonl"
DATASET_FILE = ROOT / "DATASET.md"
CAPACITY_FILE = ROOT / "docs" / "CAPACITY.md"

INVALID_HTML_FILENAMES = {
    "digigov-portal-4fd04e37.html",
    "digigov-portal-e95b6f2d.html",
}

# Large PDFs can contain complex font maps that make pypdf extraction
# extremely slow. Page counts are still measured for these documents.
LARGE_PDF_TEXT_LIMIT = 20 * 1024 * 1024


class VisibleText(HTMLParser):
    """Extract visible text from HTML."""

    def __init__(self):
        super().__init__()
        self.parts = []
        self.hidden_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag.lower() in {"script", "style", "noscript", "svg"}:
            self.hidden_depth += 1

    def handle_endtag(self, tag):
        if tag.lower() in {"script", "style", "noscript", "svg"}:
            self.hidden_depth = max(0, self.hidden_depth - 1)

    def handle_data(self, data):
        if not self.hidden_depth:
            text = data.strip()
            if text:
                self.parts.append(text)

    def get_text(self):
        return " ".join(self.parts)


def sha256_file(path):
    """Calculate a file's SHA-256 hash."""

    digest = hashlib.sha256()

    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest()


def extract_pdf_text(path, reader):
    """Extract PDF text safely, without sacrificing its page count."""

    text_parts = []
    failures = 0

    for page_number, page in enumerate(reader.pages, start=1):
        try:
            text_parts.append(page.extract_text() or "")
        except Exception as exc:
            failures += 1
            logging.warning(
                "Text extraction failed for %s, page %s: %s",
                path.name,
                page_number,
                exc,
            )

    note = ""
    if failures:
        note = f"Text extraction failed on {failures} page(s)."

    return "\n".join(text_parts), note


def measure(path):
    """Measure pages, characters and estimated tokens."""

    result = {
        "pages": 0,
        "chars": 0,
        "tokens": 0,
        "note": "",
    }

    suffix = path.suffix.lower()

    try:
        if suffix == ".pdf":
            from pypdf import PdfReader

            reader = PdfReader(str(path), strict=False)

            # Count pages before attempting any text extraction.
            result["pages"] = len(reader.pages)

            file_size = path.stat().st_size

            if file_size > LARGE_PDF_TEXT_LIMIT:
                result["note"] = (
                    "Page count measured; text extraction skipped "
                    "because the PDF exceeds the safe extraction size."
                )
                return result

            content, note = extract_pdf_text(path, reader)
            result["note"] = note

        elif suffix in {".html", ".htm"}:
            parser = VisibleText()
            parser.feed(path.read_text(encoding="utf-8", errors="replace"))
            content = parser.get_text()
            result["pages"] = 1 if content else 0

        elif suffix in {".txt", ".md", ".csv", ".json"}:
            content = path.read_text(encoding="utf-8", errors="replace")
            result["pages"] = 1 if content.strip() else 0

        else:
            result["note"] = "Unsupported file type"
            return result

        result["chars"] = len(content)
        result["tokens"] = len(content.split())

    except Exception as exc:
        logging.warning("Could not measure %s: %s", path, exc)
        result["note"] = f"Measurement error: {exc}"

    return result


def load_records():
    """Load the latest manifest record for each URL."""

    if not MANIFEST.is_file():
        logging.error("Manifest not found: %s", MANIFEST)
        return []

    latest = {}

    with MANIFEST.open("r", encoding="utf-8-sig") as file:
        for line_number, line in enumerate(file, start=1):
            if not line.strip():
                continue

            try:
                record = json.loads(line)
                url = record.get("url")

                if url:
                    latest[url] = record

            except json.JSONDecodeError:
                logging.warning(
                    "Ignoring invalid manifest line %s",
                    line_number,
                )

    return list(latest.values())


def measure_all(records):
    """Measure records while avoiding repeated work for identical files."""

    cache = {}

    for record in records:
        path = record["_resolved_path"]
        file_hash = record.get("sha256")

        if not file_hash:
            file_hash = sha256_file(path)

        if file_hash not in cache:
            cache[file_hash] = measure(path)

        stats = cache[file_hash]

        record["pages"] = stats["pages"]
        record["chars"] = stats["chars"]
        record["tokens"] = stats["tokens"]
        record["measurement_note"] = stats["note"]


def dataset_block(done, not_done, today):
    """Create the DATASET.md generated section."""

    lines = [
        f"**Last updated:** {today}",
        "",
        f"- Unique valid documents: **{len(done)}**",
        f"- Total pages: **{sum(r['pages'] for r in done):,}**",
        f"- Total characters: **{sum(r['chars'] for r in done):,}**",
        f"- Estimated tokens: **{sum(r['tokens'] for r in done):,}**",
        f"- Unavailable or excluded sources: **{len(not_done)}**",
        "",
        "## Downloaded documents",
        "",
        "| Document | Source | Pages | Size (bytes) | Measurement note |",
        "|---|---|---:|---:|---|",
    ]

    for record in done:
        title = record.get("title", "Untitled").replace("|", "\\|")
        source = record.get("source", "Unknown").replace("|", "\\|")
        note = record.get("measurement_note", "").replace("|", "\\|")

        lines.append(
            f"| {title} | {source} | {record['pages']:,} | {record.get('bytes', 0):,} | {note} |"
        )

    lines.extend(
        [
            "",
            "## Sources not included in the corpus",
            "",
        ]
    )

    if not_done:
        lines.extend(
            [
                "| Document | Status | Reason |",
                "|---|---|---|",
            ]
        )

        for record in not_done:
            title = record.get("title", "Untitled").replace("|", "\\|")
            status = record.get("status", "unknown")
            reason = str(
                record.get("error")
                or record.get("reason")
                or record.get("message")
                or "Not available"
            ).replace("|", "\\|")

            lines.append(f"| {title} | {status} | {reason} |")
    else:
        lines.append("No unavailable sources.")

    lines.append("")
    return "\n".join(lines)


def capacity_block(done, not_done, args, today):
    """Create the docs/CAPACITY.md generated section."""

    total_bytes = sum(r.get("bytes", 0) for r in done)
    total_pages = sum(r["pages"] for r in done)
    total_chars = sum(r["chars"] for r in done)
    total_tokens = sum(r["tokens"] for r in done)

    page_target = args.full_pages
    file_target = args.full_files

    page_percent = min(100, total_pages / page_target * 100) if page_target > 0 else 0

    file_percent = min(100, len(done) / file_target * 100) if file_target > 0 else 0

    lines = [
        f"**Last updated:** {today}",
        "",
        "## Corpus measurements",
        "",
        "| Metric | Current value |",
        "|---|---:|",
        f"| Unique documents | {len(done):,} |",
        f"| Total pages | {total_pages:,} |",
        f"| Total characters | {total_chars:,} |",
        f"| Estimated tokens | {total_tokens:,} |",
        f"| Total size | {total_bytes / (1024 * 1024):.2f} MiB |",
        f"| Unavailable or excluded sources | {len(not_done):,} |",
        "",
        "## Capacity targets",
        "",
        "| Target | Goal | Current | Progress |",
        "|---|---:|---:|---:|",
        (f"| Full pages | {page_target:,} | {total_pages:,} | {page_percent:.1f}% |"),
        (f"| Full files | {file_target:,} | {len(done):,} | {file_percent:.1f}% |"),
        "",
        "## Status",
        "",
    ]

    if total_pages >= page_target and len(done) >= file_target:
        lines.append("Both configured corpus targets have been reached.")
    else:
        lines.append(
            "Corpus targets have not yet been reached. "
            "Continue collecting permitted, relevant documents."
        )

    lines.append("")
    return "\n".join(lines)


def replace_generated(path, content):
    """Replace generated content while preserving the rest of a document."""

    path.parent.mkdir(parents=True, exist_ok=True)

    original = path.read_text(encoding="utf-8") if path.exists() else ""

    begin_pattern = re.compile(
        r"<!--\s*(?:BEGIN|START)[^>]*GENERATED[^>]*-->",
        re.IGNORECASE,
    )

    end_pattern = re.compile(
        r"<!--\s*END[^>]*GENERATED[^>]*-->",
        re.IGNORECASE,
    )

    begin = begin_pattern.search(original)
    end = end_pattern.search(original)

    if begin and end and begin.end() <= end.start():
        updated = original[: begin.end()] + "\n\n" + content + "\n" + original[end.start() :]
    else:
        section = (
            "<!-- BEGIN GENERATED CONTENT -->\n\n" + content + "\n<!-- END GENERATED CONTENT -->\n"
        )

        updated = original.rstrip()

        if updated:
            updated += "\n\n"

        updated += section

    path.write_text(updated, encoding="utf-8")


def main():
    """Run corpus measurements and generate reports."""

    parser = argparse.ArgumentParser(description="Measure the corpus and generate dataset reports.")

    parser.add_argument(
        "--full-pages",
        type=int,
        default=1200,
        help="Target number of pages (default: 1200)",
    )

    parser.add_argument(
        "--full-files",
        type=int,
        default=2500,
        help="Target number of files (default: 2500)",
    )

    args = parser.parse_args()

    if args.full_pages < 0 or args.full_files < 0:
        parser.error("Targets cannot be negative.")

    records = load_records()

    if not records:
        print("No manifest records found.")
        return 1

    downloaded = []

    for record in records:
        if record.get("status") != "downloaded":
            continue

        path = Path(record.get("path", ""))

        if not path.is_absolute():
            path = ROOT / path

        if path.is_file():
            record["_resolved_path"] = path
            downloaded.append(record)

    invalid = []

    for record in downloaded:
        path = record["_resolved_path"]

        if path.suffix.lower() in {".html", ".htm"} and path.name in INVALID_HTML_FILENAMES:
            invalid.append(record)

    invalid_urls = {record.get("url") for record in invalid}

    seen_hashes = set()
    done = []

    for record in downloaded:
        if record.get("url") in invalid_urls:
            continue

        file_hash = record.get("sha256")

        if not file_hash:
            file_hash = sha256_file(record["_resolved_path"])

        if file_hash in seen_hashes:
            continue

        seen_hashes.add(file_hash)
        done.append(record)

    not_done = []

    for record in records:
        path = Path(record.get("path", ""))

        if not path.is_absolute():
            path = ROOT / path

        if (
            record.get("status") != "downloaded"
            or not path.is_file()
            or record.get("url") in invalid_urls
        ):
            not_done.append(record)

    if not done:
        print("No valid downloaded documents available to measure.")
        return 1

    measure_all(done)

    if not sum(record["pages"] for record in done):
        print("Nothing measurable yet: check the downloaded documents.")
        return 1

    today = datetime.now(UTC).strftime("%Y-%m-%d")

    dataset_content = dataset_block(done, not_done, today)
    capacity_content = capacity_block(done, not_done, args, today)

    replace_generated(DATASET_FILE, dataset_content)
    replace_generated(CAPACITY_FILE, capacity_content)

    total_pages = sum(record["pages"] for record in done)

    print(
        f"files={len(done)} pages={total_pages} excluded={len(invalid)} unavailable={len(not_done)}"
    )

    for record in done:
        if record.get("measurement_note"):
            print(f"note: {record.get('title', 'Untitled')}: {record['measurement_note']}")

    print("Updated DATASET.md and docs/CAPACITY.md")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sys.exit(main())
