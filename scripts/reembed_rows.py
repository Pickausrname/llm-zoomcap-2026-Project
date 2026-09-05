"""
Re-embed search_vector for specific master_table rows from their current
search_text -- for use after manually editing search_text by hand (e.g.
via scripts/update_row.py) so the vector index stays in sync.

Usage:
    python scripts/reembed_rows.py <id> [<id> ...]

Example:
    python scripts/reembed_rows.py 4 6 7 8 9 10

Goes through src.db.knowledge_store.connect() so the master_vec sync
trigger (master_vec_after_update) fires correctly on the UPDATE. Rows
with empty search_text get search_vector set to NULL (matching ingestion
behavior), which the trigger then correctly omits from master_vec.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Running this file directly (not via `-m`) only puts scripts/ on sys.path,
# not the repo root, so `import src...` would otherwise fail regardless of
# the shell's current directory.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import sqlite_vec  # noqa: E402

from src.db.knowledge_store import connect  # noqa: E402
from src.models_onnx.embedder import embed  # noqa: E402


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    row_ids = [int(arg) for arg in sys.argv[1:]]

    with connect() as conn:
        for row_id in row_ids:
            row = conn.execute(
                "SELECT id, part_number, search_text FROM master_table WHERE id = ?",
                (row_id,),
            ).fetchone()
            if row is None:
                print(f"id={row_id}: no such row, skipping.")
                continue

            search_text = row["search_text"] or ""
            if not search_text:
                conn.execute(
                    "UPDATE master_table SET search_vector = NULL WHERE id = ?",
                    (row_id,),
                )
                print(f"id={row_id} ({row['part_number']}): empty search_text, vector set to NULL.")
                continue

            vector = embed([search_text])[0].tolist()
            serialized_vector = sqlite_vec.serialize_float32(vector)
            conn.execute(
                "UPDATE master_table SET search_vector = ? WHERE id = ?",
                (serialized_vector, row_id),
            )
            print(f"id={row_id} ({row['part_number']}): re-embedded from {len(search_text)}-char search_text.")

        conn.commit()

    with connect() as conn:
        n_vec = conn.execute("SELECT COUNT(*) FROM master_vec").fetchone()[0]
        print(f"master_vec now has {n_vec} rows.")


if __name__ == "__main__":
    main()
