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
  } = useAppStore();

  const removeFile = (index: number) => {
    setSelectedFiles((prev) => prev.filter((_, i) => i !== index));
  };

  const executeUpload = useCallback(
    async (targetFiles?: File[]) => {
      const filesToUpload = targetFiles || selectedFiles;
      if (filesToUpload.length === 0) return;

      setUploading(true);
      setUploadProgress(25, "Extracting text chunks & generating embeddings...");
      setError(null);

      // Progress indicator
      let currentPct = 25;
      const progressTicker = setInterval(() => {
        if (currentPct < 90) {
          currentPct += 25;
          let stage = "Extracting text chunks & coordinates...";
          if (currentPct >= 50 && currentPct < 80) {
            stage = "Generating FastEmbed vectors & neural embeddings...";
          } else if (currentPct >= 80) {
            stage = "Finalizing hybrid FTS + pgvector HNSW structures...";
          }
          setUploadProgress(Math.min(currentPct, 95), stage);
        }
      }, 25);

      try {
        const blobUrls: Record<string, string> = {};
        filesToUpload.forEach((f) => {
          blobUrls[f.name] = URL.createObjectURL(f);
        });
        setLocalFileUrls(blobUrls);

        const result = await uploadDocuments(filesToUpload);

        clearInterval(progressTicker);
        setUploadProgress(100, "Workspace ready!");

        const files: UploadedFile[] = filesToUpload.map((f) => ({
          name: f.name,
          size: f.size,
          type: f.type,
        }));

        // Update session state
        setSession(result.session_id, files);
        setUploading(false);
        setSelectedFiles([]);

        // Fetch document insights in the background
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
        console.error("Document upload failed:", err);
        const errMessage = err instanceof Error ? err.message : "Failed to upload and index document.";
        setError(errMessage);
        setUploading(false);
      }
    },
    [
      selectedFiles,
      setUploading,
      setUploadProgress,
      setError,
      setLocalFileUrls,
      setSession,
      setSelectedFiles,
      setLoadingInsights,
      setInsights,
    ]
  );

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
      setSelectedFiles(valid);
      // Start upload when files are dropped
      executeUpload(valid);
    },
    [executeUpload]
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
          onClick={() => executeUpload()}
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

  {/* Progress */ }
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
    </div>
  );
}
