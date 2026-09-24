from __future__ import annotations

import argparse
from pathlib import Path

from app.ingestion.pymupdf_parser import (
    PDFIngestionError,
    PyMuPDFParser,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="research-paper-ai inspect",
        description="Inspect a research-paper PDF.",
    )

    parser.add_argument(
        "pdf_path",
        type=Path,
        help="Path to the research-paper PDF.",
    )

    parser.add_argument(
        "--allow-scanned",
        action="store_true",
        help="Inspect a scanned/image-only PDF instead of rejecting it.",
    )

    args = parser.parse_args(argv)

    try:
        paper = PyMuPDFParser(allow_scanned=args.allow_scanned).parse(args.pdf_path)
    except PDFIngestionError as exc:
        print(f"ERROR: {exc}")
        return 1

    print("\n=== PAPER INGESTION REPORT ===")
    print(f"Paper ID: {paper.paper_id}")
    print(f"Filename: {paper.filename}")
    print(f"Parser: {paper.parser} {paper.parser_version}")
    print(f"Pages: {paper.page_count}")
    print(f"Extracted characters: {paper.extracted_char_count}")
    print(f"Total blocks: {sum(len(p.blocks) for p in paper.pages)}")

    print("\n=== PAGE SUMMARY ===")

    for page in paper.pages:
        print(
            f"Page {page.page_number}: "
            f"{len(page.blocks)} blocks, "
            f"{len(page.text)} characters"
        )

    print("\n=== FIRST FIVE BLOCKS ===")

    all_blocks = [block for page in paper.pages for block in page.blocks]

    for block in all_blocks[:5]:
        print(
            f"\n[{block.block_id}]"
            f"\nPage: {block.page_number}"
            f"\nOffsets: {block.start_char}:{block.end_char}"
            f"\nText: {block.text[:300]}"
        )

    if paper.warnings:
        print("\n=== WARNINGS ===")

        for warning in paper.warnings:
            print(f"- {warning}")
    else:
        print("\n=== WARNINGS ===")
        print("No warnings.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
