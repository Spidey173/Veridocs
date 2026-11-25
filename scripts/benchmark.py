"""
Veridocs reproducible local performance benchmark & profiler.

Measures:
  1. Upload -> ready ingestion time (10-page and 50-page synthetic digital PDFs)
  2. Peak memory during ingestion (tracemalloc peak MiB) and overall process RSS
  3. Streaming Q&A query latency: Time-to-First-Token (TTFT) and total SSE duration
  4. Verification latency (check_citations across multi-claim / multi-chunk inputs)
  5. Structured Summary and Executive Report generation latency
  6. Multi-session / analytics DB query latency (list_sessions, GET /analytics)

Usage:
  .venv/bin/python scripts/benchmark.py
  .venv/bin/python scripts/benchmark.py --json
  .venv/bin/python scripts/benchmark.py --cprofile
"""

from __future__ import annotations

import argparse
import cProfile
import io
import json
import logging
import os
import pstats
import resource
import sys
import tempfile
import time
import tracemalloc
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, List

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def build_synthetic_pdf(num_pages: int, title: str = "Service Level Agreement") -> bytes:
    """Create a realistic multi-page digital PDF using ReportLab."""
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    width, height = letter

    sections = [
        (
            "1. Definitions and Scope",
            "This Agreement governs cloud document processing services for Acme Enterprise Holdings.",
        ),
        (
            "2. Payment Terms and Fees",
            "All undisputed invoices are payable within thirty (30) days of receipt at $12,500 per month.",
        ),
        (
            "3. Availability and SLA",
            "Provider warrants 99.95% monthly platform availability with service credits for downtime.",
        ),
        (
            "4. Data Protection and Confidentiality",
            "Confidential records shall remain encrypted at rest using AES-256 and TLS 1.3 in transit.",
        ),
        (
            "5. Term and Termination",
            "Either party may terminate for material breach with thirty (30) days written notice before renewal.",
        ),
    ]

    for page_idx in range(1, num_pages + 1):
        y = height - 60
        c.setFont("Helvetica-Bold", 14)
        c.drawString(50, y, f"{title} — Page {page_idx}")
        y -= 28

        for sec_idx, (heading, lead) in enumerate(sections, start=1):
            c.setFont("Helvetica-Bold", 11)
            c.drawString(50, y, f"Section {page_idx}.{sec_idx}: {heading}")
            y -= 16
            c.setFont("Helvetica", 10)
            for line_num in range(3):
                line = (
                    f"{lead} Clause reference {page_idx}.{sec_idx}.{line_num + 1}: "
                    f"Compliance review date 2026-06-{(page_idx % 28) + 1:02d}, liability cap $250,000 USD."
                )
                c.drawString(50, y, line[:95])
                y -= 14
            y -= 8

        c.showPage()

    c.save()
    return buf.getvalue()


class _OfflineBenchmarkLLM:
    """Deterministic in-process LLM stub so benchmarks isolate local pipeline performance."""

    def is_configured(self) -> bool:
        return True

    def generate_answer(
        self,
        question: str,
        chunks: List[Dict[str, Any]],
        history: List[Dict[str, str]] | None = None,
    ) -> str:
        return (
            "All undisputed invoices are payable within thirty (30) days of receipt at $12,500 per month [1]. "
            "Provider warrants 99.95% monthly platform availability with service credits for downtime [2]. "
            "Either party may terminate for material breach with thirty (30) days written notice [3]."
        )

    async def generate_answer_stream(
        self,
        question: str,
        chunks: List[Dict[str, Any]],
        history: List[Dict[str, str]] | None = None,
    ) -> AsyncGenerator[str, None]:
        answer = self.generate_answer(question, chunks, history)
        for token in answer.split(" "):
            yield token + " "


def _setup_isolated_env(tmp_dir: Path) -> None:
    os.environ["LLM_API_KEY"] = ""
    os.environ["LLM_BASE_URL"] = ""
    os.environ["OPENAI_API_KEY"] = ""

    from config import get_settings
    import database
    from rate_limiter import _limiter

    settings = get_settings()
    upload_dir = tmp_dir / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    db_file = tmp_dir / "bench_veridocs.db"

    settings.UPLOAD_DIR = upload_dir
    settings.DATABASE_PATH = str(db_file)
    settings.DATABASE_URL = f"sqlite:///{db_file}"
    settings.LLM_API_KEY = ""
    settings.LLM_BASE_URL = ""

    database.reset_engine()
    database.init_db()
    _limiter.reset()


