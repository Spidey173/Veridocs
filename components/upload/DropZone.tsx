"use client";

import { useCallback, useState } from "react";
import { useDropzone } from "react-dropzone";
import { Upload, FileText, X, AlertCircle, Loader2, Sparkles } from "lucide-react";
import { useAppStore } from "@/lib/store";
import { uploadDocuments, getSessionInfo } from "@/lib/api";
import type { UploadedFile } from "@/lib/store";

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return bytes + " B";
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
  return (bytes / (1024 * 1024)).toFixed(1) + " MB";
}

export default function DropZone() {
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [isLoadingDemo, setIsLoadingDemo] = useState(false);

  const {
    isUploading,
    uploadProgress,
    setSession,
    setUploading,
    setUploadProgress,
    setLocalFileUrls,
  } = useAppStore();

  const handleLoadDemo = async () => {
    setIsLoadingDemo(true);
    setError(null);
    try {
      const info = await getSessionInfo("demo-session");
      if (info && info.file_names && info.file_names.length > 0) {
        setSession(
          "demo-session",
          info.file_names.map((name) => ({
            name,
            size: 1150,
            type: name.endsWith(".pdf") ? "application/pdf" : "text/plain",
          })),
          info.suggested_questions
        );
      } else {
        setError("Demo document is not available. Please upload your own document.");
      }
    } catch {
      setError("Could not load sample document. Please upload your own document.");
    } finally {
      setIsLoadingDemo(false);
    }
  };

  const removeFile = (index: number) => {
    setSelectedFiles((prev) => prev.filter((_, i) => i !== index));
  };

  const executeUpload = useCallback(
    async (targetFiles?: File[]) => {
      const filesToUpload = targetFiles || selectedFiles;
      if (filesToUpload.length === 0) return;

      setUploading(true);
      setUploadProgress(10);
      setError(null);

      try {
        const blobUrls: Record<string, string> = {};
        filesToUpload.forEach((f) => {
          blobUrls[f.name] = URL.createObjectURL(f);
        });
        setLocalFileUrls(blobUrls);

        const result = await uploadDocuments(
          filesToUpload,
          undefined,
          (progress) => setUploadProgress(progress)
        );

        const files: UploadedFile[] = filesToUpload.map((f) => ({
          name: f.name,
          size: f.size,
          type: f.type,
        }));

        setSession(result.session_id, files, result.suggested_questions);
        setUploading(false);
        setSelectedFiles([]);
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : "Upload failed";
        setError(msg);
        setUploading(false);
      }
    },
    [selectedFiles, setSession, setUploading, setUploadProgress, setLocalFileUrls]
  );

  const onDrop = useCallback(
    (acceptedFiles: File[]) => {
      setError(null);
      if (acceptedFiles.length === 1 && selectedFiles.length === 0) {
        executeUpload(acceptedFiles);
      } else {
        setSelectedFiles((prev) => [...prev, ...acceptedFiles]);
      }
    },
    [selectedFiles, executeUpload]
  );

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      "application/pdf": [".pdf"],
      "application/vnd.openxmlformats-officedocument.wordprocessingml.document": [".docx"],
      "application/msword": [".doc"],
      "text/plain": [".txt"],
      "image/png": [".png"],
      "image/jpeg": [".jpg", ".jpeg"],
      "image/tiff": [".tiff", ".tif"],
    },
    maxSize: 50 * 1024 * 1024,
    multiple: true,
  });

  return (
    <div className="w-full space-y-4">
      <div
        {...getRootProps()}
        className={`border-2 border-dashed rounded-lg p-8 text-center cursor-pointer transition-all ${
          isDragActive
            ? "border-[var(--color-accent)] bg-[var(--color-accent-subtle)]"
            : "border-[var(--border-default)] hover:border-[var(--color-accent)] bg-[var(--bg-surface)]"
        }`}
      >
        <input {...getInputProps()} />
        <div className="flex flex-col items-center justify-center gap-2">
          <div className="w-10 h-10 rounded-full bg-[var(--bg-subtle)] flex items-center justify-center text-[var(--color-accent)] mb-1">
            <Upload className="w-5 h-5" />
          </div>
          <p className="text-sm font-semibold text-[var(--text-primary)]">
            {isDragActive ? "Drop documents here..." : "Drag & drop contracts, Word docs, or PDF/TXT files"}
          </p>
          <p className="text-xs text-[var(--text-muted)]">
            Supports PDF, DOCX, DOC, TXT, PNG, JPG, and TIFF up to 15MB. Multi-modal layout analysis, tables, and OCR.
          </p>
        </div>
      </div>

      {/* Quick Start with Sample Agreement */}
      {selectedFiles.length === 0 && !isUploading && (
        <div className="flex items-center justify-center pt-1">
          <button
            type="button"
            onClick={handleLoadDemo}
            disabled={isLoadingDemo}
            className="inline-flex items-center gap-1.5 text-xs text-[var(--text-muted)] hover:text-[var(--color-accent)] transition-colors underline decoration-dotted disabled:opacity-50"
          >
            {isLoadingDemo ? (
              <>
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
                <span>Loading sample contract...</span>
              </>
            ) : (
              <>
                <Sparkles className="w-3.5 h-3.5 text-[var(--color-accent)]" />
                <span>Or explore with sample agreement (NDA Contract) →</span>
              </>
            )}
          </button>
        </div>
      )}

      {error && (
        <div className="flex items-center gap-2 p-3 text-xs rounded border border-red-500/20 bg-red-500/10 text-red-500">
          <AlertCircle className="w-4 h-4 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {selectedFiles.length > 0 && (
        <div className="space-y-2">
          <div className="flex items-center justify-between text-xs text-[var(--text-muted)] font-mono-data">
            <span>{selectedFiles.length} file(s) staged</span>
            <button
              type="button"
              onClick={() => executeUpload()}
              disabled={isUploading}
              className="px-3 py-1.5 rounded bg-[var(--color-accent)] text-white font-medium hover:bg-[var(--color-accent-hover)] transition-colors disabled:opacity-50 flex items-center gap-1.5"
            >
              {isUploading ? (
                <>
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  <span>Indexing {uploadProgress}%</span>
                </>
              ) : (
                <span>Upload & Index</span>
              )}
            </button>
          </div>

          <div className="divide-y divide-[var(--border-subtle)] border border-[var(--border-subtle)] rounded bg-[var(--bg-surface)] overflow-hidden">
            {selectedFiles.map((f, i) => (
              <div key={i} className="flex items-center justify-between p-2.5 text-xs">
                <div className="flex items-center gap-2 truncate">
                  <FileText className="w-4 h-4 text-[var(--color-accent)] shrink-0" />
                  <span className="font-medium text-[var(--text-primary)] truncate">{f.name}</span>
                  <span className="text-[11px] text-[var(--text-muted)] font-mono-data shrink-0">
                    ({formatFileSize(f.size)})
                  </span>
                </div>
                {!isUploading && (
                  <button
                    type="button"
                    onClick={() => removeFile(i)}
                    className="p-1 text-[var(--text-muted)] hover:text-red-500 transition-colors"
                  >
                    <X className="w-3.5 h-3.5" />
                  </button>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
