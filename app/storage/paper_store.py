"""Filesystem store for normalized ``Paper`` objects.

One JSON file per paper, named by ``paper_id``, so a parsed corpus can be
reused without reparsing every PDF. The plan keeps source documents and
normalized JSON on the filesystem until a database is actually needed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

from app.models.paper import Paper

DEFAULT_STORE_DIR = Path("data/normalized_papers")


class PaperStoreError(Exception):
    """Raised when a paper cannot be read from or written to the store."""


def paper_path(
    paper_id: str,
    store_dir: str | Path = DEFAULT_STORE_DIR,
) -> Path:
    return Path(store_dir) / f"{paper_id}.json"


def save_paper(
    paper: Paper,
    store_dir: str | Path = DEFAULT_STORE_DIR,
) -> Path:
    """Write ``paper`` to the store, replacing any existing copy."""

    destination = paper_path(paper.paper_id, store_dir)

    destination.parent.mkdir(parents=True, exist_ok=True)

    # Write to a temporary file first so an interrupted run cannot leave a
    # half-written paper behind for the eval harness to read.
    temporary = destination.with_suffix(".json.tmp")

    temporary.write_text(
        paper.model_dump_json(indent=2),
        encoding="utf-8",
    )

    temporary.replace(destination)

    return destination


def load_paper(
    paper_id: str,
    store_dir: str | Path = DEFAULT_STORE_DIR,
) -> Paper:
    source = paper_path(paper_id, store_dir)

    if not source.exists():
        raise PaperStoreError(f"No stored paper with id {paper_id!r} in {store_dir}")

    return load_paper_file(source)


def load_paper_file(path: str | Path) -> Paper:
    source = Path(path)

    try:
        return Paper.model_validate_json(source.read_text(encoding="utf-8"))
    except Exception as exc:
        raise PaperStoreError(f"Could not read stored paper {source}: {exc}") from exc


def iter_papers(
    store_dir: str | Path = DEFAULT_STORE_DIR,
) -> Iterator[Paper]:
    """Yield every stored paper, ordered by filename for reproducible runs."""

    directory = Path(store_dir)

    if not directory.exists():
        return

    for path in sorted(directory.glob("*.json")):
        yield load_paper_file(path)


def stored_paper_ids(
    store_dir: str | Path = DEFAULT_STORE_DIR,
) -> list[str]:
    directory = Path(store_dir)

    if not directory.exists():
        return []

    return sorted(path.stem for path in directory.glob("*.json"))
