ENTITY_TYPE_TO_BIOLINK: dict[str, str] = {
    "gene": "biolink:Gene",
    "disease": "biolink:DiseaseOrPhenotypicFeature",
    "drug": "biolink:Drug",
    "pathway": "biolink:Pathway",
    "protein": "biolink:Protein",
}

BIOLINK_FALLBACK = "biolink:NamedThing"

RELATION_TYPE_TO_PREDICATE: dict[str, str] = {
    "gene_disease": "biolink:gene_associated_with_condition",
    "drug_gene": "biolink:affects",
    "drug_disease": "biolink:treats",
    "gene_gene": "biolink:genetically_interacts_with",
    "disease_disease": "biolink:related_to",
}

PREDICATE_FALLBACK = "biolink:related_to"

ENTITY_TYPE_COLORS: dict[str, str] = {
    "gene": "#4A90D9",
    "disease": "#E74C3C",
    "drug": "#2ECC71",
    "pathway": "#F39C12",
    "protein": "#9B59B6",
}

COLOR_FALLBACK = "#95A5A6"