def _ingest_pdf_end_to_end(client: Any, filename: str, pdf_bytes: bytes, session_id: str) -> Dict[str, Any]:
    tracemalloc.start()
    t0 = time.perf_counter()
    res = client.post(
        "/api/documents/upload",
        files={"file": (filename, pdf_bytes, "application/pdf")},
        data={"session_id": session_id},
    )
    if res.status_code != 200:
        tracemalloc.stop()
        raise RuntimeError(f"Upload failed ({res.status_code}): {res.text}")
    doc_id = res.json()["document_id"]

    deadline = time.perf_counter() + 120.0
    status_data: Dict[str, Any] = {}
    while time.perf_counter() < deadline:
        st = client.get(f"/api/documents/{doc_id}/status")
        status_data = st.json()
        if status_data.get("status") in ("ready", "failed"):
            break
        time.sleep(0.01)

    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    _, peak_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    if status_data.get("status") != "ready":
        raise RuntimeError(f"Ingestion failed or timed out: {status_data}")

    sess_res = client.get(f"/api/sessions/{session_id}")
    chunk_count = sess_res.json().get("chunk_count") if sess_res.status_code == 200 else None

    return {
        "document_id": doc_id,
        "status": status_data.get("status"),
        "page_count": status_data.get("page_count"),
        "chunk_count": chunk_count,
        "elapsed_ms": round(elapsed_ms, 2),
        "peak_traced_mib": round(peak_bytes / (1024 * 1024), 2),
    }


def _bench_streaming_query(client: Any, session_id: str) -> Dict[str, Any]:
    import routers.query as query_router

    orig_factory = query_router.get_llm_service
    query_router.get_llm_service = lambda **kwargs: _OfflineBenchmarkLLM()
    try:
        t0 = time.perf_counter()
        ttft_ms: float | None = None
        token_count = 0
        with client.stream(
            "POST",
            "/api/query/stream",
            json={
                "session_id": session_id,
                "question": "What are the payment terms and SLA availability?",
                "history": [],
            },
        ) as resp:
            if resp.status_code != 200:
                raise RuntimeError(f"Stream failed ({resp.status_code}): {resp.read().decode()}")
            current_event = None
            for raw_line in resp.iter_lines():
                line = raw_line.decode("utf-8") if isinstance(raw_line, bytes) else raw_line
                if line.startswith("event:"):
                    current_event = line.split(":", 1)[1].strip()
                elif line.startswith("data:") and current_event == "token":
                    if ttft_ms is None:
                        ttft_ms = (time.perf_counter() - t0) * 1000.0
                    token_count += 1
        total_ms = (time.perf_counter() - t0) * 1000.0
        return {
            "ttft_ms": round(ttft_ms or total_ms, 2),
            "total_ms": round(total_ms, 2),
            "token_events": token_count,
        }
    finally:
        query_router.get_llm_service = orig_factory


def _bench_verification(iterations: int = 50) -> Dict[str, Any]:
    from verification import check_citations

    chunks = [
        {
            "chunk_id": f"c_{i}",
            "text": (
                f"Section {i}.1 Payment Terms: Undisputed invoices are payable within thirty (30) days of receipt at ${10000 + i * 100} per month. "
                f"Provider commits to 99.95% monthly uptime availability with automatic SLA service credits for unplanned outages. "
                f"Confidentiality obligations survive expiration for five (5) years after termination notice."
            ),
            "page": (i % 10) + 1,
            "filename": "contract_10p.pdf",
            "section_path": f"{i} > {i}.1 Payment Terms",
        }
        for i in range(30)
    ]

    answer = " ".join(
        [
            "Invoices are payable within thirty (30) days of receipt at $10100 per month [1].",
            "Provider commits to 99.95% monthly uptime availability with automatic service credits [2].",
            "Confidentiality obligations survive expiration for five years after termination notice [3].",
            "Material breach permits termination following thirty days written notice by either party [4].",
            "All customer records remain encrypted at rest under AES-256 cryptographic controls [5].",
        ]
        * 3
    )

    # Warm once
    check_citations(answer, chunks)

    t0 = time.perf_counter()
    for _ in range(iterations):
        res = check_citations(answer, chunks)
    total_ms = (time.perf_counter() - t0) * 1000.0
    return {
        "iterations": iterations,
        "claims": res.get("total_claims", 0),
        "chunks": len(chunks),
        "mean_ms": round(total_ms / iterations, 3),
        "total_ms": round(total_ms, 2),
    }


def _bench_summary_and_report(client: Any, doc_id: str) -> Dict[str, Any]:
    t0 = time.perf_counter()
    sum_res = client.post(f"/api/documents/{doc_id}/summary")
    summary_ms = (time.perf_counter() - t0) * 1000.0
    if sum_res.status_code != 200:
        raise RuntimeError(f"Summary failed ({sum_res.status_code}): {sum_res.text}")

    t1 = time.perf_counter()
    rep_res = client.post(f"/api/documents/{doc_id}/report")
    report_ms = (time.perf_counter() - t1) * 1000.0
    if rep_res.status_code != 200:
        raise RuntimeError(f"Report failed ({rep_res.status_code}): {rep_res.text}")

    return {
        "summary_ms": round(summary_ms, 2),
        "report_ms": round(report_ms, 2),
    }


