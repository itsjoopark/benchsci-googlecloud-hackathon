#!/usr/bin/env python3
"""
Build ORKG research-contribution enrichment CSV.

Reads rdf-export-orkg.nt (N-Triples, ~4.5 M lines) and
data/pkg2/pkg2_C23_BioEntities.tsv.gz, then writes
data/processed/orkg_contributions.csv.

One row per live Contribution node that has at least one content field
(objective / results / methodology / risk_factors / treatment).
Each row is annotated with PKG EntityIds found via mention matching.
"""

import csv
import gzip
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

ROOT = Path(__file__).parent.parent
NT_FILE = ROOT / "rdf-export-orkg.nt"
PKG_ENTITIES = ROOT / "data" / "pkg2" / "pkg2_C23_BioEntities.tsv.gz"
OUTPUT_FILE = ROOT / "data" / "processed" / "orkg_contributions.csv"

OUTPUT_COLS = [
    "contribution_id",
    "paper_id",
    "paper_title",
    "paper_doi",
    "paper_year",
    "venue",
    "disease_problem",
    "objective",
    "results",
    "methodology",
    "risk_factors",
    "treatment",
    "entity_ids",
    "entity_names",
]

# ---------------------------------------------------------------------------
# Step 1 — URI → short local ID
# ---------------------------------------------------------------------------

_ORKG_RESOURCE  = "http://orkg.org/orkg/resource/"
_ORKG_PREDICATE = "http://orkg.org/orkg/predicate/"
_ORKG_CLASS     = "http://orkg.org/orkg/class/"
_RDF_TYPE       = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"
_RDFS_LABEL     = "http://www.w3.org/2000/01/rdf-schema#label"


def local_id(uri: str) -> str:
    if uri.startswith(_ORKG_RESOURCE):
        return uri[len(_ORKG_RESOURCE):]
    if uri.startswith(_ORKG_PREDICATE):
        return uri[len(_ORKG_PREDICATE):]
    if uri.startswith(_ORKG_CLASS):
        return uri[len(_ORKG_CLASS):]
    if uri == _RDF_TYPE:
        return "rdf:type"
    if uri == _RDFS_LABEL:
        return "rdfs:label"
    # External URI: return as-is (e.g. wikidata Q-nodes in object position)
    return uri


# ---------------------------------------------------------------------------
# Step 2 — NT line parser + selective graph load
# ---------------------------------------------------------------------------

# Only store triples whose predicate matches one of these local IDs.
TRACKED_PREDICATES = {
    "rdf:type", "rdfs:label",
    "P31",                              # paper → contribution pointer
    "P107003", "P15051",                # objective (two template variants)
    "P6001",                            # results
    "P15239", "P147021",                # methodology
    "P15648",                           # therapy/treatment (literal)
    "P11", "P32", "P134011", "P15584",  # disease / research problem
    "P177047", "P177048",               # cancer stages, treatment strategies
    "wikidata:P5642",                   # risk factor (literal or resource)
    "P26", "P28", "P29",                # doi, authors, year
    "HAS_VENUE", "P30",                 # venue, research field
}


