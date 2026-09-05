"""
dlt ingestion pipeline entrypoint (`make ingest`; spec.md section 8.1).

Loads MOSFET datasheet records (`src.ingestion.resources.datasheet_records`)
through a custom `@dlt.destination` sink that writes directly to
`master_table` in `data/knowledge.db` via hand-written SQL
(`src.db.knowledge_store.connect`). A custom destination is required
here rather than a standard dlt SQL destination: dlt's default SQL
destinations infer and mutate the target schema from the data it loads,
which would fight the hand-authored `master_table` / `master_fts` /
`master_vec` schema and its sync triggers, and dlt has no native
understanding of `sqlite-vec`'s BLOB vector encoding. Writing raw SQL
ourselves keeps the schema untouched and lets us serialize embeddings
with `sqlite_vec.serialize_float32` before binding them.
"""

from __future__ import annotations

import logging

import dlt
import sqlite_vec
from dlt.common.schema import TTableSchema
from dlt.common.typing import TDataItems

from src.db.knowledge_store import connect, init_db
from src.ingestion.resources import datasheet_records

logger = logging.getLogger(__name__)

_INSERT_SQL = (
    "INSERT INTO master_table "
    "(component_type, manufacturer_name, part_number, search_text, search_vector) "
    "VALUES (?, ?, ?, ?, ?)"
)

# batch_size=1: master_table has no natural unique key to upsert on, so if a
# retried batch were larger than one row we could re-insert already-committed
# rows as duplicates after a partial failure (see dlt custom destination docs
# on batch atomicity). One row per call keeps each insert independently retryable.
# loader_file_format="typed-jsonl": the installed dlt version (1.30.0) rejects
# the plain "jsonl" format for custom destinations at runtime (raises
# `ValueErrorWithKnownValues: Received invalid value preferred_format=jsonl.
# Valid values are: ['typed-jsonl', 'parquet']`) -- "typed-jsonl" is dlt's
# replacement that preserves the same per-row-dict semantics this destination
# function expects.
@dlt.destination(name="knowledge_store_destination", batch_size=1, loader_file_format="typed-jsonl")
def knowledge_store_destination(items: TDataItems, table: TTableSchema) -> None:
    """
    Write a batch of `master_table` items straight into `data/knowledge.db`.

    Bypasses dlt's SQL client entirely so the hand-authored schema in
    `src.db.knowledge_store` (columns, FTS5 index, vector index, sync
    triggers) is never inferred or altered by dlt.

    Args:
        items: One or more `master_table` row dicts for this batch.
        table: dlt table schema metadata for the current call; only
            `master_table` items are expected here.
    """
    if table.get("name") != "master_table":
        logger.debug("Ignoring items for unexpected table %s.", table.get("name"))
        return

    with connect() as conn:
        for record in items:
            raw_vector = record.get("search_vector")
            serialized_vector = (
                sqlite_vec.serialize_float32(raw_vector) if raw_vector is not None else None
            )
            conn.execute(
                _INSERT_SQL,
                (
                    record.get("component_type", ""),
                    record.get("manufacturer_name", ""),
                    record.get("part_number", ""),
                    record.get("search_text", ""),
                    serialized_vector,
                ),
            )
        conn.commit()


def run() -> None:
    """Initialize the knowledge base schema and run the dlt ingestion pipeline."""
    init_db()

    pipeline = dlt.pipeline(
        pipeline_name="mosfet_datasheet_ingestion",
        destination=knowledge_store_destination,
        dataset_name="knowledge_store",
    )
    load_info = pipeline.run(datasheet_records())
    logger.info("dlt load complete: %s", load_info)
    print(load_info)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()
