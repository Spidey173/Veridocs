"use client";

import { useCallback, useState } from "react";
import { useDropzone } from "react-dropzone";
import {
  Upload,
  FileText,
  X,
  AlertCircle,
  Loader2,
  CheckCircle2,
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
      setUploadProgress(15, "1/4 Parsing document structure & text streams...");
      setError(null);

      // Realistic pipeline progress ticks
      let currentPct = 15;
      const progressTicker = setInterval(() => {
        if (currentPct < 90) {
          currentPct += 20;
          let stage = "1/4 Parsing document structure & text streams...";
          if (currentPct >= 35 && currentPct < 60) {
            stage = "2/4 Extracting page coordinates & bounding boxes...";
          } else if (currentPct >= 60 && currentPct < 80) {
            stage = "3/4 Generating semantic embeddings & dense index...";
          } else if (currentPct >= 80) {
            stage = "4/4 Indexing BM25 full-text & pgvector HNSW structures...";
          }
          setUploadProgress(Math.min(currentPct, 95), stage);
        }
      }, 30);

      try {
        const blobUrls: Record<string, string> = {};
        filesToUpload.forEach((f) => {
          blobUrls[f.name] = URL.createObjectURL(f);
        });
        setLocalFileUrls(blobUrls);

        const result = await uploadDocuments(filesToUpload);

        clearInterval(progressTicker);
        setUploadProgress(100, "Workspace ready");

        const files: UploadedFile[] = filesToUpload.map((f) => ({
          name: f.name,
          size: f.size,
          type: f.type,
        }));

        setSession(result.session_id, files);
        setUploading(false);
        setSelectedFiles([]);

        // Fetch insights in the background
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
    <div className="w-full">
      {/* Drop Zone: Dense, Professional, High-Contrast */}
      <div
        {...getRootProps()}
        className={`
          relative cursor-pointer rounded-lg border border-dashed p-7
          transition-colors duration-150 group text-center
          ${
            isDragActive
              ? "border-[var(--color-accent)] bg-[var(--color-accent-subtle)]"
              : "border-[var(--border-default)] hover:border-[var(--border-strong)] bg-[var(--bg-surface)] hover:bg-[var(--bg-surface-raised)]"
          }
        `}
      >
        <input {...getInputProps()} id="file-upload-input" />

        <div className="flex flex-col items-center gap-2.5">
          <Upload className="w-5 h-5 text-[var(--text-muted)] group-hover:text-[var(--text-primary)] transition-colors" />

          <div>
            <p className="text-xs font-semibold text-[var(--text-primary)] mb-0.5">
              {isDragActive ? "Drop documents here to stage" : "Drop documents or click to browse"}
            </p>
            <p className="text-[11px] text-[var(--text-muted)] font-mono-data">
              Supports PDF, DOCX, TXT • Page-level citations & verification
            </p>
          </div>
        </div>
      </div>

      {/* Selected Staged Files */}
      {selectedFiles.length > 0 && (
        <div className="mt-3 space-y-1.5 border border-[var(--border-subtle)] rounded-lg p-2.5 bg-[var(--bg-surface)]">
          <div className="flex justify-between items-center text-[11px] text-[var(--text-muted)] px-1 font-mono-data">
            <span>{selectedFiles.length} file{selectedFiles.length > 1 ? "s" : ""} staged</span>
            <span>{formatFileSize(selectedFiles.reduce((acc, f) => acc + f.size, 0))}</span>
          </div>

          <div className="max-h-32 overflow-y-auto space-y-1 pr-1">
            {selectedFiles.map((file, i) => (
              <div
                key={i}
                className="flex items-center justify-between p-1.5 rounded border border-[var(--border-subtle)] bg-[var(--bg-surface-raised)] text-xs"
              >
                <div className="flex items-center gap-2 truncate">
                  <FileText className="w-3.5 h-3.5 text-[var(--text-muted)] shrink-0" />
                  <span className="truncate text-[var(--text-primary)] font-medium">{file.name}</span>
                  <span className="text-[10px] text-[var(--text-muted)] shrink-0 font-mono-data">
                    ({formatFileSize(file.size)})
                  </span>
                </div>
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    removeFile(i);
                  }}
                  className="p-1 rounded text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-subtle)] transition-colors"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              </div>
            ))}
          </div>

          <button
            type="button"
            onClick={() => executeUpload()}
            disabled={isUploading}
            className="w-full mt-2 py-2 px-3 rounded text-xs font-semibold text-white bg-[var(--color-accent)] hover:opacity-95 transition-opacity disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
          >
            {isUploading ? (
              <>
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
                <span className="font-mono-data">{uploadStage || "Processing..."} ({uploadProgress}%)</span>
              </>
            ) : (
              <span>Upload & Start Analysis</span>
            )}
          </button>
        </div>
      )}

      {/* Uploading Progress with Honest Pipeline Steps */}
      {isUploading && (
        <div className="mt-3 p-3 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-surface)]">
          <div className="flex justify-between items-center text-[11px] mb-1.5">
            <span className="text-[var(--text-primary)] font-medium flex items-center gap-1.5">
              <Loader2 className="w-3 h-3 animate-spin text-[var(--color-accent)]" />
              {uploadStage}
            </span>
            <span className="text-[var(--text-muted)] font-mono-data">{uploadProgress}%</span>
          </div>
          <div className="h-1 bg-[var(--bg-subtle)] rounded-full overflow-hidden">
            <div
              className="h-full bg-[var(--color-accent)] transition-all duration-200"
              style={{ width: `${uploadProgress}%` }}
            />
          </div>
        </div>
      )}

      {/* Error Banner with Plain Feedback */}
      {error && (
        <div className="mt-3 flex items-start gap-2.5 p-3 rounded-lg border border-[var(--color-danger-border)] bg-[var(--color-danger-bg)] text-[var(--color-danger)] text-xs">
          <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
          <div className="flex-1">
            <p className="font-semibold mb-0.5">Document ingestion failed</p>
            <p className="opacity-90">{error}</p>
          </div>
          <button
            type="button"
            onClick={() => setError(null)}
            className="p-1 rounded hover:bg-black/10 transition-colors"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      )}
    </div>
  );
}