def _parse_line(line: str):
    """
    Parse a single N-Triples line.

    Returns (subj_local, pred_local, obj_type, obj_value) or None.
    obj_type is "uri" or "literal"; obj_value is the already-decoded string.
    """
    line = line.strip()
    if not line or line[0] == "#":
        return None

    # ---- Subject (<URI>) ----
    if line[0] != "<":
        return None  # blank nodes not needed
    try:
        s_end = line.index(">", 1)
    except ValueError:
        return None
    subj_uri = line[1:s_end]
    pos = s_end + 1
    # skip whitespace
    while pos < len(line) and line[pos] == " ":
        pos += 1

    # ---- Predicate (<URI>) ----
    if pos >= len(line) or line[pos] != "<":
        return None
    try:
        p_end = line.index(">", pos + 1)
    except ValueError:
        return None
    pred_uri = line[pos + 1:p_end]
    pred_local = local_id(pred_uri)
    if pred_local not in TRACKED_PREDICATES:
        return None  # discard early — keeps memory low

    subj_local = local_id(subj_uri)
    pos = p_end + 1
    while pos < len(line) and line[pos] == " ":
        pos += 1

    # ---- Object (<URI> or "literal") ----
    if pos >= len(line):
        return None

    if line[pos] == "<":
        try:
            o_end = line.index(">", pos + 1)
        except ValueError:
            return None
        obj_uri = line[pos + 1:o_end]
        return (subj_local, pred_local, "uri", local_id(obj_uri))

    if line[pos] == '"':
        # Scan for closing quote, skipping backslash-escaped chars
        i = pos + 1
        while i < len(line):
            ch = line[i]
            if ch == "\\":
                i += 2
                continue
            if ch == '"':
                break
            i += 1
        raw = line[pos + 1:i]
        # Unescape common escapes
        raw = (
            raw.replace('\\"', '"')
               .replace("\\n", "\n")
               .replace("\\t", "\t")
               .replace("\\\\", "\\")
        )
        return (subj_local, pred_local, "literal", raw)

    return None  # blank-node object or malformed


