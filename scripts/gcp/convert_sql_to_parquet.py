#!/usr/bin/env python3
"""
Convert MySQL dump (.sql.gz) files → sharded Parquet (snappy) for BigQuery loading.

Streaming parser that handles mysqldump 8.0 extended-INSERT syntax:
  - CREATE TABLE → extract column names + types
  - INSERT INTO ... VALUES (row),(row),...; → chunk-based state machine
  - Handles: escaped strings, NULL, _binary literals, negative numbers

Usage:
    python scripts/gcp/convert_sql_to_parquet.py

Environment:
    BATCH_SIZE  — rows per Parquet shard (default: 500000)
"""

import os
import re
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

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

# Large tables that should be processed sequentially (not in parallel pool)
LARGE_TABLES = {"C06_Link_Papers_BioEntities", "A04_Abstract"}

# ── MySQL type → pandas/arrow type mapping ───────────────────────────────────
def mysql_type_to_pandas(mysql_type: str) -> str:
    """Map MySQL column type to pandas dtype string."""
    t = mysql_type.lower().strip()
    if t.startswith(("int", "bigint", "smallint", "tinyint", "mediumint")):
        return "Int64"
    if t.startswith(("float", "double", "decimal", "numeric")):
        return "Float64"
    if t.startswith("binary"):
        return "Int64"  # _binary '0' / '1'
    # varchar, char, text, longtext, enum, date, etc. → string
    return "string"


# ── Phase 1: Parse CREATE TABLE header ───────────────────────────────────────
COL_RE = re.compile(r"^\s*`(\w+)`\s+(.+?)(?:\s+(?:NOT\s+NULL|NULL|DEFAULT|AUTO_INCREMENT|PRIMARY|KEY|UNIQUE|COMMENT|COLLATE|CHARACTER))?\s*,?\s*$", re.IGNORECASE)

