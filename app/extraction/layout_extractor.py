from __future__ import annotations

import re
from pathlib import Path

import pymupdf

from app.models.paper import Figure, Table

TABLE_CAPTION_PATTERN = re.compile(
    r"^\s*(table|tab\.)\s*" r"(\d+(?:\.\d+)*)" r"[\s.:—-]*(.*)$",
    re.IGNORECASE,
)

FIGURE_CAPTION_PATTERN = re.compile(
    r"^\s*(figure|fig\.)\s*" r"(\d+(?:\.\d+)*)" r"[\s.:—-]*(.*)$",
    re.IGNORECASE,
)

# A caption sits directly above or below the object it describes.
CAPTION_MAX_DISTANCE = 120.0

# Images smaller than this share of the page are logos or rules, and an
# image covering (almost) the whole page is a scanned page, not a figure.
MIN_IMAGE_AREA_RATIO = 0.02
MAX_IMAGE_AREA_RATIO = 0.90


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


def _vertical_distance(
    caption_bbox: tuple[float, float, float, float],
    object_bbox: tuple[float, float, float, float],
) -> float:
    """Gap between a caption and an object stacked above or below it."""

    if caption_bbox[1] >= object_bbox[3]:
        return caption_bbox[1] - object_bbox[3]

    if object_bbox[1] >= caption_bbox[3]:
        return object_bbox[1] - caption_bbox[3]

    # Vertically overlapping: the caption sits inside the object band.
    return 0.0


def _looks_like_a_real_table(table) -> bool:
    """
    ``page.find_tables`` also fires on boxed callouts, banners and
    line-separated lists. A real table has several rows, more than one
    column, and filled cells spread across those rows.
    """

    try:
        rows = table.extract()
    except Exception:
        return False

    if table.row_count < 3 or table.col_count < 2:
        return False

    filled = sum(1 for row in rows for cell in row if cell and str(cell).strip())

    if filled < 8:
        return False

    # Fewer than two filled cells per row on average means a list with
    # rules drawn around it, not a grid of data.
    return filled / max(table.row_count, 1) >= 2.0


def _table_to_text(table) -> str:
    try:
        rows = table.extract()
    except Exception:
        return ""

    lines = []

    for row in rows:
        cells = [str(cell).strip() if cell else "" for cell in row]

        if any(cells):
            lines.append(" | ".join(cells))

    return "\n".join(lines)


def _collect_layout_objects(
    source_path: str,
) -> tuple[dict[int, list], dict[int, list], list[str]]:
    """
    Read tables and images straight out of the PDF, keyed by page number.

    Captions are the most reliable signal, but a document can contain
    tables and figures that carry no caption at all, and those are only
    visible in the page layout.
    """

    tables_by_page: dict[int, list] = {}
    images_by_page: dict[int, list] = {}
    warnings: list[str] = []

    path = Path(source_path)

    if not path.is_file():
        warnings.append(
            "Source PDF is no longer available; "
            "tables and figures were detected from captions only."
        )
        return tables_by_page, images_by_page, warnings

    try:
        document = pymupdf.open(path)
    except Exception as exc:
        warnings.append(
            f"Could not re-open the PDF for layout analysis ({exc}); "
            "tables and figures were detected from captions only."
        )
        return tables_by_page, images_by_page, warnings

    try:
        for page_index in range(document.page_count):
            page = document.load_page(page_index)

            page_number = page_index + 1
            page_area = abs(page.rect) or 1.0

            try:
                found = page.find_tables().tables
            except Exception:
                found = []

            real_tables = [table for table in found if _looks_like_a_real_table(table)]

            if real_tables:
                tables_by_page[page_number] = [
                    {
                        "page_number": page_number,
                        "bbox": tuple(float(value) for value in table.bbox),
                        "text": _table_to_text(table),
                        "row_count": table.row_count,
                        "col_count": table.col_count,
                    }
                    for table in real_tables
                ]

            images = []

            for info in page.get_image_info():
                bbox = pymupdf.Rect(info["bbox"])

                area_ratio = abs(bbox) / page_area

                if area_ratio < MIN_IMAGE_AREA_RATIO:
                    continue

                if area_ratio > MAX_IMAGE_AREA_RATIO:
                    # Full-page image: a scanned page or a cover.
                    continue

                images.append(
                    {
                        "page_number": page_number,
                        "bbox": tuple(float(value) for value in bbox),
                    }
                )

            if images:
                images_by_page[page_number] = images

    finally:
        document.close()

    return tables_by_page, images_by_page, warnings