def _bench_sessions_and_analytics(client: Any) -> Dict[str, Any]:
    import database
    from models_db import Flag

    emb = np.ones((8, 384), dtype=np.float32)
    for idx in range(25):
        sid = f"bench-sess-{idx}"
        database.save_session(sid, [f"doc_{idx}.pdf"])
        doc = database.create_document(f"doc_{idx}.pdf", "application/pdf", sid, status="ready")
        database.save_chunks(
            sid,
            [
                {
                    "text": f"Sample clause {k} in document {idx}.",
                    "filename": f"doc_{idx}.pdf",
                    "page": 1,
                }
                for k in range(8)
            ],
            list(emb),
            document_id=doc["id"],
        )
        database.log_query(sid, f"Question {idx}?", "hybrid", 0.9, 2, 2)
        with database.get_db() as db:
            db.add(Flag(document_id=doc["id"], rule_id="bench_rule", severity="low", message="Sample flag"))

    t0 = time.perf_counter()
    for _ in range(20):
        database.list_sessions()
    list_sessions_ms = ((time.perf_counter() - t0) * 1000.0) / 20.0

    t1 = time.perf_counter()
    for _ in range(20):
        res = client.get("/api/analytics")
        if res.status_code != 200:
            raise RuntimeError(f"Analytics failed: {res.text}")
    analytics_ms = ((time.perf_counter() - t1) * 1000.0) / 20.0

    return {
        "list_sessions_mean_ms": round(list_sessions_ms, 3),
        "analytics_mean_ms": round(analytics_ms, 3),
    }


def run_benchmarks(enable_cprofile: bool = False) -> Dict[str, Any]:
    logging.disable(logging.INFO)
    try:
        with tempfile.TemporaryDirectory(prefix="veridocs_bench_") as tmp_str:
            tmp_dir = Path(tmp_str)
            _setup_isolated_env(tmp_dir)

            from fastapi.testclient import TestClient
            import main

            profiler = cProfile.Profile() if enable_cprofile else None
            if profiler:
                profiler.enable()

            pdf_10p = build_synthetic_pdf(10, "Master Services Agreement (10p)")
            pdf_50p = build_synthetic_pdf(50, "Enterprise Contract (50p)")

            with TestClient(main.app) as client:
                ingest_10 = _ingest_pdf_end_to_end(client, "contract_10p.pdf", pdf_10p, "bench-10p")
                ingest_50 = _ingest_pdf_end_to_end(client, "contract_50p.pdf", pdf_50p, "bench-50p")
                stream_10 = _bench_streaming_query(client, "bench-10p")
                verify_stats = _bench_verification(iterations=50)
                summary_report = _bench_summary_and_report(client, ingest_10["document_id"])
                db_queries = _bench_sessions_and_analytics(client)

            if profiler:
                profiler.disable()
                s = io.StringIO()
                ps = pstats.Stats(profiler, stream=s).sort_stats("cumulative")
                ps.print_stats(25)
                print("=== cProfile Top 25 (cumulative) ===")
                print(s.getvalue())

            ru = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            peak_rss_mib = round(ru / (1024 * 1024) if sys.platform == "darwin" else ru / 1024, 2)

            return {
                "ingestion_10p": ingest_10,
                "ingestion_50p": ingest_50,
                "query_stream_10p": stream_10,
                "verification": verify_stats,
                "summary_and_report_10p": summary_report,
                "db_hot_paths": db_queries,
                "process_peak_rss_mib": peak_rss_mib,
            }
    finally:
        logging.disable(logging.NOTSET)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Veridocs local performance benchmarks.")
    parser.add_argument("--json", action="store_true", help="Output raw JSON metrics")
    parser.add_argument("--cprofile", action="store_true", help="Print cProfile top 25 functions")
    args = parser.parse_args()

    results = run_benchmarks(enable_cprofile=args.cprofile)
    if args.json:
        print(json.dumps(results, indent=2))
    else:
        print("=== Veridocs Benchmark Results ===")
        print(
            f"Ingestion (10p PDF):    {results['ingestion_10p']['elapsed_ms']} ms | peak traced {results['ingestion_10p']['peak_traced_mib']} MiB | {results['ingestion_10p']['chunk_count']} chunks"
        )
        print(
            f"Ingestion (50p PDF):    {results['ingestion_50p']['elapsed_ms']} ms | peak traced {results['ingestion_50p']['peak_traced_mib']} MiB | {results['ingestion_50p']['chunk_count']} chunks"
        )
        print(
            f"Q&A Stream (10p PDF):   TTFT={results['query_stream_10p']['ttft_ms']} ms | total={results['query_stream_10p']['total_ms']} ms"
        )
        print(f"Verification (15x30):   mean={results['verification']['mean_ms']} ms")
        print(
            f"Summary + Report (10p): summary={results['summary_and_report_10p']['summary_ms']} ms | report={results['summary_and_report_10p']['report_ms']} ms"
        )
        print(
            f"DB Hot Paths:           list_sessions={results['db_hot_paths']['list_sessions_mean_ms']} ms | analytics={results['db_hot_paths']['analytics_mean_ms']} ms"
        )
        print(f"Process Peak RSS:       {results['process_peak_rss_mib']} MiB")


if __name__ == "__main__":
    main()
