"use client";

import React from "react";
import { ShieldCheck, Server, Database, Clock, Lock, Cpu, X, ExternalLink, CheckCircle2 } from "lucide-react";

interface ArchitectureModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export function ArchitectureModal({ isOpen, onClose }: ArchitectureModalProps) {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-md animate-fade-in">
      <div className="relative w-full max-w-4xl max-h-[90vh] overflow-y-auto rounded-2xl border border-white/10 bg-midnight-900 shadow-2xl p-6 sm:p-8">
        {/* Header */}
        <div className="flex items-center justify-between pb-6 border-b border-white/10">
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-xl bg-amber-500/10 border border-amber-500/20 text-amber-400">
              <ShieldCheck className="w-6 h-6" />
            </div>
            <div>
              <h2 className="text-xl font-bold text-white flex items-center gap-2">
                Veridocs Architecture & Security Model
              </h2>
              <p className="text-xs text-text-muted">
                Zero-trust tenant isolation, hybrid retrieval, and automated lifecycle pruning
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-2 rounded-lg text-text-muted hover:text-white hover:bg-white/5 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 py-6">
          {/* Box 1: Identity & Authentication */}
          <div className="p-4 rounded-xl border border-white/5 bg-white/[0.02]">
            <div className="flex items-center gap-2 text-amber-400 text-sm font-bold mb-2">
              <Lock className="w-4 h-4" />
              <span>1. Trustworthy Identity & Anti-IDOR</span>
            </div>
            <p className="text-xs text-text-secondary leading-relaxed mb-3">
              Eliminated client-selected identities. Operates in dual mode:
            </p>
            <ul className="text-xs text-text-muted space-y-1.5 list-disc pl-4">
              <li><strong className="text-text-primary">Demo Mode:</strong> Ephemeral tokens with fixed identity.</li>
              <li><strong className="text-text-primary">Gateway Mode:</strong> Validates trusted gateway headers (<code className="text-amber-400 text-[11px]">X-Consumer-Custom-ID</code>).</li>
              <li><strong className="text-text-primary">Anti-Spoofing:</strong> Verifies pre-shared secret (<code className="text-amber-400 text-[11px]">X-Gateway-Secret</code>).</li>
              <li><strong className="text-text-primary">Strict IDOR:</strong> Missing or mismatched ownership returns <code className="text-rose-400 text-[11px]">403 Forbidden</code>.</li>
            </ul>
          </div>

          {/* Box 2: Tightly Scoped Administrative Maintenance */}
          <div className="p-4 rounded-xl border border-white/5 bg-white/[0.02]">
            <div className="flex items-center gap-2 text-emerald-400 text-sm font-bold mb-2">
              <ShieldCheck className="w-4 h-4" />
              <span>2. Scoped Admin Maintenance Keys</span>
            </div>
            <p className="text-xs text-text-secondary leading-relaxed mb-3">
              Strict principle of least privilege applied to system credentials:
            </p>
            <ul className="text-xs text-text-muted space-y-1.5 list-disc pl-4">
              <li><strong className="text-text-primary">Scoped Dependency:</strong> <code className="text-emerald-400 text-[11px]">X-Admin-Key</code> is mounted exclusively on <code className="text-emerald-400 text-[11px]">POST /api/admin/cleanup</code>.</li>
              <li><strong className="text-text-primary">Zero User Endpoint Access:</strong> Admin key cannot upload files or query sessions (returns <code className="text-rose-400 text-[11px]">401 Unauthorized</code>).</li>
              <li><strong className="text-text-primary">Strict Bounds:</strong> Pruning age bounded between 1 and 720 hours (30 days).</li>
            </ul>
          </div>

          {/* Box 3: Automated Retention Pruning */}
          <div className="p-4 rounded-xl border border-white/5 bg-white/[0.02]">
            <div className="flex items-center gap-2 text-cyan-400 text-sm font-bold mb-2">
              <Clock className="w-4 h-4" />
              <span>3. Automated Data Lifecycle</span>
            </div>
            <p className="text-xs text-text-secondary leading-relaxed mb-3">
              Background pruning loop running directly inside the FastAPI lifespan:
            </p>
            <ul className="text-xs text-text-muted space-y-1.5 list-disc pl-4">
              <li><strong className="text-text-primary">Periodic Pruning:</strong> Runs every 60 minutes, purging records older than 24h.</li>
              <li><strong className="text-text-primary">Total Purge:</strong> Deletes raw PDF files, FAISS vector indexes, metadata, and chat history.</li>
              <li><strong className="text-text-primary">Path Traversal Safe:</strong> Path resolution guards prevent traversal exploits.</li>
            </ul>
          </div>

          {/* Box 4: Hybrid BM25 + FAISS CPU Search */}
          <div className="p-4 rounded-xl border border-white/5 bg-white/[0.02]">
            <div className="flex items-center gap-2 text-amber-400 text-sm font-bold mb-2">
              <Cpu className="w-4 h-4" />
              <span>4. Sub-Second CPU Hybrid Retrieval</span>
            </div>
            <p className="text-xs text-text-secondary leading-relaxed mb-3">
              Zero-torch lightweight architecture running smoothly on standard CPUs:
            </p>
            <ul className="text-xs text-text-muted space-y-1.5 list-disc pl-4">
              <li><strong className="text-text-primary">FastEmbed ONNX:</strong> ~70MB RAM footprint instead of 2GB+ PyTorch.</li>
              <li><strong className="text-text-primary">Reciprocal Rank Fusion:</strong> Merges BM25 lexical with FAISS semantic scores (k=60).</li>
              <li><strong className="text-text-primary">Numeric Fidelity:</strong> Strict regex check ensuring all asserted numbers exist in context.</li>
            </ul>
          </div>
        </div>

        {/* Deployment Scope Callout */}
        <div className="p-4 rounded-xl border border-amber-500/20 bg-amber-500/5 mb-6">
          <div className="flex items-center gap-2 text-amber-400 text-xs font-bold uppercase tracking-wider mb-1">
            <Server className="w-3.5 h-3.5" />
            <span>Deployment Scope & Multi-Instance Roadmap</span>
          </div>
          <p className="text-xs text-text-secondary leading-relaxed">
            The active backend implementation is scoped to <strong>Single-Instance Standalone Containers / VMs</strong> due to local filesystem storage (<code className="text-amber-400">UPLOAD_DIR</code>) and in-memory session indices. Horizontally auto-scaling across multi-replica Kubernetes clusters requires migrating session state to Redis and vector storage to managed pgvector/Milvus.
          </p>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between pt-4 border-t border-white/10 text-xs text-text-muted">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 text-emerald-400" />
            <span>105 Automated Tests Passing with 83% Coverage</span>
          </div>
          <a
            href="https://github.com/Spidey173/Veridocs"
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1 text-amber-400 hover:text-amber-300 font-medium"
          >
            <span>View GitHub Repository</span>
            <ExternalLink className="w-3.5 h-3.5" />
          </a>
        </div>
      </div>
    </div>
  );
}
