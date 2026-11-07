# 📑 Veridocs Frontend

Enterprise Next.js client for the **Veridocs** Document Intelligence Platform.

## 🚀 Key Features

- **Instant 0ms PDF Canvas**: Multi-page PDF.js viewer with local browser Blob URL rendering and smooth citation coordinate jumps.
- **Real-Time SSE Streaming**: Low-latency token streaming from the FastAPI backend with markdown support.
- **3-State Claim Verification Drawer**: Interactive visual audit drawer for claim grounding confidence scores.
- **Document Insights Panel**: Instant executive summary, entity extraction chips (Monetary, Dates, Orgs, Persons), and suggested questions.
- **Multi-File Session Workspace**: Resizable split-pane layout with optimistic loading and instant workspace transitions.

## 🛠️ Tech Stack

- **Framework**: Next.js 16 (App Router, Turbopack)
- **Language**: TypeScript
- **Styling**: Tailwind CSS, Lucide React
- **State Management**: Zustand
- **PDF Rendering**: PDF.js (bundled worker)

## ⚡ Quick Start

```bash
# Install dependencies
npm install

# Run local development server
npm run dev
```

The application will be accessible at [http://localhost:3000](http://localhost:3000).

## 🌐 Backend Configuration

By default, the frontend connects to the backend API at `http://localhost:8000`.

You can configure a custom backend endpoint by setting `NEXT_PUBLIC_API_URL` in `.env.local` or environment:
```bash
NEXT_PUBLIC_API_URL=http://localhost:8000
```