def parse_header(filepath: Path) -> tuple[str, list[str], list[str]]:
    """
    Read the header of a .sql.gz file to extract table name, column names,
    and pandas dtypes. Stops at the first INSERT line.

    Returns: (table_name, [col_names], [pandas_dtypes])
    """
    table_name = None
    columns = []
    dtypes = []
    in_create = False

    cmd = _gzcat_cmd()
    proc = subprocess.Popen(
        [cmd, str(filepath)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    try:
        for raw_line in proc.stdout:
            line = raw_line.decode("utf-8", errors="replace").rstrip("\n\r")

            if line.startswith("INSERT INTO"):
                break

            if line.startswith("CREATE TABLE"):
                # CREATE TABLE `TableName` (
                m = re.search(r"`(\w+)`", line)
                if m:
                    table_name = m.group(1)
                in_create = True
                continue

            if in_create:
                if line.strip().startswith(")"):
                    in_create = False
                    continue
                # Skip KEY/INDEX/PRIMARY/CONSTRAINT lines
                stripped = line.strip()
                if stripped.startswith(("PRIMARY", "KEY", "UNIQUE", "INDEX", "CONSTRAINT", ")")):
                    continue
                m = COL_RE.match(line)
                if m:
                    col_name = m.group(1)
                    mysql_type = m.group(2).split()[0]  # first word of type
                    columns.append(col_name)
                    dtypes.append(mysql_type_to_pandas(mysql_type))
    finally:
        proc.terminate()
        proc.wait()

    if not table_name:
        # Fallback: derive from filename
        table_name = filepath.stem.replace(".sql", "")
    if not columns:
        raise ValueError(f"No columns found in {filepath}")

    return table_name, columns, dtypes


# ── Phase 2: Streaming state-machine parser ──────────────────────────────────
# States
SCAN = 0
ROW_START = 1
VALUE_START = 2
STRING = 3
NUMBER = 4
NULL_KW = 5
BINARY_LIT = 6
AFTER_VALUE = 7
AFTER_ROW = 8

CHUNK_SIZE = 16 * 1024 * 1024  # 16 MB


def _gzcat_cmd() -> str:
    """Find available gzip decompression command."""
    for cmd in ("gzcat", "gunzip", "zcat"):
        try:
            subprocess.run([cmd, "--version"], capture_output=True, timeout=5)
            return cmd
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
    raise RuntimeError("No gzcat/gunzip/zcat found on PATH")


def stream_rows(filepath: Path, num_cols: int):
    """
    Generator that yields rows (as lists) from a .sql.gz mysqldump file.
    Uses a chunk-based state machine to handle arbitrarily large files.
    """
    cmd = _gzcat_cmd()
    # gunzip needs -c flag, gzcat doesn't
    args = [cmd]
    if cmd == "gunzip":
        args.append("-c")
    args.append(str(filepath))

    proc = subprocess.Popen(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    state = SCAN
    current_value = []
    current_row = []
    escape_next = False
    null_pos = 0
    binary_phase = 0  # 0=matching prefix, 1=collecting value
    binary_prefix = "_binary '"
    binary_prefix_pos = 0
    binary_val = []
    bad_row_count = 0

    try:
        while True:
            chunk = proc.stdout.read(CHUNK_SIZE)
            if not chunk:
                break
            data = chunk.decode("utf-8", errors="replace")

            i = 0
            n = len(data)
            while i < n:
                c = data[i]

                if state == SCAN:
                    # Look for "VALUES " to start parsing rows
                    # Fast-scan: find 'V' then check
                    vi = data.find("VALUES ", i)
                    if vi == -1:
                        break  # skip rest of chunk
                    i = vi + 7  # skip past "VALUES "
                    state = ROW_START
                    continue

                elif state == ROW_START:
                    if c == "(":
                        current_row = []
                        state = VALUE_START
                    elif c in (" ", "\n", "\r", "\t"):
                        pass  # whitespace between rows
                    else:
                        state = SCAN  # unexpected, rescan
                    i += 1

                elif state == VALUE_START:
                    if c == "'":
                        current_value = []
                        escape_next = False
                        state = STRING
                        i += 1
                    elif c == "N":
                        null_pos = 1  # matched 'N', need 'U','L','L'
                        state = NULL_KW
                        i += 1
                    elif c == "_":
                        binary_prefix_pos = 1  # matched '_', matching rest of "_binary '"
                        binary_phase = 0
                        binary_val = []
                        state = BINARY_LIT
                        i += 1
                    elif c == "-" or c.isdigit():
                        current_value = [c]
                        state = NUMBER
                        i += 1
                    elif c == ")":
                        # Empty row? Shouldn't happen but handle gracefully
                        state = AFTER_ROW
                        i += 1
                    else:
                        current_value = []
                        state = STRING  # fallback
                        i += 1

                elif state == STRING:
                    if escape_next:
                        escape_next = False
                        if c == "'":
                            current_value.append("'")
                        elif c == "\\":
                            current_value.append("\\")
                        elif c == "n":
                            current_value.append("\n")
                        elif c == "r":
                            current_value.append("\r")
                        elif c == "t":
                            current_value.append("\t")
                        elif c == "0":
                            current_value.append("\0")
                        else:
                            current_value.append(c)
                        i += 1
                    elif c == "\\":
                        escape_next = True
                        i += 1
                    elif c == "'":
                        # End of string
                        current_row.append("".join(current_value))
                        current_value = []
                        state = AFTER_VALUE
                        i += 1
                    else:
                        current_value.append(c)
                        i += 1

                elif state == NUMBER:
                    if c == "," or c == ")":
                        val_str = "".join(current_value)
                        current_row.append(val_str)
                        current_value = []
                        if c == ",":
                            state = VALUE_START
                            i += 1
                        else:  # ')'
                            state = AFTER_ROW
                            # Don't increment i, let AFTER_ROW handle it
                            # Actually, we need to handle row completion
                            if len(current_row) == num_cols:
                                yield current_row
                            else:
                                bad_row_count += 1
                                if bad_row_count <= 10:
                                    print(f"  WARN: Skipping row with {len(current_row)} cols (expected {num_cols})", file=sys.stderr)
                            current_row = []
                            state = AFTER_ROW
                            i += 1
                    else:
                        current_value.append(c)
                        i += 1

                elif state == NULL_KW:
                    expected = "NULL"
                    if null_pos < 4 and c == expected[null_pos]:
                        null_pos += 1
                        if null_pos == 4:
                            current_row.append(None)
                            state = AFTER_VALUE
                        i += 1
                    else:
                        # Not actually NULL, treat as string
                        current_row.append("N" + data[i:i])  # partial
                        state = AFTER_VALUE
                        # re-process this char
                        continue

                elif state == BINARY_LIT:
                    if binary_phase == 0:
                        # Matching rest of "_binary '"
                        if binary_prefix_pos < len(binary_prefix) and c == binary_prefix[binary_prefix_pos]:
                            binary_prefix_pos += 1
                            if binary_prefix_pos == len(binary_prefix):
                                binary_phase = 1  # now collecting value
                            i += 1
                        else:
                            # Not a _binary literal, treat accumulated as string
                            current_value = list(binary_prefix[:binary_prefix_pos])
                            current_value.append(c)
                            state = STRING
                            i += 1
                    else:
                        # Collecting binary value until closing '
                        if c == "'":
                            val_str = "".join(binary_val)
                            try:
                                current_row.append(int(val_str))
                            except ValueError:
                                current_row.append(val_str)
                            binary_val = []
                            state = AFTER_VALUE
                            i += 1
                        else:
                            binary_val.append(c)
                            i += 1

                elif state == AFTER_VALUE:
                    if c == ",":
                        state = VALUE_START
                        i += 1
                    elif c == ")":
                        if len(current_row) == num_cols:
                            yield current_row
                        else:
                            bad_row_count += 1
                            if bad_row_count <= 10:
                                print(f"  WARN: Skipping row with {len(current_row)} cols (expected {num_cols})", file=sys.stderr)
                        current_row = []
                        state = AFTER_ROW
                        i += 1
                    else:
                        i += 1  # skip whitespace

                elif state == AFTER_ROW:
                    if c == ",":
                        state = ROW_START
                        i += 1
                    elif c == ";":
                        state = SCAN
                        i += 1
                    else:
                        i += 1  # skip whitespace/newline

    finally:
        proc.terminate()
        proc.wait()

    if bad_row_count > 0:
        print(f"  Total bad rows skipped: {bad_row_count}", file=sys.stderr)


# ── Batch writer ─────────────────────────────────────────────────────────────
def write_shard(rows: list[list], columns: list[str], dtypes: list[str],
                output_path: Path):
    """Write a batch of rows to a Parquet file."""
    # Build column-oriented dict
    col_data = {col: [] for col in columns}
    for row in rows:
        for j, col in enumerate(columns):
            col_data[col].append(row[j])

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


# ── Convert one table ────────────────────────────────────────────────────────
def _fmt_size(nbytes: int) -> str:
    """Format byte count as human-readable size."""
    for unit in ("B", "KB", "MB", "GB"):
        if nbytes < 1024:
            return f"{nbytes:.1f} {unit}"
        nbytes /= 1024
    return f"{nbytes:.1f} TB"


def _fmt_rate(rows: int, elapsed: float) -> str:
    """Format rows/sec as human-readable rate."""
    if elapsed <= 0:
        return "-- rows/s"
    rate = rows / elapsed
    if rate >= 1_000_000:
        return f"{rate / 1_000_000:.1f}M rows/s"
    if rate >= 1_000:
        return f"{rate / 1_000:.1f}K rows/s"
    return f"{rate:.0f} rows/s"


def convert_one(table_name: str) -> dict:
    """Convert a single .sql.gz → sharded Parquet files. Returns result dict."""
    input_path = INPUT_DIR / f"{table_name}.sql.gz"
    input_size = input_path.stat().st_size
    t0 = time.time()

    try:
        # Phase 1: parse header
        tbl_name, columns, dtypes = parse_header(input_path)
        num_cols = len(columns)
        print(f"  [{table_name}] START — {num_cols} columns, {_fmt_size(input_size)} compressed", flush=True)

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
    print(f"Input:      {INPUT_DIR}")
    print(f"Output:     {OUTPUT_DIR}")
    print(f"Tables:     {len(TABLES)}")
    print(f"Batch size: {BATCH_SIZE:,} rows per shard")
    print()

    missing = [t for t in TABLES if not (INPUT_DIR / f"{t}.sql.gz").exists()]
    if missing:
        print(f"ERROR: Missing files: {missing}")
        sys.exit(1)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    results = []

    # Split into small and large tables
    small_tables = [t for t in TABLES if t not in LARGE_TABLES]
    large_tables = [t for t in TABLES if t in LARGE_TABLES]

    # Process small tables in parallel
    print("Processing small/medium tables (parallel, 4 workers)...")
    with ProcessPoolExecutor(max_workers=4) as executor:
        futures = {executor.submit(convert_one, t): t for t in small_tables}
        for future in as_completed(futures):
            result = future.result()
            _print_result(result)
            results.append(result)

    # Process large tables sequentially
    if large_tables:
        print()
        print("Processing large tables (sequential)...")
        for t in large_tables:
            result = convert_one(t)
            _print_result(result)
            results.append(result)

    # Summary
    ok_count = sum(1 for r in results if r["status"] == "OK")
    total_rows = sum(r["rows"] for r in results)
    total_shards = sum(r["shards"] for r in results)
    print()
    print(f"Converted {ok_count}/{len(TABLES)} tables  |  "
          f"{total_rows:,} total rows  |  {total_shards} shards")

    failed = [r["table"] for r in results if r["status"] == "FAIL"]
    if failed:
        print(f"Failed tables: {', '.join(failed)}")


def _print_result(result: dict):
    if result["status"] == "OK":
        print(
            f"  {result['status']}  {result['table']:<45s} "
            f"{result['rows']:>12,} rows  "
            f"{result['shards']:>4} shards  "
            f"{result['elapsed']:>6.1f}s"
        )
    else:
        print(f"  {result['status']}  {result['table']:<45s}  ERROR: {result.get('error', '?')}")


if __name__ == "__main__":
    main()
