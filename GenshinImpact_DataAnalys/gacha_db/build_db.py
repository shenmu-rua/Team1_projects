"""Build a traceable SQLite database from both local GI gacha datasets.

Uses only the Python standard library. The split encrypted ZIP is read directly;
no extraction, network request, or modification of the source tree is needed.
"""

from __future__ import annotations

import argparse
import bisect
import csv
import hashlib
import io
import json
import mimetypes
import os
from pathlib import Path
import sqlite3
import time
import zipfile
from collections import Counter, defaultdict
from datetime import datetime, timezone


HERE = Path(__file__).resolve().parent
DEFAULT_SOURCE = HERE.parent / "GI_gacha_dataset-main"
SCHEMA_VERSION = 1
POOLS = {
    100: (100, "新手祈愿", "新手祈愿"),
    200: (200, "常驻祈愿", "常驻祈愿"),
    301: (301, "角色活动祈愿1", "角色活动祈愿"),
    302: (302, "武器活动祈愿", "武器活动祈愿"),
    400: (301, "角色活动祈愿2", "角色活动祈愿"),
}
HEADER_02 = ["抽卡时间", "名称", "类别", "星级"]
HEADER_03 = ["name", "gacha_type", "item_type", "rank_type", "gacha_id", "gacha_time"]
INDEX_FIELDS = [
    "newbee_pull", "newbee_5", "stander_pull", "stander_5", "character_pull",
    "character_5", "weapon_pull", "weapon_5", "total_pull", "total_5",
    "begin_time", "end_time", "record_days",
]


def log(message):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {message}", flush=True)


