from __future__ import annotations

import re

import fitz

from app.models.paper import Figure, Table

TABLE_CAPTION_PATTERN = re.compile(
    r"^\s*(table|tab\.)\s*" r"(\d+(?:\.\d+)*)" r"[\s.:—-]*(.*)$",
    re.IGNORECASE,
)

FIGURE_CAPTION_PATTERN = re.compile(
    r"^\s*(figure|fig\.)\s*" r"(\d+(?:\.\d+)*)" r"[\s.:—-]*(.*)$",
    re.IGNORECASE,
)


def _caption_type(text: str) -> tuple[str, str] | None:
    """
    Returns:
        ("table", "Table 1: ...")
        ("figure", "Figure 1: ...")
    """

    table_match = TABLE_CAPTION_PATTERN.match(text)

    if table_match:
        return "table", text.strip()

    figure_match = FIGURE_CAPTION_PATTERN.match(text)

    if figure_match:
        return "figure", text.strip()

    return None


def _find_text_position(
    full_text: str,
    text: str,
    start_from: int = 0,
) -> tuple[int | None, int | None]:

    index = full_text.find(
        text,
        start_from,
    )

    if index == -1:
        return None, None

    return index, index + len(text)


def extract_tables_and_figures(
    paper,
) -> tuple[list[Table], list[Figure], list[str]]:

    tables: list[Table] = []
    figures: list[Figure] = []

    warnings: list[str] = []

    table_count = 0
    figure_count = 0

    search_offset = 0

    for page in paper.pages:

        for block in page.blocks:

            detected = _caption_type(block.text)

            if detected is None:
                continue

            object_type, caption = detected

            start_char, end_char = _find_text_position(
                paper.full_text,
                block.text,
                search_offset,
            )

            if start_char is not None:
                search_offset = end_char

            if object_type == "table":

                table_count += 1

                tables.append(
                    Table(
                        table_id=f"table_{table_count}",
                        caption=caption,
                        page_number=page.page_number,
                        bbox=block.bbox,
                        text=block.text,
                        start_char=start_char,
                        end_char=end_char,
                    )
                )

            elif object_type == "figure":

                figure_count += 1

                figures.append(
                    Figure(
                        figure_id=f"figure_{figure_count}",
                        caption=caption,
                        page_number=page.page_number,
                        bbox=block.bbox,
                        text=block.text,
                        start_char=start_char,
                        end_char=end_char,
                    )
                )

    # These are warnings, not errors.
    #
    # A PDF can legitimately have no tables or figures.
    # We therefore only warn when the document appears to
    # contain references to them but extraction failed.

    table_mentions = len(
        re.findall(
            r"\btable\s+\d+",
            paper.full_text,
            re.IGNORECASE,
        )
    )

    figure_mentions = len(
        re.findall(
            r"\b(?:figure|fig\.)\s+\d+",
            paper.full_text,
            re.IGNORECASE,
        )
    )

    if table_mentions > 0 and not tables:
        warnings.append(
            "Table references were detected, "
            "but no table captions could be extracted."
        )

    if figure_mentions > 0 and not figures:
        warnings.append(
            "Figure references were detected, "
            "but no figure captions could be extracted."
        )

    return tables, figures, warnings
