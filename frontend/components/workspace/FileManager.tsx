"use client";

import { useAppStore } from "@/lib/store";
import {
  FileText,
  Upload,
  Layers,
  Archive,
  History,
  Settings,
  Plus,
  ChevronRight,
} from "lucide-react";
import { uploadDocuments, getInsights } from "@/lib/api";
import { useState, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import type { UploadedFile } from "@/lib/store";

export default function FileManager() {
  const {
    sessionId,
    files,
    selectedFileNames,
    activeDocumentName,
    isUploading,
    toggleFileSelection,
    setActiveDocument,
    selectAllFiles,
    deselectAllFiles,
    setSession,
    setUploading,
    setUploadProgress,
    setInsights,
    setLoadingInsights,
    setLocalFileUrls,
  } = useAppStore();

  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isHoveredUpload, setIsHoveredUpload] = useState(false);

  const handleAddFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!e.target.files || e.target.files.length === 0) return;
    const acceptedFiles = Array.from(e.target.files);

    setUploading(true);
    setUploadProgress(0, "Staging additional files...");

    try {
      // 1. Generate local blob URLs immediately for instant zero-lag rendering
      const blobUrls: Record<string, string> = {};
      acceptedFiles.forEach((f) => {
        blobUrls[f.name] = URL.createObjectURL(f);
      });
      setLocalFileUrls(blobUrls);

      setUploadProgress(20, "Uploading to server...");
      const result = await uploadDocuments(acceptedFiles, (progress) => {
        setUploadProgress(Math.min(progress * 0.7, 70), "Uploading...");
      }, sessionId || undefined);

      setUploadProgress(85, "Updating vector index...");
      
      const newFiles: UploadedFile[] = acceptedFiles.map((f) => ({
        name: f.name,
        size: f.size,
        type: f.type,
      }));

      // 2. Combine existing files and new files, immediately active
      const updatedFiles = [...files, ...newFiles];
      setSession(result.session_id, updatedFiles);
      setUploadProgress(100, "Done!");
      setUploading(false);

      // 3. Update insights in background
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
      console.error(err);
      setUploading(false);
    }
  };

  const triggerUpload = () => {
    fileInputRef.current?.click();
  };

  return (
    <div className="w-full h-full flex flex-col bg-midnight-900 border-r border-white/5 select-none">
      {/* File Upload Trigger */}
      <div className="p-4 border-b border-white/5 flex flex-col gap-3">
        <div className="flex items-center justify-between">
          <span className="text-[11px] font-bold text-text-muted uppercase tracking-wider">
            Workspace
          </span>
        </div>

        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept=".pdf,.docx,.txt"
          onChange={handleAddFile}
          className="hidden"
        />

        <button
          onClick={triggerUpload}
          disabled={isUploading}
          className="w-full flex items-center justify-center gap-2 py-2.5 px-4 rounded-xl border border-dashed border-white/10 hover:border-accent-primary/50 bg-white/[0.01] hover:bg-accent-primary/[0.02] text-xs font-semibold text-text-secondary hover:text-accent-primary transition-all duration-150"
        >
          <Upload className="w-3.5 h-3.5" />
          {isUploading ? "Uploading..." : "Add document"}
        </button>
      </div>

      {/* Files List Scroll Area */}
      <div className="flex-1 overflow-y-auto px-2 py-4 space-y-5">
        <div>
          <div className="flex items-center justify-between px-2 mb-2">
            <span className="text-[10px] font-bold text-text-muted uppercase tracking-wider">
              Documents ({files.length})
            </span>
          </div>

          <div className="space-y-1">
            {files.map((file) => {
              const isActive = activeDocumentName === file.name;

              return (
                <div
                  key={file.name}
                  onClick={() => setActiveDocument(file.name)}
                  className={`
                    group flex items-center gap-2.5 p-2 rounded-xl cursor-pointer transition-all duration-150
                    ${isActive ? "bg-white/[0.04] border border-white/5" : "hover:bg-white/[0.02] border border-transparent"}
                  `}
                >
                  {/* Active document line marker */}
                  <div
                    className={`w-0.5 h-6 rounded-full transition-all ${
                      isActive ? "bg-accent-primary" : "bg-transparent group-hover:bg-white/10"
                    }`}
                  />

                  <FileText className={`w-4 h-4 shrink-0 ${isActive ? "text-accent-primary" : "text-text-muted"}`} />

                  <div className="flex-1 min-w-0">
                    <p className={`text-xs truncate ${isActive ? "text-text-primary font-semibold" : "text-text-secondary group-hover:text-text-primary"}`}>
                      {file.name}
                    </p>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
