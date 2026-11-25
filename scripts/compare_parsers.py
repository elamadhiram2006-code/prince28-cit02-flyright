"""Compare the available PDF and HTML parsers on difficult corpus files."""

import argparse
import json
import re
import time
from html.parser import HTMLParser
from pathlib import Path

from flyright.ingest.parse import (
    ParsedDoc,
    ParseError,
    parse_file,
)

MANIFEST = Path("data/manifest.jsonl")
NOTES = Path("NOTES.md")


class TextExtractor(HTMLParser):
    """Simple HTML tag-stripping parser."""

    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)

    def get_text(self):
        return re.sub(r"\s+", " ", " ".join(self.parts)).strip()


def select_files():
    """Select the ten largest downloaded PDF and HTML files."""
    latest = {}

    for line in MANIFEST.read_text(encoding="utf-8").splitlines():
        try:
            record = json.loads(line)
            latest[record["url"]] = record
        except (json.JSONDecodeError, KeyError):
            continue

    files = []

    for record in latest.values():
        if record.get("status") != "downloaded":
            continue

        if not record.get("path"):
            continue

        path = Path(record["path"])
        if (
            record.get("status") == "downloaded"
            and path.is_file()
            and path.suffix.lower() in {".pdf", ".html", ".htm"}
        ):
            files.append(path)

    return sorted(files, key=lambda p: p.stat().st_size, reverse=True)[:10]


def measure(doc: ParsedDoc):
    return {
        "title": doc.title or "Untitled",
        "pages": len(doc.pages),
        "chars": sum(len(page.text) for page in doc.pages),
        "tables": sum(page.tables for page in doc.pages),
        "headings": sum(len(page.headings) for page in doc.pages),
    }


def run_parser(path, parser_name):
    """Run one parser and collect its measurements."""
    started = time.perf_counter()

    try:
        if path.suffix.lower() == ".pdf":
            doc = parse_file(path, pdf_parser=parser_name)
        else:
            doc = parse_file(path)

        result = measure(doc)
        result["status"] = "OK"

    except (ParseError, Exception) as error:
        result = {
            "status": f"FAILED: {error}",
            "pages": 0,
            "chars": 0,
            "tables": 0,
            "headings": 0,
            "title": "-",
        }

    result["seconds"] = round(time.perf_counter() - started, 2)
    return result


def run_plain_html(path):
    """Extract HTML using basic tag stripping."""
    started = time.perf_counter()

    try:
        extractor = TextExtractor()
        extractor.feed(path.read_text(encoding="utf-8", errors="replace"))
        text = extractor.get_text()

        result = {
            "status": "OK" if text else "FAILED: empty",
            "title": "-",
            "pages": 1 if text else 0,
            "chars": len(text),
            "tables": 0,
            "headings": 0,
        }

    except OSError as error:
        result = {
            "status": f"FAILED: {error}",
            "title": "-",
            "pages": 0,
            "chars": 0,
            "tables": 0,
            "headings": 0,
        }

    result["seconds"] = round(time.perf_counter() - started, 2)
    return result


def compare(path):
    """Compare the available parsers for one file."""
    if path.suffix.lower() == ".pdf":
        first = run_parser(path, "pymupdf")
        second = run_parser(path, "pypdf")
        first_name, second_name = "PyMuPDF", "pypdf"
    else:
        first = run_parser(path, "pymupdf")
        second = run_plain_html(path)
        first_name, second_name = "Trafilatura", "Tag stripping"

    return {
        "path": str(path),
        "first_name": first_name,
        "first": first,
        "second_name": second_name,
        "second": second,
    }


def main():
    parser = argparse.ArgumentParser(description="Compare two parsers on difficult corpus files.")
    parser.add_argument(
        "paths",
        nargs="*",
        help="Optional PDF or HTML file paths.",
    )
    args = parser.parse_args()

    if args.paths:
        files = [Path(path) for path in args.paths]
    else:
        if not MANIFEST.exists():
            print("data/manifest.jsonl not found.")
            return 1
        files = select_files()

    if not files:
        print("No PDF or HTML files found to compare.")
        return 1

    results = []

    for path in files:
        if not path.is_file():
            print(f"Missing file: {path}")
            continue

        print(f"Comparing: {path}", flush=True)
        results.append(compare(path))

    if not results:
        print("No files could be compared.")
        return 1

    lines = [
        "",
        "## Parser comparison",
        "",
        "| File | Parser A | A chars | A tables | A sec | "
        "Parser B | B chars | B tables | B sec | Better parser and why |",
    ]

    for item in results:
        a = item["first"]
        b = item["second"]

        lines.append(
            f"| `{item['path']}` "
            f"| {item['first_name']} "
            f"| {a['chars']} | {a['tables']} | {a['seconds']} "
            f"| {item['second_name']} "
            f"| {b['chars']} | {b['tables']} | {b['seconds']} "
            f"| TODO: inspect and decide |"
        )

    lines.extend(
        [
            "",
            "Review at least three files manually. Fill in the final column "
            "with the better parser and a short reason.",
            "",
        ]
    )

    with NOTES.open("a", encoding="utf-8") as file:
        file.write("\n".join(lines))

    print(f"\ncompared {len(results)} files -> table written to NOTES.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
