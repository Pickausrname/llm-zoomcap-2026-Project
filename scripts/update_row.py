"""
One-off manual row editor for data/knowledge.db.

Usage:
    python scripts/update_row.py <id> <column> <value>

Example:
    python scripts/update_row.py 1 manufacturer_name nexperia

Only intended for ad-hoc manual fixes during development. Goes through
src.db.knowledge_store.connect() so the FTS5/vec0 sync triggers fire
correctly (a bare sqlite3 CLI does not load the sqlite-vec extension the
triggers depend on).
"""

from __future__ import annotations

import sys
from pathlib import Path

# Running this file directly (not via `-m`) only puts scripts/ on sys.path,
# not the repo root, so `import src...` would otherwise fail regardless of
# the shell's current directory.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.db.knowledge_store import connect  # noqa: E402

_ALLOWED_COLUMNS = {"component_type", "manufacturer_name", "part_number", "search_text"}


def main() -> None:
    if len(sys.argv) != 4:
        print(__doc__)
        sys.exit(1)

    row_id, column, value = sys.argv[1], sys.argv[2], sys.argv[3]
    if column not in _ALLOWED_COLUMNS:
        print(f"Column must be one of {sorted(_ALLOWED_COLUMNS)}, got {column!r}")
        sys.exit(1)

    with connect() as conn:
        conn.execute(f"UPDATE master_table SET {column} = ? WHERE id = ?", (value, row_id))
        conn.commit()
        row = conn.execute(
            "SELECT id, component_type, manufacturer_name, part_number FROM master_table WHERE id = ?",
            (row_id,),
        ).fetchone()
        print(dict(row) if row else f"No row with id={row_id}")


if __name__ == "__main__":
    main()
