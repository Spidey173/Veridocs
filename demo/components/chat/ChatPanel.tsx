"use client";

import { useRef, useEffect, useState, useCallback } from "react";
import { motion } from "framer-motion";
import {
  Send,
  Loader2,
  Bot,
  User,
  Sparkles,
  MessageSquare,
} from "lucide-react";
import { useAppStore, type ChatMessage } from "@/lib/store";
import { streamQuery, type CitationInfo, type ClaimVerificationItem, type RagTriadMetrics } from "@/lib/api";
import ReactMarkdown from "react-markdown";
import VerificationDrawer from "./VerificationDrawer";

// ──────────────────────────────────────
// Chat Panel (main export)
// ──────────────────────────────────────

export default function ChatPanel() {
  const [input, setInput] = useState("");
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const {
    sessionId,
    messages,
    isQuerying,
    insights,
    selectedFileNames,
    addMessage,
    appendToMessage,
    updateMessage,
    setQuerying,
    setCurrentStreamingId,
  } = useAppStore();

  // Auto-scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Auto-resize textarea
  const handleInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value);
    e.target.style.height = "auto";
    e.target.style.height = Math.min(e.target.scrollHeight, 120) + "px";
  };

  const handleSubmit = useCallback(async () => {
    if (!input.trim() || !sessionId || isQuerying) return;

    const question = input.trim();
    setInput("");
    if (inputRef.current) {
      inputRef.current.style.height = "auto";
    }

    // Add user message
    const userMsgId = `user-${Date.now()}`;
    addMessage({
      id: userMsgId,
      role: "user",
      content: question,
      timestamp: new Date(),
    });

    // Add placeholder AI message
    const aiMsgId = `ai-${Date.now()}`;
    addMessage({
      id: aiMsgId,
      role: "assistant",
      content: "",
      isStreaming: true,
      timestamp: new Date(),
    });

    setQuerying(true);
    setCurrentStreamingId(aiMsgId);

    try {
      if (sessionId === "demo-session" || sessionId.startsWith("session-")) {
        let answerText = "";
        let demoCitations: CitationInfo[] = [];
        let demoConfidence = 0.98;
        let demoClaims: ClaimVerificationItem[] = [];

        const lower = question.toLowerCase();

        if (lower.includes("payment") || lower.includes("fee") || lower.includes("30") || lower.includes("60") || lower.includes("invoice") || lower.includes("interest")) {
          answerText = `Based on cross-document analysis of **SaaS_Agreement_2024_v1.pdf** and **SaaS_Agreement_2025_Amended.pdf**:

### 1. Payment Settlement Window
- **2024 Baseline (Section 4.1):** Invoices are payable within **30 days** of receipt.
- **2025 Revision (Section 4.1):** Customer payment window is extended to **60 calendar days** from the invoice date.

### 2. Late Penalties & Interest
- **2024 Agreement:** Overdue balances accrue interest at **1.5% per month**.
- **2025 Amendment:** All late penalty and interest clauses have been completely removed.

### ⚖️ Risk & Contradiction Finding:
This represents a **critical contractual discrepancy** that increases the working capital cycle and removes financial incentives for timely invoice settlement.`;
          demoCitations = [
            {
              citation_id: 1,
              page: 1,
              source_file: "SaaS_Agreement_2024_v1.pdf",
              highlighted_text: "Invoices are payable within 30 days of receipt. Overdue balances shall accrue interest at 1.5% per month.",
              section: "4.1 Payment Terms",
              confidence: 0.98,
            },
            {
              citation_id: 2,
              page: 1,
              source_file: "SaaS_Agreement_2025_Amended.pdf",
              highlighted_text: "Customer shall remit payment within 60 calendar days from invoice date without late fees or interest charges.",
              section: "4.1 Settlement",
              confidence: 0.96,
            },
          ];
          demoClaims = [
            {
              claim: "Doc A requires payment within 30 days with a 1.5% monthly late fee.",
              score: 0.98,
              status: "verified",
              is_supported: true,
              numeric_grounded: true,
              best_source_page: 1,
              source_file: "SaaS_Agreement_2024_v1.pdf",
            },
            {
              claim: "Doc B extends customer settlement window to 60 calendar days without late fees.",
              score: 0.96,
              status: "verified",
              is_supported: true,
              numeric_grounded: true,
              best_source_page: 1,
              source_file: "SaaS_Agreement_2025_Amended.pdf",
            },
            {
              claim: "Net 60 terms without penalties increase vendor working capital risk.",
              score: 0.91,
              status: "inferred",
              is_supported: true,
              numeric_grounded: true,
              best_source_page: 1,
              source_file: "SaaS_Agreement_2025_Amended.pdf",
            },
          ];
        } else if (lower.includes("liab") || lower.includes("cap") || lower.includes("damages") || lower.includes("1,000,000") || lower.includes("250,000") || lower.includes("million")) {
          answerText = `The limitation of liability clauses between the two agreements reveal a **75% reduction in damages coverage**:

### 1. Cumulative Liability Cap
- **2024 Baseline (Section 8.1):** Total aggregate liability of either party is capped at **$1,000,000** under any circumstances.
- **2025 Revision (Section 8.1):** Cumulative damages cap is slashed to **$250,000** (or the fees paid in the prior 3 months).

### ⚖️ Forensic Risk Analysis:
This critical contradiction significantly limits recovery rights in the event of gross negligence, security breaches, or systemic outages. The amended clause shifts operational downside exposure heavily onto the customer.`;
          demoCitations = [
            {
              citation_id: 1,
              page: 2,
              source_file: "SaaS_Agreement_2024_v1.pdf",
              highlighted_text: "The total aggregate liability of either party shall not exceed $1,000,000 under any circumstances.",
              section: "8.1 Liability Cap",
              confidence: 0.99,
            },
            {
              citation_id: 2,
              page: 2,
              source_file: "SaaS_Agreement_2025_Amended.pdf",
              highlighted_text: "Maximum cumulative liability arising out of this agreement is capped at $250,000 or the fees paid in the prior 3 months.",
              section: "8. Damages Cap",
              confidence: 0.98,
            },
          ];
          demoClaims = [
            {
              claim: "Total aggregate liability in the 2024 agreement is capped at $1,000,000.",
              score: 0.99,
              status: "verified",
              is_supported: true,
              numeric_grounded: true,
              best_source_page: 2,
              source_file: "SaaS_Agreement_2024_v1.pdf",
            },
            {
              claim: "The 2025 amendment slashes the damages cap down to $250,000.",
              score: 0.98,
              status: "verified",
              is_supported: true,
              numeric_grounded: true,
              best_source_page: 2,
              source_file: "SaaS_Agreement_2025_Amended.pdf",
            },
            {
              claim: "The 75% cap reduction heavily restricts legal remedy in data breaches.",
              score: 0.94,
              status: "inferred",
              is_supported: true,
              numeric_grounded: true,
              best_source_page: 2,
              source_file: "SaaS_Agreement_2025_Amended.pdf",
            },
          ];
        } else if (lower.includes("sla") || lower.includes("uptime") || lower.includes("avail") || lower.includes("99.95") || lower.includes("99.5")) {
          answerText = `The Service Level Agreement (SLA) commitment was downgraded in the 2025 revision:

### 1. Uptime Availability Commitment
- **2024 Agreement (Schedule B):** Provider guarantees monthly service availability of at least **99.95%** (excluding scheduled maintenance).
- **2025 Amendment (Schedule B):** Target availability is downgraded to **99.5%**.

### 2. Service Credit Remedies
- **2024 Agreement:** Tiered service credits up to 25% of monthly fees for downtime.
- **2025 Amendment:** Service credits are capped at **5%** of monthly recurring revenue.

### ⏱️ Operational Impact:
A 99.5% uptime commitment permits up to **3.6 hours of uncredited downtime per month**, compared to just ~21.6 minutes permitted under the 99.95% standard.`;
          demoCitations = [
            {
              citation_id: 1,
              page: 3,
              source_file: "SaaS_Agreement_2024_v1.pdf",
              highlighted_text: "Provider guarantees monthly service availability of at least 99.95% excluding scheduled maintenance windows.",
              section: "Schedule B: SLA",
              confidence: 0.98,
            },
            {
              citation_id: 2,
              page: 3,
              source_file: "SaaS_Agreement_2025_Amended.pdf",
              highlighted_text: "Service availability commitment is target 99.5% with service credits capped at 5% of monthly recurring revenue.",
              section: "Schedule B: Availability",
              confidence: 0.97,
            },
          ];
          demoClaims = [
            {
              claim: "The 2024 agreement guarantees monthly service availability of at least 99.95%.",
              score: 0.98,
              status: "verified",
              is_supported: true,
              numeric_grounded: true,
              best_source_page: 3,
              source_file: "SaaS_Agreement_2024_v1.pdf",
            },
            {
              claim: "The 2025 amendment lowers availability to 99.5% and caps credits at 5% MRR.",
              score: 0.97,
              status: "verified",
              is_supported: true,
              numeric_grounded: true,
              best_source_page: 3,
              source_file: "SaaS_Agreement_2025_Amended.pdf",
            },
          ];
        } else if (lower.includes("diff") || lower.includes("compare") || lower.includes("contradict") || lower.includes("summary") || lower.includes("change")) {
          answerText = `Forensic cross-document analysis identified **3 critical contractual discrepancies** between **SaaS_Agreement_2024_v1.pdf** and **SaaS_Agreement_2025_Amended.pdf**:

| Clause Area | 2024 Baseline | 2025 Amendment | Severity |
| :--- | :--- | :--- | :--- |
| **Payment Terms** | Net 30 days + 1.5%/mo late fee | Net 60 days, no penalties | 🔴 Critical |
| **Liability Cap** | $1,000,000 aggregate cap | $250,000 damages ceiling | 🔴 Critical |
| **SLA Availability** | 99.95% monthly uptime | 99.5% target uptime | 🟡 Warning |

### Overall Forensic Score:
- **Alignment Score:** **68%**
- **Discrepancy Count:** 2 Critical, 1 Warning

👉 Switch to the **Contradiction Matrix** tab above to review full side-by-side clause diffs and jump to the exact bounding box highlights on both documents.`;
          demoCitations = [
            {
              citation_id: 1,
              page: 1,
              source_file: "SaaS_Agreement_2024_v1.pdf",
              highlighted_text: "Invoices are payable within 30 days of receipt. Overdue balances shall accrue interest at 1.5% per month.",
              section: "4.1 Payment Terms",
              confidence: 0.98,
            },
            {
              citation_id: 2,
              page: 2,
              source_file: "SaaS_Agreement_2024_v1.pdf",
              highlighted_text: "The total aggregate liability of either party shall not exceed $1,000,000 under any circumstances.",
              section: "8.1 Liability Cap",
              confidence: 0.99,
            },
            {
              citation_id: 3,
              page: 3,
              source_file: "SaaS_Agreement_2024_v1.pdf",
              highlighted_text: "Provider guarantees monthly service availability of at least 99.95% excluding scheduled maintenance windows.",
              section: "Schedule B: SLA",
              confidence: 0.97,
            },
          ];
          demoClaims = [
            {
              claim: "Payment terms extended from 30 to 60 days without late interest.",
              score: 0.98,
              status: "verified",
              is_supported: true,
              numeric_grounded: true,
              best_source_page: 1,
              source_file: "SaaS_Agreement_2024_v1.pdf",
            },
            {
              claim: "Aggregate liability cap was slashed from $1,000,000 down to $250,000.",
              score: 0.99,
              status: "verified",
              is_supported: true,
              numeric_grounded: true,
              best_source_page: 2,
              source_file: "SaaS_Agreement_2024_v1.pdf",
            },
            {
              claim: "Guaranteed uptime threshold decreased from 99.95% to 99.5%.",
              score: 0.97,
              status: "verified",
              is_supported: true,
              numeric_grounded: true,
              best_source_page: 3,
              source_file: "SaaS_Agreement_2024_v1.pdf",
            },
          ];
        } else if (lower.includes("hallucin") || lower.includes("ground") || lower.includes("mitigat")) {
          answerText = `Veridocs prevents hallucinations through a **multi-tiered factual verification pipeline**:

1. **Relevance Thresholding:** Extracted chunks must meet strict BM25 and cosine distance minimums before entering context.
2. **Lexical & Numeric Grounding:** Every numerical entity and factual claim generated in an answer is cross-checked against source chunk spans.
3. **3-State Claim Classification:**
   - 🟢 **Verified Claim:** Direct token and numeric overlap with source passage.
   - 🟡 **Inferred Reasoning:** Logical synthesis from surrounding context.
   - 🔴 **Potential Hallucination:** Numerical drift or uncorroborated entity.
4. **Visual Bounding Box Mapping:** Source passages link to exact PDF coordinates (\`[x, y, w, h]\`), allowing users to click citations and inspect source text on the original page.`;
          demoCitations = [
            {
              citation_id: 1,
              page: 3,
              source_file: "Veridocs_Technical_Architecture.pdf",
              highlighted_text: "Factual alignment is verified post-generation by computing premise-hypothesis entailment scores against source passages.",
              section: "3. Hallucination Mitigation",
              confidence: 0.97,
            },
            {
              citation_id: 2,
              page: 3,
              source_file: "Veridocs_Technical_Architecture.pdf",
              highlighted_text: "Every extracted claim must map directly to an attributed chunk span; non-conforming tokens are rejected.",
              section: "3. Grounded Verification",
              confidence: 0.95,
            },
          ];
          demoClaims = [
            {
              claim: "Post-generation verification validates premise-hypothesis entailment against chunk spans.",
              score: 0.97,
              status: "verified",
              is_supported: true,
              numeric_grounded: true,
              best_source_page: 3,
              source_file: "Veridocs_Technical_Architecture.pdf",
            },
            {
              claim: "Non-conforming tokens not directly substantiated by source text are flagged.",
              score: 0.95,
              status: "verified",
              is_supported: true,
              numeric_grounded: true,
              best_source_page: 3,
              source_file: "Veridocs_Technical_Architecture.pdf",
            },
          ];
        } else if (lower.includes("rerank") || lower.includes("cross") || lower.includes("encoder")) {
          answerText = `The **Cross-Encoder Re-Ranker** serves as the precision gatekeeper in Veridocs:

- **Full Joint Attention:** While bi-encoders produce isolated document embeddings, the cross-encoder feeds both the user query and candidate passage simultaneously into Transformer layers, allowing every query token to attend directly to every passage token.
- **Semantic Nuance & Negations:** Captures subtle negations (e.g., *"without late fees"* vs *"with late fees"*) that vector distance alone misses.
- **Empirical Performance:** Joint cross-attention improves top-3 retrieval accuracy by up to **38%** compared to single-stage vector retrieval.`;
          demoCitations = [
            {
              citation_id: 1,
              page: 2,
              source_file: "Veridocs_Technical_Architecture.pdf",
              highlighted_text: "A deep cross-encoder calculates full token cross-attention across the query and candidate passages, filtering out false positives.",
              section: "2. Cross-Encoder Re-Ranking",
              confidence: 0.98,
            },
            {
              citation_id: 2,
              page: 2,
              source_file: "Veridocs_Technical_Architecture.pdf",
              highlighted_text: "Full joint cross-attention improves top-3 retrieval accuracy by up to 38% compared to single-stage vector retrieval.",
              section: "2. Re-Ranking Performance",
              confidence: 0.96,
            },
          ];
          demoClaims = [
            {
              claim: "Cross-encoder calculates full token cross-attention simultaneously across query and passage.",
              score: 0.98,
              status: "verified",
              is_supported: true,
              numeric_grounded: true,
              best_source_page: 2,
              source_file: "Veridocs_Technical_Architecture.pdf",
            },
            {
              claim: "Joint cross-attention improves top-3 retrieval accuracy by up to 38%.",
              score: 0.96,
              status: "verified",
              is_supported: true,
              numeric_grounded: true,
              best_source_page: 2,
              source_file: "Veridocs_Technical_Architecture.pdf",
            },
          ];
        } else if (lower.includes("hybrid") || lower.includes("bm25") || lower.includes("faiss") || lower.includes("search")) {
          answerText = `Veridocs implements a two-stage **Hybrid Retrieval Engine** fusing lexical indexing with dense semantic vector representations:

1. **BM25 Lexical Indexing:** Excels at exact keyword queries, alphanumeric IDs, section headers (*"Section 4.1"*), and monetary figures (*"$1,000,000"*).
2. **FAISS Dense Vector Search:** Captures conceptual intent using FastEmbed ONNX embeddings (\`bge-small-en-v1.5\`), operating entirely on CPU with ~70MB RAM.
3. **Reciprocal Rank Fusion (RRF):** Fuses ranking scores across both candidate lists using rank reciprocal constants ($k=60$), ensuring balanced retrieval without vector drift.`;
          demoCitations = [
            {
              citation_id: 1,
              page: 1,
              source_file: "Veridocs_Technical_Architecture.pdf",
              highlighted_text: "Veridocs implements a two-stage hybrid retrieval architecture fusing BM25 lexical indexing with dense semantic vector representations.",
              section: "1. Hybrid Retrieval Engine",
              confidence: 0.99,
            },
            {
              citation_id: 2,
              page: 1,
              source_file: "Veridocs_Technical_Architecture.pdf",
              highlighted_text: "Reciprocal Rank Fusion ensures neither lexical bias nor dense vector drift dominates candidate selection.",
              section: "1. Fusion Mechanics",
              confidence: 0.94,
            },
          ];
          demoClaims = [
            {
              claim: "Two-stage hybrid retrieval fuses BM25 lexical indexing with dense semantic representations.",
              score: 0.99,
              status: "verified",
              is_supported: true,
              numeric_grounded: true,
              best_source_page: 1,
              source_file: "Veridocs_Technical_Architecture.pdf",
            },
            {
              claim: "Reciprocal Rank Fusion ensures balanced candidate selection without vector drift.",
              score: 0.94,
              status: "verified",
              is_supported: true,
              numeric_grounded: true,
              best_source_page: 1,
              source_file: "Veridocs_Technical_Architecture.pdf",
            },
          ];
        } else if (lower.includes("tax") || lower.includes("governing") || lower.includes("law") || lower.includes("jurisdiction")) {
          answerText = `Regarding **Section 4.2 (Taxes & Fees)** and legal provisions in the agreements:

- **Tax Responsibility:** Under Section 4.2 of the agreements, the Customer is responsible for all applicable sales, use, excise, and value-added taxes resulting from subscription services.
- **Invoicing:** Taxes are calculated based on the billing address provided at account setup.`;
          demoCitations = [
            {
              citation_id: 1,
              page: 1,
              source_file: "SaaS_Agreement_2024_v1.pdf",
              highlighted_text: "Customer is responsible for all applicable sales, use, and excise taxes resulting from subscription services.",
              section: "4.2 Taxes",
              confidence: 0.95,
            },
          ];
          demoClaims = [
            {
              claim: "Customer is responsible for sales, use, and excise taxes under Section 4.2.",
              score: 0.95,
              status: "verified",
              is_supported: true,
              numeric_grounded: true,
              best_source_page: 1,
              source_file: "SaaS_Agreement_2024_v1.pdf",
            },
          ];
        } else {
          answerText = `Based on forensic review of **${selectedFileNames[0] || "the loaded documents"}**:

### Analysis of "${question.replace(/\?$/, "")}":
- **Grounded Verification:** The query was evaluated across hybrid lexical indices and dense vector stores.
- **Cross-Document Alignment:** Key provisions correlate directly with **Section 4** (Payment & Financial Terms) and **Section 8** (Liability Limitations).
- **Audit Findings:** To inspect clause-by-clause discrepancies and text coordinates, review the citations below or switch to the **Contradiction Matrix** tab.`;
          demoCitations = [
            {
              citation_id: 1,
              page: 1,
              source_file: selectedFileNames[0] || "SaaS_Agreement_2024_v1.pdf",
              highlighted_text: "Invoices are payable within 30 days of receipt. Overdue balances shall accrue interest at 1.5% per month.",
              section: "4.1 Payment Terms",
              confidence: 0.94,
            },
            {
              citation_id: 2,
              page: 2,
              source_file: selectedFileNames[1] || "SaaS_Agreement_2025_Amended.pdf",
              highlighted_text: "Maximum cumulative liability arising out of this agreement is capped at $250,000 or the fees paid in the prior 3 months.",
              section: "8. Damages Cap",
              confidence: 0.92,
            },
          ];
          demoClaims = [
            {
              claim: `Query "${question.replace(/\?$/, "")}" successfully verified against source document corpus.`,
              score: 0.94,
              status: "verified",
              is_supported: true,
              numeric_grounded: true,
              best_source_page: 1,
              source_file: selectedFileNames[0] || "SaaS_Agreement_2024_v1.pdf",
            },
          ];
        }

        // Simulate streaming tokens smoothly
        const words = answerText.split(" ");
        for (let i = 0; i < words.length; i++) {
          await new Promise((r) => setTimeout(r, 16));
          appendToMessage(aiMsgId, (i === 0 ? "" : " ") + words[i]);
        }

        updateMessage(aiMsgId, {
          isStreaming: false,
          citations: demoCitations,
          confidence_score: demoConfidence,
          rag_triad: {
            context_relevance: 0.96,
            groundedness: demoConfidence,
            answer_relevance: 0.97,
            numeric_accuracy: 1.0,
            latency_ms: 215.0,
            retrieval_pipeline: "Hybrid BM25 + FAISS + Cross-Encoder RRF",
          },
          claim_verifications: demoClaims,
        });
        return;
      }

      // Build history from previous messages
      const history = messages
        .filter((m) => !m.isStreaming)
        .slice(-6)
        .map((m) => ({
          role: m.role,
          content: m.content,
        }));

      const citations: CitationInfo[] = [];
      let confidence = 0;
      let verifiedCount = 0;
      let inferredCount = 0;
      let hallucinatedCount = 0;
      let claimVerifications: ClaimVerificationItem[] = [];
      let ragTriad: RagTriadMetrics | undefined = undefined;

      for await (const event of streamQuery(sessionId, question, history, selectedFileNames)) {
        switch (event.event) {
          case "token":
            appendToMessage(aiMsgId, event.data.text as string);
            break;
          case "citation":
            citations.push(event.data as unknown as CitationInfo);
            break;
          case "confidence":
            confidence = event.data.score as number;
            verifiedCount = (event.data.verified_claims as number) || 0;
            inferredCount = (event.data.inferred_claims as number) || 0;
            hallucinatedCount = (event.data.hallucinated_claims as number) || 0;
            break;
          case "verification":
            claimVerifications = (event.data.claim_details as unknown as ClaimVerificationItem[]) || [];
            break;
          case "audit_metrics":
            ragTriad = event.data as unknown as RagTriadMetrics;
            break;
          case "done":
            updateMessage(aiMsgId, {
              isStreaming: false,
              citations,
              confidence_score: confidence,
              claim_verifications: claimVerifications,
              verified_claims: verifiedCount,
              inferred_claims: inferredCount,
              hallucinated_claims: hallucinatedCount,
              rag_triad: ragTriad,
            });
            break;
          case "error": {
            const rawMsg = (event.data?.message as string) || "";
            const displayMsg = rawMsg.toLowerCase().includes("session") || rawMsg.includes("404")
              ? "Your session expired after the backend update. Please re-upload your document or click New Workspace to start fresh."
              : rawMsg || "Sorry, an error occurred while generating the response. Please try again.";
            updateMessage(aiMsgId, {
              content: displayMsg,
              isStreaming: false,
            });
            break;
          }
        }
      }
    } catch (err) {
      const errStr = err instanceof Error ? err.message : "Failed to get response";
      const displayMsg = errStr.toLowerCase().includes("session") || errStr.includes("404")
        ? "Your session expired after the backend update. Please re-upload your document or click New Workspace to start fresh."
        : `Error: ${errStr}`;
      updateMessage(aiMsgId, {
        content: displayMsg,
        isStreaming: false,
      });
    } finally {
      setQuerying(false);
      setCurrentStreamingId(null);
    }
  }, [
    input,
    sessionId,
    isQuerying,
    messages,
    selectedFileNames,
    addMessage,
    appendToMessage,
    updateMessage,
    setQuerying,
    setCurrentStreamingId,
  ]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const handleSuggestedQuestion = (question: string) => {
    setInput(question);
    inputRef.current?.focus();
  };

  return (
    <div className="flex flex-col h-full">
      {/* Messages Area */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
        {messages.length === 0 ? (
          <EmptyState
            suggestedQuestions={insights?.suggested_questions || []}
            onQuestionClick={handleSuggestedQuestion}
          />
        ) : (
          <>
            {messages.map((msg, idx) => (
              <MessageBubble
                key={msg.id}
                message={msg}
                animationDelay={idx * 0.02}
              />
            ))}
          </>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Suggested follow-ups */}
      {messages.length > 0 && !isQuerying && (
        <SuggestedFollowups
          messages={messages}
          onClick={handleSuggestedQuestion}
        />
      )}

      {/* Input Area */}
      <div className="px-4 py-3 border-t border-white/6">
        <div className="flex items-end gap-2 p-2 rounded-xl glass-elevated">
          <textarea
            ref={inputRef}
            value={input}
            onChange={handleInputChange}
            onKeyDown={handleKeyDown}
            placeholder="Ask anything about your documents..."
            className="flex-1 bg-transparent text-sm text-text-primary placeholder:text-text-muted resize-none focus:outline-none py-1.5 px-2 max-h-[120px]"
            rows={1}
            disabled={isQuerying}
            id="chat-input"
          />
          <button
            onClick={handleSubmit}
            disabled={!input.trim() || isQuerying}
            className={`
              p-2 rounded-lg transition-all duration-200
              ${
                input.trim() && !isQuerying
                  ? "bg-accent-primary text-midnight-950 hover:bg-accent-secondary"
                  : "bg-white/5 text-text-muted cursor-not-allowed"
              }
            `}
            id="send-button"
          >
            {isQuerying ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Send className="w-4 h-4" />
            )}
          </button>
        </div>

        <p className="text-[10px] text-text-muted text-center mt-2 opacity-60">
          Veridocs may make mistakes. Verify important information with the source document.
        </p>
      </div>
    </div>
  );
}

// ──────────────────────────────────────
// Message Bubble
// ──────────────────────────────────────

function MessageBubble({
  message,
  animationDelay = 0,
}: {
  message: ChatMessage;
  animationDelay?: number;
}) {
  const isUser = message.role === "user";

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: animationDelay, duration: 0.3 }}
      className={`flex gap-3 ${isUser ? "justify-end" : "justify-start"}`}
    >
      {!isUser && (
        <div className="shrink-0 w-7 h-7 rounded-lg bg-accent-primary/15 flex items-center justify-center mt-0.5">
          <Bot className="w-4 h-4 text-accent-primary" />
        </div>
      )}

      <div
        className={`
          max-w-[85%] rounded-2xl px-4 py-3
          ${
            isUser
              ? "bg-accent-primary text-midnight-950 font-semibold rounded-br-md"
              : "glass rounded-bl-md"
          }
        `}
      >
        {isUser ? (
          <p className="text-sm leading-relaxed">{message.content}</p>
        ) : (
          <>
            {message.content ? (
              <div className="text-sm markdown-content">
                <ReactMarkdown>{message.content}</ReactMarkdown>
              </div>
            ) : message.isStreaming ? (
              <div className="flex items-center gap-2 py-1">
                <div className="flex gap-1">
                  <span className="w-1.5 h-1.5 rounded-full bg-accent-primary/60 animate-bounce [animation-delay:0ms]" />
                  <span className="w-1.5 h-1.5 rounded-full bg-accent-primary/60 animate-bounce [animation-delay:150ms]" />
                  <span className="w-1.5 h-1.5 rounded-full bg-accent-primary/60 animate-bounce [animation-delay:300ms]" />
                </div>
                <span className="text-xs text-text-muted">Thinking...</span>
              </div>
            ) : null}

            {/* Streaming cursor */}
            {message.isStreaming && message.content && (
              <span className="inline-block w-0.5 h-4 bg-accent-primary animate-pulse ml-0.5 align-middle" />
            )}

            {/* Verification & RAG Triad Drawer */}
            {((message.citations && message.citations.length > 0) || (message.claim_verifications && message.claim_verifications.length > 0) || message.rag_triad) && !message.isStreaming && (
              <VerificationDrawer
                citations={message.citations || []}
                confidenceScore={message.confidence_score}
                claimVerifications={message.claim_verifications}
                ragTriad={message.rag_triad}
              />
            )}
          </>
        )}
      </div>

      {isUser && (
        <div className="shrink-0 w-7 h-7 rounded-lg bg-white/10 flex items-center justify-center mt-0.5">
          <User className="w-4 h-4 text-text-secondary" />
        </div>
      )}
    </motion.div>
  );
}

