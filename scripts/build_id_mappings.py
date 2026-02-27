#!/usr/bin/env python3
"""
Build PKG <-> PrimeKG ID mapping files.

Outputs:
  data/mappings/chebi_to_drugbank.json  -- { "CHEBI10003": "DB00001", ... }
  data/mappings/mesh_to_drugbank.json   -- { "meshC531550": "DB04855", ... }
  data/mappings/mesh_to_mondo.json      -- { "meshD001943": "MONDO:0021100", ... }

PKG drug ID breakdown:
  meshC*  156,976  (MeSH Supplemental Concepts — dominant)
  CHEBI*   33,862
  meshD*    5,811
"""

import gzip
import io
import json
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

OUTPUT_DIR = Path(__file__).parent.parent / "data" / "mappings"

# UniChem: DrugBank (src2) → ChEBI (src7)
UNICHEM_DB_CHEBI_URL = (
    "https://ftp.ebi.ac.uk/pub/databases/chembl/UniChem/data/"
    "wholeSourceMapping/src_id2/src2src7.txt.gz"
)
# UniChem: DrugBank (src2) → FDA SRS/UNII (src14)
UNICHEM_DB_SRS_URL = (
    "https://ftp.ebi.ac.uk/pub/databases/chembl/UniChem/data/"
    "wholeSourceMapping/src_id2/src2src14.txt.gz"
)
# NLM MeSH supplemental concepts (drugs have UNII registry numbers)
MESH_SUPP_URL = (
    "https://nlmpubs.nlm.nih.gov/projects/mesh/MESH_FILES/xmlmesh/supp2026.gz"
)
MONDO_OBO_URL = "https://purl.obolibrary.org/obo/mondo.obo"

PKG_ENTITIES = (
    Path(__file__).parent.parent / "data" / "pkg2" / "pkg2_C23_BioEntities.tsv.gz"
)


# ---------------------------------------------------------------------------
# Shared helper
# ---------------------------------------------------------------------------

def _fetch_unichem_gz(url: str) -> dict[str, str]:
    """Download a UniChem src→src gz file and return {from_id: to_id}."""
    with urllib.request.urlopen(url) as resp:
        raw = resp.read()
    mapping: dict[str, str] = {}
    with gzip.open(io.BytesIO(raw), "rt") as fh:
        fh.readline()  # skip header
        for line in fh:
            parts = line.rstrip("\n").split("\t")
            if len(parts) >= 2 and parts[0].strip() and parts[1].strip():
                mapping[parts[0].strip()] = parts[1].strip()
    return mapping


# ---------------------------------------------------------------------------
# Step 1: ChEBI → DrugBank via UniChem
# ---------------------------------------------------------------------------

def build_chebi_to_drugbank() -> dict[str, str]:
    print("Downloading UniChem DrugBank→ChEBI mapping …")
    # File col0=DrugBank (DB*), col1=CHEBI:NNNNN — invert to CHEBI{N} → DrugBank
    db_to_chebi_raw = _fetch_unichem_gz(UNICHEM_DB_CHEBI_URL)
    mapping: dict[str, str] = {}
    for db_id, chebi_raw in db_to_chebi_raw.items():
        # "CHEBI:30402" → "CHEBI30402"
        chebi_key = chebi_raw.replace("CHEBI:", "CHEBI")
        mapping[chebi_key] = db_id
    print(f"  → {len(mapping):,} ChEBI→DrugBank entries")
    return mapping


# ---------------------------------------------------------------------------
# Step 2: MeSH (drug) → DrugBank via UNII bridge
#   NLM supp XML: MeSH-ID → UNII
#   UniChem src2src14 (inverted): UNII → DrugBank
# ---------------------------------------------------------------------------

def build_mesh_to_drugbank() -> dict[str, str]:
    # 2a. Build UNII → DrugBank from UniChem
    print("Downloading UniChem DrugBank→SRS/UNII mapping …")
    db_to_unii = _fetch_unichem_gz(UNICHEM_DB_SRS_URL)
    unii_to_db: dict[str, str] = {v: k for k, v in db_to_unii.items()}
    print(f"  → {len(unii_to_db):,} UNII→DrugBank entries")

    # 2b. Parse NLM MeSH supplemental concepts XML: MeSH-ID → UNII
    print("Downloading NLM MeSH supplemental concepts XML …")
    with urllib.request.urlopen(MESH_SUPP_URL) as resp:
        raw = resp.read()
    with gzip.open(io.BytesIO(raw), "rb") as fh:
        xml_bytes = fh.read()

    root = ET.fromstring(xml_bytes)
    mesh_id_to_unii: dict[str, str] = {}
    for rec in root.findall("SupplementalRecord"):
        ui_el = rec.find("SupplementalRecordUI")
        if ui_el is None:
            continue
        mesh_id = ui_el.text.strip()  # e.g. "C531550"
        # Preferred UNII is in ConceptList/Concept[@PreferredConceptYN='Y']/RegistryNumberList/RegistryNumber
        for concept in rec.findall(".//Concept[@PreferredConceptYN='Y']"):
            rn_el = concept.find("RegistryNumberList/RegistryNumber")
            if rn_el is not None and rn_el.text:
                unii = rn_el.text.strip()
                if unii:
                    mesh_id_to_unii[mesh_id] = unii
                    break

    print(f"  → {len(mesh_id_to_unii):,} MeSH supplemental IDs with UNII")

    # 2c. Join: mesh{ID} → UNII → DrugBank
    mapping: dict[str, str] = {}
    for mesh_id, unii in mesh_id_to_unii.items():
        db_id = unii_to_db.get(unii)
        if db_id:
            mapping[f"mesh{mesh_id}"] = db_id

    print(f"  → {len(mapping):,} MeSH→DrugBank entries")
    return mapping


