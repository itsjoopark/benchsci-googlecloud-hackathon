ENTITY_TYPE_TO_BIOLINK: dict[str, str] = {
    "gene": "biolink:Gene",
    "disease": "biolink:DiseaseOrPhenotypicFeature",
    "drug": "biolink:Drug",
    "pathway": "biolink:Pathway",
    "protein": "biolink:Protein",
}

BIOLINK_FALLBACK = "biolink:NamedThing"

RELATION_TYPE_TO_PREDICATE: dict[str, str] = {
    "gene_disease":    "biolink:gene_associated_with_condition",
    "disease_gene":    "biolink:gene_associated_with_condition",
    "drug_gene":       "biolink:affects",
    "gene_drug":       "biolink:affects",
    "drug_disease":    "biolink:treats",
    "disease_drug":    "biolink:treats",
    "gene_gene":       "biolink:genetically_interacts_with",
    "disease_disease": "biolink:correlated_with",
    "drug_drug":       "biolink:interacts_with",
}

PREDICATE_FALLBACK = "biolink:related_to"

# Human-readable labels derived from PrimeKG's display_relation column.
# These provide domain-specific terminology (e.g. "target" for drug→gene)
# instead of generic Biolink predicate names.
RELATION_TYPE_TO_DISPLAY_LABEL: dict[str, str] = {
    "disease_gene":    "associated with",
    "gene_disease":    "associated with",
    "drug_gene":       "target",
    "gene_drug":       "target",
    "drug_disease":    "indication",
    "disease_drug":    "indication",
    "gene_gene":       "interacts with",
    "disease_disease": "associated with",
    "drug_drug":       "synergistic interaction",
}

DISPLAY_LABEL_FALLBACK = "related to"

ENTITY_TYPE_COLORS: dict[str, str] = {
    "gene": "#4A90D9",
    "disease": "#E74C3C",
    "drug": "#2ECC71",
    "pathway": "#F39C12",
    "protein": "#9B59B6",
}

COLOR_FALLBACK = "#95A5A6"
