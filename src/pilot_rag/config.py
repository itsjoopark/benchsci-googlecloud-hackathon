from dataclasses import dataclass
import os


@dataclass(frozen=True)
class Settings:
    project_id: str = os.getenv("GCP_PROJECT_ID", "multihopwanderer-1771992134")
    location: str = os.getenv("GCP_LOCATION", "us-central1")
    source_bq_dataset: str = os.getenv("SOURCE_BQ_DATASET", "kg_raw")
    target_bq_dataset: str = os.getenv("TARGET_BQ_DATASET", "multihopwanderer")
    source_table_a04: str = os.getenv("SRC_TABLE_A04_ABSTRACT", "A04_Abstract")
    source_table_c11: str = os.getenv("SRC_TABLE_C11_TRIALS", "C11_ClinicalTrials")
    source_table_c15: str = os.getenv("SRC_TABLE_C15_PATENTS", "C15_Patents")
    source_table_c06: str = os.getenv("SRC_TABLE_C06_PAPER_ENTITIES", "C06_Link_Papers_BioEntities")
    source_table_c13: str = os.getenv("SRC_TABLE_C13_TRIAL_ENTITIES", "C13_Link_ClinicalTrials_BioEntities")
    source_table_c18: str = os.getenv("SRC_TABLE_C18_PATENT_ENTITIES", "C18_Link_Patents_BioEntities")

    # Pilot controls
    pilot_doc_limit: int = int(os.getenv("PILOT_DOC_LIMIT", "5000"))
    max_chunk_chars: int = int(os.getenv("MAX_CHUNK_CHARS", "3500"))
    chunk_overlap_chars: int = int(os.getenv("CHUNK_OVERLAP_CHARS", "300"))
    min_linked_entities: int = int(os.getenv("MIN_LINKED_ENTITIES", "2"))
    enable_entity_type_filter: bool = os.getenv("ENABLE_ENTITY_TYPE_FILTER", "false").lower() == "true"
    allowed_entity_types_csv: str = os.getenv("ALLOWED_ENTITY_TYPES", "gene,disease,drug,pathway,protein")

    # Vertex model and index
    embedding_model: str = os.getenv("VERTEX_EMBEDDING_MODEL", "gemini-embedding-001")
    fallback_embedding_model: str = os.getenv("VERTEX_EMBEDDING_MODEL_FALLBACK", "text-embedding-005")
    vector_dimensions: int = int(os.getenv("VECTOR_DIMENSIONS", "3072"))
    vector_index_display_name: str = os.getenv("VECTOR_INDEX_DISPLAY_NAME", "pkg2-pilot-index")
    vector_endpoint_display_name: str = os.getenv("VECTOR_ENDPOINT_DISPLAY_NAME", "pkg2-pilot-endpoint")
    embed_workers: int = int(os.getenv("EMBED_WORKERS", "2"))
    embed_batch_size: int = int(os.getenv("EMBED_BATCH_SIZE", "250"))
    embed_max_retries: int = int(os.getenv("EMBED_MAX_RETRIES", "6"))
    embed_base_backoff_ms: int = int(os.getenv("EMBED_BASE_BACKOFF_MS", "500"))
    embed_request_interval_ms: int = int(os.getenv("EMBED_REQUEST_INTERVAL_MS", "100"))

    # API behavior
    default_top_k: int = int(os.getenv("DEFAULT_TOP_K", "5"))
    vector_score_weight: float = float(os.getenv("VECTOR_SCORE_WEIGHT", "0.7"))
    keyword_score_weight: float = float(os.getenv("KEYWORD_SCORE_WEIGHT", "0.3"))


SETTINGS = Settings()
