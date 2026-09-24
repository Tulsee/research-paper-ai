from __future__ import annotations

from app.models.paper import Paper


def locate_chunk_pages(
    paper: Paper,
    start_char: int,
    end_char: int,
) -> tuple[int, int]:

    matching_pages = []

    for page in paper.pages:

        page_blocks = page.blocks

        if not page_blocks:
            continue

        page_start = min(block.start_char for block in page_blocks)

        page_end = max(block.end_char for block in page_blocks)

        if end_char > page_start and start_char < page_end:
            matching_pages.append(page.page_number)

    if not matching_pages:

        return 1, 1

    return (
        min(matching_pages),
        max(matching_pages),
    )
