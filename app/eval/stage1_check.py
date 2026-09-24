"""Stage 1 measurement harness.

Turns the plan's stage-1 exit criteria into a number and an exit code:

    >=95%  correct title
    >=95%  correct abstract
    >=90%  correct canonical section tree
    100%   structural invariants (every block resolves to a page, every
           offset round-trips, no chunk escapes its section)

Two kinds of check run here. Invariants need no labels and run on every
stored paper. Accuracy needs a gold label file per paper, which is written
by hand — ``--init-gold`` bootstraps a template from the current parse,
but a template is a starting point for a human, not a label.

Gold file: ``data/gold/stage1/<paper_id>.json``

    {
      "paper_id": "5f2a...",
      "filename": "paper.pdf",
      "verified": false,
      "title": "The title exactly as printed on the paper",
      "abstract_prefix": "The first sentence of the abstract, verbatim.",
      "canonical_roles": ["abstract", "intro", "methods", "results"]
    }

``verified`` must be flipped to ``true`` by whoever checked the label
against the PDF; unverified files are ignored when scoring, so a
bootstrapped template can never inflate a score by agreeing with the
parser that produced it.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from difflib import SequenceMatcher
from pathlib import Path

from app.models.paper import Paper
from app.storage.paper_store import (
    DEFAULT_STORE_DIR,
    iter_papers,
)

DEFAULT_GOLD_DIR = Path("data/gold/stage1")

TITLE_THRESHOLD = 0.95
ABSTRACT_THRESHOLD = 0.95
SECTION_THRESHOLD = 0.90

# Two strings count as the same title/abstract above this similarity.
FUZZY_MATCH_RATIO = 0.95


def normalize(text: str | None) -> str:
    """Lowercase, drop punctuation, collapse whitespace."""

    if not text:
        return ""

    lowered = text.lower()

    without_punctuation = re.sub(r"[^\w\s]", " ", lowered)

    return " ".join(without_punctuation.split())


def similarity(left: str, right: str) -> float:
    if not left or not right:
        return 0.0

    return SequenceMatcher(None, left, right).ratio()


def canonical_role_sequence(paper: Paper) -> list[str]:
    """Ordered canonical roles, each counted once."""

    sequence: list[str] = []

    for section in paper.sections:
        role = section.canonical_role

        if role and role not in sequence:
            sequence.append(role)

    return sequence


# ---------------------------------------------------------------------------
# Structural invariants — no labels required
# ---------------------------------------------------------------------------


def check_invariants(paper: Paper) -> list[str]:
    """Return a list of invariant violations; empty means clean."""

    failures: list[str] = []

    full_text = paper.full_text

    for page in paper.pages:
        if page.page_number < 1 or page.page_number > paper.page_count:
            failures.append(f"page {page.page_number} is outside 1..{paper.page_count}")

    all_blocks = [block for page in paper.pages for block in page.blocks]

    for block in all_blocks:
        if block.page_number < 1:
            failures.append(f"block {block.block_id} has no page number")

        if block.end_char <= block.start_char:
            failures.append(f"block {block.block_id} has an empty or reversed span")

        elif full_text[block.start_char : block.end_char] != block.text:
            failures.append(f"block {block.block_id} offsets do not round-trip")

    for section in paper.sections:
        if section.end_char < section.start_char:
            failures.append(f"section {section.section_id} has a reversed span")

        if section.page_start > section.page_end:
            failures.append(f"section {section.section_id} has a reversed page range")

        if section.end_char > len(full_text):
            failures.append(f"section {section.section_id} span exceeds the full text")

    sections_by_id = {section.section_id: section for section in paper.sections}

    for chunk in paper.chunks:
        section = sections_by_id.get(chunk.section_id)

        if section is None:
            failures.append(f"chunk {chunk.chunk_id} references an unknown section")
            continue

        if chunk.start_char < section.start_char or chunk.end_char > section.end_char:
            failures.append(f"chunk {chunk.chunk_id} escapes its section span")

        if chunk.page_start < 1 or chunk.page_end > paper.page_count:
            failures.append(
                f"chunk {chunk.chunk_id} page range "
                f"{chunk.page_start}-{chunk.page_end} is outside the paper"
            )

        if full_text[chunk.start_char : chunk.end_char].strip() != chunk.text.strip():
            failures.append(f"chunk {chunk.chunk_id} offsets do not round-trip")

    return failures


# ---------------------------------------------------------------------------
# Accuracy against gold labels
# ---------------------------------------------------------------------------


def load_gold(
    paper_id: str,
    gold_dir: str | Path = DEFAULT_GOLD_DIR,
) -> dict | None:
    """Return a verified gold label, or None if missing or unverified."""

    path = Path(gold_dir) / f"{paper_id}.json"

    if not path.exists():
        return None

    label = json.loads(path.read_text(encoding="utf-8"))

    if not label.get("verified"):
        return None

    return label


def score_title(paper: Paper, gold: dict) -> bool | None:
    expected = gold.get("title")

    if not expected:
        return None

    return similarity(normalize(paper.title), normalize(expected)) >= FUZZY_MATCH_RATIO


def score_abstract(paper: Paper, gold: dict) -> bool | None:
    expected_prefix = gold.get("abstract_prefix")

    if not expected_prefix:
        return None

    detected = normalize(paper.abstract)
    expected = normalize(expected_prefix)

    if not detected:
        return False

    if expected in detected:
        return True

    # Allow small parser-side character noise at the head of the abstract.
    window = detected[: len(expected)]

    return similarity(window, expected) >= FUZZY_MATCH_RATIO


def score_sections(paper: Paper, gold: dict) -> tuple[bool, list[str], list[str]] | None:
    expected_roles = gold.get("canonical_roles")

    if not expected_roles:
        return None

    detected = canonical_role_sequence(paper)

    missing = [role for role in expected_roles if role not in detected]
    extra = [role for role in detected if role not in expected_roles]

    return detected == list(expected_roles), missing, extra


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def _rate(correct: int, total: int) -> str:
    if not total:
        return "  n/a  (no labels)"

    return f"{correct / total:6.1%}  ({correct}/{total})"


def _verdict(rate: float | None, threshold: float) -> str:
    if rate is None:
        return "SKIP"

    return "PASS" if rate >= threshold else "FAIL"


def run(
    store_dir: str | Path = DEFAULT_STORE_DIR,
    gold_dir: str | Path = DEFAULT_GOLD_DIR,
) -> int:
    """Print the stage-1 report. Returns a process exit code."""

    papers = list(iter_papers(store_dir))

    if not papers:
        print(f"No stored papers in {store_dir}.")
        print("Parse some PDFs first:  research-paper-ai process <pdf> --save")
        return 1

    title_correct = title_total = 0
    abstract_correct = abstract_total = 0
    sections_correct = sections_total = 0

    invariant_failures: dict[str, list[str]] = {}
    unlabelled: list[str] = []

    print("=" * 78)
    print("STAGE 1 CHECK")
    print("=" * 78)
    print(f"Papers: {len(papers)}   store: {store_dir}   gold: {gold_dir}")
    print()

    for paper in papers:
        failures = check_invariants(paper)

        if failures:
            invariant_failures[paper.paper_id] = failures

        gold = load_gold(paper.paper_id, gold_dir)

        label = f"{paper.filename} ({paper.paper_id})"

        if gold is None:
            unlabelled.append(label)
            status = "no verified gold label"

        else:
            outcomes = []

            title_result = score_title(paper, gold)

            if title_result is not None:
                title_total += 1
                title_correct += title_result
                outcomes.append(f"title {'ok' if title_result else 'WRONG'}")

            abstract_result = score_abstract(paper, gold)

            if abstract_result is not None:
                abstract_total += 1
                abstract_correct += abstract_result
                outcomes.append(f"abstract {'ok' if abstract_result else 'WRONG'}")

            section_result = score_sections(paper, gold)

            if section_result is not None:
                matched, missing, extra = section_result

                sections_total += 1
                sections_correct += matched

                detail = "ok"

                if not matched:
                    parts = []

                    if missing:
                        parts.append(f"missing {', '.join(missing)}")

                    if extra:
                        parts.append(f"extra {', '.join(extra)}")

                    detail = "WRONG" + (f" ({'; '.join(parts)})" if parts else "")

                outcomes.append(f"sections {detail}")

            status = " | ".join(outcomes) or "gold label has no scorable fields"

        marker = "x" if failures else " "

        print(f"[{marker}] {label}")
        print(f"      {status}")

        if failures:
            for failure in failures:
                print(f"      INVARIANT: {failure}")

        if paper.warnings:
            print(f"      {len(paper.warnings)} extraction warning(s)")

    title_rate = title_correct / title_total if title_total else None
    abstract_rate = abstract_correct / abstract_total if abstract_total else None
    sections_rate = sections_correct / sections_total if sections_total else None

    print()
    print("=" * 78)
    print("EXIT CRITERIA")
    print("=" * 78)

    print(
        f"Title       >= {TITLE_THRESHOLD:.0%}   "
        f"{_rate(title_correct, title_total)}   "
        f"{_verdict(title_rate, TITLE_THRESHOLD)}"
    )
    print(
        f"Abstract    >= {ABSTRACT_THRESHOLD:.0%}   "
        f"{_rate(abstract_correct, abstract_total)}   "
        f"{_verdict(abstract_rate, ABSTRACT_THRESHOLD)}"
    )
    print(
        f"Sections    >= {SECTION_THRESHOLD:.0%}   "
        f"{_rate(sections_correct, sections_total)}   "
        f"{_verdict(sections_rate, SECTION_THRESHOLD)}"
    )

    clean = len(papers) - len(invariant_failures)

    print(
        f"Invariants  == 100%   {_rate(clean, len(papers))}   "
        f"{'PASS' if not invariant_failures else 'FAIL'}"
    )

    print()

    if unlabelled:
        print(f"{len(unlabelled)} paper(s) without a verified gold label:")

        for label in unlabelled:
            print(f"  - {label}")

        print("Bootstrap templates with:  research-paper-ai check --init-gold")
        print()

    # The plan wants 20 papers across >=3 publishers; a passing rate on a
    # handful of papers is not the criterion being met.
    if title_total and title_total < 20:
        print(
            f"NOTE: scored on {title_total} paper(s). The stage-1 criterion is "
            "20 papers spanning at least 3 publishers, so this is a smoke "
            "test, not the exit criterion."
        )
        print()

    failed = bool(invariant_failures)

    for rate, threshold in (
        (title_rate, TITLE_THRESHOLD),
        (abstract_rate, ABSTRACT_THRESHOLD),
        (sections_rate, SECTION_THRESHOLD),
    ):
        if rate is not None and rate < threshold:
            failed = True

    if not any((title_total, abstract_total, sections_total)):
        print("No verified gold labels, so accuracy was not measured.")

        # Unmeasured is not the same as passing: stage 1 stays unproven
        # until somebody labels papers, so this is a non-zero exit.
        return 1

    return 1 if failed else 0


def init_gold(
    store_dir: str | Path = DEFAULT_STORE_DIR,
    gold_dir: str | Path = DEFAULT_GOLD_DIR,
) -> int:
    """Write an unverified gold template for every stored paper."""

    directory = Path(gold_dir)

    directory.mkdir(parents=True, exist_ok=True)

    written = 0
    skipped = 0

    for paper in iter_papers(store_dir):
        path = directory / f"{paper.paper_id}.json"

        if path.exists():
            skipped += 1
            continue

        abstract = (paper.abstract or "").strip()

        template = {
            "paper_id": paper.paper_id,
            "filename": paper.filename,
            "verified": False,
            "title": paper.title,
            "abstract_prefix": abstract[:200],
            "canonical_roles": canonical_role_sequence(paper),
        }

        path.write_text(
            json.dumps(template, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        written += 1

    print(f"Wrote {written} template(s) to {directory} ({skipped} already existed).")
    print()
    print("These are the PARSER'S OWN OUTPUT, not labels. For each file:")
    print("  1. open the PDF and correct title, abstract_prefix, canonical_roles")
    print('  2. set "verified": true')
    print("Unverified files are ignored when scoring.")

    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="research-paper-ai check",
        description="Measure stage-1 parsing against its exit criteria.",
    )

    parser.add_argument(
        "--store",
        type=Path,
        default=DEFAULT_STORE_DIR,
        help="Directory of normalized paper JSON.",
    )

    parser.add_argument(
        "--gold",
        type=Path,
        default=DEFAULT_GOLD_DIR,
        help="Directory of gold label JSON.",
    )

    parser.add_argument(
        "--init-gold",
        action="store_true",
        help="Write gold templates for stored papers, then exit.",
    )

    args = parser.parse_args(argv)

    if args.init_gold:
        return init_gold(args.store, args.gold)

    return run(args.store, args.gold)


if __name__ == "__main__":
    sys.exit(main())
