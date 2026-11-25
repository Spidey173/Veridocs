"use client";

import { useState } from "react";
import { useAppStore } from "@/lib/store";
import {
  CheckCircle2,
  HelpCircle,
  ExternalLink,
  Edit2,
  Save,
  ShieldAlert,
  FileSpreadsheet
} from "lucide-react";
import { updateDocumentExtraction, overrideDocumentType, type ExtractionResult } from "@/lib/api";

interface Props {
  documentId: string;
  extraction: ExtractionResult | null;
  currentDocType?: string;
}

export default function FieldsViewer({ documentId, extraction, currentDocType }: Props) {
  const { setCurrentPage, updateExtractionUserEdit, updateFile, activeDocumentName } = useAppStore();
  const [editingField, setEditingField] = useState<string | null>(null);
  const [editValue, setEditValue] = useState<string>("");
  const [isSaving, setIsSaving] = useState(false);
  const [docTypeSelector, setDocTypeSelector] = useState<string>(currentDocType || extraction?.schema_type || "other");

  const fields = extraction?.fields || {};
  const userEdits = extraction?.user_edits || {};
  const verifiedRatio = extraction?.verified_ratio ?? 0;

  const handleDocTypeChange = async (newType: string) => {
    setDocTypeSelector(newType);
    try {
      await overrideDocumentType(documentId, newType);
      if (activeDocumentName) {
        updateFile(activeDocumentName, { doc_type: newType });
      }
    } catch (e) {
      console.error("Failed to override doc type:", e);
    }
  };

  const handleStartEdit = (key: string, currentVal: any) => {
    setEditingField(key);
    setEditValue(typeof currentVal === "object" ? JSON.stringify(currentVal) : String(currentVal ?? ""));
  };

  const handleSaveEdit = async (key: string) => {
    setIsSaving(true);
    try {
      updateExtractionUserEdit(documentId, key, editValue);
      await updateDocumentExtraction(documentId, { [key]: editValue });
      setEditingField(null);
    } catch (e) {
      console.error("Failed to save edit:", e);
    } finally {
      setIsSaving(false);
    }
  };

  if (!extraction || Object.keys(fields).length === 0) {
    return (
      <div className="flex flex-col items-center justify-center p-8 text-center text-muted-foreground">
        <FileSpreadsheet className="w-10 h-10 mb-2 opacity-40" />
        <p className="text-sm font-medium">No structured schema extracted</p>
        <p className="text-xs text-muted-foreground mt-1">
          Structured fields and evidence quotes are populated automatically upon ingestion.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4 p-3 text-left">
      {/* Header: Doc Type Selector and Verified Metric */}
      <div className="p-2.5 rounded-lg border border-border bg-card/60 space-y-2">
        <div className="flex items-center justify-between">
          <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
            Document Type
          </span>
          <select
            value={docTypeSelector}
            onChange={(e) => handleDocTypeChange(e.target.value)}
            className="text-xs bg-muted border border-border rounded px-2 py-0.5 font-medium text-foreground capitalize focus:outline-none focus:ring-1 focus:ring-primary"
          >
            <option value="invoice">Invoice</option>
            <option value="contract">Contract</option>
            <option value="research_paper">Research Paper</option>
            <option value="resume">Resume</option>
            <option value="other">Other</option>
          </select>
        </div>

        <div className="flex items-center justify-between pt-1 border-t border-border/40 text-xs">
          <span className="text-muted-foreground">Evidence Grounding Ratio:</span>
          <span className={`font-semibold flex items-center gap-1 ${
            verifiedRatio >= 0.7 ? "text-emerald-500" : "text-amber-500"
          }`}>
            {Math.round(verifiedRatio * 100)}% Verified
          </span>
        </div>
      </div>

      {/* Field Cards */}
      <div className="space-y-2.5">
        {Object.entries(fields).map(([fieldName, fieldData]: [string, any]) => {
          if (!fieldData || typeof fieldData !== "object") return null;

          // If line items array, render specially
          if (Array.isArray(fieldData)) {
            return (
              <div key={fieldName} className="p-2.5 rounded-lg border border-border bg-card/40 space-y-2">
                <span className="text-xs font-semibold text-foreground capitalize">
                  {fieldName.replace(/_/g, " ")} ({fieldData.length})
                </span>
                <div className="space-y-1.5 pl-2 border-l-2 border-border/60">
                  {fieldData.map((item, idx) => (
                    <div key={idx} className="text-xs text-muted-foreground space-y-0.5">
                      <div className="flex justify-between gap-2">
                        <span className="text-foreground/90 font-medium">
                          {item.description || item.value || JSON.stringify(item)}
                        </span>
                        {item.amount !== undefined && (
                          <span className="font-mono text-foreground shrink-0">${item.amount}</span>
                        )}
                        {item.date && (
                          <span className="font-mono text-primary shrink-0">{item.date}</span>
                        )}
                      </div>
                      {item.quote && (
                        <div className="flex items-center justify-between text-[10px] text-muted-foreground">
                          <span className="italic truncate">&quot;{item.quote}&quot;</span>
                          <span className="shrink-0 ml-2">
                            {item.verified ? "✓" : "?"} p.{item.page || 1}
                          </span>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            );
          }

          const hasUserEdit = userEdits[fieldName] !== undefined;
          const displayValue = hasUserEdit ? userEdits[fieldName] : fieldData.value;
          const isVerified = Boolean(fieldData.verified);
          const hasMathMismatch = Boolean(fieldData.math_mismatch);
          const quote = fieldData.quote || "";
          const pageNum = fieldData.page || 1;

          return (
            <div
              key={fieldName}
              className={`p-2.5 rounded-lg border transition-all ${
                hasMathMismatch
                  ? "border-destructive/60 bg-destructive/5"
                  : isVerified
                  ? "border-border bg-card/40 hover:border-border/80"
                  : "border-amber-500/30 bg-amber-500/5"
              }`}
            >
              {/* Field Label and Verification Badges */}
              <div className="flex items-center justify-between gap-1 mb-1">
                <span className="text-xs font-semibold text-foreground/90 capitalize truncate">
                  {fieldName.replace(/_/g, " ")}
                </span>

                <div className="flex items-center gap-1 shrink-0">
                  {hasMathMismatch && (
                    <span className="text-[10px] font-medium px-1.5 py-0.5 rounded bg-destructive/15 text-destructive flex items-center gap-0.5">
                      <ShieldAlert className="w-2.5 h-2.5" />
                      Math Mismatch
                    </span>
                  )}
                  {isVerified ? (
                    <span className="text-[10px] font-medium px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-500 flex items-center gap-0.5">
                      <CheckCircle2 className="w-2.5 h-2.5" />
                      Verified
                    </span>
                  ) : (
                    <span className="text-[10px] font-medium px-1.5 py-0.5 rounded bg-amber-500/15 text-amber-500 flex items-center gap-0.5">
                      <HelpCircle className="w-2.5 h-2.5" />
                      Unverified
                    </span>
                  )}
                </div>
              </div>

              {/* Field Value with Inline Edit */}
              <div className="flex items-center justify-between gap-2 mt-1">
                {editingField === fieldName ? (
                  <div className="flex items-center gap-1 w-full">
                    <input
                      type="text"
                      value={editValue}
                      onChange={(e) => setEditValue(e.target.value)}
                      className="text-xs bg-background border border-primary rounded px-2 py-1 w-full text-foreground focus:outline-none"
                    />
                    <button
                      onClick={() => handleSaveEdit(fieldName)}
                      disabled={isSaving}
                      className="p-1 rounded bg-primary text-primary-foreground hover:bg-primary/90"
                    >
                      <Save className="w-3.5 h-3.5" />
                    </button>
                  </div>
                ) : (
                  <>
                    <span className="text-xs text-foreground font-medium break-all">
                      {String(displayValue || "—")}
                      {hasUserEdit && (
                        <span className="text-[10px] text-muted-foreground ml-1.5 italic font-normal">
                          (edited)
                        </span>
                      )}
                    </span>
                    <button
                      onClick={() => handleStartEdit(fieldName, displayValue)}
                      className="p-1 text-muted-foreground hover:text-foreground opacity-60 hover:opacity-100 transition-opacity"
                    >
                      <Edit2 className="w-3 h-3" />
                    </button>
                  </>
                )}
              </div>

              {/* Evidence Quote and Jump to Page */}
              {quote && (
                <div
                  onClick={() => setCurrentPage(pageNum)}
                  className="mt-2 p-1.5 rounded bg-muted/60 border border-border/50 text-[11px] text-muted-foreground hover:text-foreground hover:border-primary/40 cursor-pointer transition-colors group"
                >
                  <div className="flex items-center justify-between gap-1 mb-0.5 text-[10px] font-semibold text-primary/80">
                    <span>Evidence (Page {pageNum})</span>
                    <ExternalLink className="w-2.5 h-2.5 opacity-60 group-hover:opacity-100" />
                  </div>
                  <p className="line-clamp-2 italic font-mono text-[10px]">
                    &quot;{quote}&quot;
                  </p>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
