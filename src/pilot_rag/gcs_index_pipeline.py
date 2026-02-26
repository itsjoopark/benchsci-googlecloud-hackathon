from __future__ import annotations

import json
import random
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from google.api_core.exceptions import DeadlineExceeded, InternalServerError, ServiceUnavailable, TooManyRequests
from google.cloud import aiplatform, storage

from .bq_store import BQStore, EvidenceDoc
from .chunking import chunk_document
from .config import SETTINGS
from .vertex_client import EmbeddingService


@dataclass
class BuildGCSResult:
    run_id: str
    mode: str
    docs: int
    chunks: int
    embedded_chunks: int
    failed_chunks: int
    embedding_dim: int
    gcs_prefix: str
    shard_count: int
    index_resource: str
    manifest_stats_uri: str
    run_summary_uri: str
    failed_chunks_uri: str


class GCSBatchIndexBuilder:
    def __init__(self, bucket_name: str, prefix: str | None = None, run_id: str | None = None):
        self.bucket_name = bucket_name
        self.run_id = run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        self._custom_prefix = prefix
        self.storage_client = storage.Client(project=SETTINGS.project_id)
        self.bucket = self.storage_client.bucket(bucket_name)

    def _resolve_prefix(self, mode: str) -> str:
        if self._custom_prefix:
            return self._custom_prefix.rstrip("/")
        return f"vector-search/pkg2-{mode}/{self.run_id}"

    def _upload_file(self, local_path: Path, blob_name: str, content_type: str = "application/json") -> str:
        blob = self.bucket.blob(blob_name)
        blob.upload_from_filename(str(local_path), content_type=content_type)
        return f"gs://{self.bucket_name}/{blob_name}"

    def _upload_json(self, obj: dict, blob_name: str) -> str:
        blob = self.bucket.blob(blob_name)
        blob.upload_from_string(json.dumps(obj, ensure_ascii=False, indent=2), content_type="application/json")
        return f"gs://{self.bucket_name}/{blob_name}"

    def _download_json(self, blob_name: str) -> dict | None:
        blob = self.bucket.blob(blob_name)
        if not blob.exists(self.storage_client):
            return None
        return json.loads(blob.download_as_bytes().decode("utf-8"))

    @staticmethod
    def _is_retryable_error(exc: Exception) -> bool:
        if isinstance(exc, (TooManyRequests, ServiceUnavailable, DeadlineExceeded, InternalServerError)):
            return True
        msg = str(exc).lower()
        retry_tokens = ("429", "503", "rate", "quota", "unavailable", "deadline", "timeout", "internal")
        return any(t in msg for t in retry_tokens)

    def _embed_batches_parallel(
        self,
        chunks: list[dict],
        workers: int,
        batch_size: int,
        max_retries: int,
        base_backoff_ms: int,
        request_interval_ms: int,
    ) -> tuple[list[dict], list[dict], int, int]:
        batches: list[list[dict]] = [chunks[i : i + batch_size] for i in range(0, len(chunks), batch_size)]
        thread_local = threading.local()
        gate_lock = threading.Lock()
        gate = {"next_allowed": 0.0}

        def _get_service() -> EmbeddingService:
            svc = getattr(thread_local, "svc", None)
            if svc is None:
                svc = EmbeddingService(max_batch_size=batch_size)
                thread_local.svc = svc
            return svc

        def _call_batch(batch_records: list[dict]) -> tuple[list[dict], list[dict], int]:
            retries_used = 0
            for attempt in range(max_retries + 1):
                try:
                    with gate_lock:
                        now = time.monotonic()
                        wait = gate["next_allowed"] - now
                        if wait > 0:
                            time.sleep(wait)
                        gate["next_allowed"] = time.monotonic() + (request_interval_ms / 1000.0)

                    svc = _get_service()
                    vectors = svc.embed([r["chunk_text"] for r in batch_records], task_type="RETRIEVAL_DOCUMENT")
                    ok_records = []
                    for rec, vec in zip(batch_records, vectors):
                        out = dict(rec)
                        out["embedding"] = vec
                        ok_records.append(out)
                    return ok_records, [], retries_used
                except Exception as exc:
                    if attempt >= max_retries or not self._is_retryable_error(exc):
                        failed = []
                        for rec in batch_records:
                            d = dict(rec)
                            d["error"] = str(exc)
                            failed.append(d)
                        return [], failed, retries_used
                    retries_used += 1
                    sleep_s = (base_backoff_ms / 1000.0) * (2**attempt) + random.uniform(0, 0.25)
                    time.sleep(sleep_s)
            return [], [], retries_used

        ok_all: list[dict] = []
        failed_all: list[dict] = []
        total_retries = 0

        with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
            futures = [pool.submit(_call_batch, b) for b in batches]
            for fut in as_completed(futures):
                ok, failed, retries_used = fut.result()
                ok_all.extend(ok)
                failed_all.extend(failed)
                total_retries += retries_used

        dim = len(ok_all[0]["embedding"]) if ok_all else 0
        return ok_all, failed_all, total_retries, dim

    def _iter_docs(
        self,
        mode: str,
        limit: int,
        min_linked_entities: int,
        enable_entity_type_filter: bool,
        allowed_entity_types: list[str],
        start_after_doc_id: str,
    ) -> Iterable[EvidenceDoc]:
        bq = BQStore()
        if mode == "pilot":
            docs = bq.fetch_pilot_docs(limit=limit)
            docs = [d for d in docs if d.doc_id > start_after_doc_id]
            for d in docs:
                yield d
            return

        yielded = 0
        for d in bq.iter_filtered_docs(
            min_linked_entities=min_linked_entities,
            enable_entity_type_filter=enable_entity_type_filter,
            allowed_entity_types=allowed_entity_types,
            start_after_doc_id=start_after_doc_id,
        ):
            if limit > 0 and yielded >= limit:
                break
            yielded += 1
            yield d

    def _manifest_stats(
        self,
        mode: str,
        limit: int,
        min_linked_entities: int,
        enable_entity_type_filter: bool,
        allowed_entity_types: list[str],
    ) -> dict:
        bq = BQStore()
        if mode == "full":
            stats = bq.fetch_manifest_stats(
                min_linked_entities=min_linked_entities,
                enable_entity_type_filter=enable_entity_type_filter,
                allowed_entity_types=allowed_entity_types,
            )
            if limit > 0:
                stats["docs_total_capped"] = limit
            return stats

        docs = bq.fetch_pilot_docs(limit=max(1, limit))
        out = {
            "docs_total": len(docs),
            "docs_paper": sum(1 for d in docs if d.doc_type == "paper"),
            "docs_trial": sum(1 for d in docs if d.doc_type == "trial"),
            "docs_patent": sum(1 for d in docs if d.doc_type == "patent"),
            "pilot_limit": limit,
        }
        return out

    def build(
        self,
        mode: str,
        limit: int,
        batch_docs: int,
        workers: int,
        max_retries: int,
        min_linked_entities: int,
        enable_entity_type_filter: bool,
        allowed_entity_types: list[str],
        resume_run_id: str | None = None,
        dry_run: bool = False,
        skip_index: bool = False,
    ) -> BuildGCSResult:
        if mode not in {"pilot", "full"}:
            raise ValueError("mode must be 'pilot' or 'full'")

        if resume_run_id:
            self.run_id = resume_run_id

        prefix = self._resolve_prefix(mode)
        checkpoint_blob = f"{prefix}/checkpoint.json"
        checkpoint = self._download_json(checkpoint_blob) if resume_run_id else None

        start_after_doc_id = ""
        shard_index = 0
        totals = {
            "docs": 0,
            "chunks": 0,
            "embedded_chunks": 0,
            "failed_chunks": 0,
            "embedding_dim": 0,
            "retries": 0,
        }

        if checkpoint:
            start_after_doc_id = checkpoint.get("last_doc_id", "")
            shard_index = int(checkpoint.get("next_shard_index", 0))
            for k in totals:
                if k in checkpoint:
                    totals[k] = int(checkpoint[k])

        manifest = self._manifest_stats(
            mode=mode,
            limit=limit,
            min_linked_entities=min_linked_entities,
            enable_entity_type_filter=enable_entity_type_filter,
            allowed_entity_types=allowed_entity_types,
        )
        manifest.update(
            {
                "mode": mode,
                "run_id": self.run_id,
                "gcs_prefix": f"gs://{self.bucket_name}/{prefix}",
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "min_linked_entities": min_linked_entities,
                "enable_entity_type_filter": enable_entity_type_filter,
                "allowed_entity_types": allowed_entity_types,
                "batch_docs": batch_docs,
                "workers": workers,
                "max_retries": max_retries,
            }
        )
        manifest_uri = self._upload_json(manifest, f"{prefix}/manifest_stats.json")

        if dry_run:
            summary = {
                "mode": mode,
                "run_id": self.run_id,
                "dry_run": True,
                "docs": totals["docs"],
                "chunks": totals["chunks"],
                "embedded_chunks": totals["embedded_chunks"],
                "failed_chunks": totals["failed_chunks"],
                "retries": totals["retries"],
                "embedding_dim": totals["embedding_dim"],
                "manifest_stats_uri": manifest_uri,
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }
            summary_uri = self._upload_json(summary, f"{prefix}/run_summary.json")
            return BuildGCSResult(
                run_id=self.run_id,
                mode=mode,
                docs=0,
                chunks=0,
                embedded_chunks=0,
                failed_chunks=0,
                embedding_dim=0,
                gcs_prefix=f"gs://{self.bucket_name}/{prefix}",
                shard_count=0,
                index_resource="",
                manifest_stats_uri=manifest_uri,
                run_summary_uri=summary_uri,
                failed_chunks_uri="",
            )

        failed_chunk_rows: list[dict] = []
        docs_buffer: list[EvidenceDoc] = []
        last_doc_id = start_after_doc_id

        def _flush_shard(
            docs_for_shard: list[EvidenceDoc], idx: int
        ) -> tuple[int, int, int, int, int, int, str | None]:
            if not docs_for_shard:
                return 0, 0, 0, 0, None

            per_chunk: list[dict] = []
            for d in docs_for_shard:
                chunks = chunk_document(
                    doc_id=d.doc_id,
                    doc_type=d.doc_type,
                    text=d.text,
                    max_chars=SETTINGS.max_chunk_chars,
                    overlap_chars=SETTINGS.chunk_overlap_chars,
                )
                for c in chunks:
                    per_chunk.append(
                        {
                            "chunk_id": c.chunk_id,
                            "doc_id": c.doc_id,
                            "doc_type": c.doc_type,
                            "chunk_index": c.chunk_index,
                            "chunk_text": c.text,
                            "source_id": d.source_id,
                            "entity_count": d.entity_count,
                        }
                    )

            ok_rows, failed_rows, retries, dim = self._embed_batches_parallel(
                chunks=per_chunk,
                workers=workers,
                batch_size=SETTINGS.embed_batch_size,
                max_retries=max_retries,
                base_backoff_ms=SETTINGS.embed_base_backoff_ms,
                request_interval_ms=SETTINGS.embed_request_interval_ms,
            )

            with tempfile.TemporaryDirectory() as td:
                local_file = Path(td) / f"part-{idx:05d}.jsonl"
                with local_file.open("w", encoding="utf-8") as f:
                    for r in ok_rows:
                        rec = {
                            "id": r["chunk_id"],
                            "embedding": r["embedding"],
                            "restricts": [{"namespace": "doc_type", "allow": [r["doc_type"]]}],
                            "embedding_metadata": {
                                "doc_id": r["doc_id"],
                                "doc_type": r["doc_type"],
                                "source_id": r["source_id"],
                                "chunk_index": r["chunk_index"],
                                "entity_count": r["entity_count"],
                                "run_id": self.run_id,
                                "model_id": SETTINGS.embedding_model,
                            },
                        }
                        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                shard_uri = self._upload_file(local_file, f"{prefix}/shards/part-{idx:05d}.jsonl", content_type="application/json")

            for fr in failed_rows:
                failed_chunk_rows.append(
                    {
                        "run_id": self.run_id,
                        "shard_index": idx,
                        "chunk_id": fr["chunk_id"],
                        "doc_id": fr["doc_id"],
                        "doc_type": fr["doc_type"],
                        "source_id": fr.get("source_id", ""),
                        "error": fr.get("error", "embedding_failure"),
                        "created_at": datetime.now(timezone.utc).isoformat(),
                    }
                )

            return len(docs_for_shard), len(per_chunk), len(ok_rows), len(failed_rows), retries, dim, shard_uri

        for d in self._iter_docs(
            mode=mode,
            limit=limit,
            min_linked_entities=min_linked_entities,
            enable_entity_type_filter=enable_entity_type_filter,
            allowed_entity_types=allowed_entity_types,
            start_after_doc_id=start_after_doc_id,
        ):
            docs_buffer.append(d)
            last_doc_id = d.doc_id
            if len(docs_buffer) < batch_docs:
                continue

            docs_n, chunks_n, ok_n, fail_n, retries_n, dim_n, _ = _flush_shard(docs_buffer, shard_index)
            totals["docs"] += docs_n
            totals["chunks"] += chunks_n
            totals["embedded_chunks"] += ok_n
            totals["failed_chunks"] += fail_n
            totals["retries"] += retries_n
            if not totals["embedding_dim"] and dim_n:
                totals["embedding_dim"] = dim_n

            checkpoint_obj = {
                "run_id": self.run_id,
                "mode": mode,
                "last_doc_id": last_doc_id,
                "next_shard_index": shard_index + 1,
                **totals,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            self._upload_json(checkpoint_obj, checkpoint_blob)
            docs_buffer = []
            shard_index += 1

        if docs_buffer:
            docs_n, chunks_n, ok_n, fail_n, retries_n, dim_n, _ = _flush_shard(docs_buffer, shard_index)
            totals["docs"] += docs_n
            totals["chunks"] += chunks_n
            totals["embedded_chunks"] += ok_n
            totals["failed_chunks"] += fail_n
            totals["retries"] += retries_n
            if not totals["embedding_dim"] and dim_n:
                totals["embedding_dim"] = dim_n
            shard_index += 1
            self._upload_json(
                {
                    "run_id": self.run_id,
                    "mode": mode,
                    "last_doc_id": last_doc_id,
                    "next_shard_index": shard_index,
                    **totals,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                },
                checkpoint_blob,
            )

        failed_chunks_uri = ""
        if failed_chunk_rows:
            with tempfile.TemporaryDirectory() as td:
                local_failed = Path(td) / "failed_chunks.jsonl"
                with local_failed.open("w", encoding="utf-8") as f:
                    for row in failed_chunk_rows:
                        f.write(json.dumps(row, ensure_ascii=False) + "\n")
                failed_chunks_uri = self._upload_file(
                    local_failed,
                    f"{prefix}/failed_chunks.jsonl",
                    content_type="application/json",
                )

        index_resource = ""
        if not skip_index and totals["embedded_chunks"] > 0:
            aiplatform.init(project=SETTINGS.project_id, location=SETTINGS.location)
            index = aiplatform.MatchingEngineIndex.create_tree_ah_index(
                display_name=f"pkg2-{mode}-batch-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}",
                contents_delta_uri=f"gs://{self.bucket_name}/{prefix}/shards",
                dimensions=totals["embedding_dim"] or SETTINGS.vector_dimensions,
                approximate_neighbors_count=150,
                distance_measure_type="DOT_PRODUCT_DISTANCE",
                index_update_method="BATCH_UPDATE",
                sync=True,
            )
            index_resource = index.resource_name

        summary = {
            "mode": mode,
            "run_id": self.run_id,
            "docs": totals["docs"],
            "chunks": totals["chunks"],
            "embedded_chunks": totals["embedded_chunks"],
            "failed_chunks": totals["failed_chunks"],
            "retries": totals["retries"],
            "embedding_dim": totals["embedding_dim"],
            "workers": workers,
            "max_retries": max_retries,
            "batch_docs": batch_docs,
            "embed_batch_size": SETTINGS.embed_batch_size,
            "manifest_stats_uri": manifest_uri,
            "failed_chunks_uri": failed_chunks_uri,
            "index_resource": index_resource,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
        summary_uri = self._upload_json(summary, f"{prefix}/run_summary.json")

        return BuildGCSResult(
            run_id=self.run_id,
            mode=mode,
            docs=totals["docs"],
            chunks=totals["chunks"],
            embedded_chunks=totals["embedded_chunks"],
            failed_chunks=totals["failed_chunks"],
            embedding_dim=totals["embedding_dim"],
            gcs_prefix=f"gs://{self.bucket_name}/{prefix}",
            shard_count=shard_index,
            index_resource=index_resource,
            manifest_stats_uri=manifest_uri,
            run_summary_uri=summary_uri,
            failed_chunks_uri=failed_chunks_uri,
        )
