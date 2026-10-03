"use client";

import { useCallback, useState, useEffect } from "react";
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
import { uploadDocuments, getInsights, getApiBase } from "@/lib/api";
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
    setUploadProgress(0, "Uploading files...");
    setError(null);

    try {
      // 1. Generate local blob URLs immediately so PDFViewer loads at 0ms from browser RAM
      const blobUrls: Record<string, string> = {};
      selectedFiles.forEach((f) => {
        blobUrls[f.name] = URL.createObjectURL(f);
      });
      setLocalFileUrls(blobUrls);

      setUploadProgress(15, "Uploading to server...");

      const result = await uploadDocuments(selectedFiles, (progress) => {
        setUploadProgress(Math.min(progress * 0.7, 70), "Uploading files...");
      });

      setUploadProgress(85, "Finalizing vector index...");

      const files: UploadedFile[] = selectedFiles.map((f) => ({
        name: f.name,
        size: f.size,
        type: f.type,
      }));

      // 2. Open workspace IMMEDIATELY — do NOT block user on LLM summary generation
      setUploadProgress(100, "Complete!");
      setSession(result.session_id, files);
      setSelectedFiles([]);
      setUploading(false);

      // 3. Fetch insights asynchronously in background with zero UI freeze
      setLoadingInsights(true);
      getInsights(result.session_id)
        .then((insights) => {
          if (insights) setInsights(insights);
        })
        .catch((err) => {
          console.warn("Background insights fetch:", err);
        })
        .finally(() => {
          setLoadingInsights(false);
        });
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Upload failed. Please try again.";
      if (msg.includes("Network error") || msg.includes("Failed to fetch")) {
        setError(`Cannot reach backend at ${getApiBase()}. Make sure your backend server is running (uvicorn backend.main:app), or try the Interactive Demo below!`);
      } else {
        setError(msg);
      }
      setUploading(false);
    }
  };

  const handleTryDemo = () => {
    const demoFiles: UploadedFile[] = [
      {
        name: "Veridocs_Technical_Architecture.pdf",
        size: 1420000,
        type: "application/pdf",
        pages: 3,
      },
    ];
    setSession("demo-session", demoFiles);
    setInsights({
      session_id: "demo-session",
      executive_summary: {
        purpose: "Enterprise document intelligence engine combining hybrid retrieval, neural cross-encoder re-ranking, and strict factual grounding.",
        key_findings: [
          "Hybrid Search couples BM25 lexical token matching with dense vector FAISS index for high-recall candidate selection.",
          "Cross-Encoder Re-Ranking computes joint sequence attention, lifting top-k precision by 38% over dense-only retrieval.",
          "Strict citation grounding ensures every claim is attributed to exact page, chunk, and bounding box references.",
          "Sub-second streaming latency achieved through token pipelining and asynchronous query execution.",
        ],
        risks: [
          "Low-contrast scanned PDFs require OCR preprocessing before chunking.",
          "Excessive context length in naive RAG without re-ranking leads to lost-in-the-middle degradation.",
        ],
        conclusions: [
          "Veridocs provides auditable, production-grade enterprise document reasoning with zero unverified hallucinations.",
        ],
      },
      suggested_questions: [
        "How does Veridocs mitigate hallucinations?",
        "What is the role of the Cross-Encoder re-ranker?",
        "Explain the hybrid retrieval architecture",
        "How are citations and page coordinates verified?",
      ],
      key_entities: [
        { entity_type: "Component", value: "FAISS Vector Index", count: 8, page: 1 },
        { entity_type: "Component", value: "BM25 Retriever", count: 6, page: 1 },
        { entity_type: "Model", value: "Cross-Encoder Re-Ranker", count: 12, page: 2 },
        { entity_type: "Metric", value: "38% Precision Gain", count: 4, page: 2 },
        { entity_type: "Feature", value: "Grounded Citations", count: 9, page: 3 },
      ],
      total_pages: 3,
      total_chunks: 18,
      processing_time_ms: 384,
    });

    addMessage({
      id: "welcome-msg",
      role: "assistant",
      content: `Welcome to **Veridocs**! 👋\n\nI have loaded the **Veridocs Technical Architecture Whitepaper** into your workspace. You can explore:\n- **Verified Citations**: Click on any citation badge like [1] or [2] below to view the verified source page.\n- **Executive Insights**: Check the right-hand panel for automated key findings, entities, and risk analysis.\n- **Document Navigation**: Use the PDF viewer in the center column to browse pages.\n\nTry asking any question, or select one of the suggested prompts below!`,
      citations: [
        {
          citation_id: 1,
          page: 1,
          source_file: "Veridocs_Technical_Architecture.pdf",
          highlighted_text: "Veridocs implements a two-stage hybrid retrieval architecture fusing BM25 lexical indexing with dense semantic vector representations.",
          section: "1. Hybrid Retrieval Engine",
          confidence: 0.98,
        },
        {
          citation_id: 2,
          page: 2,
          source_file: "Veridocs_Technical_Architecture.pdf",
          highlighted_text: "A deep cross-encoder calculates full token cross-attention across the query and candidate passages, filtering out false positives.",
          section: "2. Neural Re-Ranking",
          confidence: 0.96,
        },
      ],
      confidence_score: 0.97,
      timestamp: new Date(),
    });
  };

  return (
    <div className="w-full max-w-2xl mx-auto">
      {/* Drop Zone */}
      <div
        {...getRootProps()}
        className={`
          relative cursor-pointer rounded-2xl border-2 border-dashed p-12
          transition-all duration-300 group
          ${
            isDragActive
              ? "dropzone-active border-accent-primary bg-accent-primary/5"
              : "border-white/10 hover:border-white/20 hover:bg-white/[0.02]"
          }
        `}
      >
        <input {...getInputProps()} id="file-upload-input" />

        <div className="flex flex-col items-center gap-4 text-center">
          <motion.div
            animate={isDragActive ? { scale: 1.1, y: -4 } : { scale: 1, y: 0 }}
            transition={{ type: "spring", stiffness: 300 }}
            className={`
              p-4 rounded-2xl transition-colors duration-300
              ${isDragActive ? "bg-accent-primary/15" : "bg-white/5 group-hover:bg-white/8"}
            `}
          >
            <Upload
              className={`w-8 h-8 transition-colors ${
                isDragActive ? "text-accent-primary" : "text-text-muted group-hover:text-text-secondary"
              }`}
            />
          </motion.div>

          <div>
            <p className="text-lg font-medium text-text-primary mb-1">
              {isDragActive ? "Drop files here" : "Drop documents or click to browse"}
            </p>
            <p className="text-sm text-text-muted">
              Supports PDF, DOCX, TXT • Up to 50MB per file
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
            className="mt-4 space-y-2"
          >
            {selectedFiles.map((file, index) => (
              <motion.div
                key={`${file.name}-${index}`}
                initial={{ opacity: 0, x: -20 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: 20 }}
                transition={{ delay: index * 0.05 }}
                className="flex items-center gap-3 p-3 rounded-xl glass"
              >
                <FileText className="w-5 h-5 text-accent-primary shrink-0" />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-text-primary truncate">
                    {file.name}
                  </p>
                  <p className="text-xs text-text-muted">
                    {formatFileSize(file.size)}
                  </p>
                </div>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    removeFile(index);
                  }}
                  className="p-1 rounded-lg hover:bg-white/10 transition-colors"
                >
                  <X className="w-4 h-4 text-text-muted" />
                </button>
              </motion.div>
            ))}

            {/* Upload Button */}
            <motion.button
              whileHover={{ scale: 1.01 }}
              whileTap={{ scale: 0.99 }}
              onClick={handleUpload}
              disabled={isUploading}
              className={`
                w-full mt-4 py-3.5 px-6 rounded-xl font-bold text-sm
                flex items-center justify-center gap-2
                transition-all duration-300 shadow-lg
                ${
                  isUploading
                    ? "bg-accent-primary/20 text-accent-primary/50 cursor-not-allowed border border-accent-primary/10"
                    : "bg-accent-primary hover:bg-accent-secondary text-midnight-950 shadow-accent-primary/20 hover:shadow-accent-primary/35 border border-transparent"
                }
              `}
            >
              {isUploading ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  <span>{uploadStage || "Processing..."}</span>
                </>
              ) : (
                <>
                  <Upload className="w-4 h-4" />
                  <span>
                    Upload & Analyze{" "}
                    {selectedFiles.length === 1
                      ? "Document"
                      : `${selectedFiles.length} Documents`}
                  </span>
                </>
              )}
            </motion.button>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Progress Bar */}
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
            className="mt-4 flex items-center gap-3 p-4 rounded-xl bg-danger/10 border border-danger/20 text-danger text-sm"
          >
            <AlertCircle className="w-5 h-5 shrink-0" />
            <p className="flex-1">{error}</p>
            <button
              onClick={() => setError(null)}
              className="p-1 rounded-lg hover:bg-danger/20 transition-colors"
            >
              <X className="w-4 h-4" />
            </button>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Interactive Demo Workspace Button */}
      <div className="mt-6 flex flex-col sm:flex-row items-center justify-center gap-3">
        <button
          type="button"
          onClick={handleTryDemo}
          className="group flex items-center gap-2 px-4 py-2.5 rounded-xl text-xs font-semibold
            bg-white/5 hover:bg-accent-primary/10 text-text-secondary hover:text-accent-primary
            border border-white/10 hover:border-accent-primary/30 transition-all shadow-sm"
        >
          <Sparkles className="w-3.5 h-3.5 text-accent-primary group-hover:scale-110 transition-transform" />
          <span>Launch Interactive Demo Workspace</span>
          <span className="text-[10px] px-2 py-0.5 rounded-full bg-accent-primary/20 text-accent-primary font-medium">Instant Preview</span>
        </button>
      </div>
    </div>
  );
}
