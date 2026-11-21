#!/usr/bin/env python3
"""
Real end-to-end HTTP integration test for Veridocs.
Starts uvicorn on a real port, connects over HTTP, uploads a real 6-page PDF,
queries it, and validates SSE stream tokens and real page citations.
"""

import os
import sys
import time
import subprocess
import json
from pathlib import Path
import httpx

ROOT_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = ROOT_DIR / "backend"
VENV_SITE_PACKAGES = ROOT_DIR / ".venv/lib/python3.11/site-packages"

PORT = 8008
BASE_URL = f"http://127.0.0.1:{PORT}"

def main():
    print("=" * 60)
    print("  🧪 VERIDOCS REAL HTTP END-TO-END VERIFICATION")
    print("=" * 60)

    # 1. Start uvicorn on real port
    env = {
        **os.environ,
        "PYTHONPATH": f"{VENV_SITE_PACKAGES}:{BACKEND_DIR}",
    }
    python_bin = sys.executable

    print(f"\n[1/6] Starting uvicorn backend on port {PORT}...")
    server = subprocess.Popen(
        [python_bin, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", str(PORT)],
        cwd=str(BACKEND_DIR),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    try:
        # 2. Wait for backend to be healthy
        print("[2/6] Waiting for backend to become ready...")
        ready = False
        start_time = time.time()
        with httpx.Client(base_url=BASE_URL, timeout=10.0) as client:
            for attempt in range(20):
                try:
                    res = client.get("/api/health")
                    if res.status_code == 200:
                        data = res.json()
                        if data.get("status") == "healthy":
                            elapsed = time.time() - start_time
                            print(f"       Backend healthy in {elapsed:.2f}s! Data: {data}")
                            ready = True
                            break
                except Exception:
                    pass
                time.sleep(0.5)

            if not ready:
                print("ERROR: Backend did not become healthy within 10 seconds.")
                return 1

            # 3. Check LLM status
            print("\n[3/6] Checking LLM status endpoint...")
            llm_res = client.get("/api/llm/status")
            print(f"       Status: {llm_res.status_code}, Body: {llm_res.json()}")
            assert llm_res.status_code == 200

            # 4. Upload real 6-page PDF
            print("\n[4/6] Uploading real 6-page Master Cloud Agreement...")
            sample_pdf = BACKEND_DIR / "sample_agreement.pdf"
            assert sample_pdf.exists(), "sample_agreement.pdf missing!"
            pdf_bytes = sample_pdf.read_bytes()

            upload_res = client.post(
                "/api/upload",
                files=[("files", ("test_agreement.pdf", pdf_bytes, "application/pdf"))]
            )
            print(f"       Upload HTTP status: {upload_res.status_code}")
            assert upload_res.status_code == 200
            upload_data = upload_res.json()
            session_id = upload_data["session_id"]
            chunk_count = upload_data["chunk_count"]
            print(f"       Session ID: {session_id}")
            print(f"       Indexed Chunks: {chunk_count} across 6 pages")
            assert chunk_count >= 5, f"Expected at least 5 chunks, got {chunk_count}"

            # 5. Verify PDF serving endpoint
            print("\n[5/6] Verifying raw PDF binary serving endpoint...")
            pdf_res = client.get(f"/api/documents/{session_id}/pdf?document_name=test_agreement.pdf")
            print(f"       PDF serving HTTP status: {pdf_res.status_code}, Length: {len(pdf_res.content)} bytes")
            assert pdf_res.status_code == 200
            assert len(pdf_res.content) == len(pdf_bytes)

            # 6. Test real HTTP SSE streaming query
            print("\n[6/6] Executing real HTTP SSE streaming query: 'What is the liability cap?'...")
            events_received = []
            tokens = []
            citations = []
            citation_checks = []

            with client.stream(
                "POST",
                "/api/query/stream",
                json={"session_id": session_id, "question": "What is the liability cap?"}
            ) as stream_res:
                print(f"       Stream HTTP status: {stream_res.status_code}")
                assert stream_res.status_code == 200
                current_event = None

                for line in stream_res.iter_lines():
                    if line.startswith("event: "):
                        current_event = line.replace("event: ", "").strip()
                    elif line.startswith("data: ") and current_event:
                        payload_str = line.replace("data: ", "").strip()
                        if payload_str:
                            payload = json.loads(payload_str)
                            events_received.append(current_event)
                            if current_event == "token":
                                tokens.append(payload.get("text", ""))
                            elif current_event == "citation":
                                citations.append(payload)
                            elif current_event == "citation_check":
                                citation_checks.append(payload)
                        current_event = None

            print(f"       SSE Events Received: {set(events_received)}")
            print(f"       Total Tokens Received: {len(tokens)}")
            print(f"       Citations Found: {len(citations)}")
            for c in citations:
                print(f"         * Citation #{c['citation_id']}: Doc '{c['source_file']}', Page {c['page']}")
                print(f"           Excerpt: {c['highlighted_text'][:90]}...")
                # Verify that liability was retrieved from Page 6!
                assert c["page"] == 6, f"Expected citation on page 6 (Liability section), got page {c['page']}"

            assert len(citations) > 0, "No citations emitted!"
            assert "done" in events_received, "Missing 'done' event!"
            print("\n" + "=" * 60)
            print("  ✅ REAL HTTP STACK END-TO-END VERIFICATION: 100% PASSED!")
            print("=" * 60)
            return 0

    finally:
        print("\nStopping uvicorn server...")
        server.terminate()
        try:
            server.wait(timeout=3)
        except subprocess.TimeoutExpired:
            server.kill()

if __name__ == "__main__":
    sys.exit(main())

