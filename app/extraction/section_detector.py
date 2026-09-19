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


def canonical_role(text: str) -> str | None:
    cleaned = clean_heading(text).lower()

    for role, patterns in CANONICAL_PATTERNS.items():
        for pattern in patterns:
            if re.match(pattern, cleaned, re.IGNORECASE):
                return role

    return None


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


def detect_title(paper: Paper) -> str | None:
    if not paper.pages:
        return None

    first_page = paper.pages[0]

    candidates = [block for block in first_page.blocks if block.text.strip()]

    if not candidates:
        return None

    # Restrict title search to the upper portion of page 1.
    top_blocks = [
        block for block in candidates if block.bbox[1] <= first_page.height * 0.40
    ]

    if not top_blocks:
        top_blocks = candidates[:10]

    # Prefer the largest font block.
    with_font = [block for block in top_blocks if block.font_size is not None]

    if with_font:
        max_font = max(block.font_size for block in with_font)

        title_candidates = [
            block
            for block in with_font
            if block.font_size and block.font_size >= max_font * 0.90
        ]

        if title_candidates:
            # Usually the first large block is the title.
            return max(
                title_candidates,
                key=lambda block: block.font_size or 0,
            ).text.strip()

    return top_blocks[0].text.strip()


def detect_sections(paper: Paper) -> list[Section]:
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

    sections = detect_sections(paper)

    paper.sections = sections

    paper.abstract = extract_abstract(
        paper,
        sections,
    )

    if paper.title is None:
        paper.warnings.append("Could not reliably detect paper title.")

    if paper.abstract is None:
        paper.warnings.append("Could not reliably detect abstract.")

    if not sections:
        paper.warnings.append("No section headings were detected.")

    return paper
