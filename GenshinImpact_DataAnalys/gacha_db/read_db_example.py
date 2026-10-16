"""Small read-only pandas/Matplotlib example. Never loads the whole database."""

from __future__ import annotations

import argparse
from pathlib import Path
import sqlite3

import pandas as pd


HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=HERE / "genshin_gacha.db")
    parser.add_argument("--plot", action="store_true", help="Save a small pool-count chart next to this script")
    args = parser.parse_args()
    path = args.db.resolve()
    if not path.is_file():
        raise SystemExit(f"Database not found: {path}")
    with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as connection:
        overview = pd.read_sql_query("SELECT * FROM v_dataset_summary ORDER BY dataset", connection)
        summary = pd.read_sql_query("SELECT * FROM v_pool_summary ORDER BY dataset,gacha_type", connection)
        print("Dataset overview:")
        print(overview.to_string(index=False))
        print("\nPool summary (rates describe this sample):")
        print(summary.to_string(index=False))

        player_id = connection.execute(
            "SELECT min(player_id) FROM players WHERE dataset_id=?", (3,)
        ).fetchone()[0]
        sql = """
            SELECT player_id, player_key, name, gacha_type, pool_group, rank_type,
                   gacha_id, gacha_time, pool_seq, source_file, source_row
            FROM v_pulls
            WHERE player_id=?
            ORDER BY pool_group, pool_seq
        """
        # Filter first, then read bounded chunks. Keep IDs as strings throughout.
        chunks = pd.read_sql_query(
            sql, connection, params=(player_id,), chunksize=100_000,
            parse_dates=["gacha_time"], dtype={"gacha_id": "string"},
        )
        for number, chunk in enumerate(chunks, 1):
            print(f"\nExample account, chunk {number}: {len(chunk):,} records")
            print(chunk.head(10).to_string(index=False))
            # Put later cleaning / feature extraction here; write derived data
            # to a separate file or a new table in a separate analysis database.

    if args.plot:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        pivot = summary.pivot(index="gacha_type", columns="dataset", values="pulls").fillna(0)
        pivot.index = [str(value) for value in pivot.index]
        axes = pivot.plot.bar(figsize=(9, 5), color=["#7c9db8", "#dba75e"])
        axes.set(xlabel="Original gacha type", ylabel="Observed pulls", title="Genshin gacha dataset coverage")
        axes.grid(axis="y", alpha=0.2)
        axes.set_axisbelow(True)
        plt.xticks(rotation=0)
        plt.tight_layout()
        output = HERE / "pool_counts_example.png"
        plt.savefig(output, dpi=160)
        plt.close()
        print(f"\nChart saved: {output}")


if __name__ == "__main__":
    main()
