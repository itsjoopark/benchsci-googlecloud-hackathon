"""
orkg_context.py — query ORKG evidence for an entity pair from BigQuery.

Requires: google-cloud-bigquery
Table   : multihopwanderer-1771992134.kg_raw.orkg_contributions

Entity ID formats (PKG convention):
  genes    → NCBIGene672
  drugs    → meshD002945  |  CHEBI35042  |  meshC027806
  diseases → meshD002583  |  meshD001943
"""

import re
from google.cloud import bigquery

_PROJECT  = "multihopwanderer-1771992134"
_TABLE    = "`multihopwanderer-1771992134.kg_raw.orkg_contributions`"
_SAFE_ID  = re.compile(r"^[A-Za-z0-9:_-]{3,40}$")


def get_orkg_context(entity_a: str, entity_b: str, max_rows: int = 10) -> str:
    """
    Return a plain-text evidence block for injecting into an LLM prompt.

    Queries orkg_contributions for contributions that mention BOTH entity_a
    AND entity_b in their entity_ids column (pipe-separated PKG IDs).
    Falls back to OR if the AND query returns nothing.

    Args:
        entity_a:  PKG entity ID for the first node  (e.g. "meshD002945")
        entity_b:  PKG entity ID for the second node (e.g. "meshD002583")
        max_rows:  cap on rows returned (default 10)

    Returns:
        Formatted string ready to paste into an LLM system/user prompt,
        or an empty string if no evidence exists.

    Example:
        context = get_orkg_context("meshD002945", "meshD002583")
        # → injects into prompt as:
        #   RESEARCH EVIDENCE FROM ORKG (18 papers, 2003–2024):
        #   [2024] "Pembrolizumab ... cervical cancer (KEYNOTE-A18)" (DOI:...)
        #     Disease/Problem: Cervical cancer
        #     Objective: To determine whether adding pembrolizumab ...
        #     Results: Pembrolizumab + CRT improved PFS (HR 0.70, p=0.002) ...
        #     Treatment: Pembrolizumab 200 mg Q3W + cisplatin-based CRT ...
        #   ...
    """
    if not (_SAFE_ID.match(entity_a) and _SAFE_ID.match(entity_b)):
        raise ValueError(f"Invalid entity ID(s): {entity_a!r}, {entity_b!r}")

    client = bigquery.Client(project=_PROJECT)

    def _fetch(operator: str):
        sql = f"""
            SELECT paper_title, paper_doi, paper_year,
                   disease_problem, objective, results, methodology,
                   risk_factors, treatment
            FROM {_TABLE}
            WHERE entity_ids LIKE '%{entity_a}%'
              {operator} entity_ids LIKE '%{entity_b}%'
            ORDER BY paper_year DESC
            LIMIT {max_rows}
        """
        return [dict(r) for r in client.query(sql).result()]

    rows = _fetch("AND")
    qualifier = ""
    if not rows:
        rows = _fetch("OR")
        qualifier = " (partial — single entity match)"

    if not rows:
        return ""

    years      = [r["paper_year"] for r in rows if r.get("paper_year")]
    year_range = f"{min(years)}–{max(years)}" if years else ""
    header     = f"RESEARCH EVIDENCE FROM ORKG ({len(rows)} paper(s), {year_range}){qualifier}:\n"

    blocks = []
    for r in rows:
        year  = r.get("paper_year") or "n.d."
        title = r.get("paper_title") or "Untitled"
        doi   = r.get("paper_doi")
        lines = [f'[{year}] "{title}"' + (f" (DOI:{doi})" if doi else "")]
        for key, label in [
            ("disease_problem", "Disease/Problem"),
            ("objective",       "Objective"),
            ("results",         "Results"),
            ("methodology",     "Methodology"),
            ("risk_factors",    "Risk factors"),
            ("treatment",       "Treatment"),
        ]:
            if (r.get(key) or "").strip():
                lines.append(f"  {label}: {r[key].strip()}")
        blocks.append("\n".join(lines))

    return header + "\n\n".join(blocks)


if __name__ == "__main__":
    import sys
    a = sys.argv[1] if len(sys.argv) > 2 else "meshD002945"
    b = sys.argv[2] if len(sys.argv) > 2 else "meshD002583"
    print(f"Querying ORKG for: {a} + {b}\n")
    result = get_orkg_context(a, b)
    print(result if result else "No results found.")
