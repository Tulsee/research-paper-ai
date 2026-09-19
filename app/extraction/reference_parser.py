from __future__ import annotations

import re

from app.models.paper import Reference

REFERENCE_HEADING_PATTERN = re.compile(
    r"^\s*(references|bibliography|works cited)\s*$",
    re.IGNORECASE,
)

NUMBERED_REFERENCE_PATTERN = re.compile(
    r"""
    ^\s*
    (?:
        \[
            (?P<bracket>\d+)
        \]
        |
        (?P<number>\d+)
        [.)]
    )
    \s+
    (?P<text>.+)
    $
    """,
    re.VERBOSE,
)

YEAR_PATTERN = re.compile(r"\b(19|20)\d{2}\b")


def find_reference_section(paper):
    for section in paper.sections:

        if section.canonical_role == "references":
            return section

        if REFERENCE_HEADING_PATTERN.match(section.heading.strip()):
            return section

    return None


def split_numbered_references(
    text: str,
) -> list[tuple[int | None, str]]:

    lines = [line.strip() for line in text.splitlines() if line.strip()]

    references: list[tuple[int | None, str]] = []

    current_number: int | None = None
    current_text: list[str] = []

    for line in lines:

        match = NUMBERED_REFERENCE_PATTERN.match(line)

        if match:

            # Save previous reference.
            if current_text:

                references.append(
                    (
                        current_number,
                        " ".join(current_text),
                    )
                )

            number = match.group("bracket") or match.group("number")

            current_number = int(number)

            current_text = [match.group("text").strip()]

        else:

            # Continuation line.
            if current_text:
                current_text.append(line)

    if current_text:

        references.append(
            (
                current_number,
                " ".join(current_text),
            )
        )

    return references


def extract_year(text: str) -> int | None:

    years = YEAR_PATTERN.findall(text)

    if not years:
        return None

    matches = re.findall(
        r"\b(?:19|20)\d{2}\b",
        text,
    )

    if not matches:
        return None

    # Usually the first four-digit year is publication year.
    return int(matches[0])


def extract_authors(text: str) -> list[str]:

    # Simple heuristic:
    #
    # Everything before the first title-like separator.
    #
    # This is deliberately conservative because author
    # parsing will later be replaced by GROBID.

    year_match = YEAR_PATTERN.search(text)

    if year_match:

        author_part = text[: year_match.start()]

        author_part = author_part.strip(" .,:;()-")

        if author_part:

            candidates = re.split(
                r",| and ",
                author_part,
                flags=re.IGNORECASE,
            )

            return [candidate.strip() for candidate in candidates if candidate.strip()]

    return []


def parse_references(paper) -> tuple[list[Reference], list[str]]:

    warnings: list[str] = []

    reference_section = find_reference_section(paper)

    if reference_section is None:

        warnings.append("Reference section could not be detected.")

        return [], warnings

    raw_references = split_numbered_references(reference_section.text)

    if not raw_references:

        warnings.append(
            "Reference section was detected, "
            "but no numbered references could be parsed."
        )

        return [], warnings

    references: list[Reference] = []

    for index, (number, raw_text) in enumerate(
        raw_references,
        start=1,
    ):

        references.append(
            Reference(
                reference_id=f"ref_{index}",
                number=number,
                raw_text=raw_text,
                authors=extract_authors(raw_text),
                year=extract_year(raw_text),
            )
        )

    return references, warnings
