"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { motion } from "framer-motion";
import {
  ZoomIn,
  ZoomOut,
  ChevronLeft,
  ChevronRight,
  Maximize2,
  FileText,
} from "lucide-react";
import { useAppStore } from "@/lib/store";
import { getPdfUrl } from "@/lib/api";

export default function PDFViewer() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const isDragging = useRef(false);
  const startX = useRef(0);
  const startY = useRef(0);
  const scrollLeft = useRef(0);
  const scrollTop = useRef(0);

  const handleMouseDown = (e: React.MouseEvent) => {
    if (e.button !== 0 && e.button !== 2) return;
    const container = containerRef.current;
    if (!container) return;
    isDragging.current = true;
    startX.current = e.pageX - container.offsetLeft;
    startY.current = e.pageY - container.offsetTop;
    scrollLeft.current = container.scrollLeft;
    scrollTop.current = container.scrollTop;
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    if (!isDragging.current) return;
    e.preventDefault();
    const container = containerRef.current;
    if (!container) return;
    const x = e.pageX - container.offsetLeft;
    const y = e.pageY - container.offsetTop;
    const walkX = x - startX.current;
    const walkY = y - startY.current;
    container.scrollLeft = scrollLeft.current - walkX;
    container.scrollTop = scrollTop.current - walkY;
  };

  const handleMouseUpOrLeave = () => {
    isDragging.current = false;
  };

  const handleContextMenu = (e: React.MouseEvent) => {
    e.preventDefault();
  };

  const [pdfDoc, setPdfDoc] = useState<any>(null);
  const [rendering, setRendering] = useState(false);
  const [isLoadingDoc, setIsLoadingDoc] = useState(false);
  const [pdfLib, setPdfLib] = useState<any>(null);
  const renderTaskRef = useRef<any>(null);

  const {
    sessionId,
    files,
    activeDocumentName,
    currentPage,
    totalPages,
    pdfScale,
    highlightedCitation,
    localFileUrls,
    setCurrentPage,
    setTotalPages,
    setPdfScale,
  } = useAppStore();

  // Keep track of scale in ref for high-performance event listeners
  const scaleRef = useRef(pdfScale);
  useEffect(() => {
    scaleRef.current = pdfScale;
  }, [pdfScale]);

  // Trackpad pinch-to-zoom listener
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const handleWheel = (e: WheelEvent) => {
      if (e.ctrlKey) {
        e.preventDefault();
        const delta = -e.deltaY * 0.005;
        const nextScale = Math.min(Math.max(scaleRef.current + delta, 0.5), 1.5);
        setPdfScale(nextScale);
      }
    };

    container.addEventListener("wheel", handleWheel, { passive: false });
    return () => {
      container.removeEventListener("wheel", handleWheel);
    };
  }, [setPdfScale]);

  // Touch screen pinch-to-zoom
  const lastTouchDistance = useRef<number | null>(null);

  const handleTouchStart = (e: React.TouchEvent) => {
    if (e.touches.length === 2) {
      const dist = Math.hypot(
        e.touches[0].pageX - e.touches[1].pageX,
        e.touches[0].pageY - e.touches[1].pageY
      );
      lastTouchDistance.current = dist;
    }
  };

  const handleTouchMove = (e: React.TouchEvent) => {
    if (e.touches.length === 2 && lastTouchDistance.current !== null) {
      e.preventDefault();
      const dist = Math.hypot(
        e.touches[0].pageX - e.touches[1].pageX,
        e.touches[0].pageY - e.touches[1].pageY
      );
      const factor = dist / lastTouchDistance.current;
      const delta = (factor - 1) * 0.15;
      const nextScale = Math.min(Math.max(scaleRef.current + delta, 0.5), 1.5);
      setPdfScale(nextScale);
      lastTouchDistance.current = dist;
    }
  };

  const handleTouchEnd = () => {
    lastTouchDistance.current = null;
  };

  // Load PDF.js library eagerly
  useEffect(() => {
    async function loadPdfJs() {
      const pdfjsLib = await import("pdfjs-dist");
      pdfjsLib.GlobalWorkerOptions.workerSrc = `/pdf.worker.min.mjs`;
      setPdfLib(pdfjsLib);
    }
    loadPdfJs();
  }, []);

  // Load PDF document dynamically when active document changes
  // Prioritizes instant local memory Blob URLs (0ms) over remote network fetches
  useEffect(() => {
    if (sessionId === "demo-session") {
      setPdfDoc(null);
      setTotalPages(3);
      setIsLoadingDoc(false);
      return;
    }

    if (!pdfLib || !sessionId || !activeDocumentName) return;

    let isMounted = true;
    setIsLoadingDoc(true);

    async function loadPdf() {
      try {
        const localUrl = localFileUrls ? localFileUrls[activeDocumentName!] : undefined;
        const url = localUrl || getPdfUrl(sessionId!, activeDocumentName!);
        const doc = await pdfLib.getDocument({ url }).promise;
        if (!isMounted) return;
        setPdfDoc(doc);
        setTotalPages(doc.numPages);
      } catch (err) {
        console.error("Failed to load PDF:", err);
      } finally {
        if (isMounted) setIsLoadingDoc(false);
      }
    }

    loadPdf();

    return () => {
      isMounted = false;
    };
  }, [pdfLib, sessionId, activeDocumentName, localFileUrls, files, setTotalPages]);

  // Render current page with seamless render cancellation for rapid page switching
  const renderPage = useCallback(async () => {
    if (!pdfDoc || !canvasRef.current) return;

    // Cleanly cancel previous rendering task if another page or zoom was selected rapidly
    if (renderTaskRef.current) {
      try {
        renderTaskRef.current.cancel();
      } catch {}
      renderTaskRef.current = null;
    }

    setRendering(true);

    try {
      const page = await pdfDoc.getPage(currentPage);
      const viewport = page.getViewport({ scale: pdfScale * 1.5 });
      const canvas = canvasRef.current;
      const context = canvas.getContext("2d");

      if (!context) return;

      canvas.height = viewport.height;
      canvas.width = viewport.width;

      const renderTask = page.render({
        canvasContext: context,
        viewport,
      });
      renderTaskRef.current = renderTask;

      await renderTask.promise;
    } catch (err: any) {
      if (err?.name !== "RenderingCancelledException") {
        console.error("Failed to render page:", err);
      }
    } finally {
      renderTaskRef.current = null;
      setRendering(false);
    }
  }, [pdfDoc, currentPage, pdfScale]);

  useEffect(() => {
    renderPage();
  }, [pdfDoc, currentPage, pdfScale, renderPage]);

  // Navigate on citation highlight with smooth auto-scroll
  useEffect(() => {
    if (highlightedCitation) {
      setCurrentPage(highlightedCitation.page);
      if (containerRef.current) {
        containerRef.current.scrollTo({ top: 0, behavior: "smooth" });
      }
    }
  }, [highlightedCitation, setCurrentPage]);

  const goToPage = (page: number) => {
    if (page >= 1 && page <= totalPages) {
      setCurrentPage(page);
    }
  };

  const zoomIn = () => setPdfScale(Math.min(pdfScale + 0.1, 1.5));
  const zoomOut = () => setPdfScale(Math.max(pdfScale - 0.1, 0.5));
  const fitWidth = () => setPdfScale(1.0);

  if (!sessionId) return null;

  if (!activeDocumentName) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center text-center p-6 bg-midnight-950">
        <FileText className="w-10 h-10 text-text-muted mb-3 opacity-40 animate-pulse" />
        <p className="text-sm text-text-muted font-medium">
          Select a document from the Left Sidebar to begin reading
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full bg-midnight-950">
      {/* Toolbar */}
      <div className="flex items-center justify-between px-4 py-2 border-b border-white/6 bg-surface-primary/80 backdrop-blur-sm">
        <div className="flex items-center gap-1">
          <button
            onClick={() => goToPage(currentPage - 1)}
            disabled={currentPage <= 1}
            className="p-1.5 rounded-lg hover:bg-white/8 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
          >
            <ChevronLeft className="w-4 h-4" />
          </button>

          <div className="flex items-center gap-1.5 px-2">
            <input
              type="number"
              value={currentPage}
              onChange={(e) => goToPage(parseInt(e.target.value) || 1)}
              className="w-10 text-center text-xs bg-white/5 border border-white/10 rounded px-1 py-0.5 focus:outline-none focus:border-accent-primary"
              min={1}
              max={totalPages}
            />
            <span className="text-xs text-text-muted">/ {totalPages}</span>
          </div>

          <button
            onClick={() => goToPage(currentPage + 1)}
            disabled={currentPage >= totalPages}
            className="p-1.5 rounded-lg hover:bg-white/8 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
          >
            <ChevronRight className="w-4 h-4" />
          </button>
        </div>

        <div className="flex items-center gap-1">
          <button
            onClick={zoomOut}
            className="p-1.5 rounded-lg hover:bg-white/8 transition-colors"
            title="Zoom out"
          >
            <ZoomOut className="w-4 h-4" />
          </button>

          <span className="text-xs text-text-muted px-1 min-w-[3rem] text-center">
            {Math.round(pdfScale * 100)}%
          </span>

          <button
            onClick={zoomIn}
            className="p-1.5 rounded-lg hover:bg-white/8 transition-colors"
            title="Zoom in"
          >
            <ZoomIn className="w-4 h-4" />
          </button>

          <div className="w-px h-4 bg-white/10 mx-1" />

          <button
            onClick={fitWidth}
            className="p-1.5 rounded-lg hover:bg-white/8 transition-colors"
            title="Fit width"
          >
            <Maximize2 className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* PDF Canvas or Interactive Demo Document */}
      <div
        ref={containerRef}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUpOrLeave}
        onMouseLeave={handleMouseUpOrLeave}
        onContextMenu={handleContextMenu}
        onTouchStart={handleTouchStart}
        onTouchMove={handleTouchMove}
        onTouchEnd={handleTouchEnd}
        className="flex-1 overflow-auto flex p-4 cursor-grab active:cursor-grabbing select-none"
      >
        <div className="relative m-auto">
          {pdfDoc ? (
            <>
              <canvas
                ref={canvasRef}
                className="shadow-2xl rounded-sm"
                style={{ background: "white" }}
              />

              {/* Citation highlight overlay with golden flash & breadcrumb */}
              <AnimatePresence>
                {highlightedCitation && highlightedCitation.page === currentPage && (
                  <motion.div
                    initial={{ opacity: 0, scale: 0.99 }}
                    animate={{ opacity: 1, scale: 1 }}
                    exit={{ opacity: 0 }}
                    transition={{ duration: 0.2 }}
                    className="absolute inset-0 pointer-events-none rounded ring-4 ring-amber-400/90 shadow-[0_0_50px_rgba(251,191,36,0.3)]"
                  >
                    <div className="absolute top-3 left-3 right-3 p-2.5 rounded-lg bg-midnight-950/90 border border-amber-400/50 backdrop-blur-md text-amber-200 text-xs font-medium flex items-center gap-2 shadow-xl">
                      <span className="w-2 h-2 rounded-full bg-amber-400 animate-ping" />
                      <span className="font-semibold text-amber-300">Cited on Page {currentPage}:</span>
                      <span className="italic truncate">&quot;{highlightedCitation.highlighted_text}&quot;</span>
                    </div>
                    <div className="absolute top-[14%] left-[6%] right-[6%] h-[24%] bg-amber-400/15 border-2 border-amber-400/70 rounded-md animate-pulse" />
                  </motion.div>
                )}
              </AnimatePresence>

              {rendering && (
                <div className="absolute inset-0 flex items-center justify-center bg-midnight-950/50">
                  <div className="w-6 h-6 border-2 border-accent-primary/30 border-t-accent-primary rounded-full animate-spin" />
                </div>
              )}
            </>
          ) : isLoadingDoc && sessionId !== "demo-session" ? (
            <div
              style={{
                width: `${560 * pdfScale}px`,
                minHeight: `${780 * pdfScale}px`,
              }}
              className="bg-midnight-900/60 border border-white/10 rounded-2xl flex flex-col items-center justify-center p-8 backdrop-blur-xl shadow-2xl select-none"
            >
              <div className="w-12 h-12 rounded-2xl bg-accent-primary/10 border border-accent-primary/20 flex items-center justify-center mb-4">
                <FileText className="w-6 h-6 text-accent-primary animate-pulse" />
              </div>
              <p className="text-sm font-semibold text-text-primary mb-1">
                Loading {activeDocumentName}...
              </p>
              <p className="text-xs text-text-muted mb-4">
                Preparing pages and citations
              </p>
              <div className="w-48 h-1.5 bg-white/10 rounded-full overflow-hidden">
                <div className="h-full bg-gradient-to-r from-accent-primary to-amber-500 animate-[shimmer_1.5s_infinite] w-full" />
              </div>
            </div>
          ) : (
            <div
              style={{
                width: `${560 * pdfScale}px`,
                minHeight: `${780 * pdfScale}px`,
                fontSize: `${13 * pdfScale}px`,
              }}
              className="bg-white text-gray-900 shadow-2xl rounded-md p-8 sm:p-12 transition-all border border-gray-200 select-text"
            >
              <div className="border-b border-gray-200 pb-4 mb-6">
                <div className="flex items-center justify-between text-xs text-gray-500 font-mono mb-2">
                  <span>VERIDOCS TECHNICAL WHITEPAPER</span>
                  <span>PAGE {currentPage} OF 3</span>
                </div>
                <h2 className="text-xl font-bold text-gray-900 tracking-tight">
                  {currentPage === 1 && "1. Hybrid Retrieval Engine (BM25 + FAISS Dense Search)"}
                  {currentPage === 2 && "2. Neural Re-Ranking & Score Normalization"}
                  {currentPage === 3 && "3. Hallucination Mitigation & Auditable Citations"}
                </h2>
              </div>

              <div className="space-y-4 leading-relaxed text-gray-700">
                {currentPage === 1 && (
                  <>
                    <p className={`p-2 rounded transition-colors ${highlightedCitation?.page === 1 ? "bg-amber-100 ring-2 ring-amber-400 font-medium text-gray-900" : ""}`}>
                      Veridocs implements a two-stage hybrid retrieval architecture fusing BM25 lexical indexing with dense semantic vector representations.
                    </p>
                    <p>
                      BM25 captures exact lexical entities, codes, and numerical values, while sentence embeddings capture high-level semantic intent. By indexing both sparse inverted token indexes and compressed FAISS vector clusters, the candidate generator achieves high recall across technical terminology and conversational queries.
                    </p>
                    <p>
                      Reciprocal Rank Fusion ensures neither lexical bias nor dense vector drift dominates candidate selection. Each document chunk is segmented using sliding recursive windows with semantic boundary preservation.
                    </p>
                  </>
                )}

                {currentPage === 2 && (
                  <>
                    <p className={`p-2 rounded transition-colors ${highlightedCitation?.page === 2 ? "bg-amber-100 ring-2 ring-amber-400 font-medium text-gray-900" : ""}`}>
                      A deep cross-encoder calculates full token cross-attention across the query and candidate passages, filtering out false positives.
                    </p>
                    <p>
                      The cross-encoder evaluates bidirectional token interaction, eliminating semantic mismatch errors common in cosine-similarity search. While bi-encoders map documents to fixed embeddings independently, joint sequence modeling reveals negation, conditional modifiers, and document subtleties.
                    </p>
                    <p>
                      Full joint cross-attention improves top-3 retrieval accuracy by up to 38% compared to single-stage vector retrieval, significantly reducing context noise fed into the generation model.
                    </p>
                  </>
                )}

                {currentPage === 3 && (
                  <>
                    <p className={`p-2 rounded transition-colors ${highlightedCitation?.page === 3 ? "bg-amber-100 ring-2 ring-amber-400 font-medium text-gray-900" : ""}`}>
                      Factual alignment is verified post-generation by computing premise-hypothesis entailment scores against source passages.
                    </p>
                    <p>
                      Every extracted claim must map directly to an attributed chunk span; non-conforming tokens are rejected. A calibrated confidence score is generated alongside each answer, warning users when a claim falls below factual confidence thresholds.
                    </p>
                    <p>
                      All outputs are fully auditable and link directly to source documents and coordinate coordinates. This ensures mission-critical enterprise workflows maintain regulatory compliance and provable data provenance.
                    </p>
                  </>
                )}
              </div>

              <div className="mt-12 pt-6 border-t border-gray-100 flex items-center justify-between text-xs text-gray-400">
                <span>Veridocs Document Verification Platform</span>
                <span>Confidential & Proprietary</span>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Page Thumbnails (bottom strip) */}
      {totalPages > 0 && totalPages <= 50 && (
        <div className="flex items-center gap-1 px-4 py-2 border-t border-white/6 overflow-x-auto bg-surface-primary/80">
          {Array.from({ length: Math.min(totalPages, 20) }, (_, i) => (
            <button
              key={i + 1}
              onClick={() => goToPage(i + 1)}
              className={`
                min-w-[2rem] h-7 rounded text-xs font-medium transition-all
                ${
                  currentPage === i + 1
                    ? "bg-accent-primary text-midnight-950 font-bold"
                    : "bg-white/5 text-text-muted hover:bg-white/10 hover:text-text-secondary"
                }
              `}
            >
              {i + 1}
            </button>
          ))}
          {totalPages > 20 && (
            <span className="text-xs text-text-muted px-2">
              +{totalPages - 20} more
            </span>
          )}
        </div>
      )}
    </div>
  );
}

function AnimatePresence({ children }: { children: React.ReactNode }) {
  // Simple wrapper — actual AnimatePresence from framer-motion
  // is used inline above; this is for the overlay only
  return <>{children}</>;
}
