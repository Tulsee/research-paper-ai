import argparse

from pathlib import Path

from app.ingestion.pipeline import (
    process_pdf,
)

from app.ingestion.pymupdf_parser import (
    PDFIngestionError,
)

from app.storage.paper_store import (
    DEFAULT_STORE_DIR,
    save_paper,
)


def _detection_breakdown(items) -> str:
    """e.g. "  (3 captioned, 1 from layout)"."""

    if not items:
        return ""

    captioned = sum(1 for item in items if item.caption)
    uncaptioned = len(items) - captioned

    parts = []

    if captioned:
        parts.append(f"{captioned} captioned")

    if uncaptioned:
        parts.append(f"{uncaptioned} from layout")

    return "  (" + ", ".join(parts) + ")"


def main(argv: list[str] | None = None) -> int:

    parser = argparse.ArgumentParser(
        prog="research-paper-ai process",
        description="Parse, enrich and chunk a research-paper PDF.",
    )

    parser.add_argument(
        "pdf_paths",
        type=Path,
        nargs="+",
        help="One or more research-paper PDFs.",
    )

    parser.add_argument(
        "--save",
        action="store_true",
        help="Write each normalized Paper to the store as JSON.",
    )

    parser.add_argument(
        "--store",
        type=Path,
        default=DEFAULT_STORE_DIR,
        help="Where --save writes normalized paper JSON.",
    )

    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Print one summary line per paper instead of the full report.",
    )

    parser.add_argument(
        "--allow-scanned",
        action="store_true",
        help="Process scanned/image-only PDFs instead of rejecting them.",
    )

    args = parser.parse_args(argv)

    failures = 0

    for pdf_path in args.pdf_paths:

        try:
            paper = process_pdf(
                pdf_path,
                allow_scanned=args.allow_scanned,
            )

        except PDFIngestionError as exc:

            print(f"ERROR {pdf_path}: {exc}")

            failures += 1

            continue

        if args.save:

            destination = save_paper(paper, args.store)

            saved_note = f"  ->  {destination}"

        else:
            saved_note = ""

        if args.quiet:

            print(
                f"{paper.filename}: "
                f"{paper.page_count} pages, "
                f"{len(paper.sections)} sections, "
                f"{len(paper.chunks)} chunks, "
                f"{len(paper.warnings)} warnings"
                f"{saved_note}"
            )

            continue

        _report(paper)

        if saved_note:
            print(f"Saved{saved_note}")

    return 1 if failures else 0


def _report(paper) -> None:

    print()
    print("=" * 70)
    print("PAPER")
    print("=" * 70)

    print(f"ID:       {paper.paper_id}")

    print(f"Title:    {paper.title}")

    print(f"Pages:    {paper.page_count}")

    print(f"Characters:{paper.extracted_char_count}")

    print(f"Sections: {len(paper.sections)}")

    print(f"Tables:   {len(paper.tables)}" f"{_detection_breakdown(paper.tables)}")

    print(f"Figures:  {len(paper.figures)}" f"{_detection_breakdown(paper.figures)}")

    print(f"References:{len(paper.references)}")

    print(f"Chunks:   {len(paper.chunks)}")

    print()
    print("=" * 70)
    print("SECTIONS")
    print("=" * 70)

    for section in paper.sections:

        print(
            f"{section.section_id:15}"
            f"{section.canonical_role or '-':18}"
            f"{section.heading}"
        )

    print()
    print("=" * 70)
    print("CHUNKS")
    print("=" * 70)

    for chunk in paper.chunks[:10]:

        print(f"\n[{chunk.chunk_id}]")

        print(f"Section: {chunk.section_heading}")

        print(f"Tokens:  {chunk.token_count}")

        print(f"Pages:   " f"{chunk.page_start}-" f"{chunk.page_end}")

        print(f"Text:    " f"{chunk.text[:200]}...")

    print()

    if paper.warnings:

        print("=" * 70)
        print("WARNINGS")
        print("=" * 70)

        for warning in paper.warnings:

            print(f"- {warning}")


if __name__ == "__main__":
    raise SystemExit(main())
