from __future__ import annotations

import math
from typing import Iterable

from google.cloud import aiplatform
from vertexai.language_models import TextEmbeddingInput, TextEmbeddingModel

from .config import SETTINGS


class EmbeddingService:
    def __init__(
        self,
        project_id: str = SETTINGS.project_id,
        location: str = SETTINGS.location,
        max_batch_size: int = SETTINGS.embed_batch_size,
    ):
        self.project_id = project_id
        self.location = location
        aiplatform.init(project=project_id, location=location)

        self.model_name = SETTINGS.embedding_model
        self.fallback_model_name = SETTINGS.fallback_embedding_model
        self.max_batch_size = max_batch_size
        self.model = self._load_model()

    def _load_model(self):
        try:
            return TextEmbeddingModel.from_pretrained(self.model_name)
        except Exception:
            return TextEmbeddingModel.from_pretrained(self.fallback_model_name)

    def embed(self, texts: Iterable[str], task_type: str = "RETRIEVAL_DOCUMENT") -> list[list[float]]:
        texts = list(texts)
        out: list[list[float]] = []
        for i in range(0, len(texts), self.max_batch_size):
            batch = texts[i : i + self.max_batch_size]
            items = [TextEmbeddingInput(text=t, task_type=task_type) for t in batch]
            resp = self.model.get_embeddings(items)
            out.extend([r.values for r in resp])
        return out

    @staticmethod
    def cosine_similarity(a: list[float], b: list[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        na = math.sqrt(sum(x * x for x in a))
        nb = math.sqrt(sum(y * y for y in b))
        return dot / (na * nb) if na and nb else 0.0


class VectorIndexService:
    """Managed wrapper for Vertex AI Vector Search objects.

    The pilot stores embeddings in BigQuery and performs node-pair constrained
    reranking in application code. This class prepares managed index resources
    for scale-up and can be extended to full ANN serving.
    """

    def __init__(self, project_id: str = SETTINGS.project_id, location: str = SETTINGS.location):
        self.project_id = project_id
        self.location = location
        aiplatform.init(project=project_id, location=location)

    def ensure_index(self, dimensions: int) -> tuple[str, str]:
        index = aiplatform.MatchingEngineIndex.create_tree_ah_index(
            display_name=SETTINGS.vector_index_display_name,
            dimensions=dimensions,
            approximate_neighbors_count=150,
            distance_measure_type="DOT_PRODUCT_DISTANCE",
            index_update_method="STREAM_UPDATE",
            sync=True,
        )
        endpoint = aiplatform.MatchingEngineIndexEndpoint.create(
            display_name=SETTINGS.vector_endpoint_display_name,
            public_endpoint_enabled=True,
            sync=True,
        )
        return index.resource_name, endpoint.resource_name