def extract_tables_and_figures(
    paper,
) -> tuple[list[Table], list[Figure], list[str]]:

    tables: list[Table] = []
    figures: list[Figure] = []

    warnings: list[str] = []

    (
        tables_by_page,
        images_by_page,
        layout_warnings,
    ) = _collect_layout_objects(paper.source_path)

    warnings.extend(layout_warnings)

    # ------------------------------------------------------------------
    # Pass 1: collect captions in reading order.
    # ------------------------------------------------------------------

    caption_entries: list[dict] = []

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

            caption_entries.append(
                {
                    "object_type": object_type,
                    "caption": caption,
                    "text": block.text,
                    "page_number": page.page_number,
                    "bbox": block.bbox,
                    "start_char": start_char,
                    "end_char": end_char,
                    "matched": None,
                }
            )

    # ------------------------------------------------------------------
    # Pass 2: pair each caption with a laid-out object.
    #
    # A caption normally sits next to its object, but a figure pushed to
    # the bottom of a page can carry its caption onto the next one, so
    # neighbouring pages are searched when the caption's own page has
    # nothing left to claim.
    # ------------------------------------------------------------------

    for entry in caption_entries:

        pool = tables_by_page if entry["object_type"] == "table" else images_by_page

        page_number = entry["page_number"]

        for offset, max_distance in (
            (0, CAPTION_MAX_DISTANCE),
            (-1, None),
            (1, None),
        ):
            candidates = [
                candidate
                for candidate in pool.get(page_number + offset, [])
                if not candidate.get("claimed")
            ]

            if max_distance is None:
                # On the page before the caption take the lowest object,
                # on the page after it take the highest one.
                candidates.sort(key=lambda candidate: candidate["bbox"][1])

                if not candidates:
                    nearest = None
                elif offset < 0:
                    nearest = candidates[-1]
                else:
                    nearest = candidates[0]

            else:
                nearest = None
                nearest_distance = max_distance

                for candidate in candidates:
                    distance = _vertical_distance(entry["bbox"], candidate["bbox"])

                    if distance <= nearest_distance:
                        nearest = candidate
                        nearest_distance = distance

            if nearest is not None:
                nearest["claimed"] = True
                entry["matched"] = nearest
                break

    # ------------------------------------------------------------------
    # Pass 3: emit captioned and uncaptioned objects in document order.
    # ------------------------------------------------------------------

    table_items: list[tuple[int, float, dict]] = []
    figure_items: list[tuple[int, float, dict]] = []

    for entry in caption_entries:
        matched = entry["matched"]

        page_number = matched["page_number"] if matched else entry["page_number"]
        bbox = matched["bbox"] if matched else entry["bbox"]

        item = {
            "caption": entry["caption"],
            "page_number": page_number,
            "bbox": bbox,
            "start_char": entry["start_char"],
            "end_char": entry["end_char"],
            "detection_source": "caption+layout" if matched else "caption",
            "matched": matched,
            "text": entry["text"],
        }

        target = table_items if entry["object_type"] == "table" else figure_items

        target.append((page_number, bbox[1], item))

    for page_number, candidates in tables_by_page.items():
        for candidate in candidates:
            if candidate.get("claimed"):
                continue

            table_items.append(
                (
                    page_number,
                    candidate["bbox"][1],
                    {
                        "caption": None,
                        "page_number": page_number,
                        "bbox": candidate["bbox"],
                        "start_char": None,
                        "end_char": None,
                        "detection_source": "layout",
                        "matched": candidate,
                        "text": candidate["text"],
                    },
                )
            )

    for page_number, candidates in images_by_page.items():
        for candidate in candidates:
            if candidate.get("claimed"):
                continue

            figure_items.append(
                (
                    page_number,
                    candidate["bbox"][1],
                    {
                        "caption": None,
                        "page_number": page_number,
                        "bbox": candidate["bbox"],
                        "start_char": None,
                        "end_char": None,
                        "detection_source": "layout",
                        "matched": candidate,
                        "text": "",
                    },
                )
            )

    table_items.sort(key=lambda item: (item[0], item[1]))
    figure_items.sort(key=lambda item: (item[0], item[1]))

    for index, (_, _, item) in enumerate(table_items, start=1):
        matched = item["matched"]

        tables.append(
            Table(
                table_id=f"table_{index}",
                caption=item["caption"],
                page_number=item["page_number"],
                bbox=item["bbox"],
                text=(matched or {}).get("text") or item["text"],
                start_char=item["start_char"],
                end_char=item["end_char"],
                detection_source=item["detection_source"],
                row_count=(matched or {}).get("row_count"),
                col_count=(matched or {}).get("col_count"),
            )
        )

    for index, (_, _, item) in enumerate(figure_items, start=1):
        figures.append(
            Figure(
                figure_id=f"figure_{index}",
                caption=item["caption"],
                page_number=item["page_number"],
                bbox=item["bbox"],
                text=item["text"],
                start_char=item["start_char"],
                end_char=item["end_char"],
                detection_source=item["detection_source"],
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
