#!/usr/bin/env python3
"""
Convert MySQL dump (.sql.gz) files → sharded Parquet (snappy) for BigQuery loading.

Optimized streaming parser using regex tokenization (10-50x faster than char-by-char).
Handles mysqldump 8.0 extended-INSERT syntax:
  - CREATE TABLE → extract column names + types
  - INSERT INTO ... VALUES → regex-based value extraction
  - Handles: escaped strings, NULL, _binary literals, negative numbers

Usage:
    python scripts/gcp/convert_sql_to_parquet.py

Environment:
    BATCH_SIZE  — rows per Parquet shard (default: 500000)
"""

import io
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

# ── Paths ────────────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
INPUT_DIR = REPO_ROOT / "data" / "pkg2_sql"
OUTPUT_DIR = REPO_ROOT / "data" / "pkg2_sql_parquet"

BATCH_SIZE = int(os.environ.get("BATCH_SIZE", "500000"))

# ── All 12 PKG 2.0 tables ───────────────────────────────────────────────────
TABLES = [
    "C23_BioEntities",
    "C13_Link_ClinicalTrials_BioEntities",
    "C21_Bioentity_Relationships",
    "C18_Link_Patents_BioEntities",
    "C15_Patents",
    "C06_Link_Papers_BioEntities",
    "C11_ClinicalTrials",
    "C01_Papers",
    "A04_Abstract",
    "A06_MeshHeadingList",
    "A01_Articles",
    "A03_KeywordList",
]

# Large tables processed sequentially to limit concurrent gzcat/memory usage
LARGE_TABLES = {"C06_Link_Papers_BioEntities", "A04_Abstract"}


# ── MySQL type → pandas type mapping ─────────────────────────────────────────
def mysql_type_to_pandas(mysql_type: str) -> str:
    t = mysql_type.lower().strip()
    if t.startswith(("int", "bigint", "smallint", "tinyint", "mediumint")):
        return "Int64"
    if t.startswith(("float", "double", "decimal", "numeric")):
        return "Float64"
    if t.startswith("binary"):
        return "Int64"  # _binary '0' / '1'
    return "string"


# ── Phase 1: Parse CREATE TABLE header ───────────────────────────────────────
_COL_RE = re.compile(
    r"^\s*`(\w+)`\s+(.+?)(?:\s+(?:NOT\s+NULL|NULL|DEFAULT|AUTO_INCREMENT|"
    r"PRIMARY|KEY|UNIQUE|COMMENT|COLLATE|CHARACTER))?\s*,?\s*$",
    re.IGNORECASE,
)


def _gzcat_cmd() -> str:
    for cmd in ("gzcat", "gunzip", "zcat"):
        try:
            subprocess.run([cmd, "--version"], capture_output=True, timeout=5)
            return cmd
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
    raise RuntimeError("No gzcat/gunzip/zcat found on PATH")


