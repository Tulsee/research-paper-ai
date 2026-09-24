from app.extraction.section_detector import (
    canonical_role,
    detect_sections,
    enrich_paper_sections,
    toc_page_numbers,
)
from app.models.paper import Paper, PaperPage, TextBlock

BODY = "This is a paragraph of running text that stands in for the body of the paper."


def build_paper(pages: list[list[str]], paper_id: str = "toc123") -> Paper:
    """
    Assemble a Paper from page/block text, mirroring the parser's layout:
    blocks joined by a blank line, offsets into one full_text.
    """

    parts: list[str] = []
    offset = 0

    paper_pages: list[PaperPage] = []

    for page_index, block_texts in enumerate(pages):
        page_number = page_index + 1

        blocks: list[TextBlock] = []

        for block_index, text in enumerate(block_texts):
            if parts:
                separator = "\n\n"
                parts.append(separator)
                offset += len(separator)

            start = offset

            parts.append(text)
            offset += len(text)

            blocks.append(
                TextBlock(
                    block_id=f"{paper_id}:p{page_number}:b{block_index}",
                    page_number=page_number,
                    start_char=start,
                    end_char=offset,
                    text=text,
                    bbox=(0.0, 0.0, 100.0, 20.0),
                    block_index=block_index,
                    # Headings are set apart by size in these fixtures.
                    font_size=14.0 if len(text.split()) <= 6 else 10.0,
                    is_bold=len(text.split()) <= 6,
                )
            )

        paper_pages.append(
            PaperPage(
                page_number=page_number,
                width=595.0,
                height=842.0,
                blocks=blocks,
                text="\n\n".join(block_texts),
            )
        )

    full_text = "".join(parts)

    return Paper(
        paper_id=paper_id,
        source_path=f"/tmp/{paper_id}.pdf",
        filename=f"{paper_id}.pdf",
        full_text=full_text,
        pages=paper_pages,
        page_count=len(paper_pages),
        extracted_char_count=len(full_text),
    )


def thesis_like_paper() -> Paper:
    """A contents page whose entries duplicate the real headings."""

    return build_paper(
        [
            ["A Thesis About Something"],
            [
                "Table of Contents",
                "Abstract \n2",
                "1 Introduction \n7",
                "2 Research Methodology \n16",
                "3 Conclusion \n49",
                "References \n51",
            ],
            ["Abstract", BODY],
            ["1 Introduction", BODY],
            ["2 Research Methodology", BODY],
            ["3 Conclusion", BODY],
            ["References", "[1] Someone. A paper. 2024."],
        ]
    )


def test_a_contents_page_is_detected():

    assert toc_page_numbers(thesis_like_paper()) == {2}


def test_contents_entries_do_not_become_sections():

    paper = thesis_like_paper()

    sections = detect_sections(paper)

    pages = {section.page_start for section in sections}

    assert 2 not in pages

    roles = [
        section.canonical_role for section in sections if section.canonical_role
    ]

    # Each role appears once, in document order, instead of twice.
    assert roles == ["abstract", "intro", "methods", "conclusion", "references"]


def test_skipping_a_contents_page_is_warned_about():

    paper = enrich_paper_sections(thesis_like_paper())

    assert any("table-of-contents page(s) 2" in warning for warning in paper.warnings)


def test_a_contents_page_is_detected_without_a_contents_heading():
    """Entries with dot leaders are enough; not every TOC is labelled."""

    paper = build_paper(
        [
            ["A Paper"],
            [
                "Abstract ......... 2",
                "1 Introduction ......... 7",
                "2 Methods ......... 16",
                "References ......... 51",
            ],
            ["Abstract", BODY],
        ]
    )

    assert toc_page_numbers(paper) == {2}


def test_a_paper_without_front_matter_has_no_contents_page():

    paper = build_paper(
        [
            ["A Paper With No Contents Page", "Abstract", BODY],
            ["1 Introduction", BODY],
            ["2 Methods", BODY],
        ]
    )

    assert toc_page_numbers(paper) == set()


def test_body_text_is_never_mistaken_for_a_contents_page():
    """Numbered list items and citations end lines with numbers too."""

    paper = build_paper(
        [
            ["1 Introduction", BODY],
            [
                "We evaluate three models.",
                "The baseline reaches an accuracy of 91",
                "The proposed model reaches 94",
                "Improvement over the baseline is 3",
            ],
        ]
    )

    assert toc_page_numbers(paper) == set()


def test_contents_pages_are_only_looked_for_in_front_matter():
    """A list-like page deep in a long document is body text."""

    front = [["A Paper"], ["Abstract", BODY]]

    body = [["Section", BODY] for _ in range(40)]

    late_list = [
        [
            "Result A ......... 12",
            "Result B ......... 18",
            "Result C ......... 24",
            "Result D ......... 31",
        ]
    ]

    paper = build_paper(front + body + late_list)

    assert toc_page_numbers(paper) == set()


def test_the_most_specific_canonical_phrase_wins():

    # Both "literature review" and "introduction" appear here. The longer,
    # more specific phrase decides, so this is related work rather than the
    # introduction it would have been under declaration order.
    assert canonical_role("14 Literature Review Introduction") == "related_work"

    assert canonical_role("Literature Review") == "related_work"
    assert canonical_role("Introduction") == "intro"

    # Genuinely ambiguous headings fall to the longest phrase too, which is
    # a rule rather than a judgement: "state of the art" beats "methods".
    assert canonical_role("State of the Art Methods") == "related_work"
