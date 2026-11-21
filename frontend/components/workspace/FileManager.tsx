"use client";

import { useAppStore } from "@/lib/store";
import { FileText, Upload, Trash2, Loader2, Plus } from "lucide-react";
import { uploadDocuments, deleteDocument } from "@/lib/api";
import { useRef } from "react";
import type { UploadedFile } from "@/lib/store";

export default function FileManager() {
  const {
    sessionId,
    files,
    activeDocumentName,
    isUploading,
    uploadProgress,
    setActiveDocument,
    setSession,
    setUploading,
    setUploadProgress,
    setLocalFileUrls,
  } = useAppStore();

  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleAddFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!e.target.files || e.target.files.length === 0) return;
    const acceptedFiles = Array.from(e.target.files);

    setUploading(true);
    setUploadProgress(15);

    try {
      const blobUrls: Record<string, string> = {};
      acceptedFiles.forEach((f) => {
        blobUrls[f.name] = URL.createObjectURL(f);
      });
      setLocalFileUrls(blobUrls);

      const result = await uploadDocuments(
        acceptedFiles,
        sessionId || undefined,
        (progress) => setUploadProgress(progress)
      );

      const newFiles: UploadedFile[] = acceptedFiles.map((f) => ({
        name: f.name,
        size: f.size,
        type: f.type,
      }));

      const merged = [...files];
      for (const nf of newFiles) {
        if (!merged.some((m) => m.name === nf.name)) {
          merged.push(nf);
        }
      }

      setSession(result.session_id, merged);
      setActiveDocument(newFiles[0]?.name || activeDocumentName);
      setUploading(false);
    } catch (err) {
      console.error("Upload error:", err);
      setUploading(false);
    }
  };

  const handleDeleteFile = async (e: React.MouseEvent, docName: string) => {
    e.stopPropagation();
    if (!sessionId) return;
    try {
      await deleteDocument(sessionId, docName);
      const remaining = files.filter((f) => f.name !== docName);
      setSession(sessionId, remaining);
      if (activeDocumentName === docName) {
        setActiveDocument(remaining[0]?.name || null);
      }
    } catch (err) {
      console.error("Delete document error:", err);
    }
  };

  return (
    <div className="w-full h-full flex flex-col bg-[var(--bg-surface)] text-[var(--text-primary)] select-none">
      {/* Header */}
      <div className="h-10 px-3 border-b border-[var(--border-subtle)] flex items-center justify-between shrink-0">
        <span className="text-[11px] font-mono-data font-semibold text-[var(--text-muted)] uppercase tracking-wider">
          Documents ({files.length})
        </span>

        <button
          type="button"
          onClick={() => fileInputRef.current?.click()}
          disabled={isUploading}
          className="flex items-center gap-1 px-2 py-1 rounded bg-[var(--color-accent-subtle)] text-[var(--color-accent)] hover:bg-[var(--color-accent)] hover:text-white text-[11px] font-medium transition-colors"
          title="Add PDF or TXT document"
        >
          <Plus className="w-3 h-3" />
          <span>Add</span>
        </button>

        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,.txt"
          multiple
          onChange={handleAddFile}
          className="hidden"
        />
      </div>

      {/* Upload progress indicator */}
      {isUploading && (
        <div className="p-2.5 bg-[var(--bg-subtle)] border-b border-[var(--border-subtle)] flex items-center gap-2 text-xs">
          <Loader2 className="w-3.5 h-3.5 animate-spin text-[var(--color-accent)]" />
          <span className="text-[11px] text-[var(--text-secondary)]">Indexing {uploadProgress}%</span>
        </div>
      )}

      {/* Files List */}
      <div className="flex-1 overflow-y-auto p-2 space-y-1">
        {files.length === 0 ? (
          <div className="p-4 text-center text-xs text-[var(--text-muted)]">
            <p>No documents in workspace.</p>
          </div>
        ) : (
          files.map((file) => {
            const isActive = file.name === activeDocumentName;
            return (
              <div
                key={file.name}
                onClick={() => setActiveDocument(file.name)}
                className={`w-full flex items-center justify-between p-2 rounded cursor-pointer text-xs transition-colors group ${
                  isActive
                    ? "bg-[var(--color-accent-subtle)] border border-[var(--color-accent-border)] text-[var(--color-accent)] font-semibold"
                    : "hover:bg-[var(--bg-subtle)] text-[var(--text-secondary)] border border-transparent"
                }`}
              >
                <div className="flex items-center gap-2 truncate min-w-0">
                  <FileText className="w-3.5 h-3.5 shrink-0" />
                  <span className="truncate">{file.name}</span>
                </div>

                <button
                  type="button"
                  onClick={(e) => handleDeleteFile(e, file.name)}
                  className="opacity-0 group-hover:opacity-100 p-1 rounded hover:text-red-500 transition-opacity ml-1"
                  title="Remove document"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
