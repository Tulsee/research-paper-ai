import sys

from app.ingestion.pipeline import (
    process_pdf,
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


def main():

    if len(sys.argv) != 2:

        print("Usage: " "uv run python -m " "app.cli.process_pdf " "<pdf_path>")

        raise SystemExit(1)

    pdf_path = sys.argv[1]

    paper = process_pdf(pdf_path)

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
    main()