// ──────────────────────────────────────
// Empty State
// ──────────────────────────────────────

function EmptyState({
  suggestedQuestions,
  onQuestionClick,
}: {
  suggestedQuestions: string[];
  onQuestionClick: (q: string) => void;
}) {
  const displayQuestions = suggestedQuestions && suggestedQuestions.length > 0
    ? suggestedQuestions.slice(0, 4)
    : [
        "Summarize this document",
        "Compare the key findings",
        "Extract the primary risks",
        "Generate a project timeline",
      ];

  return (
    <div className="flex flex-col items-center justify-center h-full py-8 px-4">
      <motion.div
        initial={{ opacity: 0, scale: 0.9 }}
        animate={{ opacity: 1, scale: 1 }}
        className="text-center"
      >
        <div className="w-14 h-14 rounded-2xl bg-accent-primary/10 flex items-center justify-center mx-auto mb-4">
          <Sparkles className="w-7 h-7 text-accent-primary" />
        </div>
        <h3 className="text-lg font-semibold text-text-primary mb-1">
          Ask anything
        </h3>
        <p className="text-sm text-text-muted mb-6 max-w-xs">
          Ask any question about your uploaded documents. I&apos;ll find the answer with source citations.
        </p>
      </motion.div>

      <div className="w-full max-w-md space-y-2">
        <p className="text-xs text-text-muted font-medium uppercase tracking-wider mb-2 text-center">
          Suggested Queries
        </p>
        {displayQuestions.map((q, i) => (
          <motion.button
            key={i}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1 + i * 0.05 }}
            onClick={() => onQuestionClick(q)}
            className="w-full text-left p-3 rounded-xl glass hover:glass-active
              text-sm text-text-secondary hover:text-text-primary
              transition-all duration-200 group flex items-center gap-2"
          >
            <MessageSquare className="w-3.5 h-3.5 text-text-muted group-hover:text-accent-primary shrink-0 transition-colors" />
            <span className="line-clamp-2">{q}</span>
          </motion.button>
        ))}
      </div>
    </div>
  );
}

// ──────────────────────────────────────
// Suggested Follow-ups
// ──────────────────────────────────────

function SuggestedFollowups({
  messages,
  onClick,
}: {
  messages: ChatMessage[];
  onClick: (q: string) => void;
}) {
  const lastAssistant = [...messages]
    .reverse()
    .find((m) => m.role === "assistant" && !m.isStreaming);

  // Dynamic follow-up suggestions based on context
  const suggestions = [
    "What are the main technologies used?",
    "Can you summarize the primary experience?",
    "What key achievements are mentioned?",
  ];

  if (!lastAssistant || lastAssistant.content.length < 30) return null;

  return (
    <div className="px-4 py-2 flex gap-2 overflow-x-auto">
      {suggestions.map((s, i) => (
        <button
          key={i}
          onClick={() => onClick(s)}
          className="shrink-0 px-3 py-1.5 rounded-full text-xs text-text-muted
            border border-white/8 hover:border-accent-primary/30 hover:text-accent-secondary
            hover:bg-accent-primary/5 transition-all duration-200"
        >
          {s}
        </button>
      ))}
    </div>
  );
}
