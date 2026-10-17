# 📑 Veridocs Frontend

Enterprise Next.js 15 client for the **Veridocs** Document Intelligence Platform.

## 🚀 Key Features

- **Instant 0ms PDF Canvas**: Multi-page PDF.js viewer with local browser Blob URL rendering and smooth citation coordinate jumps.
- **Real-Time SSE Streaming**: Low-latency token streaming from the FastAPI backend with markdown support.
- **3-State Claim Verification Drawer**: Interactive visual audit drawer for claim grounding confidence scores.
- **Document Insights Panel**: Instant executive summary, entity extraction chips (Monetary, Dates, Orgs, Persons), and suggested questions.
- **Multi-File Session Workspace**: Resizable split-pane layout with optimistic loading and instant workspace transitions.

## 🛠️ Tech Stack

- **Framework**: Next.js 15 (App Router, Turbopack)
- **Language**: TypeScript
- **Styling**: Tailwind CSS, Lucide React
- **State Management**: Zustand (with local Blob URL caching)
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

By default, the frontend connects directly to the production Render cloud backend:
`https://veridocs-backend-xlzk.onrender.com`

You can customize this in `lib/api.ts` or set `NEXT_PUBLIC_API_URL` in `.env.local` if running a local backend instance.