def json_text(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class SplitZipReader(io.RawIOBase):
    """Seekable concatenation of .zip.001, .zip.002, ... without disk copies."""

    def __init__(self, parts):
        super().__init__()
        self.parts = list(parts)
        self.streams = [part.open("rb") for part in self.parts]
        self.offsets = [0]
        for part in self.parts:
            self.offsets.append(self.offsets[-1] + part.stat().st_size)
        self.position = 0

    def readable(self):
        return True

    def seekable(self):
        return True

    def tell(self):
        return self.position

    def seek(self, offset, whence=io.SEEK_SET):
        if whence == io.SEEK_SET:
            position = offset
        elif whence == io.SEEK_CUR:
            position = self.position + offset
        elif whence == io.SEEK_END:
            position = self.offsets[-1] + offset
        else:
            raise ValueError("Invalid whence")
        if position < 0:
            raise ValueError("Negative seek position")
        self.position = position
        return position

    def read(self, size=-1):
        remaining = max(0, self.offsets[-1] - self.position)
        if size >= 0:
            remaining = min(remaining, size)
        chunks = []
        while remaining:
            index = bisect.bisect_right(self.offsets, self.position) - 1
            stream = self.streams[index]
            stream.seek(self.position - self.offsets[index])
            size_here = min(remaining, self.offsets[index + 1] - self.position)
            chunk = stream.read(size_here)
            if not chunk:
                raise EOFError(f"Truncated archive part: {self.parts[index]}")
            chunks.append(chunk)
            self.position += len(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)

    def close(self):
        for stream in self.streams:
            stream.close()
        super().close()


SCHEMA = """
PRAGMA user_version = 1;
CREATE TABLE metadata (key TEXT PRIMARY KEY, value_json TEXT NOT NULL);
CREATE TABLE datasets (
    dataset_id INTEGER PRIMARY KEY, code TEXT UNIQUE NOT NULL,
    description TEXT NOT NULL, documented_players INTEGER,
    documented_pulls INTEGER, documented_cutoff TEXT
);
CREATE TABLE gacha_types (
    gacha_type INTEGER PRIMARY KEY, pool_group INTEGER NOT NULL,
    pool_name TEXT NOT NULL, pool_group_name TEXT NOT NULL
);
CREATE TABLE source_files (
    source_file_id INTEGER PRIMARY KEY,
    dataset_id INTEGER REFERENCES datasets,
    player_id INTEGER REFERENCES players,
    relative_path TEXT UNIQUE NOT NULL, source_kind TEXT NOT NULL,
    container_parts_json TEXT, byte_size INTEGER NOT NULL, sha256 TEXT NOT NULL,
    encoding TEXT, header_json TEXT, data_rows INTEGER NOT NULL DEFAULT 0,
    imported_rows INTEGER NOT NULL DEFAULT 0, rejected_rows INTEGER NOT NULL DEFAULT 0,
    blank_rows INTEGER NOT NULL DEFAULT 0, normalized_rows INTEGER NOT NULL DEFAULT 0,
    min_time TEXT, max_time TEXT, status TEXT NOT NULL
);
CREATE TABLE players (
    player_id INTEGER PRIMARY KEY, dataset_id INTEGER NOT NULL REFERENCES datasets,
    player_key TEXT NOT NULL, uid_suffix TEXT,
    UNIQUE(dataset_id, player_key)
);
CREATE TABLE items (
    item_id INTEGER PRIMARY KEY, name TEXT NOT NULL,
    item_type INTEGER NOT NULL CHECK(item_type IN (0, 1)),
    rank_type INTEGER NOT NULL CHECK(rank_type IN (3, 4, 5)),
    UNIQUE(name, item_type, rank_type)
);
CREATE TABLE pulls (
    pull_id INTEGER PRIMARY KEY,
    player_id INTEGER NOT NULL REFERENCES players,
    source_file_id INTEGER NOT NULL REFERENCES source_files,
    source_row INTEGER NOT NULL CHECK(source_row >= 2),
    item_id INTEGER NOT NULL REFERENCES items,
    gacha_type INTEGER NOT NULL REFERENCES gacha_types,
    pool_group INTEGER GENERATED ALWAYS AS
        (CASE WHEN gacha_type = 400 THEN 301 ELSE gacha_type END) VIRTUAL,
    pool_seq INTEGER NOT NULL CHECK(pool_seq >= 1),
    gacha_id TEXT, gacha_time TEXT NOT NULL
);
CREATE TABLE rejected_rows (
    reject_id INTEGER PRIMARY KEY, source_file_id INTEGER NOT NULL REFERENCES source_files,
    source_row INTEGER NOT NULL, reason TEXT NOT NULL, raw_fields_json TEXT NOT NULL
);
CREATE TABLE quality_issues (
    issue_id INTEGER PRIMARY KEY, source_file_id INTEGER NOT NULL REFERENCES source_files,
    source_row INTEGER, issue_code TEXT NOT NULL, details_json TEXT NOT NULL
);
CREATE TABLE resource_assets (
    source_file_id INTEGER PRIMARY KEY REFERENCES source_files,
    mime_type TEXT NOT NULL, description TEXT NOT NULL, content BLOB NOT NULL
);
CREATE TABLE legacy_player_index (
    player_id INTEGER PRIMARY KEY REFERENCES players,
    source_file_id INTEGER NOT NULL REFERENCES source_files, source_row INTEGER NOT NULL,
    uid TEXT NOT NULL,
    newbee_pull INTEGER NOT NULL, newbee_5 INTEGER NOT NULL,
    stander_pull INTEGER NOT NULL, stander_5 INTEGER NOT NULL,
    character_pull INTEGER NOT NULL, character_5 INTEGER NOT NULL,
    weapon_pull INTEGER NOT NULL, weapon_5 INTEGER NOT NULL,
    total_pull INTEGER NOT NULL, total_5 INTEGER NOT NULL,
    begin_time TEXT NOT NULL, end_time TEXT NOT NULL, record_days INTEGER NOT NULL
);
CREATE TABLE legacy_histograms (
    source_file_id INTEGER NOT NULL REFERENCES source_files,
    pool_group INTEGER NOT NULL, metric TEXT NOT NULL,
    draw_index INTEGER NOT NULL, frequency INTEGER NOT NULL,
    PRIMARY KEY(source_file_id, metric, draw_index)
) WITHOUT ROWID;
CREATE TABLE summary_pool (
    dataset_id INTEGER NOT NULL REFERENCES datasets,
    gacha_type INTEGER NOT NULL REFERENCES gacha_types,
    pulls INTEGER NOT NULL, star3 INTEGER NOT NULL, star4 INTEGER NOT NULL,
    star5 INTEGER NOT NULL, first_time TEXT NOT NULL, last_time TEXT NOT NULL,
    PRIMARY KEY(dataset_id, gacha_type)
) WITHOUT ROWID;
CREATE TABLE summary_player_pool (
    player_id INTEGER NOT NULL REFERENCES players, pool_group INTEGER NOT NULL,
    pulls INTEGER NOT NULL, star3 INTEGER NOT NULL, star4 INTEGER NOT NULL,
    star5 INTEGER NOT NULL, first_time TEXT NOT NULL, last_time TEXT NOT NULL,
    PRIMARY KEY(player_id, pool_group)
) WITHOUT ROWID;
CREATE TABLE summary_daily (
    dataset_id INTEGER NOT NULL REFERENCES datasets, pull_date TEXT NOT NULL,
    gacha_type INTEGER NOT NULL REFERENCES gacha_types,
    rank_type INTEGER NOT NULL, item_type INTEGER NOT NULL, pulls INTEGER NOT NULL,
    PRIMARY KEY(dataset_id, pull_date, gacha_type, rank_type, item_type)
) WITHOUT ROWID;
CREATE TABLE summary_item (
    dataset_id INTEGER NOT NULL REFERENCES datasets,
    gacha_type INTEGER NOT NULL REFERENCES gacha_types,
    item_id INTEGER NOT NULL REFERENCES items, pulls INTEGER NOT NULL,
    PRIMARY KEY(dataset_id, gacha_type, item_id)
) WITHOUT ROWID;
CREATE VIEW v_pulls AS
SELECT r.pull_id, d.code AS dataset, p.player_id, p.player_key, p.uid_suffix,
       i.name, r.gacha_type, g.pool_name, r.pool_group, g.pool_group_name,
       i.item_type, CASE i.item_type WHEN 0 THEN '角色' ELSE '武器' END AS item_type_name,
       i.rank_type, r.gacha_id, r.gacha_time, r.pool_seq,
       r.source_file_id, f.relative_path AS source_file, r.source_row
FROM pulls AS r JOIN players AS p USING(player_id)
JOIN datasets AS d USING(dataset_id) JOIN items AS i USING(item_id)
JOIN gacha_types AS g USING(gacha_type)
JOIN source_files AS f USING(source_file_id);
CREATE VIEW v_pool_summary AS
SELECT d.code AS dataset, s.gacha_type, g.pool_name, g.pool_group,
       g.pool_group_name, s.pulls, s.star3, s.star4, s.star5,
       1.0*s.star5/s.pulls AS observed_star5_rate, s.first_time, s.last_time
FROM summary_pool AS s JOIN datasets AS d USING(dataset_id)
JOIN gacha_types AS g USING(gacha_type);
CREATE VIEW v_dataset_summary AS
SELECT d.code AS dataset,
       (SELECT count(*) FROM players AS p WHERE p.dataset_id=d.dataset_id) AS players,
       coalesce(sum(s.pulls),0) AS pulls, coalesce(sum(s.star5),0) AS star5,
       min(s.first_time) AS first_time, max(s.last_time) AS last_time
FROM datasets AS d LEFT JOIN summary_pool AS s USING(dataset_id)
GROUP BY d.dataset_id;
"""


def add_stats(mapping, key, star, timestamp):
    stats = mapping.get(key)
    if stats is None:
        stats = [0, 0, 0, 0, timestamp, timestamp]
        mapping[key] = stats
    stats[0] += 1
    stats[star - 2] += 1
    stats[4] = min(stats[4], timestamp)
    stats[5] = max(stats[5], timestamp)


class Builder:
    def __init__(self, connection, root):
        self.db = connection
        self.root = root
        self.players = {}
        self.items = {}
        self.sources = {}
        self.pool_stats = {}
        self.player_stats = {}
        self.daily = Counter()
        self.item_stats = Counter()
        self.total = 0
        self.rejected = 0
        self.empty_files = 0
        self.index_mismatches = 0
        self.commit_rows = 0
        self.previous_log = time.monotonic()

    def add_source(self, path, kind, data=None, container_parts=None):
        dataset_id = 2 if path.startswith("GI_gacha_dataset_02/") else (
            3 if path.startswith("GI_gacha_dataset_03/") else None)
        physical = self.root / path
        size = len(data) if data is not None else physical.stat().st_size
        digest = hashlib.sha256(data).hexdigest() if data is not None else sha256_file(physical)
        cursor = self.db.execute(
            """INSERT INTO source_files
               (dataset_id,relative_path,source_kind,container_parts_json,byte_size,sha256,status)
               VALUES(?,?,?,?,?,?,?)""",
            (dataset_id, path, kind, json_text(container_parts) if container_parts else None,
             size, digest, "pending" if kind == "pull_csv" else "stored"),
        )
        source_id = cursor.lastrowid
        self.sources[path] = source_id
        return source_id

    def issue(self, source_id, source_row, code, details):
        self.db.execute(
            "INSERT INTO quality_issues(source_file_id,source_row,issue_code,details_json) VALUES(?,?,?,?)",
            (source_id, source_row, code, json_text(details)),
        )

    def player(self, dataset_id, key):
        identity = (dataset_id, key)
        if identity not in self.players:
            cursor = self.db.execute(
                "INSERT INTO players(dataset_id,player_key,uid_suffix) VALUES(?,?,?)",
                (dataset_id, key, key[-4:] if dataset_id == 3 else None),
            )
            self.players[identity] = cursor.lastrowid
        return self.players[identity]

    def item(self, name, item_type, rank):
        identity = (name, item_type, rank)
        if identity not in self.items:
            cursor = self.db.execute(
                "INSERT INTO items(name,item_type,rank_type) VALUES(?,?,?)", identity)
            self.items[identity] = cursor.lastrowid
        return self.items[identity]

    def ingest(self, dataset_id, player_key, path, raw, forced_pool=None, parts=None):
        source_id = self.add_source(path, "pull_csv", raw, parts)
        player_id = self.player(dataset_id, player_key)
        self.db.execute("UPDATE source_files SET player_id=? WHERE source_file_id=?", (player_id, source_id))
        if not raw:
            self.db.execute("UPDATE source_files SET status='empty' WHERE source_file_id=?", (source_id,))
            self.empty_files += 1
            return
        try:
            text = raw.decode("utf-8-sig")
            encoding = "utf-8-sig"
        except UnicodeDecodeError:
            text = raw.decode("gb18030")
            encoding = "gb18030"
            self.issue(source_id, None, "fallback_encoding", {"encoding": encoding})
        reader = csv.reader(io.StringIO(text, newline=""), strict=True)
        header = next(reader)
        wanted = HEADER_02 if dataset_id == 2 else HEADER_03
        if header != wanted:
            raise ValueError(f"Unexpected CSV header in {path}: {header!r}")
        records = []
        counts = Counter()
        seen_ids = {}
        last_time = None
        for fields in reader:
            source_row = reader.line_num
            if not fields or not any(field.strip() for field in fields):
                counts["blank"] += 1
                continue
            counts["data"] += 1
            original_fields = fields
            fields = [field.strip() for field in fields]
            if fields != original_fields:
                counts["normalized"] += 1
                self.issue(source_id, source_row, "trimmed_whitespace", {"raw_fields": original_fields})
            try:
                if len(fields) != len(wanted):
                    raise ValueError(f"column_count: expected {len(wanted)}, got {len(fields)}")
                if dataset_id == 2:
                    timestamp, name, item_label, rank = fields
                    item_type = {"角色": 0, "武器": 1}[item_label]
                    pool = forced_pool
                    gacha_id = None
                else:
                    name, pool, item_type, rank, gacha_id, timestamp = fields
                    pool, item_type = int(pool), int(item_type)
                    if not gacha_id or not gacha_id.isascii() or not gacha_id.isdecimal():
                        raise ValueError("gacha_id must be nonempty decimal text")
                rank = int(rank)
                if not name:
                    raise ValueError("empty item name")
                if item_type not in (0, 1) or rank not in (3, 4, 5) or pool not in POOLS:
                    raise ValueError("unknown item_type/rank_type/gacha_type")
                if (len(timestamp) != 19 or timestamp[10] != " " or
                        datetime.fromisoformat(timestamp).strftime("%Y-%m-%d %H:%M:%S") != timestamp):
                    raise ValueError("invalid timestamp (expected YYYY-MM-DD HH:MM:SS)")
            except (ValueError, KeyError) as exc:
                self.db.execute(
                    "INSERT INTO rejected_rows(source_file_id,source_row,reason,raw_fields_json) VALUES(?,?,?,?)",
                    (source_id, source_row, str(exc), json_text(original_fields)),
                )
                counts["rejected"] += 1
                self.rejected += 1
                continue
            if last_time is not None and timestamp < last_time:
                self.issue(source_id, source_row, "source_time_decreases", {"previous_time": last_time, "time": timestamp})
            last_time = timestamp
            # The README only specifies an upper cutoff, not a lower bound.
            if dataset_id == 3 and timestamp > "2022-07-26 23:59:59":
                self.issue(source_id, source_row, "outside_documented_date_range", {"time": timestamp})
            if item_type == 0 and rank == 3:
                self.issue(source_id, source_row, "three_star_character", {"name": name})
            signature = (name, pool, item_type, rank, timestamp)
            if gacha_id is not None:
                if gacha_id in seen_ids:
                    first_row, first_signature = seen_ids[gacha_id]
                    code = "duplicate_gacha_id" if signature == first_signature else "conflicting_gacha_id"
                    self.issue(source_id, source_row, code, {"gacha_id": gacha_id, "first_source_row": first_row})
                else:
                    seen_ids[gacha_id] = (source_row, signature)
            item_id = self.item(name, item_type, rank)
            records.append([player_id, source_id, source_row, item_id, pool, 0, gacha_id, timestamp])
            group = POOLS[pool][0]
            add_stats(self.pool_stats, (dataset_id, pool), rank, timestamp)
            add_stats(self.player_stats, (player_id, group), rank, timestamp)
            self.daily[(dataset_id, timestamp[:10], pool, rank, item_type)] += 1
            self.item_stats[(dataset_id, pool, item_id)] += 1
        sequences = Counter()
        for record in sorted(records, key=lambda r: (r[7], int(r[6]) if r[6] else 0, r[2])):
            group = POOLS[record[4]][0]
            sequences[group] += 1
            record[5] = sequences[group]
        self.db.executemany(
            """INSERT INTO pulls(player_id,source_file_id,source_row,item_id,gacha_type,
                                 pool_seq,gacha_id,gacha_time) VALUES(?,?,?,?,?,?,?,?)""", records)
        timestamps = [record[7] for record in records]
        self.db.execute(
            """UPDATE source_files SET encoding=?,header_json=?,data_rows=?,imported_rows=?,
               rejected_rows=?,blank_rows=?,normalized_rows=?,min_time=?,max_time=?,status=?
               WHERE source_file_id=?""",
            (encoding, json_text(header), counts["data"], len(records), counts["rejected"],
             counts["blank"], counts["normalized"], min(timestamps, default=None),
             max(timestamps, default=None), "imported" if records else ("rejected" if counts["rejected"] else "header_only"), source_id),
        )
        self.total += len(records)
        self.commit_rows += len(records)
        if self.commit_rows >= 100_000:
            self.db.commit()
            self.commit_rows = 0

    def store_assets(self):
        for path in sorted(self.root.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(self.root).as_posix()
            if path.suffix.lower() == ".csv" and relative.startswith("GI_gacha_dataset_02/"):
                continue
            if relative in self.sources:
                continue
            # Generated bytecode and Git internals are not dataset resources.
            if any(part in (".git", "__pycache__") for part in path.parts):
                continue
            raw = path.read_bytes()
            source_id = self.add_source(relative, "resource", raw)
            description = "Original supporting resource; not raw pull records."
            if path.name == "player_index.csv":
                description = "Original dataset_03 player index; also available as legacy_player_index."
            elif path.suffix.lower() == ".json":
                description = "Original prefiltered analysis histogram; also available as legacy_histograms."
            elif path.suffix.lower() == ".npy":
                description = "Original dynamic-programming probability array; load BLOB with numpy.load(BytesIO(...), allow_pickle=False)."
            self.db.execute("INSERT INTO resource_assets VALUES(?,?,?,?)",
                            (source_id, mimetypes.guess_type(path.name)[0] or "application/octet-stream", description, raw))
            if path.suffix.lower() == ".json" and path.name.startswith("GI_"):
                group = {"character": 301, "newbee": 100, "stander": 200, "weapon": 302}[path.stem.split("_")[1]]
                histogram = json.loads(raw.decode("utf-8-sig"))
                rows = [(source_id, group, metric, n, frequency)
                        for metric, values in histogram.items() for n, frequency in enumerate(values)]
                self.db.executemany("INSERT INTO legacy_histograms VALUES(?,?,?,?,?)", rows)

    def import_original_index(self):
        path = "GI_gacha_dataset_03/player_index.csv"
        source_id = self.sources[path]
        with (self.root / path).open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            for record in reader:
                uid = record["uid"]
                player_id = self.players.get((3, uid))
                if player_id is None:
                    self.index_mismatches += 1
                    self.issue(source_id, reader.line_num, "index_player_missing", {"uid": uid})
                    continue
                values = [int(record[field]) if field not in ("begin_time", "end_time") else record[field] for field in INDEX_FIELDS]
                self.db.execute("INSERT INTO legacy_player_index VALUES(" + ",".join("?" for _ in range(17)) + ")",
                                (player_id, source_id, reader.line_num, uid, *values))
                observed = []
                first, last = [], []
                for group in (100, 200, 301, 302):
                    stats = self.player_stats.get((player_id, group))
                    observed.extend([stats[0], stats[3]] if stats else [0, 0])
                    if stats:
                        first.append(stats[4]); last.append(stats[5])
                observed.extend([sum(observed[::2]), sum(observed[1::2])])
                if observed != values[:10]:
                    self.index_mismatches += 1
                    self.issue(source_id, reader.line_num, "index_count_mismatch",
                               {"uid": uid, "expected": values[:10], "observed": observed})
                if first and (min(first), max(last)) != (record["begin_time"], record["end_time"]):
                    self.issue(source_id, reader.line_num, "index_time_mismatch",
                               {"uid": uid, "expected": [record["begin_time"], record["end_time"]], "observed": [min(first), max(last)]})

    def write_summaries(self):
        self.db.executemany("INSERT INTO summary_pool VALUES(?,?,?,?,?,?,?,?)",
                            [(*key, *stats) for key, stats in sorted(self.pool_stats.items())])
        self.db.executemany("INSERT INTO summary_player_pool VALUES(?,?,?,?,?,?,?,?)",
                            [(*key, *stats) for key, stats in sorted(self.player_stats.items())])
        self.db.executemany("INSERT INTO summary_daily VALUES(?,?,?,?,?,?)",
                            [(*key, value) for key, value in sorted(self.daily.items())])
        self.db.executemany("INSERT INTO summary_item VALUES(?,?,?,?)",
                            [(*key, value) for key, value in sorted(self.item_stats.items())])


def rows_dict(db, sql):
    cursor = db.execute(sql)
    names = [column[0] for column in cursor.description]
    return [dict(zip(names, row)) for row in cursor]


def build(args):
    root = args.source.resolve()
    output = args.output.resolve()
    if not (root / "GI_gacha_dataset_02").is_dir() or not (root / "GI_gacha_dataset_03").is_dir():
        raise SystemExit(f"Expected both dataset directories under {root}")
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists() and not args.overwrite:
        raise SystemExit(f"Output already exists: {output}. Use --overwrite to rebuild.")
    temporary = output.with_name(output.stem + ".building.db")
    if temporary.exists():
        raise SystemExit(f"An unfinished build exists: {temporary}. Rename it before retrying.")
    start = time.monotonic()
    db = sqlite3.connect(temporary)
    try:
        # Only the unpublished temporary file uses these fast bulk-load settings.
        db.execute("PRAGMA journal_mode=OFF")
        db.execute("PRAGMA synchronous=OFF")
        db.execute("PRAGMA cache_size=-131072")
        db.execute("PRAGMA temp_store=FILE")
        db.execute("PRAGMA foreign_keys=ON")
        db.executescript(SCHEMA)
        db.executemany("INSERT INTO datasets VALUES(?,?,?,?,?,?)", [
            (2, "GI_gacha_dataset_02", "Early manually collected player exports", None, None, None),
            (3, "GI_gacha_dataset_03", "Voluntarily public feixiaoqiu records, released 2022-08-31", 16289, 15599315, "2022-07-26"),
        ])
        db.executemany("INSERT INTO gacha_types VALUES(?,?,?,?)", [(code, *values) for code, values in POOLS.items()])
        metadata = {
            "schema_version": SCHEMA_VERSION,
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "source_root_at_build": str(root),
            "builder_sha256": sha256_file(Path(__file__)),
            "gacha_id_storage": "TEXT: never coerce IDs to floating point",
            "item_type_semantics": "02 labels mapped to 0=character/1=weapon; 03 numeric source values retained. Some English records suggest inconsistent/inverted coding: inspect all rows of accounts flagged three_star_character before type-based analysis.",
            "item_name_semantics": "Original multilingual names retained; no alias translation or item-name merging performed",
            "time_semantics": "Original naive wall-clock strings; timezone not asserted by source",
            "player_identity": "(dataset_id, full player_key); last 4 UID digits are NOT unique",
            "sequence_rule": "Within player and pool_group: gacha_time, numeric gacha_id if present, source_row; 02 same-second ties follow source order",
            "cleaning_policy": "Keep all structurally valid rows including duplicates; quarantine malformed rows; do not merge accounts across datasets",
            "summary_scope": "All imported valid rows, including flagged records; no first-5-star or last-100-pull exclusions",
            "legacy_histogram_scope": "Original ScanTool outputs with historical filtering; do not add these frequencies to raw pulls",
            "source_usage_notice": "Dataset_03 readme: learning and exchange only; original README files are embedded in resource_assets",
        }
        db.executemany("INSERT INTO metadata VALUES(?,?)", [(key, json_text(value)) for key, value in metadata.items()])
        builder = Builder(db, root)
        files_02 = sorted((root / "GI_gacha_dataset_02").glob("*/*.csv"))
        log(f"Import dataset_02: {len(files_02):,} CSV files")
        for path in files_02:
            builder.ingest(2, path.parent.name, path.relative_to(root).as_posix(),
                           path.read_bytes(), forced_pool=int(path.stem.removeprefix("gacha")))
        db.commit()
        log(f"dataset_02 complete: {builder.total:,} pulls; {builder.empty_files} empty files")
        parts = sorted((root / "GI_gacha_dataset_03").glob("*.zip.[0-9][0-9][0-9]"))
        if not parts or [int(path.suffix[1:]) for path in parts] != list(range(1, len(parts) + 1)):
            raise ValueError("Missing or non-contiguous split ZIP parts")
        if len({path.name.rsplit(".", 1)[0] for path in parts}) != 1:
            raise ValueError("Expected one split ZIP archive")
        part_names = [path.relative_to(root).as_posix() for path in parts]
        for path in parts:
            builder.add_source(path.relative_to(root).as_posix(), "archive_part")
        with SplitZipReader(parts) as combined, zipfile.ZipFile(combined) as archive:
            all_files = [info for info in archive.infolist() if not info.is_dir()]
            csv_files = [info for info in all_files if info.filename.startswith("player_data/") and info.filename.endswith(".csv")]
            if len(all_files) != len(csv_files):
                raise ValueError("Unexpected non-player files inside archive; review before importing")
            names = [info.filename for info in csv_files]
            if len(set(names)) != len(names):
                raise ValueError("Duplicate ZIP member names")
            log(f"Import dataset_03: {len(csv_files):,} encrypted CSV members (streaming)")
            for n, info in enumerate(sorted(csv_files, key=lambda entry: entry.filename), 1):
                raw = archive.read(info, pwd=args.password.encode("utf-8"))
                builder.ingest(3, Path(info.filename).stem, "GI_gacha_dataset_03/" + info.filename,
                               raw, parts=part_names)
                if time.monotonic() - builder.previous_log >= 15 or n == len(csv_files):
                    log(f"dataset_03 files {n:,}/{len(csv_files):,}; total imported pulls {builder.total:,}")
                    builder.previous_log = time.monotonic()
        log("Store original supporting files and reconcile every account with player_index.csv")
        builder.store_assets()
        builder.import_original_index()
        builder.write_summaries()
        db.commit()
        heartbeat = [time.monotonic()]

        def progress():
            if time.monotonic() - heartbeat[0] >= 20:
                log("SQLite is working on the current index/validation step")
                heartbeat[0] = time.monotonic()
            return 0

        db.set_progress_handler(progress, 1_000_000)
        for name, sql in [
            ("player / merged pool / chronological sequence", "CREATE INDEX idx_pulls_player_pool_seq ON pulls(player_id,pool_group,pool_seq)"),
            ("pool / item", "CREATE INDEX idx_pulls_pool_item ON pulls(gacha_type,item_id)"),
            ("time", "CREATE INDEX idx_pulls_time ON pulls(gacha_time)"),
            ("quality issue provenance", "CREATE INDEX idx_quality_source_row ON quality_issues(source_file_id,source_row)"),
        ]:
            log(f"Create index: {name}")
            db.execute(sql)
        db.commit()
        log("Validate database integrity, foreign keys, row accounting and summary totals")
        integrity = [row[0] for row in db.execute("PRAGMA integrity_check")]
        if integrity != ["ok"]:
            raise ValueError(f"SQLite integrity failure: {integrity}")
        foreign_key_errors = list(db.execute("PRAGMA foreign_key_check"))
        if foreign_key_errors:
            raise ValueError(f"Foreign key failures: {foreign_key_errors[:10]}")
        fact_rows = db.execute("SELECT count(*) FROM pulls").fetchone()[0]
        source_rows = db.execute("SELECT sum(data_rows),sum(imported_rows),sum(rejected_rows) FROM source_files WHERE source_kind='pull_csv'").fetchone()
        summary_rows = db.execute("SELECT sum(pulls) FROM summary_pool").fetchone()[0]
        if not (source_rows[0] == fact_rows + builder.rejected and source_rows[1] == fact_rows == summary_rows == builder.total and source_rows[2] == builder.rejected):
            raise ValueError("Source/fact/summary row-accounting mismatch")
        for table in ("summary_daily", "summary_item", "summary_player_pool"):
            if db.execute(f"SELECT sum(pulls) FROM {table}").fetchone()[0] != fact_rows:
                raise ValueError(f"Summary count mismatch: {table}")
        if db.execute("SELECT count(*) FROM source_files WHERE source_kind='pull_csv' AND player_id IS NULL").fetchone()[0]:
            raise ValueError("A primary CSV is missing its player reference")
        report = {
            "schema_version": SCHEMA_VERSION,
            "created_at_utc": metadata["created_at_utc"],
            "database": output.name,
            "datasets": rows_dict(db, "SELECT * FROM v_dataset_summary ORDER BY dataset"),
            "pool_summary": rows_dict(db, "SELECT * FROM v_pool_summary ORDER BY dataset,gacha_type"),
            "source_csv_files": db.execute("SELECT count(*) FROM source_files WHERE source_kind='pull_csv'").fetchone()[0],
            "empty_source_files": builder.empty_files,
            "imported_pulls": fact_rows,
            "rejected_rows": builder.rejected,
            "items": len(builder.items),
            "resource_assets": db.execute("SELECT count(*) FROM resource_assets").fetchone()[0],
            "legacy_player_index_rows": db.execute("SELECT count(*) FROM legacy_player_index").fetchone()[0],
            "legacy_histogram_bins": db.execute("SELECT count(*) FROM legacy_histograms").fetchone()[0],
            "quality_issues": rows_dict(db, "SELECT issue_code,count(*) AS rows FROM quality_issues GROUP BY issue_code ORDER BY issue_code"),
            "quality_issue_accounts": rows_dict(db, "SELECT q.issue_code,count(DISTINCT f.player_id) AS accounts FROM quality_issues q JOIN source_files f USING(source_file_id) GROUP BY q.issue_code ORDER BY q.issue_code"),
            "original_index_count_mismatches": builder.index_mismatches,
            "validation": {"integrity_check": integrity[0], "foreign_key_errors": len(foreign_key_errors),
                           "source_rows_accounted_for": True, "all_summary_totals_match": True,
                           "source_player_links_complete": True,
                           "original_index_counts_match": builder.index_mismatches == 0},
        }
        dataset03 = next(row for row in report["datasets"] if row["dataset"] == "GI_gacha_dataset_03")
        report["validation"]["dataset03_matches_documented_counts"] = (dataset03["pulls"] == 15599315 and dataset03["players"] == 16289)
        db.execute("INSERT INTO metadata VALUES(?,?)", ("build_report", json_text(report)))
        db.commit()
        log("Build SQLite query planner statistics")
        db.execute("ANALYZE")
        db.commit()
        db.execute("PRAGMA journal_mode=DELETE")
        db.execute("PRAGMA synchronous=FULL")
        db.close()
        os.replace(temporary, output)
        report["database_bytes"] = output.stat().st_size
        report["elapsed_seconds"] = round(time.monotonic() - start, 2)
        log("Compute final database SHA-256")
        report["database_sha256"] = sha256_file(output)
        report_path = output.with_name("import_report.json")
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        log(f"Complete: {output}; {fact_rows:,} pulls; {report['database_bytes']/1024**3:.2f} GiB")
        log(f"Validation report: {report_path}")
    except BaseException:
        db.close()
        log(f"Build did not publish a final database; diagnostic temporary file retained: {temporary}")
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=HERE / "genshin_gacha.db")
    parser.add_argument("--password", default="OneBST", help="Password published in dataset_03/readme.md")
    parser.add_argument("--overwrite", action="store_true", help="Replace an existing final DB only after successful validation")
    build(parser.parse_args())


if __name__ == "__main__":
    main()
