import os
import sys
import time
import requests
import json
from pathlib import Path

# Add backend directory to path
backend_dir = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(backend_dir))

from pdf_processor import extract_text_from_pdf, chunk_text
from vector_store import VectorStore
from config import get_model_registry
import database
import numpy as np

SESSION_ID = "resume-test-session"
RESUME_PATH = backend_dir / "uploads" / "24150a67-5338-4222-848d-066756129b40_Pruthvi_Resume (5).pdf"

print(f"Indexing resume: {RESUME_PATH.name} into session '{SESSION_ID}'...")
database.delete_session(SESSION_ID)
database.save_session(SESSION_ID, [RESUME_PATH.name])

pages = extract_text_from_pdf(str(RESUME_PATH))
chunks = chunk_text(pages, document_name=RESUME_PATH.name)
print(f"Created {len(chunks)} chunks.")

reg = get_model_registry()
texts = [c["text"] for c in chunks]
embeddings = list(reg.embedding_model.embed(texts))
norm_embs = [np.asarray(e, dtype=np.float32) / np.linalg.norm(e) for e in embeddings]
VectorStore.save_chunks(SESSION_ID, chunks, norm_embs)
print("Chunks saved to database.")

# Test questions
TEST_QUESTIONS = [
    "what projects did he build",
    "what is his CGPA",
    "does he know Kubernetes",
    "ok thanks",
]

BASE_URL = "http://127.0.0.1:8000"

print("\n" + "="*70)
print("TESTING LIVE STREAM QA ENDPOINTS")
print("="*70)

history = []

for q in TEST_QUESTIONS:
    print(f"\n>>> QUESTION: {q}")
    payload = {
        "session_id": SESSION_ID,
        "question": q,
        "history": list(history)
    }

    res = requests.post(
        f"{BASE_URL}/api/query/stream",
        json=payload,
        stream=True,
        headers={"Content-Type": "application/json"}
    )

    full_text = ""
    citations = []
    citation_check = None

    current_event = ""
    for line in res.iter_lines(decode_unicode=True):
        if not line:
            continue
        if line.startswith("event: "):
            current_event = line[7:].strip()
        elif line.startswith("data: ") and current_event:
            try:
                data = json.loads(line[6:])
                if current_event == "token":
                    token = data.get("text", "")
                    full_text += token
                elif current_event == "citation":
                    citations.append(data)
                elif current_event == "citation_check":
                    citation_check = data
            except:
                pass

    print("\n--- ANSWER ---")
    print(full_text.strip())

    print("\n--- CITATIONS ---")
    if citations:
        for c in citations:
            print(f"  [{c.get('citation_id')}] Page {c.get('page')}: {c.get('source_file')} | Excerpt: {c.get('highlighted_text', '')[:100]}...")
    else:
        print("  (None)")

    print("\n--- CITATION CHECK ---")
    if citation_check:
        print(f"  Score: {int(citation_check.get('citation_score', 0)*100)}% grounded ({citation_check.get('supported_claims')}/{citation_check.get('total_claims')} claims verified)")
        for cl in citation_check.get("claims", []):
            status = "SUPPORTED" if cl.get("is_supported") else "UNSUPPORTED"
            print(f"    [{status} - {int(cl.get('overlap_score', 0)*100)}%] {cl.get('claim')}")
    else:
        print("  (No citation check needed/emitted)")

    # Update conversation history
    history.append({"role": "user", "content": q})
    history.append({"role": "assistant", "content": full_text.strip()})