# ---------------------------------------------------------------------------
# Step 3: MeSH (disease) → MONDO via MONDO OBO
# ---------------------------------------------------------------------------

def build_mesh_to_mondo() -> dict[str, str]:
    print("Downloading MONDO OBO file …")
    with urllib.request.urlopen(MONDO_OBO_URL) as resp:
        obo_text = resp.read().decode("utf-8")

    mapping: dict[str, str] = {}
    current_id: str | None = None
    mesh_xrefs: list[str] = []

    for line in obo_text.splitlines():
        line = line.strip()
        if line == "[Term]":
            if current_id and mesh_xrefs:
                for mesh in mesh_xrefs:
                    mapping[f"mesh{mesh}"] = current_id
            current_id = None
            mesh_xrefs = []
        elif line.startswith("id: MONDO:"):
            current_id = line[4:]  # e.g. "MONDO:0021100"
        elif line.startswith("xref: MESH:"):
            # "xref: MESH:D001943 {source=...}" → "D001943"
            raw_val = line[len("xref: MESH:"):]
            mesh_id = raw_val.split()[0].split("{")[0].strip()
            if mesh_id:
                mesh_xrefs.append(mesh_id)

    # flush last block
    if current_id and mesh_xrefs:
        for mesh in mesh_xrefs:
            mapping[f"mesh{mesh}"] = current_id

    print(f"  → {len(mapping):,} MeSH→MONDO entries")
    return mapping


# ---------------------------------------------------------------------------
# Write + stats
# ---------------------------------------------------------------------------

def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as fh:
        json.dump(data, fh, separators=(",", ":"))
    print(f"  Wrote {path}  ({len(data):,} entries, {path.stat().st_size / 1024:.1f} KB)")


def coverage_stats(
    chebi_map: dict, mesh_drug_map: dict, mesh_disease_map: dict
) -> None:
    if not PKG_ENTITIES.exists():
        print("PKG C23 BioEntities not found — skipping coverage stats.")
        return

    print("\nCoverage against PKG C23 BioEntities …")
    drug_chebi_total = drug_chebi_mapped = 0
    drug_mesh_total = drug_mesh_mapped = 0
    disease_total = disease_mapped = 0

    with gzip.open(PKG_ENTITIES, "rt") as fh:
        fh.readline()
        for line in fh:
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 2:
                continue
            eid, etype = parts[0].strip(), parts[1].strip()
            if etype == "drug":
                if eid.startswith("CHEBI"):
                    drug_chebi_total += 1
                    if eid in chebi_map:
                        drug_chebi_mapped += 1
                elif eid.lower().startswith("mesh"):
                    drug_mesh_total += 1
                    if eid in mesh_drug_map:
                        drug_mesh_mapped += 1
            elif etype == "disease":
                disease_total += 1
                if eid in mesh_disease_map:
                    disease_mapped += 1

    def pct(n, d):
        return f"{100*n/d:.1f}%" if d else "n/a"

    print(f"  Drugs  CHEBI: {drug_chebi_mapped:>6,} / {drug_chebi_total:>6,}  ({pct(drug_chebi_mapped, drug_chebi_total)})")
    print(f"  Drugs  MeSH : {drug_mesh_mapped:>6,} / {drug_mesh_total:>6,}  ({pct(drug_mesh_mapped, drug_mesh_total)})")
    total_drug = drug_chebi_total + drug_mesh_total
    total_drug_mapped = drug_chebi_mapped + drug_mesh_mapped
    print(f"  Drugs  TOTAL: {total_drug_mapped:>6,} / {total_drug:>6,}  ({pct(total_drug_mapped, total_drug)})")
    print(f"  Diseases     : {disease_mapped:>6,} / {disease_total:>6,}  ({pct(disease_mapped, disease_total)})")


def spot_check(chebi_map: dict, mesh_drug_map: dict, mesh_disease_map: dict) -> None:
    print("\nSpot checks:")
    checks = [
        (chebi_map,        "CHEBI100246",  "DB01059",       "nitrofurantoin"),
        (mesh_drug_map,    "meshC531550",  "DB09074",        "olaparib"),
        (mesh_disease_map, "meshD001943",  "MONDO:0021100",  "breast neoplasm"),
    ]
    for mapping, key, expected, label in checks:
        result = mapping.get(key)
        status = "PASS" if result == expected else f"FAIL (got {result!r})"
        print(f"  [{status}] {key} → {result!r}  ({label}, expected {expected!r})")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    chebi_map = build_chebi_to_drugbank()
    mesh_drug_map = build_mesh_to_drugbank()
    mesh_disease_map = build_mesh_to_mondo()

    write_json(OUTPUT_DIR / "chebi_to_drugbank.json", chebi_map)
    write_json(OUTPUT_DIR / "mesh_to_drugbank.json", mesh_drug_map)
    write_json(OUTPUT_DIR / "mesh_to_mondo.json", mesh_disease_map)

    spot_check(chebi_map, mesh_drug_map, mesh_disease_map)
    coverage_stats(chebi_map, mesh_drug_map, mesh_disease_map)

    print("\nDone.")


if __name__ == "__main__":
    main()
