# Veridocs — Interactive Portfolio Demo

This folder contains the standalone, zero-config interactive showcase for **Veridocs**, pre-configured and live on [Vercel](https://vercel.com) at:
**`https://veridocs-demo.vercel.app/`** *(also mirrored at `https://veridocs-app.vercel.app/`)*

---

## 🌟 What This Demo Showcases

1. **Physical Canvas Visual Grounding**:
   - Clicking citations automatically centers the document page and animates a glowing highlight box over the exact cited words.
2. **Forensic Contradiction Matrix**:
   - Cross-document diffing comparing an Original 2023 Master Services Agreement against a 2024 Amendment, flagging changes in retainer fees ($15,000/mo vs $22,500/mo), liability caps ($1M vs $2.5M), and termination windows.
3. **Sentence-by-Sentence 3-State Claim Audit**:
   - Classifies assertions into **Verified Claim** (exact token and numeric match), **Inferred Reasoning**, or **Potential Hallucination** (highlighting unsupported relations or altered numbers).
4. **Real-time RAG Triad Observability**:
   - Live telemetry measuring Context Relevance, Groundedness, Answer Relevance, and Numeric Token Fidelity.
5. **Full Architecture & Security Walkthrough**:
   - Explains the single-instance backend design, HMAC token isolation, scoped admin maintenance key, and automated 60-minute background retention loop.

---

## 🚀 How to Deploy to Vercel in 2 Minutes

### Method A: Deploy via Vercel Dashboard (Recommended)

1. Go to [vercel.com/new](https://vercel.com/new) and import your `Spidey173/Veridocs` GitHub repository.
2. In the **Configure Project** screen:
   - **Project Name:** `veridocs` (this will automatically assign `https://veridocs.vercel.app/`)
   - **Framework Preset:** `Next.js`
   - **Root Directory:** Click **Edit** and select `demo`.
3. Click **Deploy**. Vercel will install dependencies and deploy the live demo in ~60 seconds.

---

### Method B: Deploy via Vercel CLI

```bash
cd demo
npm install
npx vercel --prod
```

When prompted:
- Set project name: `veridocs`
- The CLI will publish to `https://veridocs.vercel.app/`.

---

## 💻 Local Development

```bash
cd demo
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) in your browser.