def parse_header(filepath: Path) -> tuple[str, list[str], list[str]]:
    """Extract table name, column names, and pandas dtypes from CREATE TABLE."""
    table_name = None
    columns = []
    dtypes = []
    in_create = False

    cmd = _gzcat_cmd()
    proc = subprocess.Popen([cmd, str(filepath)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        for raw_line in proc.stdout:
            line = raw_line.decode("utf-8", errors="replace").rstrip("\n\r")
            if line.startswith("INSERT INTO"):
                break
            if line.startswith("CREATE TABLE"):
                m = re.search(r"`(\w+)`", line)
                if m:
                    table_name = m.group(1)
                in_create = True
                continue
            if in_create:
                if line.strip().startswith(")"):
                    in_create = False
                    continue
                stripped = line.strip()
                if stripped.startswith(("PRIMARY", "KEY", "UNIQUE", "INDEX", "CONSTRAINT", ")")):
                    continue
                m = _COL_RE.match(line)
                if m:
                    columns.append(m.group(1))
                    dtypes.append(mysql_type_to_pandas(m.group(2).split()[0]))
    finally:
        proc.terminate()
        proc.wait()

    if not table_name:
        table_name = filepath.stem.replace(".sql", "")
    if not columns:
        raise ValueError(f"No columns found in {filepath}")
    return table_name, columns, dtypes


# ── Phase 2: Regex-based streaming parser ────────────────────────────────────
# Single regex matching all 4 value types in INSERT ... VALUES syntax.
# Runs in C (re engine) → 20-50x faster than Python char-by-char parsing.
# Group 1: _binary value, Group 2: string content, Group 3: NULL, Group 4: number
_VALUE_RE = re.compile(
    rb"_binary\s+'([^']*)'"                        # _binary '0' or '1'
    rb"|'((?:[^'\\]|\\.)*)'"                        # 'string with \'escapes'
    rb"|(NULL)"                                     # NULL keyword
    rb"|(-?[0-9]+(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?)"  # 123, -0.5, 1e10
    , re.DOTALL
)

_UNESCAPE_RE = re.compile(rb"\\(.)", re.DOTALL)
_UNESCAPE_MAP = {
    ord("\\"): b"\\",
    ord("'"): b"'",
    ord("n"): b"\n",
    ord("r"): b"\r",
    ord("t"): b"\t",
    ord("0"): b"\x00",
}


def _unescape_mysql(data: bytes) -> str:
    """Unescape MySQL backslash sequences and decode to UTF-8."""
    if b"\\" not in data:
        return data.decode("utf-8", errors="replace")

    def _repl(m):
        c = m.group(1)[0]
        return _UNESCAPE_MAP.get(c, m.group(1))

    return _UNESCAPE_RE.sub(_repl, data).decode("utf-8", errors="replace")


def stream_rows(filepath: Path, num_cols: int):
    """
    Stream rows from .sql.gz using regex tokenization.

    Reads INSERT lines one at a time (each ~10-50MB), extracts all value tokens
    via a compiled regex, and groups them into rows by column count. This avoids
    the Python-level char-by-char loop entirely.
    """
    cmd = _gzcat_cmd()
    args = [cmd]
    if cmd == "gunzip":
        args.append("-c")
    args.append(str(filepath))

    proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    buffered = io.BufferedReader(proc.stdout, buffer_size=32 * 1024 * 1024)

    bad_row_count = 0

    try:
        for raw_line in buffered:
            if not raw_line.startswith(b"INSERT INTO"):
                continue

            # Find VALUES section
            vi = raw_line.find(b"VALUES ")
            if vi == -1:
                continue
            data = raw_line[vi + 7:]

            # Regex-extract all value tokens; group into rows by num_cols
            current_row = []
            for m in _VALUE_RE.finditer(data):
                if m.group(1) is not None:
                    # _binary literal → int
                    try:
                        current_row.append(int(m.group(1)))
                    except ValueError:
                        current_row.append(m.group(1).decode("utf-8", errors="replace"))
                elif m.group(2) is not None:
                    # Quoted string → unescape + decode
                    current_row.append(_unescape_mysql(m.group(2)))
                elif m.group(3) is not None:
                    # NULL
                    current_row.append(None)
                elif m.group(4) is not None:
                    # Number (kept as string; type-coerced in write_shard)
                    current_row.append(m.group(4).decode("ascii"))

                if len(current_row) == num_cols:
                    yield current_row
                    current_row = []

            if current_row:
                bad_row_count += 1
                if bad_row_count <= 10:
                    print(
                        f"  WARN: Partial row ({len(current_row)}/{num_cols} cols) "
                        f"at end of INSERT",
                        file=sys.stderr,
                    )
    finally:
        proc.terminate()
        proc.wait()

    if bad_row_count > 0:
        print(f"  Total bad/partial rows: {bad_row_count}", file=sys.stderr)


# ── Batch writer ─────────────────────────────────────────────────────────────
def write_shard(
    rows: list[list], columns: list[str], dtypes: list[str], output_path: Path
) -> int:
    """Write a batch of rows to a Parquet file. Returns row count."""
    # Build column-oriented dict (list comprehension is ~3x faster than loop)
    col_data = {col: [row[j] for row in rows] for j, col in enumerate(columns)}
    df = pd.DataFrame(col_data)

    # Apply types
    for col, dtype in zip(columns, dtypes):
        if dtype == "Int64":
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")
        elif dtype == "Float64":
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("Float64")
        else:
            df[col] = df[col].astype("string")

    df.to_parquet(output_path, engine="pyarrow", compression="snappy", index=False)
    return len(df)


# ── Progress helpers ─────────────────────────────────────────────────────────
def _fmt_size(nbytes: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if nbytes < 1024:
            return f"{nbytes:.1f} {unit}"
        nbytes /= 1024
    return f"{nbytes:.1f} TB"


def _fmt_rate(rows: int, elapsed: float) -> str:
    if elapsed <= 0:
        return "-- rows/s"
    rate = rows / elapsed
    if rate >= 1_000_000:
        return f"{rate / 1_000_000:.1f}M rows/s"
    if rate >= 1_000:
        return f"{rate / 1_000:.1f}K rows/s"
    return f"{rate:.0f} rows/s"


# ── Convert one table ────────────────────────────────────────────────────────
def convert_one(table_name: str) -> dict:
    """Convert a single .sql.gz → sharded Parquet files. Returns result dict."""
    input_path = INPUT_DIR / f"{table_name}.sql.gz"
    input_size = input_path.stat().st_size
    t0 = time.time()

    try:
        # Phase 1: parse header
        _, columns, dtypes = parse_header(input_path)
        num_cols = len(columns)
        print(
            f"  [{table_name}] START — {num_cols} columns, "
            f"{_fmt_size(input_size)} compressed",
            flush=True,
        )

        # Phase 2: stream rows and write shards
        batch = []
        shard_idx = 0
        total_rows = 0

        for row in stream_rows(input_path, num_cols):
            batch.append(row)
            if len(batch) >= BATCH_SIZE:
                shard_path = OUTPUT_DIR / f"{table_name}_{shard_idx:03d}.parquet"
                written = write_shard(batch, columns, dtypes, shard_path)
                total_rows += written
                shard_idx += 1
                elapsed_so_far = time.time() - t0
                shard_size = shard_path.stat().st_size
                print(
                    f"    [{table_name}] shard {shard_idx:>4d}: "
                    f"{total_rows:>12,} rows  "
                    f"({_fmt_size(shard_size)})  "
                    f"{_fmt_rate(total_rows, elapsed_so_far)}  "
                    f"{elapsed_so_far:>6.1f}s elapsed",
                    flush=True,
                )
                batch = []

        # Write remaining rows
        if batch:
            shard_path = OUTPUT_DIR / f"{table_name}_{shard_idx:03d}.parquet"
            written = write_shard(batch, columns, dtypes, shard_path)
            total_rows += written
            shard_idx += 1
            elapsed_so_far = time.time() - t0
            shard_size = shard_path.stat().st_size
            print(
                f"    [{table_name}] shard {shard_idx:>4d} (final): "
                f"{total_rows:>12,} rows  "
                f"({_fmt_size(shard_size)})  "
                f"{_fmt_rate(total_rows, elapsed_so_far)}  "
                f"{elapsed_so_far:>6.1f}s elapsed",
                flush=True,
            )

        elapsed = time.time() - t0
        print(
            f"  [{table_name}] DONE — {total_rows:,} rows, "
            f"{shard_idx} shards, {elapsed:.1f}s "
            f"({_fmt_rate(total_rows, elapsed)})",
            flush=True,
        )
        return {
            "table": table_name,
            "status": "OK",
            "rows": total_rows,
            "shards": shard_idx,
            "elapsed": round(elapsed, 1),
        }
    except Exception as e:
        elapsed = time.time() - t0
        print(f"  [{table_name}] FAILED after {elapsed:.1f}s — {e}", flush=True)
        import traceback
        traceback.print_exc()
        return {
            "table": table_name,
            "status": "FAIL",
            "rows": 0,
            "shards": 0,
            "elapsed": round(elapsed, 1),
            "error": str(e),
        }


# ── Main ─────────────────────────────────────────────────────────────────────
def main():
    print(f"Input:      {INPUT_DIR}", flush=True)
    print(f"Output:     {OUTPUT_DIR}", flush=True)
    print(f"Tables:     {len(TABLES)}", flush=True)
    print(f"Batch size: {BATCH_SIZE:,} rows per shard", flush=True)
    print(flush=True)

    # Show input file sizes
    total_input_size = 0
    missing = []
    for t in TABLES:
        fp = INPUT_DIR / f"{t}.sql.gz"
        if not fp.exists():
            missing.append(t)
        else:
            sz = fp.stat().st_size
            total_input_size += sz
            print(f"  {t:<45s} {_fmt_size(sz):>10s}", flush=True)
    print(f"  {'TOTAL':<45s} {_fmt_size(total_input_size):>10s}", flush=True)
    print(flush=True)

    if missing:
        print(f"ERROR: Missing files: {missing}", flush=True)
        sys.exit(1)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    results = []
    pipeline_t0 = time.time()

    # Split into small and large tables
    small_tables = [t for t in TABLES if t not in LARGE_TABLES]
    large_tables = [t for t in TABLES if t in LARGE_TABLES]

    # Process small/medium tables in parallel (4 workers)
    print(f"{'─' * 60}", flush=True)
    print(
        f"Phase 1: Small/medium tables (parallel, 4 workers) "
        f"— {len(small_tables)} tables",
        flush=True,
    )
    print(f"{'─' * 60}", flush=True)
    with ProcessPoolExecutor(max_workers=4) as executor:
        futures = {executor.submit(convert_one, t): t for t in small_tables}
        for future in as_completed(futures):
            result = future.result()
            _print_result(result)
            results.append(result)

    # Process large tables sequentially (less memory pressure)
    if large_tables:
        print(flush=True)
        print(f"{'─' * 60}", flush=True)
        print(
            f"Phase 2: Large tables (sequential) — {len(large_tables)} tables",
            flush=True,
        )
        print(f"{'─' * 60}", flush=True)
        for t in large_tables:
            result = convert_one(t)
            _print_result(result)
            results.append(result)

    # Summary
    pipeline_elapsed = time.time() - pipeline_t0
    ok_count = sum(1 for r in results if r["status"] == "OK")
    total_rows = sum(r["rows"] for r in results)
    total_shards = sum(r["shards"] for r in results)
    print(flush=True)
    print(f"{'═' * 60}", flush=True)
    print(
        f"  Converted {ok_count}/{len(TABLES)} tables  |  "
        f"{total_rows:,} total rows  |  {total_shards} shards",
        flush=True,
    )
    print(
        f"  Total time: {pipeline_elapsed:.1f}s  |  "
        f"Overall rate: {_fmt_rate(total_rows, pipeline_elapsed)}",
        flush=True,
    )
    print(f"{'═' * 60}", flush=True)

    failed = [r["table"] for r in results if r["status"] == "FAIL"]
    if failed:
        print(f"Failed tables: {', '.join(failed)}", flush=True)


def _print_result(result: dict):
    if result["status"] == "OK":
        print(
            f"  ✓ {result['table']:<45s} "
            f"{result['rows']:>12,} rows  "
            f"{result['shards']:>4} shards  "
            f"{result['elapsed']:>6.1f}s",
            flush=True,
        )
    else:
        print(
            f"  ✗ {result['table']:<45s}  ERROR: {result.get('error', '?')}",
            flush=True,
        )


if __name__ == "__main__":
    main()
