# Veridocs

An AI document assistant that lets you chat with your documents, view citations, and compare files to highlight differences.

🌐 **[Live Demo](https://veridocs17.vercel.app/)** | 📦 **[GitHub Repository](https://github.com/Spidey173/Veridocs)**

---

## Features

- **Document Q&A**: Upload PDF, DOCX, or TXT files and ask questions.
- **Citations & Highlights**: See exact page citations and visual highlights in the document viewer.
- **Document Comparison**: Compare two documents side-by-side to detect differences.
- **Hybrid Search**: Combines full-text search and PostgreSQL pgvector HNSW cosine embeddings for accurate answers.

---

## Quickstart

Run both backend and frontend with one command:

```bash
./run.sh
```

Then open `http://localhost:3000` in your browser.

---

## Running Tests

```bash
pytest backend/tests
```

---

## License

MIT
