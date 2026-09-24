from __future__ import annotations

from dataclasses import dataclass

import tiktoken

from app.models.paper import Chunk, Paper, Section
from app.chunking.page_locator import (
    locate_chunk_pages,
)

TARGET_TOKENS = 800
OVERLAP_RATIO = 0.15

OVERLAP_TOKENS = int(TARGET_TOKENS * OVERLAP_RATIO)


@dataclass
class TokenizedSection:
    section: Section
    tokens: list[int]
    token_offsets: list[tuple[int, int]]


class SectionChunker:
    """
    Creates chunks independently inside each section.

    Important:
    A chunk can never cross a section boundary.
    """

    def __init__(
        self,
        model_encoding: str = "cl100k_base",
        target_tokens: int = TARGET_TOKENS,
        overlap_ratio: float = OVERLAP_RATIO,
    ):
        self.encoder = tiktoken.get_encoding(model_encoding)

        self.target_tokens = target_tokens

        self.overlap_tokens = max(
            1,
            int(target_tokens * overlap_ratio),
        )

    def _encode_with_offsets(
        self,
        text: str,
    ) -> tuple[list[int], list[tuple[int, int]]]:

        tokens = self.encoder.encode(
            text,
            disallowed_special=(),
        )

        offsets: list[tuple[int, int]] = []

        cursor = 0

        for token in tokens:

            token_text = self.encoder.decode([token])

            position = text.find(
                token_text,
                cursor,
            )

            if position == -1:

                # Fallback for unusual tokenization.
                start = cursor
                end = cursor

            else:

                start = position
                end = position + len(token_text)

            offsets.append((start, end))

            cursor = end

        return tokens, offsets

    def _create_section_chunks(
        self,
        section: Section,
    ) -> list[tuple[str, int, int, int]]:

        text = section.text.strip()

        if not text:
            return []

        tokens, offsets = self._encode_with_offsets(text)

        if not tokens:
            return []

        chunks = []

        start_token = 0

        while start_token < len(tokens):

            end_token = min(
                start_token + self.target_tokens,
                len(tokens),
            )

            chunk_tokens = tokens[start_token:end_token]

            if not chunk_tokens:
                break

            first_offset = offsets[start_token]

            last_offset = offsets[end_token - 1]

            local_start = first_offset[0]
            local_end = last_offset[1]

            chunk_text = text[local_start:local_end].strip()

            if not chunk_text:
                break

            chunks.append(
                (
                    chunk_text,
                    local_start,
                    local_end,
                    len(chunk_tokens),
                )
            )

            # Entire section has been consumed.
            if end_token >= len(tokens):
                break

            next_start = end_token - self.overlap_tokens

            # Ensure progress.
            if next_start <= start_token:
                next_start = start_token + 1

            start_token = next_start

        return chunks

    def chunk_paper(
        self,
        paper: Paper,
    ) -> Paper:

        chunks: list[Chunk] = []

        global_chunk_index = 0

        for section in paper.sections:

            section_chunks = self._create_section_chunks(section)

            for (
                chunk_text,
                local_start,
                local_end,
                token_count,
            ) in section_chunks:

                global_start = section.start_char + local_start

                global_end = section.start_char + local_end

                page_start, page_end = locate_chunk_pages(
                    paper,
                    global_start,
                    global_end,
                )

                chunk_id = f"{paper.paper_id}:" f"chunk_{global_chunk_index}"

                chunks.append(
                    Chunk(
                        chunk_id=chunk_id,
                        text=chunk_text,
                        token_count=token_count,
                        section_id=section.section_id,
                        section_heading=section.heading,
                        canonical_role=(section.canonical_role),
                        page_start=page_start,
                        page_end=page_end,
                        start_char=global_start,
                        end_char=global_end,
                        chunk_index=global_chunk_index,
                    )
                )

                global_chunk_index += 1

        paper.chunks = chunks

        return paper
