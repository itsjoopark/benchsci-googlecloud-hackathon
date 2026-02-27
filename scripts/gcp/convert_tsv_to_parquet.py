#!/usr/bin/env python3
"""
Convert PKG 2.0 TSV.gz files → Parquet (snappy) for BigQuery loading.

Handles two common data issues:
  - Truncated gzip files: decompresses via gzcat subprocess (recovers all
    complete rows before the truncation point)
  - Malformed rows (wrong field count): skips bad lines with a warning

Usage:
    python scripts/gcp/convert_tsv_to_parquet.py
"""

import io
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

# ── Paths ────────────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
INPUT_DIR = REPO_ROOT / "data" / "pkg2"
OUTPUT_DIR = REPO_ROOT / "data" / "pkg2_parquet"

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

# ── Type coercion rules ─────────────────────────────────────────────────────
INT64_COLUMNS = {
    "id", "Id", "PMID", "PMID_Version",
    "PubYear", "AuthorNum", "StartPosition", "EndPosition", "ClaimNum",
    "CitedCount", "CitedCount_ClinicalArticle",
    "CitedCount_ClinicalTrailStudy", "CitedCount_Patent",
    "IsClinicalArticle", "IsResearchArticle",
    "is_neural_normalized",
    "isWithdrawn", "has_citing_paper", "is_granted_by_NIH", "is_CPC_A61",
}

FLOAT64_COLUMNS = {
    "prob", "StdCitedCount",
    "Human", "Animal", "MolecularCellular", "APT",
}


def coerce_types(df: pd.DataFrame) -> pd.DataFrame:
    """Apply type coercion rules to a DataFrame."""
    for col in df.columns:
        if col in INT64_COLUMNS:
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")
        elif col in FLOAT64_COLUMNS:
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("Float64")
        else:
            df[col] = df[col].fillna("").astype(str)
    return df


def decompress_gzcat(filepath: Path) -> bytes:
    """Decompress a .gz file via gzcat, tolerating truncated archives.

    gzcat writes all recoverable data to stdout before exiting with an error
    on truncated files. Python's gzip module raises immediately on EOF errors,
    so subprocess is the reliable path here.
    """
    proc = subprocess.run(
        ["gzcat", str(filepath)],
        capture_output=True,
    )
    # We don't check returncode — truncated files return rc=1 but stdout is valid
    return proc.stdout


def convert_one(table_name: str) -> dict:
    """Convert a single TSV.gz → Parquet. Returns a result dict."""
    input_path = INPUT_DIR / f"{table_name}.tsv.gz"
    output_path = OUTPUT_DIR / f"{table_name}.parquet"

    t0 = time.time()
    try:
        raw = decompress_gzcat(input_path)
        if not raw:
            raise ValueError("gzcat produced no output")

        df = pd.read_csv(
            io.BytesIO(raw),
            sep="\t",
            dtype=str,
            keep_default_na=False,
            na_values=[""],
            low_memory=False,
            on_bad_lines="skip",
        )
        # Free the raw bytes immediately
        del raw

        if df.empty:
            raise ValueError("DataFrame is empty after parsing")

        df = coerce_types(df)
        df.to_parquet(output_path, engine="pyarrow", compression="snappy", index=False)

        elapsed = time.time() - t0
        size_mb = output_path.stat().st_size / (1024 * 1024)
        return {
            "table": table_name,
            "status": "OK",
            "rows": len(df),
            "size_mb": round(size_mb, 1),
            "elapsed": round(elapsed, 1),
        }
    except Exception as e:
        elapsed = time.time() - t0
        return {
            "table": table_name,
            "status": "FAIL",
            "rows": 0,
            "size_mb": 0,
            "elapsed": round(elapsed, 1),
            "error": str(e),
        }


def main():
    print(f"Input:  {INPUT_DIR}")
    print(f"Output: {OUTPUT_DIR}")
    print(f"Tables: {len(TABLES)}")
    print()

    missing = [t for t in TABLES if not (INPUT_DIR / f"{t}.tsv.gz").exists()]
    if missing:
        print(f"ERROR: Missing files: {missing}")
        sys.exit(1)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    results = []
    with ProcessPoolExecutor(max_workers=4) as executor:
        futures = {executor.submit(convert_one, t): t for t in TABLES}
        for future in as_completed(futures):
            result = future.result()
            status = result["status"]
            table = result["table"]
            if status == "OK":
                print(
                    f"  {status}  {table:<45s} "
                    f"{result['rows']:>10,} rows  "
                    f"{result['size_mb']:>8.1f} MB  "
                    f"{result['elapsed']:>5.1f}s"
                )
            else:
                print(f"  {status}  {table:<45s}  ERROR: {result.get('error', '?')}")
            results.append(result)

    ok_count = sum(1 for r in results if r["status"] == "OK")
    total_rows = sum(r["rows"] for r in results)
    total_mb = sum(r["size_mb"] for r in results)
    print()
    print(f"Converted {ok_count}/{len(TABLES)} tables  |  {total_rows:,} total rows  |  {total_mb:.1f} MB Parquet")

    failed = [r["table"] for r in results if r["status"] == "FAIL"]
    if failed:
        print(f"Failed tables: {', '.join(failed)}")
        # Exit 0 so the shell script continues to upload whatever succeeded
        # The shell script will report which tables are missing


if __name__ == "__main__":
    main()
