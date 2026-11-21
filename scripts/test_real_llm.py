#!/usr/bin/env python3
"""
Test streaming QA with a real live OpenAI-compatible LLM against the 6-page Master Agreement.
"""

import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = ROOT_DIR / "backend"
VENV_SITE_PACKAGES = ROOT_DIR / ".venv/lib/python3.11/site-packages"

sys.path.insert(0, str(VENV_SITE_PACKAGES))
sys.path.insert(0, str(BACKEND_DIR))

# Set real OpenAI-compatible endpoint from environment or fallback
from dotenv import load_dotenv
load_dotenv()
load_dotenv(BACKEND_DIR / ".env")

if not os.getenv("LLM_BASE_URL"):
    os.environ["LLM_BASE_URL"] = os.getenv("LLM_BASE_URL", "https://api.groq.com/openai/v1")
if not os.getenv("LLM_MODEL"):
    os.environ["LLM_MODEL"] = os.getenv("LLM_MODEL", "openai/gpt-oss-120b")

from fastapi.testclient import TestClient
import main
import database
from vector_store import VectorStore
from llm_service import get_llm_service
from verification import check_citations, extract_citations_from_answer

def main_test():
    print("=" * 65)
    print("  🤖 REAL LIVE LLM STREAMING & CITATION VERIFICATION")
    print("=" * 65)

    with TestClient(main.app) as client:
        # 1. Verify LLM status is configured
        status = client.get("/api/llm/status").json()
        print(f"\n[1] LLM Status: Configured={status['configured']}, BaseURL={status['base_url']}, Model={status['model']}")
        assert status["configured"] is True

        # 2. Ask question 1: Answer is in document (Section 5, Page 6)
        q1 = "What is the limitation of liability cap and what governing law applies?"
        print(f"\n[2] Asking Question 1 (Supported Claim): '{q1}'")
        res1 = client.post("/api/query/stream", json={"session_id": "demo-session", "question": q1})
        assert res1.status_code == 200

        full_answer = ""
        citations = []
        checks = []

        lines = res1.text.split("\n")
        cur_event = None
        for line in lines:
            if line.startswith("event: "):
                cur_event = line.replace("event: ", "").strip()
            elif line.startswith("data: ") and cur_event:
                data_str = line.replace("data: ", "").strip()
                if data_str:
                    import json
                    d = json.loads(data_str)
                    if cur_event == "token":
                        full_answer += d.get("text", "")
                    elif cur_event == "citation":
                        citations.append(d)
                    elif cur_event == "citation_check":
                        checks.append(d)
                cur_event = None

        print("\n--- REAL LLM ANSWER ---")
        print(full_answer.strip())
        print("-----------------------")

        print(f"\n--- CITATIONS ({len(citations)} found) ---")
        for c in citations:
            print(f"  * Citation #{c['citation_id']}: Doc '{c['source_file']}', Page {c['page']}")
            print(f"    Text: {c['highlighted_text'][:80]}...")

        if checks:
            print(f"\n--- CITATION CHECK RESULT ---")
            chk = checks[0]
            print(f"  Citation Support Score: {chk['citation_score']:.1%}")
            print(f"  Supported Claims: {chk['supported_claims']} / {chk['total_claims']}")
            for clm in chk["claims"]:
                status_icon = "✅" if clm["is_supported"] else "⚠️"
                print(f"  {status_icon} Claim: \"{clm['claim'][:65]}...\" (Overlap: {clm['overlap_score']:.2f}, Page: {clm['matched_page']})")

        # 3. Ask question 2: Answer NOT in document (Unrelated / Hallucination probe)
        q2 = "What are the rules regarding pets or dogs on company premises?"
        print(f"\n[3] Asking Question 2 (Not in Document): '{q2}'")
        res2 = client.post("/api/query/stream", json={"session_id": "demo-session", "question": q2})
        assert res2.status_code == 200

        full_answer2 = ""
        citations2 = []
        lines2 = res2.text.split("\n")
        cur_event = None
        for line in lines2:
            if line.startswith("event: "):
                cur_event = line.replace("event: ", "").strip()
            elif line.startswith("data: ") and cur_event:
                data_str = line.replace("data: ", "").strip()
                if data_str:
                    import json
                    d = json.loads(data_str)
                    if cur_event == "token":
                        full_answer2 += d.get("text", "")
                    elif cur_event == "citation":
                        citations2.append(d)
                cur_event = None

        print("\n--- REAL LLM ANSWER (UNFOUND TOPIC) ---")
        print(full_answer2.strip())
        print("---------------------------------------")

        print("\n" + "=" * 65)
        print("  ✅ REAL LLM VERIFICATION COMPLETE: ALL CHECKS PASSED")
        print("=" * 65)

if __name__ == "__main__":
    main_test()

