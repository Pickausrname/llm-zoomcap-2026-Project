"""
dlt resource definitions for the MOSFET datasheet ingestion pipeline.

Discovers PDF datasheets under `config.RAW_DIR`, extracts the six
required fields from each (spec.md section 8.4), embeds `search_text`
via the local ONNX embedder (spec.md section 7.2), and yields exactly
the five fields persisted to `master_table`: `component_type`,
`manufacturer_name`, `part_number`, `search_text`, `search_vector`.
`id` is never yielded here -- it is the SQLite autoincrement primary
key assigned on insert (spec.md section 5.1, section 9 Field Mapping).
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from pathlib import Path
from typing import TypedDict

import dlt

from src.config import RAW_DIR
from src.ingestion.pdf_extractor import extract_first_page_fields
from src.models_onnx.embedder import embed

logger = logging.getLogger(__name__)

__all__ = ["MasterTableRecord", "discover_pdf_paths", "datasheet_records"]


class MasterTableRecord(TypedDict):
    """The exact five fields written to `master_table` by the custom destination."""

    component_type: str
    manufacturer_name: str
    part_number: str
    search_text: str
    search_vector: list[float] | None


def discover_pdf_paths(raw_dir: Path = RAW_DIR) -> list[Path]:
    """
    Glob `raw_dir` strictly for `*.pdf` files.

    Args:
        raw_dir: Directory to search. Defaults to `config.RAW_DIR`.

    Returns:
        Sorted list of matching PDF paths (empty if `raw_dir` is missing
        or contains no PDFs).
    """
    if not raw_dir.exists():
        logger.warning("RAW_DIR %s does not exist; no PDFs to ingest.", raw_dir)
        return []
    return sorted(raw_dir.glob("*.pdf"))


def _embed_search_text(search_text: str) -> list[float] | None:
    """Embed `search_text` via the ONNX embedder, or None if there is nothing to embed."""
    if not search_text:
        return None
    vector = embed([search_text])
    return vector[0].tolist()


@dlt.resource(name="master_table", write_disposition="append")
def datasheet_records(raw_dir: Path = RAW_DIR) -> Iterator[MasterTableRecord]:
    """
    Yield one `master_table` record per MOSFET datasheet PDF under `raw_dir`.

    A single malformed PDF (unreadable file, failed embedding, etc.) is
    logged and skipped rather than aborting the whole run (spec.md
    section 8.5).

    Args:
        raw_dir: Directory containing source PDFs. Defaults to
            `config.RAW_DIR`.

    Yields:
        `MasterTableRecord` dictionaries containing only the five fields
        persisted to `master_table` -- no `id`.
    """
    pdf_paths = discover_pdf_paths(raw_dir)
    logger.info("Discovered %d PDF datasheet(s) under %s.", len(pdf_paths), raw_dir)

    for pdf_path in pdf_paths:
        try:
            fields = extract_first_page_fields(pdf_path)
        except Exception:
            logger.warning(
                "Extraction failed for %s; skipping this file.", pdf_path.name, exc_info=True
            )
            continue

        try:
            search_vector = _embed_search_text(fields["search_text"])
        except Exception:
            logger.warning(
                "Embedding failed for %s; storing without a vector.", pdf_path.name, exc_info=True
            )
            search_vector = None

        yield {
            "component_type": fields["component_type"],
            "manufacturer_name": fields["manufacturer_name"],
            "part_number": fields["part_number"],
            "search_text": fields["search_text"],
            "search_vector": search_vector,
        }
