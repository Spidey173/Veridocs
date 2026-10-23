"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  ZoomIn,
  ZoomOut,
  ChevronLeft,
  ChevronRight,
  Maximize2,
  FileText,
  AlertOctagon,
  AlertTriangle,
  Target,
} from "lucide-react";
import type { PDFDocumentProxy, PDFPageProxy, RenderTask, PageViewport } from "pdfjs-dist";
import { useAppStore } from "@/lib/store";
import { fetchPdfBlobUrl } from "@/lib/api";

interface BoundingBoxRect {
  x: number;
  y: number;
  width: number;
  height: number;
}

export default function PDFViewer() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const isDragging = useRef(false);
  const startX = useRef(0);
  const startY = useRef(0);
  const scrollLeft = useRef(0);
  const scrollTop = useRef(0);

  const [pdfDoc, setPdfDoc] = useState<PDFDocumentProxy | null>(null);
  const [rendering, setRendering] = useState(false);
  const [isLoadingDoc, setIsLoadingDoc] = useState(false);
  const [pdfLib, setPdfLib] = useState<typeof import("pdfjs-dist") | null>(null);
  const [boundingBoxes, setBoundingBoxes] = useState<BoundingBoxRect[]>([]);
  const [highlightAnchor, setHighlightAnchor] = useState<{ top: number; left: number } | null>(null);

  const renderTaskRef = useRef<RenderTask | null>(null);
  const currentPageObjRef = useRef<PDFPageProxy | null>(null);
  const currentViewportRef = useRef<PageViewport | null>(null);

  const {
    sessionId,
    files,
    activeDocumentName,
    currentPage,
    totalPages,
    pdfScale,
    highlightedCitation,
    activeVisualHighlight,
    localFileUrls,
    setCurrentPage,
    setTotalPages,
    setPdfScale,
  } = useAppStore();

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
  useEffect(() => {
    if (sessionId === "demo-session") {
      setPdfDoc(null);
      setTotalPages(3);
      setIsLoadingDoc(false);
      return;
    }

    if (!pdfLib || !sessionId || !activeDocumentName) return;

    const currentLib = pdfLib;
    let isMounted = true;
    setIsLoadingDoc(true);

    let createdBlobUrl: string | null = null;

    async function loadPdf() {
      try {
        let url = localFileUrls ? localFileUrls[activeDocumentName!] : undefined;
        if (!url) {
          url = await fetchPdfBlobUrl(sessionId!, activeDocumentName!);
          createdBlobUrl = url;
        }
        const doc = await currentLib.getDocument({ url }).promise;
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
      if (createdBlobUrl) {
        URL.revokeObjectURL(createdBlobUrl);
      }
    };
  }, [pdfLib, sessionId, activeDocumentName, localFileUrls, files, setTotalPages]);

  // Compute text bounding boxes using PDF.js text layer coordinates
  const computeBoundingBoxes = useCallback(
    async (pageObj: PDFPageProxy, viewport: PageViewport, snippet: string) => {
      if (!pageObj || !snippet) {
        setBoundingBoxes([]);
        setHighlightAnchor(null);
        return;
      }

      try {
        const textContent = await pageObj.getTextContent();
        const items = textContent.items;
        if (!items || items.length === 0) return;

        const cleanSnippet = snippet.replace(/\s+/g, " ").trim().toLowerCase();

        // Build full page string with item ranges
        let fullPageText = "";
        const itemRanges: Array<{
          start: number;
          end: number;
          item: { str?: string; transform?: number[]; width?: number; height?: number };
        }> = [];

        for (const rawItem of items) {
          const it = rawItem as { str?: string; transform?: number[]; width?: number; height?: number };
          if (typeof it.str !== "string") continue;
          const start = fullPageText.length;
          fullPageText += it.str + " ";
          const end = fullPageText.length;
          itemRanges.push({ start, end, item: it });
        }

        const pageLower = fullPageText.toLowerCase();

        // 1. Direct or partial phrase search
        let matchStart = pageLower.indexOf(cleanSnippet);
        let matchEnd = -1;

        if (matchStart !== -1) {
          matchEnd = matchStart + cleanSnippet.length;
        } else {
          // Fallback to first 4-6 key words
          const words = cleanSnippet.split(" ").filter((w) => w.length > 3);
          if (words.length >= 3) {
            const prefix = words.slice(0, 4).join(" ");
            const pIdx = pageLower.indexOf(prefix);
            if (pIdx !== -1) {
              matchStart = pIdx;
              matchEnd = pIdx + prefix.length;
            }
          }
        }

        const boxes: BoundingBoxRect[] = [];

        if (matchStart !== -1 && matchEnd !== -1) {
          for (const range of itemRanges) {
            if (range.end > matchStart && range.start < matchEnd) {
              const it = range.item;
              if (it.transform) {
                const tx = it.transform[4];
                const ty = it.transform[5];
                const w = it.width || 20;
                const h = it.height || 12;

                const rect = viewport.convertToViewportRectangle([tx, ty, tx + w, ty + h]);
                const minX = Math.min(rect[0], rect[2]);
                const maxX = Math.max(rect[0], rect[2]);
                const minY = Math.min(rect[1], rect[3]);
                const maxY = Math.max(rect[1], rect[3]);

                boxes.push({
                  x: minX,
                  y: minY,
                  width: Math.max(maxX - minX, 10),
                  height: Math.max(maxY - minY, 8),
                });
              }
            }
          }
        } else {
          // Token fuzzy fallback (numbers and major keywords)
          const keywords = cleanSnippet.split(" ").filter((w) => w.length >= 4);
          for (const range of itemRanges) {
            const it = range.item;
            const strLower = (it.str || "").toLowerCase();
            if (keywords.some((kw) => strLower.includes(kw))) {
              if (it.transform) {
                const tx = it.transform[4];
                const ty = it.transform[5];
                const w = it.width || 20;
                const h = it.height || 12;
                const rect = viewport.convertToViewportRectangle([tx, ty, tx + w, ty + h]);
                boxes.push({
                  x: Math.min(rect[0], rect[2]),
                  y: Math.min(rect[1], rect[3]),
                  width: Math.max(Math.abs(rect[2] - rect[0]), 10),
                  height: Math.max(Math.abs(rect[3] - rect[1]), 8),
                });
              }
            }
          }
        }

        if (boxes.length > 0) {
          setBoundingBoxes(boxes);
          const topMin = Math.min(...boxes.map((b) => b.y));
          const leftMin = Math.min(...boxes.map((b) => b.x));
          setHighlightAnchor({ top: topMin, left: leftMin });

          if (containerRef.current) {
            containerRef.current.scrollTo({
              top: Math.max(0, topMin - 100),
              behavior: "smooth",
            });
          }
        } else {
          setBoundingBoxes([]);
          setHighlightAnchor(null);
        }
      } catch (err) {
        console.error("Bounding box computation error:", err);
      }
    },
    []
  );

  // Render current page
  const renderPage = useCallback(async () => {
    if (!pdfDoc || !canvasRef.current) return;

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

      currentPageObjRef.current = page;
      currentViewportRef.current = viewport;

      const renderTask = page.render({
        canvasContext: context,
        viewport,
        canvas,
      });
      renderTaskRef.current = renderTask;

      await renderTask.promise;

      // Re-calculate visual bounding boxes after rendering
      const targetSnippet =
        activeVisualHighlight?.snippet || highlightedCitation?.highlighted_text || "";
      const targetPage =
        activeVisualHighlight?.page || highlightedCitation?.page;

      if (targetSnippet && targetPage === currentPage) {
        computeBoundingBoxes(page, viewport, targetSnippet);
      } else {
        setBoundingBoxes([]);
        setHighlightAnchor(null);
      }
    } catch (err: unknown) {
      if ((err as Error)?.name !== "RenderingCancelledException") {
        console.error("Failed to render page:", err);
      }
    } finally {
      renderTaskRef.current = null;
      setRendering(false);
    }
  }, [pdfDoc, currentPage, pdfScale, activeVisualHighlight, highlightedCitation, computeBoundingBoxes]);

  useEffect(() => {
    renderPage();
  }, [pdfDoc, currentPage, pdfScale, renderPage]);

  // Trigger bounding box recomputation when active highlight changes
  useEffect(() => {
    const targetSnippet =
      activeVisualHighlight?.snippet || highlightedCitation?.highlighted_text || "";
    const targetPage =
      activeVisualHighlight?.page || highlightedCitation?.page;

    if (targetSnippet && targetPage === currentPage && currentPageObjRef.current && currentViewportRef.current) {
      computeBoundingBoxes(currentPageObjRef.current, currentViewportRef.current, targetSnippet);
    }
  }, [activeVisualHighlight, highlightedCitation, currentPage, computeBoundingBoxes]);

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

  // Active target highlight details
  const activeSnippet =
    activeVisualHighlight?.snippet || highlightedCitation?.highlighted_text || "";
  const activeSeverity = activeVisualHighlight?.severity || "citation";
  const activeLabel =
    activeVisualHighlight?.label ||
    (highlightedCitation ? `Cited Source [Page ${highlightedCitation.page}]` : "");

  return (
    <div className="flex flex-col h-full bg-midnight-950 select-none">
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

        {/* Visual Grounding Status Pill */}
        {activeSnippet && (
          <div className="hidden sm:flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-white/5 border border-white/10 text-xs">
            <Target className="w-3.5 h-3.5 text-accent-primary animate-pulse" />
            <span className="text-[11px] font-semibold text-text-secondary">
              Pixel Grounding Active
            </span>
          </div>
        )}

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

              {/* Pixel-Level Bounding Box Highlights & Floating Badge */}
              <AnimatePresence>
                {activeSnippet && (
                  <>
                    {/* Anchored Floating Header Badge */}
                    {highlightAnchor && (
                      <motion.div
                        initial={{ opacity: 0, y: -8, scale: 0.95 }}
                        animate={{ opacity: 1, y: 0, scale: 1 }}
                        exit={{ opacity: 0 }}
                        style={{
                          position: "absolute",
                          top: `${Math.max(8, highlightAnchor.top - 46)}px`,
                          left: `${Math.max(8, highlightAnchor.left)}px`,
                          zIndex: 40,
                        }}
                        className={`pointer-events-none flex items-center gap-2 px-3 py-1.5 rounded-lg border shadow-2xl backdrop-blur-md text-xs font-semibold ${
                          activeSeverity === "critical"
                            ? "bg-midnight-950/95 border-rose-500/70 text-rose-200 shadow-rose-500/20"
                            : activeSeverity === "warning"
                            ? "bg-midnight-950/95 border-amber-500/70 text-amber-200 shadow-amber-500/20"
                            : "bg-midnight-950/95 border-amber-400/70 text-amber-300 shadow-amber-400/20"
                        }`}
                      >
                        <span
                          className={`w-2 h-2 rounded-full animate-ping ${
                            activeSeverity === "critical"
                              ? "bg-rose-500"
                              : activeSeverity === "warning"
                              ? "bg-amber-400"
                              : "bg-amber-400"
                          }`}
                        />
                        <span className="font-bold">{activeLabel}:</span>
                        <span className="italic truncate max-w-[260px] opacity-90">
                          &quot;{activeSnippet}&quot;
                        </span>
                      </motion.div>
                    )}

                    {/* Exact Bounding Boxes for Each Line/Word */}
                    {boundingBoxes.map((box, i) => (
                      <motion.div
                        key={`bbox-${i}`}
                        initial={{ opacity: 0, scale: 0.97 }}
                        animate={{ opacity: 1, scale: 1 }}
                        exit={{ opacity: 0 }}
                        style={{
                          position: "absolute",
                          left: `${box.x}px`,
                          top: `${box.y}px`,
                          width: `${box.width}px`,
                          height: `${box.height}px`,
                          zIndex: 35,
                        }}
                        className={`pointer-events-none rounded transition-all ${
                          activeSeverity === "critical"
                            ? "bg-rose-500/25 border-2 border-rose-500/90 shadow-[0_0_15px_rgba(244,63,94,0.4)] animate-pulse"
                            : activeSeverity === "warning"
                            ? "bg-amber-400/25 border-2 border-amber-400/90 shadow-[0_0_15px_rgba(251,191,36,0.4)] animate-pulse"
                            : "bg-amber-400/25 border-2 border-amber-400/90 shadow-[0_0_15px_rgba(251,191,36,0.4)] animate-pulse"
                        }`}
                      />
                    ))}

                    {/* Fallback if boundingBoxes calculation yields 0 text items */}
                    {boundingBoxes.length === 0 && (
                      <motion.div
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0 }}
                        className="absolute inset-0 pointer-events-none rounded ring-4 ring-amber-400/80 shadow-[0_0_40px_rgba(251,191,36,0.2)]"
                      >
                        <div className="absolute top-3 left-3 right-3 p-2.5 rounded-lg bg-midnight-950/90 border border-amber-400/50 backdrop-blur-md text-amber-200 text-xs font-medium flex items-center gap-2 shadow-xl">
                          <span className="w-2 h-2 rounded-full bg-amber-400 animate-ping" />
                          <span className="font-semibold">{activeLabel}:</span>
                          <span className="italic truncate">&quot;{activeSnippet}&quot;</span>
                        </div>
                      </motion.div>
                    )}
                  </>
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
              <p className="text-xs text-text-muted mb-4">Preparing pages and citations</p>
              <div className="w-48 h-1.5 bg-white/10 rounded-full overflow-hidden">
                <div className="h-full bg-gradient-to-r from-accent-primary to-amber-500 animate-[shimmer_1.5s_infinite] w-full" />
              </div>
            </div>
          ) : (
            /* Interactive Demo Document with Pixel-Level Bounding Box Simulation */
            <div
              style={{
                width: `${580 * pdfScale}px`,
                minHeight: `${800 * pdfScale}px`,
                fontSize: `${13 * pdfScale}px`,
              }}
              className="bg-white text-gray-900 shadow-2xl rounded-md p-8 sm:p-12 transition-all border border-gray-200 relative select-text"
            >
              <div className="border-b border-gray-200 pb-4 mb-6">
                <div className="flex items-center justify-between text-xs text-gray-500 font-mono mb-2">
                  <span className="uppercase font-bold tracking-wider">
                    {activeDocumentName.replace(".pdf", "").replace(/_/g, " ")}
                  </span>
                  <span>PAGE {currentPage} OF 3</span>
                </div>
                <h2 className="text-lg font-bold text-gray-900 tracking-tight">
                  {activeDocumentName.includes("2024")
                    ? "MASTER SAAS & SERVICES AGREEMENT (2024 BASELINE)"
                    : activeDocumentName.includes("2025")
                    ? "AMENDED MASTER SERVICES AGREEMENT (2025 REVISION)"
                    : "VERIDOCS TECHNICAL ARCHITECTURE & BENCHMARK REPORT"}
                </h2>
              </div>

              {/* Document Body Content based on document & page */}
              <div className="space-y-4 leading-relaxed text-gray-700">
                {activeDocumentName.includes("2024") ? (
                  <>
                    {currentPage === 1 && (
                      <div className="space-y-3">
                        <h3 className="font-bold text-gray-900">Section 4. Financial & Payment Terms</h3>
                        <div
                          className={`p-3 rounded-lg transition-all relative ${
                            activeSnippet.includes("30 days")
                              ? "bg-rose-50 border-2 border-rose-500 shadow-[0_0_25px_rgba(244,63,94,0.3)] animate-pulse"
                              : "bg-gray-50 border border-gray-200"
                          }`}
                        >
                          {activeSnippet.includes("30 days") && (
                            <div className="absolute -top-3 left-3 px-2 py-0.5 rounded bg-rose-600 text-white text-[10px] font-mono font-bold shadow-lg flex items-center gap-1">
                              <AlertOctagon className="w-3 h-3" />
                              ⚖️ Contradiction Point: Net 30 with 1.5% late fee
                            </div>
                          )}
                          <p className="font-semibold text-gray-900">4.1 Payment Terms</p>
                          <p>
                            Invoices are payable within 30 days of receipt. Overdue balances shall accrue interest at 1.5% per month.
                          </p>
                        </div>
                        <p className="text-gray-600">
                          4.2 Taxes. Customer is responsible for all applicable sales, use, and excise taxes resulting from subscription services.
                        </p>
                      </div>
                    )}

                    {currentPage === 2 && (
                      <div className="space-y-3">
                        <h3 className="font-bold text-gray-900">Section 8. Limitation of Liability</h3>
                        <div
                          className={`p-3 rounded-lg transition-all relative ${
                            activeSnippet.includes("1,000,000")
                              ? "bg-rose-50 border-2 border-rose-500 shadow-[0_0_25px_rgba(244,63,94,0.3)] animate-pulse"
                              : "bg-gray-50 border border-gray-200"
                          }`}
                        >
                          {activeSnippet.includes("1,000,000") && (
                            <div className="absolute -top-3 left-3 px-2 py-0.5 rounded bg-rose-600 text-white text-[10px] font-mono font-bold shadow-lg flex items-center gap-1">
                              <AlertOctagon className="w-3 h-3" />
                              ⚖️ Contradiction Point: $1M Liability Cap
                            </div>
                          )}
                          <p className="font-semibold text-gray-900">8.1 Liability Cap</p>
                          <p>
                            The total aggregate liability of either party shall not exceed $1,000,000 under any circumstances.
                          </p>
                        </div>
                      </div>
                    )}

                    {currentPage === 3 && (
                      <div className="space-y-3">
                        <h3 className="font-bold text-gray-900">Schedule B: Service Level Agreement (SLA)</h3>
                        <div
                          className={`p-3 rounded-lg transition-all relative ${
                            activeSnippet.includes("99.95%")
                              ? "bg-amber-50 border-2 border-amber-500 shadow-[0_0_25px_rgba(245,158,11,0.3)] animate-pulse"
                              : "bg-gray-50 border border-gray-200"
                          }`}
                        >
                          {activeSnippet.includes("99.95%") && (
                            <div className="absolute -top-3 left-3 px-2 py-0.5 rounded bg-amber-500 text-white text-[10px] font-mono font-bold shadow-lg flex items-center gap-1">
                              <AlertTriangle className="w-3 h-3" />
                              ⚖️ Modification: 99.95% Availability
                            </div>
                          )}
                          <p className="font-semibold text-gray-900">B.1 Availability Commitment</p>
                          <p>
                            Provider guarantees monthly service availability of at least 99.95% excluding scheduled maintenance windows.
                          </p>
                        </div>
                      </div>
                    )}
                  </>
                ) : activeDocumentName.includes("2025") ? (
                  <>
                    {currentPage === 1 && (
                      <div className="space-y-3">
                        <h3 className="font-bold text-gray-900">Section 4. Settlement Schedule</h3>
                        <div
                          className={`p-3 rounded-lg transition-all relative ${
                            activeSnippet.includes("60 calendar days")
                              ? "bg-rose-50 border-2 border-rose-500 shadow-[0_0_25px_rgba(244,63,94,0.3)] animate-pulse"
                              : "bg-gray-50 border border-gray-200"
                          }`}
                        >
                          {activeSnippet.includes("60 calendar days") && (
                            <div className="absolute -top-3 left-3 px-2 py-0.5 rounded bg-rose-600 text-white text-[10px] font-mono font-bold shadow-lg flex items-center gap-1">
                              <AlertOctagon className="w-3 h-3" />
                              ⚖️ Contradiction Point: 60 days with 0% penalty
                            </div>
                          )}
                          <p className="font-semibold text-gray-900">4.1 Settlement</p>
                          <p>
                            Customer shall remit payment within 60 calendar days from invoice date without late fees or interest charges.
                          </p>
                        </div>
                      </div>
                    )}

                    {currentPage === 2 && (
                      <div className="space-y-3">
                        <h3 className="font-bold text-gray-900">Section 8. Damages & Indemnity</h3>
                        <div
                          className={`p-3 rounded-lg transition-all relative ${
                            activeSnippet.includes("250,000")
                              ? "bg-rose-50 border-2 border-rose-500 shadow-[0_0_25px_rgba(244,63,94,0.3)] animate-pulse"
                              : "bg-gray-50 border border-gray-200"
                          }`}
                        >
                          {activeSnippet.includes("250,000") && (
                            <div className="absolute -top-3 left-3 px-2 py-0.5 rounded bg-rose-600 text-white text-[10px] font-mono font-bold shadow-lg flex items-center gap-1">
                              <AlertOctagon className="w-3 h-3" />
                              ⚖️ Contradiction Point: Reduced to $250k
                            </div>
                          )}
                          <p className="font-semibold text-gray-900">8.1 Damages Cap</p>
                          <p>
                            Maximum cumulative liability arising out of this agreement is capped at $250,000 or the fees paid in the prior 3 months.
                          </p>
                        </div>
                      </div>
                    )}

                    {currentPage === 3 && (
                      <div className="space-y-3">
                        <h3 className="font-bold text-gray-900">Schedule B: Availability Target</h3>
                        <div
                          className={`p-3 rounded-lg transition-all relative ${
                            activeSnippet.includes("99.5%")
                              ? "bg-amber-50 border-2 border-amber-500 shadow-[0_0_25px_rgba(245,158,11,0.3)] animate-pulse"
                              : "bg-gray-50 border border-gray-200"
                          }`}
                        >
                          {activeSnippet.includes("99.5%") && (
                            <div className="absolute -top-3 left-3 px-2 py-0.5 rounded bg-amber-500 text-white text-[10px] font-mono font-bold shadow-lg flex items-center gap-1">
                              <AlertTriangle className="w-3 h-3" />
                              ⚖️ Downgraded to 99.5% Target
                            </div>
                          )}
                          <p className="font-semibold text-gray-900">B.1 Availability Commitment</p>
                          <p>
                            Service availability commitment is target 99.5% with service credits capped at 5% of monthly recurring revenue.
                          </p>
                        </div>
                      </div>
                    )}
                  </>
                ) : (
                  /* Technical Whitepaper default */
                  <>
                    {currentPage === 1 && (
                      <div className="space-y-3">
                        <div
                          className={`p-3 rounded-lg transition-all relative ${
                            activeSnippet.includes("two-stage hybrid")
                              ? "bg-amber-50 border-2 border-amber-400 shadow-[0_0_25px_rgba(251,191,36,0.3)] animate-pulse"
                              : ""
                          }`}
                        >
                          {activeSnippet.includes("two-stage hybrid") && (
                            <div className="absolute -top-3 left-3 px-2 py-0.5 rounded bg-amber-500 text-white text-[10px] font-mono font-bold shadow-lg flex items-center gap-1">
                              <Target className="w-3 h-3" />
                              🎯 Grounded Claim Citation [97% Faithfulness]
                            </div>
                          )}
                          <p className="font-medium text-gray-900">
                            Veridocs implements a two-stage hybrid retrieval architecture fusing BM25 lexical indexing with dense semantic vector representations.
                          </p>
                        </div>
                        <p>
                          BM25 captures exact lexical entities, codes, and numerical values, while sentence embeddings capture high-level semantic intent. By indexing both sparse inverted token indexes and compressed FAISS vector clusters, the candidate generator achieves high recall across technical terminology and conversational queries.
                        </p>
                      </div>
                    )}

                    {currentPage === 2 && (
                      <div className="space-y-3">
                        <div
                          className={`p-3 rounded-lg transition-all relative ${
                            activeSnippet.includes("cross-encoder")
                              ? "bg-amber-50 border-2 border-amber-400 shadow-[0_0_25px_rgba(251,191,36,0.3)] animate-pulse"
                              : ""
                          }`}
                        >
                          {activeSnippet.includes("cross-encoder") && (
                            <div className="absolute -top-3 left-3 px-2 py-0.5 rounded bg-amber-500 text-white text-[10px] font-mono font-bold shadow-lg flex items-center gap-1">
                              <Target className="w-3 h-3" />
                              🎯 Grounded Claim Citation [98% Precision]
                            </div>
                          )}
                          <p className="font-medium text-gray-900">
                            A deep cross-encoder calculates full token cross-attention across the query and candidate passages, filtering out false positives.
                          </p>
                        </div>
                        <p>
                          Full joint cross-attention improves top-3 retrieval accuracy by up to 38% compared to single-stage vector retrieval, significantly reducing context noise fed into the generation model.
                        </p>
                      </div>
                    )}

                    {currentPage === 3 && (
                      <div className="space-y-3">
                        <div
                          className={`p-3 rounded-lg transition-all relative ${
                            activeSnippet.includes("factual alignment") ||
                            activeSnippet.includes("entailment")
                              ? "bg-amber-50 border-2 border-amber-400 shadow-[0_0_25px_rgba(251,191,36,0.3)] animate-pulse"
                              : ""
                          }`}
                        >
                          {(activeSnippet.includes("factual alignment") ||
                            activeSnippet.includes("entailment")) && (
                            <div className="absolute -top-3 left-3 px-2 py-0.5 rounded bg-amber-500 text-white text-[10px] font-mono font-bold shadow-lg flex items-center gap-1">
                              <Target className="w-3 h-3" />
                              🎯 Grounded Entailment Verification [97% Confidence]
                            </div>
                          )}
                          <p className="font-medium text-gray-900">
                            Factual alignment is verified post-generation by computing premise-hypothesis entailment scores against source passages.
                          </p>
                        </div>
                        <p>
                          Every extracted claim must map directly to an attributed chunk span; non-conforming tokens are rejected. A calibrated confidence score is generated alongside each answer.
                        </p>
                      </div>
                    )}
                  </>
                )}
              </div>

              <div className="mt-12 pt-6 border-t border-gray-100 flex items-center justify-between text-xs text-gray-400">
                <span>Veridocs Forensic Verification Engine</span>
                <span>Confidential & Certified</span>
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
            <span className="text-xs text-text-muted px-2">+{totalPages - 20} more</span>
          )}
        </div>
      )}
    </div>
  );
}
