from __future__ import annotations

import re
from statistics import median

from app.models.paper import Paper, Section, TextBlock

CANONICAL_PATTERNS: dict[str, list[str]] = {
    "abstract": [
        r"^abstract$",
        r"^summary$",
    ],
    "intro": [
        r"^introduction$",
        r"^background$",
        r"^motivation$",
    ],
    "related_work": [
        r"^related work$",
        r"^literature review$",
        r"^literature survey$",
        r"^prior work$",
        r"^state of the art$",
    ],
    "methods": [
        r"^methods?$",
        r"^methodology$",
        r"^materials and methods$",
        r"^experimental setup$",
        r"^proposed approach$",
        r"^system design$",
    ],
    "results": [
        r"^results?$",
        r"^experiments?$",
        r"^evaluation$",
        r"^findings$",
    ],
    "discussion": [
        r"^discussion$",
        r"^analysis$",
    ],
    "conclusion": [
        r"^conclusions?$",
        r"^summary and conclusion$",
        r"^future work$",
        r"^conclusions and future work$",
    ],
    "references": [
        r"^references$",
        r"^bibliography$",
        r"^works cited$",
    ],
}


NUMBERING_PATTERN = re.compile(
    r"""
    ^
    (?:
        # 1 Introduction
        \d+(?:\.\d+)*

        |

        # 1. Introduction
        \d+(?:\.\d+)*[.)]

        |

        # I. INTRODUCTION
        [IVXLCDM]+[.)]

        |

        # A. INTRODUCTION
        [A-Z][.)]
    )
    \s*
    """,
    re.IGNORECASE | re.VERBOSE,
)