def load_graph(nt_file: Path) -> dict:
    """
    Single-pass load: stream NT file, discard untracked predicates.
    Returns graph[node_id][pred] = [(obj_type, obj_value), ...]
    """
    graph: dict = defaultdict(lambda: defaultdict(list))
    n_stored = 0
    n_lines = 0

    print(f"Streaming {nt_file.name} …", flush=True)
    with open(nt_file, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            n_lines += 1
            if n_lines % 1_000_000 == 0:
                print(f"  … {n_lines:,} lines read, {n_stored:,} triples kept", flush=True)
            parsed = _parse_line(line)
            if parsed is None:
                continue
            subj, pred, obj_type, obj_value = parsed
            graph[subj][pred].append((obj_type, obj_value))
            n_stored += 1

    print(
        f"  Finished: {n_lines:,} lines, {n_stored:,} triples kept, "
        f"{len(graph):,} nodes in graph",
        flush=True,
    )
    return graph


# ---------------------------------------------------------------------------
# Steps 3–4 — Identify live Contributions/Papers, build reverse index
# ---------------------------------------------------------------------------

def identify_nodes(graph: dict) -> tuple:
    """
    Walk the graph to find live Contribution and Paper nodes, then build
    a contrib_id → paper_id reverse index from Paper.P31 edges.
    """
    contributions: set = set()
    papers: set = set()

    for node_id, preds in graph.items():
        type_vals = {v for _, v in preds.get("rdf:type", [])}
        if "Contribution" in type_vals and "ContributionDeleted" not in type_vals:
            contributions.add(node_id)
        if (
            ("Paper" in type_vals or "FeaturedPaper" in type_vals)
            and "PaperDeleted" not in type_vals
        ):
            papers.add(node_id)

    # P31: Paper → Contribution (paper has the edge, contribution is the target)
    contrib_to_paper: dict = {}
    for paper_id in papers:
        for _, contrib_id in graph[paper_id].get("P31", []):
            contrib_to_paper[contrib_id] = paper_id

    print(f"  Live contributions : {len(contributions):,}")
    print(f"  Live papers        : {len(papers):,}")
    print(f"  Contributions with known paper: {len(contrib_to_paper):,}")
    return contributions, papers, contrib_to_paper


# ---------------------------------------------------------------------------
# Step 5 — PKG BioEntities vocabulary
# ---------------------------------------------------------------------------

def load_bio_entities(pkg_file: Path) -> tuple:
    """
    Load gene/drug/disease mentions from PKG C23 BioEntities.
    Returns (mention_to_id, first_word_index).
    """
    KEEP_TYPES = {"gene", "drug", "disease"}
    mention_to_id: dict = {}
    first_word_index: dict = defaultdict(list)
    skipped = 0

    with gzip.open(pkg_file, "rt") as fh:
        fh.readline()  # header
        for line in fh:
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 3:
                continue
            entity_id   = parts[0].strip()
            entity_type = parts[1].strip()
            mention     = parts[2].strip()

            if entity_type not in KEEP_TYPES or len(mention) < 4:
                skipped += 1
                continue

            mention_lower = mention.lower()
            if mention_lower in mention_to_id:
                continue  # keep first occurrence

            mention_to_id[mention_lower] = entity_id
            first_word = mention_lower.split()[0]
            first_word_index[first_word].append(mention_lower)

    print(
        f"  BioEntities loaded: {len(mention_to_id):,} mentions "
        f"({skipped:,} skipped)",
        flush=True,
    )
    return mention_to_id, first_word_index


# ---------------------------------------------------------------------------
# Step 6 — Fast entity mention finder
# ---------------------------------------------------------------------------

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def find_entities(
    text: str,
    mention_to_id: dict,
    first_word_index: dict,
) -> tuple:
    """
    Return (entity_ids, entity_names) for BioEntities found in text.
    Uses first-word index to avoid full scan of 260 K mentions.
    """
    if not text:
        return [], []

    text_lower = text.lower()
    tokens = set(_TOKEN_RE.findall(text_lower))

    # Candidates: mentions whose first word appears in the text tokens
    candidates: set = set()
    for token in tokens:
        for mention in first_word_index.get(token, []):
            candidates.add(mention)

    entity_ids: list = []
    entity_names: list = []
    seen_ids: set = set()

    for mention in candidates:
        if mention in text_lower:
            eid = mention_to_id[mention]
            if eid not in seen_ids:
                entity_ids.append(eid)
                entity_names.append(mention)
                seen_ids.add(eid)

    return entity_ids, entity_names


# ---------------------------------------------------------------------------
# Row builder helpers
# ---------------------------------------------------------------------------

def _resolve(node_id: str, graph: dict) -> Optional[str]:
    """Look up rdfs:label for a graph node (returns None if absent)."""
    node = graph.get(node_id)
    if node is None:
        return None
    entries = node.get("rdfs:label", [])
    if entries:
        return entries[0][1]
    return None


def _clean(text: str) -> str:
    """Replace newlines/tabs with spaces and collapse runs of whitespace."""
    return " ".join(text.split())


def _get_text(entries: list, graph: dict) -> Optional[str]:
    """First non-empty value from a list of (obj_type, obj_value) pairs."""
    for obj_type, obj_value in entries:
        if obj_type == "literal":
            val = _clean(obj_value)
            if val:
                return val
        else:  # uri → resolve label
            label = _resolve(obj_value, graph)
            if label:
                val = _clean(label)
                if val:
                    return val
    return None


def _get_all_texts(entries: list, graph: dict) -> list:
    """All non-empty values from a list of (obj_type, obj_value) pairs."""
    out = []
    for obj_type, obj_value in entries:
        if obj_type == "literal":
            val = _clean(obj_value)
            if val:
                out.append(val)
        else:
            label = _resolve(obj_value, graph)
            if label:
                val = _clean(label)
                if val:
                    out.append(val)
    return out


def _first(*pred_keys: str, nid: str, graph: dict) -> str:
    """First non-empty text value across the given predicate keys on node nid."""
    node = graph.get(nid, {})
    for key in pred_keys:
        val = _get_text(node.get(key, []), graph)
        if val:
            return val
    return ""


def _all_pipe(*pred_keys: str, nid: str, graph: dict) -> str:
    """Pipe-joined all texts from multiple predicate keys on node nid."""
    node = graph.get(nid, {})
    texts = []
    for key in pred_keys:
        texts.extend(_get_all_texts(node.get(key, []), graph))
    return "|".join(texts)


# ---------------------------------------------------------------------------
# Steps 7–8 — Build rows + write CSV
# ---------------------------------------------------------------------------

def build_rows(
    graph: dict,
    contributions: set,
    contrib_to_paper: dict,
    mention_to_id: dict,
    first_word_index: dict,
) -> list:
    rows = []
    n_no_paper = 0
    n_no_content = 0

    for contrib_id in contributions:
        paper_id = contrib_to_paper.get(contrib_id)
        if not paper_id:
            n_no_paper += 1
            continue

        # --- Paper-level fields ---
        paper_title = _clean(_resolve(paper_id, graph) or "")
        paper_doi   = _first("P26",      nid=paper_id, graph=graph)
        paper_year  = _first("P29",      nid=paper_id, graph=graph)
        venue       = _first("HAS_VENUE", nid=paper_id, graph=graph)

        # --- Contribution-level fields ---
        disease_problem = _first(
            "P11", "P32", "P134011", "P15584", nid=contrib_id, graph=graph
        )
        objective   = _first("P107003", "P15051", nid=contrib_id, graph=graph)
        results     = _first("P6001",            nid=contrib_id, graph=graph)
        methodology = _first("P15239", "P147021", nid=contrib_id, graph=graph)
        risk_factors = _all_pipe(
            "wikidata:P5642", nid=contrib_id, graph=graph
        )
        treatment = _all_pipe(
            "P177048", "P177047", "P15648", nid=contrib_id, graph=graph
        )

        # Skip rows where all content fields are empty
        if not any([objective, results, methodology, risk_factors, treatment]):
            n_no_content += 1
            continue

        # --- Entity tagging ---
        combined_text = " ".join(
            filter(None, [
                disease_problem, objective, results,
                methodology, risk_factors, treatment, paper_title,
            ])
        )
        eids, enames = find_entities(combined_text, mention_to_id, first_word_index)

        # Skip rows with no biomedical entity match
        if not eids:
            n_no_content += 1
            continue

        rows.append({
            "contribution_id": contrib_id,
            "paper_id":        paper_id,
            "paper_title":     paper_title,
            "paper_doi":       paper_doi,
            "paper_year":      paper_year,
            "venue":           venue,
            "disease_problem": disease_problem,
            "objective":       objective,
            "results":         results,
            "methodology":     methodology,
            "risk_factors":    risk_factors,
            "treatment":       treatment,
            "entity_ids":      "|".join(eids),
            "entity_names":    "|".join(enames),
        })

    print(f"  Rows built           : {len(rows):,}")
    print(f"  Skipped (no paper)   : {n_no_paper:,}")
    print(f"  Skipped (no content) : {n_no_content:,}")
    return rows


def write_csv(rows: list, output_file: Path) -> None:
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=OUTPUT_COLS)
        writer.writeheader()
        writer.writerows(rows)
    size_kb = output_file.stat().st_size / 1024
    print(
        f"  Wrote {output_file.relative_to(ROOT)}  "
        f"({len(rows):,} rows, {size_kb:.0f} KB)",
        flush=True,
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    if not NT_FILE.exists():
        print(f"ERROR: NT file not found: {NT_FILE}", file=sys.stderr)
        sys.exit(1)
    if not PKG_ENTITIES.exists():
        print(f"ERROR: PKG entities not found: {PKG_ENTITIES}", file=sys.stderr)
        sys.exit(1)

    print("=" * 60)
    print("Step 1–2: Load ORKG graph (single pass)")
    print("=" * 60)
    graph = load_graph(NT_FILE)

    print()
    print("=" * 60)
    print("Step 3–4: Identify contributions / papers")
    print("=" * 60)
    contributions, papers, contrib_to_paper = identify_nodes(graph)

    print()
    print("=" * 60)
    print("Step 5: Load PKG BioEntities vocabulary")
    print("=" * 60)
    mention_to_id, first_word_index = load_bio_entities(PKG_ENTITIES)

    print()
    print("=" * 60)
    print("Step 7: Build contribution rows")
    print("=" * 60)
    rows = build_rows(graph, contributions, contrib_to_paper, mention_to_id, first_word_index)

    print()
    print("=" * 60)
    print("Step 8: Write CSV")
    print("=" * 60)
    write_csv(rows, OUTPUT_FILE)

    # Quick entity-tagging stats
    n_with_entities = sum(1 for r in rows if r["entity_ids"])
    print(f"  Rows with ≥1 entity : {n_with_entities:,} ({100*n_with_entities/max(len(rows),1):.1f}%)")
    print()
    print("Done.")


if __name__ == "__main__":
    main()
