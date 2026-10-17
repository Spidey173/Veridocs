"use client";

import { useCallback, useState } from "react";
import { useDropzone } from "react-dropzone";
import { motion, AnimatePresence } from "framer-motion";
import {
  Upload,
  FileText,
  X,
  AlertCircle,
  Loader2,
  Sparkles,
} from "lucide-react";
import { useAppStore } from "@/lib/store";
import { uploadDocuments, getInsights } from "@/lib/api";
import type { UploadedFile } from "@/lib/store";

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return bytes + " B";
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
  return (bytes / (1024 * 1024)).toFixed(1) + " MB";
}

export default function DropZone() {
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [error, setError] = useState<string | null>(null);

  const {
    isUploading,
    uploadProgress,
    uploadStage,
    setSession,
    setUploading,
    setUploadProgress,
    setInsights,
    setLoadingInsights,
    setLocalFileUrls,
    addMessage,
    setActiveDiffReport,
  } = useAppStore();

  const onDrop = useCallback(
    (acceptedFiles: File[]) => {
      setError(null);
      const valid = acceptedFiles.filter((f) => {
        const ext = f.name.split(".").pop()?.toLowerCase();
        return ["pdf", "docx", "txt"].includes(ext || "");
      });
      if (valid.length === 0) {
        setError("Please upload PDF, DOCX, or TXT files.");
        return;
      }
      setSelectedFiles((prev) => [...prev, ...valid]);
    },
    []
  );

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      "application/pdf": [".pdf"],
      "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        [".docx"],
      "text/plain": [".txt"],
    },
    multiple: true,
  });

  const removeFile = (index: number) => {
    setSelectedFiles((prev) => prev.filter((_, i) => i !== index));
  };

  const handleUpload = async () => {
    if (selectedFiles.length === 0) return;

    setUploading(true);
    setUploadProgress(15, "Uploading documents & generating local blobs...");
    setError(null);

    // Dynamic progress ticker during server processing & vector indexing
    let currentPct = 15;
    const progressTicker = setInterval(() => {
      if (currentPct < 88) {
        currentPct += Math.floor(Math.random() * 8) + 4;
        let stage = "Extracting text chunks & coordinates...";
        if (currentPct > 40 && currentPct <= 70) {
          stage = "Generating FastEmbed vectors & neural embeddings...";
        } else if (currentPct > 70) {
          stage = "Finalizing hybrid BM25 + FAISS structures...";
        }
        setUploadProgress(Math.min(currentPct, 92), stage);
      }
    }, 160);

    try {
      const blobUrls: Record<string, string> = {};
      selectedFiles.forEach((f) => {
        blobUrls[f.name] = URL.createObjectURL(f);
      });
      setLocalFileUrls(blobUrls);

      const result = await uploadDocuments(selectedFiles);

      clearInterval(progressTicker);
      setUploadProgress(100, "Workspace ready!");

      const files: UploadedFile[] = selectedFiles.map((f) => ({
        name: f.name,
        size: f.size,
        type: f.type,
      }));

      // Immediately enter workspace in sub-second time
      setSession(result.session_id, files);
      setUploading(false);
      setSelectedFiles([]);

      // Fetch insights asynchronously in background without blocking UI
      setLoadingInsights(true);
      getInsights(result.session_id)
        .then((insights) => {
          if (insights) setInsights(insights);
        })
        .catch((err) => {
          console.warn("Background insights load:", err);
        })
        .finally(() => {
          setLoadingInsights(false);
        });
    } catch (err: unknown) {
      clearInterval(progressTicker);
      console.error("Upload error:", err);
      const msg = err instanceof Error ? err.message : "Failed to process documents. Please check backend connection.";
      setError(msg);
      setUploading(false);
    }
  };

  const handleTryDemo = () => {
    const demoFiles: UploadedFile[] = [
      {
        name: "SaaS_Agreement_2024_v1.pdf",
        size: 2150000,
        type: "application/pdf",
        pages: 3,
      },
      {
        name: "SaaS_Agreement_2025_Amended.pdf",
        size: 2280000,
        type: "application/pdf",
        pages: 3,
      },
      {
        name: "Veridocs_Technical_Architecture.pdf",
        size: 2450000,
        type: "application/pdf",
        pages: 3,
      },
    ];

    setSession("demo-session", demoFiles);

    setActiveDiffReport({
      doc_a_name: "SaaS_Agreement_2024_v1.pdf",
      doc_b_name: "SaaS_Agreement_2025_Amended.pdf",
      alignment_score: 0.68,
      summary:
        "Forensic cross-document analysis identified 3 critical discrepancies: Payment terms extended from 30 to 60 days, liability cap reduced by 75%, and SLA uptime commitment downgraded.",
      critical_count: 2,
      warning_count: 1,
      conflicts: [
        {
          id: "diff-1",
          topic: "Payment Terms & Late Penalties",
          severity: "critical",
          conflict_type: "contradiction",
          explanation:
            "Doc A requires payment within 30 days with a 1.5% monthly late fee. Doc B extends payment to 60 days and deletes all late penalty clauses.",
          risk_analysis:
            "Increases working capital cycle and removes financial incentive for timely invoice settlement.",
          doc_a: {
            filename: "SaaS_Agreement_2024_v1.pdf",
            page: 1,
            snippet:
              "Invoices are payable within 30 days of receipt. Overdue balances shall accrue interest at 1.5% per month.",
            section: "4.1 Payment Terms",
          },
          doc_b: {
            filename: "SaaS_Agreement_2025_Amended.pdf",
            page: 1,
            snippet:
              "Customer shall remit payment within 60 calendar days from invoice date without late fees or interest charges.",
            section: "4.1 Settlement",
          },
        },
        {
          id: "diff-2",
          topic: "Limitation of Liability Cap",
          severity: "critical",
          conflict_type: "numeric_mismatch",
          explanation:
            "Aggregate liability cap was slashed from $1,000,000 in Doc A down to $250,000 in Doc B.",
          risk_analysis:
            "Significantly impairs recovery rights in the event of gross negligence, data breaches, or major system failure.",
          doc_a: {
            filename: "SaaS_Agreement_2024_v1.pdf",
            page: 2,
            snippet:
              "The total aggregate liability of either party shall not exceed $1,000,000 under any circumstances.",
            section: "8. Liability Limitation",
          },
          doc_b: {
            filename: "SaaS_Agreement_2025_Amended.pdf",
            page: 2,
            snippet:
              "Maximum cumulative liability arising out of this agreement is capped at $250,000 or the fees paid in the prior 3 months.",
            section: "8. Damages Cap",
          },
        },
        {
          id: "diff-3",
          topic: "Service Level Agreement (SLA) & Uptime",
          severity: "warning",
          conflict_type: "modification",
          explanation:
            "Guaranteed uptime threshold decreased from 99.95% to 99.5%, allowing an extra 3.6 hours of uncredited downtime per month.",
          risk_analysis:
            "Reduces operational reliability guarantees for production workflows.",
          doc_a: {
            filename: "SaaS_Agreement_2024_v1.pdf",
            page: 3,
            snippet:
              "Provider guarantees monthly service availability of at least 99.95% excluding scheduled maintenance windows.",
            section: "Schedule B: SLA",
          },
          doc_b: {
            filename: "SaaS_Agreement_2025_Amended.pdf",
            page: 3,
            snippet:
              "Service availability commitment is target 99.5% with service credits capped at 5% of monthly recurring revenue.",
            section: "Schedule B: Availability",
          },
        },
      ],
    });

    setInsights({
      session_id: "demo-session",
      executive_summary: {
        purpose:
          "Veridocs Technical Architecture & Forensic Cross-Document Intelligence Platform.",
        key_findings: [
          "Cross-Document Contradiction Engine detects covenant modifications, numerical discrepancies, and liability changes across multiple files.",
          "Pixel-Level Visual Grounding highlights exact text coordinates on the PDF canvas for both citations and conflicting clauses.",
          "Two-stage hybrid retrieval (BM25 + FAISS via RRF) and cross-encoder re-ranking eliminate hallucinated answers.",
        ],
        risks: [
          "Contract amendments often subtly weaken liability caps and extend payment windows without explicit redlines.",
        ],
        conclusions: [
          "Automated forensic diffing combined with coordinate-level visual grounding transforms document analysis from passive chat into rigorous auditing.",
        ],
      },
      suggested_questions: [
        "What are the payment term differences between the 2024 and 2025 agreements?",
        "How was the liability cap altered between Doc A and Doc B?",
        "How does the pixel-level visual grounding locate citations?",
      ],
      key_entities: [
        { entity_type: "ORG", value: "Veridocs AI", count: 18, page: 1 },
        { entity_type: "MONEY", value: "$1,000,000 vs $250,000", count: 8, page: 2 },
        { entity_type: "TIME", value: "30 Days vs 60 Days", count: 6, page: 1 },
        { entity_type: "METRIC", value: "99.95% vs 99.5%", count: 4, page: 3 },
      ],
      total_pages: 3,
      total_chunks: 14,
      processing_time_ms: 220,
    });

    addMessage({
      id: "initial-assistant-msg",
      role: "assistant",
      content:
        "Welcome to **Veridocs Forensic Intelligence Studio**.\n\nI have pre-loaded two comparative contracts (**SaaS Agreement 2024** and **2025 Amended Revision**) alongside the technical whitepaper.\n\n👉 Switch to the **Contradiction Matrix** tab to see detected covenant conflicts, or click any citation below to see **pixel-level visual grounding** directly on the document canvas!",
      citations: [
        {
          citation_id: 1,
          page: 1,
          source_file: "SaaS_Agreement_2024_v1.pdf",
          highlighted_text:
            "Invoices are payable within 30 days of receipt. Overdue balances shall accrue interest at 1.5% per month.",
          section: "4.1 Payment Terms",
          confidence: 0.98,
        },
        {
          citation_id: 2,
          page: 1,
          source_file: "SaaS_Agreement_2025_Amended.pdf",
          highlighted_text:
            "Customer shall remit payment within 60 calendar days from invoice date without late fees or interest charges.",
          section: "4.1 Settlement",
          confidence: 0.96,
        },
        {
          citation_id: 3,
          page: 2,
          source_file: "Veridocs_Technical_Architecture.pdf",
          highlighted_text:
            "A deep cross-encoder calculates full token cross-attention across the query and candidate passages, filtering out false positives.",
          section: "2. Neural Re-Ranking",
          confidence: 0.96,
        },
      ],
      confidence_score: 0.97,
      rag_triad: {
        context_relevance: 0.95,
        groundedness: 0.97,
        answer_relevance: 0.96,
        numeric_accuracy: 1.0,
        latency_ms: 185.0,
        retrieval_pipeline: "Hybrid BM25 + FAISS + Cross-Encoder RRF"
      },
      claim_verifications: [
        {
          claim: "Veridocs implements a two-stage hybrid retrieval architecture fusing BM25 lexical indexing with dense semantic vector representations.",
          score: 0.98,
          status: "verified",
          is_supported: true,
          numeric_grounded: true,
          best_source_page: 1,
          source_file: "Veridocs_Technical_Architecture.pdf"
        }
      ],
      timestamp: new Date(),
    });
  };

  return (
    <div className="w-full max-w-xl mx-auto">
      {/* Drop Zone */}
      <div
        {...getRootProps()}
        className={`
          relative cursor-pointer rounded-2xl border-2 border-dashed p-10
          transition-all duration-300 group
          ${
            isDragActive
              ? "border-accent-primary bg-accent-primary/5"
              : "border-white/10 hover:border-white/20 hover:bg-white/[0.02]"
          }
        `}
      >
        <input {...getInputProps()} id="file-upload-input" />

        <div className="flex flex-col items-center gap-3.5 text-center">
          <motion.div
            animate={isDragActive ? { scale: 1.05 } : { scale: 1 }}
            className={`
              p-3.5 rounded-2xl transition-colors
              ${isDragActive ? "bg-accent-primary/15 text-accent-primary" : "bg-white/5 text-text-muted group-hover:text-text-secondary group-hover:bg-white/8"}
            `}
          >
            <Upload className="w-7 h-7" />
          </motion.div>

          <div>
            <p className="text-base font-semibold text-text-primary mb-1">
              {isDragActive ? "Drop documents here" : "Drop documents or click to browse"}
            </p>
            <p className="text-xs text-text-muted">
              Supports PDF, DOCX, TXT • Page-level citations & verification
            </p>
          </div>
        </div>
      </div>

      {/* Selected Files */}
      <AnimatePresence>
        {selectedFiles.length > 0 && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            className="mt-4 space-y-2 overflow-hidden"
          >
            <div className="flex justify-between items-center text-xs text-text-muted px-1">
              <span>{selectedFiles.length} file{selectedFiles.length > 1 ? "s" : ""} selected</span>
              <span>{formatFileSize(selectedFiles.reduce((acc, f) => acc + f.size, 0))}</span>
            </div>

            <div className="max-h-36 overflow-y-auto space-y-1.5 pr-1">
              {selectedFiles.map((file, i) => (
                <div
                  key={i}
                  className="flex items-center justify-between p-2.5 rounded-xl bg-white/[0.03] border border-white/5 text-xs"
                >
                  <div className="flex items-center gap-2 truncate">
                    <FileText className="w-3.5 h-3.5 text-accent-primary shrink-0" />
                    <span className="truncate text-text-secondary">{file.name}</span>
                    <span className="text-[10px] text-text-muted shrink-0">
                      ({formatFileSize(file.size)})
                    </span>
                  </div>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      removeFile(i);
                    }}
                    className="p-1 rounded-lg hover:bg-white/10 text-text-muted hover:text-white transition-colors"
                  >
                    <X className="w-3.5 h-3.5" />
                  </button>
                </div>
              ))}
            </div>

            <button
              onClick={handleUpload}
              disabled={isUploading}
              className="w-full mt-3 py-2.5 px-4 rounded-xl font-semibold text-xs text-midnight-950
                bg-gradient-to-r from-accent-primary to-accent-secondary hover:opacity-95 transition-all
                shadow-lg shadow-accent-primary/20 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
            >
              {isUploading ? (
                <>
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  <span>{uploadStage || "Processing..."} ({uploadProgress}%)</span>
                </>
              ) : (
                <span>Upload & Start Analysis</span>
              )}
            </button>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Progress */}
      <AnimatePresence>
        {isUploading && (
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            className="mt-4"
          >
            <div className="flex justify-between text-xs text-text-muted mb-2">
              <span>{uploadStage}</span>
              <span>{uploadProgress}%</span>
            </div>
            <div className="h-1.5 bg-white/5 rounded-full overflow-hidden">
              <motion.div
                className="h-full bg-gradient-to-r from-accent-primary to-accent-secondary rounded-full"
                initial={{ width: 0 }}
                animate={{ width: `${uploadProgress}%` }}
                transition={{ duration: 0.3 }}
              />
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Error */}
      <AnimatePresence>
        {error && (
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            className="mt-4 flex items-center gap-3 p-3.5 rounded-xl bg-danger/10 border border-danger/20 text-danger text-xs"
          >
            <AlertCircle className="w-4 h-4 shrink-0" />
            <p className="flex-1">{error}</p>
            <button
              onClick={() => setError(null)}
              className="p-1 rounded-lg hover:bg-danger/20 transition-colors"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Interactive Demo Workspace Button */}
      {selectedFiles.length === 0 && (
        <div className="mt-6 flex items-center justify-center">
          <button
            type="button"
            onClick={handleTryDemo}
            className="group flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-semibold
              bg-white/5 hover:bg-accent-primary/10 text-text-secondary hover:text-accent-primary
              border border-white/10 hover:border-accent-primary/30 transition-all shadow-sm"
          >
            <Sparkles className="w-3.5 h-3.5 text-accent-primary group-hover:scale-110 transition-transform" />
            <span>Launch Interactive Demo Workspace</span>
            <span className="text-[10px] px-2 py-0.5 rounded-full bg-accent-primary/20 text-accent-primary font-medium">Instant</span>
          </button>
        </div>
      )}
    </div>
  );
}