def clean_heading(text: str) -> str:
    text = re.sub(
        NUMBERING_PATTERN,
        "",
        text.strip(),
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text.strip()


# A heading longer than this is prose, not a section label, so the
# phrase pass in canonical_role() does not run on it.
MAX_PHRASE_MATCH_WORDS = 8

# Words that only name a section when they are the WHOLE heading. As a
# phrase they are ordinary research vocabulary: "Sentiment Analysis" is not
# a discussion section, and "Migration Analysis" is part of a title.
EXACT_ONLY_PATTERNS = frozenset(
    {
        r"^summary$",
        r"^background$",
        r"^motivation$",
        r"^analysis$",
        r"^evaluation$",
        r"^findings$",
        r"^experiments?$",
    }
)


def normalize_heading(text: str) -> str:
    """Lowercase a cleaned heading and flatten the spellings that vary."""

    cleaned = clean_heading(text).lower()

    cleaned = cleaned.replace("&", "and")

    # Drop trailing punctuation: "Methodology:" and "Methodology" are one
    # heading.
    cleaned = re.sub(r"[\s:;.,\-–—]+$", "", cleaned)

    return " ".join(cleaned.split())


def canonical_role(text: str) -> str | None:
    """
    Map a heading onto a canonical role, or None if it is not one.

    Two passes. An exact match wins, so "Summary and Conclusion" is a
    conclusion rather than an abstract. Failing that, a canonical phrase
    appearing inside a short heading is accepted, which is what catches
    real-world headings like "Research Methodology" or "Findings and
    Conclusion" that an exact match alone misses.
    """

    cleaned = normalize_heading(text)

    if not cleaned:
        return None

    for role, patterns in CANONICAL_PATTERNS.items():
        for pattern in patterns:
            if re.match(pattern, cleaned, re.IGNORECASE):
                return role

    if len(cleaned.split()) > MAX_PHRASE_MATCH_WORDS:
        return None

    # The most specific phrase wins, not the first one declared: in
    # "Literature Review Introduction", "literature review" beats
    # "introduction", so the heading is related work.
    best_role: str | None = None
    best_length = 0

    for role, patterns in CANONICAL_PATTERNS.items():
        for pattern in patterns:
            if pattern in EXACT_ONLY_PATTERNS:
                continue

            # Patterns are anchored phrases; reuse them unanchored.
            phrase = pattern.strip("^$")

            match = re.search(rf"\b(?:{phrase})\b", cleaned, re.IGNORECASE)

            if match and len(match.group(0)) > best_length:
                best_role = role
                best_length = len(match.group(0))

    return best_role


# Front matter that lists the document's own structure. Its entries look
# exactly like headings, so they must be excluded before heading detection
# or every section gets a phantom duplicate.
TOC_HEADING = re.compile(
    r"""
    ^(
        (table\s+of\s+)?contents
        |
        list\s+of\s+(figures|tables|abbreviations|acronyms|symbols)
    )$
    """,
    re.IGNORECASE | re.VERBOSE,
)

# A contents entry: text, then leaders or a line break, then a page number.
# "Abstract \n2", "3 Methodology .... 16", "References    51".
TOC_ENTRY = re.compile(
    r"""
    [^\s.]                      # the end of the entry text
    [ \t]*
    (?:
        \.{2,}                  # dot leaders
        |
        [ \t]{3,}               # a wide gap
        |
        \n[ \t]*                # or the number on its own line
    )
    [ \t]*
    \d{1,4}
    [ \t]*$
    """,
    re.MULTILINE | re.VERBOSE,
)

# A contents page is front matter; a page this far in is body text that
# merely happens to end lines with numbers.
TOC_MAX_PAGE_FRACTION = 0.25
TOC_MIN_PAGES_SEARCHED = 10

TOC_MIN_ENTRIES = 3
TOC_MIN_ENTRY_RATIO = 0.4


def toc_page_numbers(paper: Paper) -> set[int]:
    """
    Page numbers that are a table of contents (or list of figures/tables).

    Detection is per page rather than per line: contents pages are almost
    always wholly contents, and judging a single line in the middle of the
    body text is far riskier than judging a front-matter page.
    """

    if not paper.pages:
        return set()

    searched = max(
        TOC_MIN_PAGES_SEARCHED,
        int(len(paper.pages) * TOC_MAX_PAGE_FRACTION),
    )

    toc_pages: set[int] = set()

    for page in paper.pages[:searched]:
        if not page.blocks:
            continue

        if any(TOC_HEADING.match(clean_heading(block.text)) for block in page.blocks):
            toc_pages.add(page.page_number)
            continue

        lines = [line for line in page.text.splitlines() if line.strip()]

        if not lines:
            continue

        entries = len(TOC_ENTRY.findall(page.text))

        if entries >= TOC_MIN_ENTRIES and entries >= len(lines) * TOC_MIN_ENTRY_RATIO:
            toc_pages.add(page.page_number)

    return toc_pages


def heading_level(text: str) -> int:
    match = NUMBERING_PATTERN.match(text.strip())

    if not match:
        return 1

    prefix = match.group(0).strip()

    numbers = re.findall(r"\d+", prefix)

    if numbers:
        return len(numbers)

    return 1


def is_probable_heading(
    block: TextBlock,
    body_font_size: float,
) -> bool:
    text = block.text.strip()

    if not text:
        return False

    # Very long text blocks are usually paragraphs.
    if len(text) > 180:
        return False

    # Multi-sentence paragraphs are unlikely to be headings.
    if text.count(".") >= 2:
        return False

    cleaned = clean_heading(text)

    # Explicit canonical headings get strong priority.
    if canonical_role(cleaned):
        return True

    # Numbered headings.
    if NUMBERING_PATTERN.match(text):
        return True

    # Heading should normally be short.
    if len(cleaned.split()) > 14:
        return False

    # Font-based detection.
    larger_font = (
        block.font_size is not None and block.font_size >= body_font_size * 1.15
    )

    if larger_font and (block.is_bold or text.isupper()):
        return True

    # Bold short text.
    if block.is_bold and len(cleaned.split()) <= 10:
        return True

    # Short uppercase headings.
    if text.isupper() and len(cleaned.split()) <= 10:
        return True

    return False


# Metadata titles are often the authoring tool's filename, not a real title.
JUNK_METADATA_TITLE = re.compile(
    r"""
    ^(
        microsoft\s+word\s*-\s*.*
        |
        .*\.(docx?|pdf|tex|rtf|odt)\s*$
        |
        untitled.*
        |
        (thesis|report|paper|draft|final|manuscript)\s*\d*
    )$
    """,
    re.IGNORECASE | re.VERBOSE,
)

# Running headers, emails, dates and page furniture that sit near the top
# of the first text page but are never the title.
NON_TITLE_LINE = re.compile(
    r"""
    ^(
        \S+@\S+                                  # email address
        |
        (page\s*)?\d+(\s*/\s*\d+)?              # page numbers
        |
        (https?://|www\.)\S+                      # URLs
        |
        (doi|arxiv)\b.*                           # identifiers
        |
        .*\b(19|20)\d{2}\b\s*$                   # bare dates/years
    )$
    """,
    re.IGNORECASE | re.VERBOSE,
)


def _is_plausible_title(text: str) -> bool:
    text = re.sub(r"\s+", " ", text).strip()

    if not text:
        return False

    # Titles are a line or two, not a paragraph.
    if len(text) > 250:
        return False

    words = text.split()

    if len(words) < 2 or len(words) > 30:
        return False

    # A section heading ("Abstract", "1 Introduction") is not the title.
    if canonical_role(text):
        return False

    if NON_TITLE_LINE.match(text):
        return False

    # Running text that happens to be short: a title is not a sentence,
    # and never starts mid-sentence.
    if not (text[0].isupper() or text[0].isdigit()):
        return False

    if text.endswith(("...", ".", ",", ";", ":")):
        return False

    if re.search(r"[.!?]\s+\S", text):
        return False

    # Require some letters; drop blocks that are mostly digits/symbols.
    letters = sum(1 for char in text if char.isalpha())

    if letters < len(text) * 0.5:
        return False

    return True


def title_from_metadata(paper: Paper) -> str | None:
    """Use the PDF's own metadata title when it looks like a real title."""

    raw = (paper.pdf_metadata or {}).get("title", "")

    title = re.sub(r"\s+", " ", str(raw)).strip()

    if not title:
        return None

    if JUNK_METADATA_TITLE.match(title):
        return None

    if not _is_plausible_title(title):
        return None

    return title


def _page_body_font_size(page) -> float | None:
    """Typical running-text font size on a single page."""

    sizes = [
        block.font_size
        for block in page.blocks
        if block.font_size is not None and len(block.text.split()) >= 5
    ]

    return median(sizes) if sizes else None


def title_from_text(paper: Paper) -> str | None:
    """
    Pick the largest-font plausible block near the top of the first page
    that actually carries text.

    Scanned cover pages contain no text at all, so the first page with
    blocks is used rather than page 1.
    """

    for page in paper.pages:
        candidates = [block for block in page.blocks if block.text.strip()]

        if not candidates:
            continue

        # Only the first page carrying text can hold the title. Looking
        # further would return a sentence from the body of the paper.

        # Restrict the search to the upper portion of the page, but fall
        # back to the first few blocks for pages with unusual layouts.
        top_blocks = [
            block for block in candidates if block.bbox[1] <= page.height * 0.40
        ] or candidates[:10]

        body_font_size = _page_body_font_size(page)

        plausible = [
            block
            for block in top_blocks
            if _is_plausible_title(block.text)
            and (
                block.font_size is None
                or body_font_size is None
                or block.font_size >= body_font_size * 1.10
            )
        ]

        if not plausible:
            return None

        with_font = [block for block in plausible if block.font_size is not None]

        if with_font:
            max_font = max(block.font_size for block in with_font)

            # The title is the first block set in (near-)largest type.
            for block in with_font:
                if block.font_size and block.font_size >= max_font * 0.90:
                    return re.sub(r"\s+", " ", block.text).strip()

        return re.sub(r"\s+", " ", plausible[0].text).strip()

    return None


def detect_title(paper: Paper) -> str | None:
    return title_from_metadata(paper) or title_from_text(paper)


def detect_sections(
    paper: Paper,
    toc_pages: set[int] | None = None,
) -> list[Section]:
    if toc_pages is None:
        toc_pages = toc_page_numbers(paper)

    all_blocks: list[TextBlock] = []

    for page in paper.pages:
        all_blocks.extend(page.blocks)

    if not all_blocks:
        return []

    font_sizes = [
        block.font_size
        for block in all_blocks
        if block.font_size is not None and len(block.text.split()) >= 5
    ]

    body_font_size = median(font_sizes) if font_sizes else 10.0

    headings: list[TextBlock] = []

    for block in all_blocks:
        # A contents entry reads as a heading but is not one.
        if block.page_number in toc_pages:
            continue

        if is_probable_heading(
            block,
            body_font_size,
        ):
            headings.append(block)

    sections: list[Section] = []

    for index, heading_block in enumerate(headings):
        next_heading = headings[index + 1] if index + 1 < len(headings) else None

        start_char = heading_block.start_char

        if next_heading:
            end_char = next_heading.start_char
        else:
            end_char = len(paper.full_text)

        section_text = paper.full_text[start_char:end_char].strip()

        section_id = f"section_{index + 1}"

        section = Section(
            section_id=section_id,
            heading=heading_block.text.strip(),
            canonical_role=canonical_role(heading_block.text),
            level=heading_level(heading_block.text),
            page_start=heading_block.page_number,
            page_end=(next_heading.page_number if next_heading else paper.page_count),
            start_char=start_char,
            end_char=end_char,
            text=section_text,
        )

        sections.append(section)

    return sections


def extract_abstract(
    paper: Paper,
    sections: list[Section],
) -> str | None:
    for section in sections:
        if section.canonical_role == "abstract":
            text = section.text

            # Remove the heading itself.
            lines = text.splitlines()

            if lines:
                first_line = lines[0].strip()

                if canonical_role(first_line) == "abstract":
                    text = "\n".join(lines[1:]).strip()

            return text or None

    # Fallback: look for "Abstract—" or "Abstract:"
    match = re.search(
        r"(?is)\babstract\s*[:—-]\s*(.+?)(?=\n\s*(?:1[\s.)]+|introduction\b))",
        paper.full_text,
    )

    if match:
        return match.group(1).strip()

    return None


def enrich_paper_sections(paper: Paper) -> Paper:
    paper.title = detect_title(paper)

    toc_pages = toc_page_numbers(paper)

    sections = detect_sections(paper, toc_pages)

    paper.sections = sections

    if toc_pages:
        # Surfaced rather than hidden: a page wrongly classified as
        # contents loses every heading on it.
        paper.warnings.append(
            "Skipped table-of-contents page(s) "
            f"{', '.join(str(number) for number in sorted(toc_pages))} "
            "during heading detection."
        )

    paper.abstract = extract_abstract(
        paper,
        sections,
    )

    if paper.title is None:
        # A cover page made of an image (or of vector artwork) carries no
        # text layer at all, so nothing can be read from it directly.
        cover_has_no_text = bool(paper.pages and not paper.pages[0].blocks)

        if cover_has_no_text:
            paper.warnings.append(
                "Could not detect paper title: page 1 carries no text layer "
                "(cover image) and the PDF metadata has no usable title. "
                "OCR would be required to read it."
            )
        else:
            paper.warnings.append("Could not reliably detect paper title.")

    if paper.abstract is None:
        paper.warnings.append("Could not reliably detect abstract.")

    if not sections:
        paper.warnings.append("No section headings were detected.")

    return paper
