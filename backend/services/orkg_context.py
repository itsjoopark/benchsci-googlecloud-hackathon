"""ORKG (Open Research Knowledge Graph) evidence retrieval for AI overview enrichment.

Queries the ``kg_raw.orkg_contributions`` BigQuery table, which contains
structured scholarly contributions (paper titles, DOIs, results, methodology,
etc.) tagged with PKG-style entity IDs (e.g. ``NCBIGene672``, ``meshD002945``).
"""

from __future__ import annotations

import logging
import re
from typing import Sequence

from google.cloud import bigquery

from backend.config import settings

logger = logging.getLogger(__name__)

_bq_client: bigquery.Client | None = None

# ── Prefix mapping for numeric-only IDs ────────────────────────────────
_TYPE_PREFIX_MAP: dict[str, list[str]] = {
    "gene": ["NCBIGene"],
    "disease": ["meshD", "MONDO"],
    "drug": ["meshD", "CHEBI", "CHEMBL"],
    "pathway": ["meshD"],
    "protein": ["UniProt", "NCBIGene"],
}

# ── Patterns that indicate an ID is already in PKG form ─────────────────
_PKG_RE = re.compile(
    r"^(NCBIGene|mesh[A-Z]|CHEBI|CHEMBL|MONDO|UniProt|GO|HP|DOID|Reactome)",
    re.IGNORECASE,
)


def _get_bq_client() -> bigquery.Client:
    global _bq_client
    if _bq_client is None:
        _bq_client = bigquery.Client(project=settings.GCP_PROJECT_ID)
    return _bq_client


def _to_pkg_ids(entity_id: str, entity_type: str | None = None) -> list[str]:
    """Generate candidate PKG-style IDs from a source entity ID.

    The ORKG contributions table stores entity references using PKG conventions
    (``NCBIGene672``, ``meshD002738``) inside a pipe-separated ``entity_ids``
    column.  The frontend / backend may pass IDs in different formats, so we
    produce all plausible variants.

    >>> sorted(_to_pkg_ids("672", "gene"))
    ['672', 'NCBIGene672']
    >>> _to_pkg_ids("MESH:D002738")
    ['MESH:D002738', 'meshD002738']
    >>> _to_pkg_ids("NCBIGene672")
    ['NCBIGene672']
    """
    candidates: list[str] = [entity_id]

    # Already in PKG form with no colon — return as-is
    if _PKG_RE.match(entity_id) and ":" not in entity_id:
        return candidates

    # Collapse colon-separated prefixes: MESH:D002738 → meshD002738
    if ":" in entity_id:
        prefix, suffix = entity_id.split(":", 1)
        collapsed = prefix.lower() + suffix
        # Fix casing: meshd002738 → meshD002738
        if collapsed.startswith("mesh") and len(collapsed) > 4:
            collapsed = "mesh" + collapsed[4:]
        candidates.append(collapsed)

    # Numeric-only IDs: add type-based prefixes
    if entity_id.isdigit() and entity_type:
        for prefix in _TYPE_PREFIX_MAP.get(entity_type, []):
            candidates.append(f"{prefix}{entity_id}")

    return candidates


def get_orkg_context(
    entity_a_id: str,
    entity_b_id: str,
    entity_a_type: str | None = None,
    entity_b_type: str | None = None,
    limit: int | None = None,
) -> str:
    """Retrieve ORKG scholarly contributions mentioning the given entity pair.

    Uses a two-phase strategy:
    1. AND match — contributions referencing *both* entities (strongest signal).
    2. OR fallback — contributions referencing *either* entity (broader context).

    Returns a pre-formatted text block suitable for injection into the Gemini
    prompt, or an empty string if nothing is found.
    """
    if not settings.ORKG_ENABLED:
        return ""

    max_results = limit or settings.ORKG_MAX_RESULTS
    table = f"{settings.GCP_PROJECT_ID}.{settings.BQ_DATASET}.{settings.ORKG_BQ_TABLE}"

    ids_a = _to_pkg_ids(entity_a_id, entity_a_type)
    ids_b = _to_pkg_ids(entity_b_id, entity_b_type)
    all_ids = list(set(ids_a + ids_b))

    client = _get_bq_client()

    # Phase 1: AND match — both entities present
    rows = _query_orkg(client, table, ids_a, ids_b, max_results, mode="and")

    # Phase 2: OR fallback if AND returned nothing
    if not rows:
        rows = _query_orkg(client, table, ids_a, ids_b, max_results, mode="or")

    if not rows:
        return ""

    return _format_orkg_rows(rows)


def _query_orkg(
    client: bigquery.Client,
    table: str,
    ids_a: Sequence[str],
    ids_b: Sequence[str],
    limit: int,
    mode: str,
) -> list[dict]:
    """Execute a parameterized query against the ORKG contributions table."""
    all_ids = list(set(list(ids_a) + list(ids_b)))

    if mode == "and":
        # Contributions that mention at least one ID from each entity
        where = """
            EXISTS (SELECT 1 FROM UNNEST(@ids_a) AS a WHERE STRPOS(entity_ids, a) > 0)
            AND EXISTS (SELECT 1 FROM UNNEST(@ids_b) AS b WHERE STRPOS(entity_ids, b) > 0)
        """
        params = [
            bigquery.ArrayQueryParameter("ids_a", "STRING", list(ids_a)),
            bigquery.ArrayQueryParameter("ids_b", "STRING", list(ids_b)),
        ]
    else:
        # Contributions that mention any of the IDs
        where = "EXISTS (SELECT 1 FROM UNNEST(@all_ids) AS aid WHERE STRPOS(entity_ids, aid) > 0)"
        params = [
            bigquery.ArrayQueryParameter("all_ids", "STRING", all_ids),
        ]

    sql = f"""
    SELECT
        paper_title,
        doi,
        result,
        methodology,
        treatment,
        entity_ids,
        contribution_label
    FROM `{table}`
    WHERE {where}
    LIMIT @limit
    """
    params.append(bigquery.ScalarQueryParameter("limit", "INT64", limit))

    try:
        result = client.query(
            sql,
            job_config=bigquery.QueryJobConfig(query_parameters=params),
        ).result()
        return [dict(row) for row in result]
    except Exception:
        logger.warning("ORKG BigQuery query failed (mode=%s)", mode, exc_info=True)
        return []


def _format_orkg_rows(rows: list[dict]) -> str:
    """Format ORKG rows into a text block for the Gemini prompt."""
    lines: list[str] = []
    for i, row in enumerate(rows, 1):
        parts: list[str] = []
        title = row.get("paper_title") or ""
        doi = row.get("doi") or ""
        result = row.get("result") or ""
        methodology = row.get("methodology") or ""
        treatment = row.get("treatment") or ""
        label = row.get("contribution_label") or ""

        if title:
            parts.append(f"Paper: {title.strip()}")
        if doi:
            parts.append(f"DOI: {doi.strip()}")
        if label:
            parts.append(f"Contribution: {label.strip()}")
        if result:
            parts.append(f"Result: {result.strip()[:300]}")
        if methodology:
            parts.append(f"Method: {methodology.strip()[:200]}")
        if treatment:
            parts.append(f"Treatment: {treatment.strip()[:200]}")

        if parts:
            lines.append(f"{i}. " + " | ".join(parts))

    return "\n".join(lines)
