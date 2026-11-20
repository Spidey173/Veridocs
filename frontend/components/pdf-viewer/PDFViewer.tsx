"use client";

import { useEffect, useRef, useState, useCallback } from "react";
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
        const nextScale = Math.min(Math.max(scaleRef.current + delta, 0.3), 1.5);
        setPdfScale(nextScale);
      }
    };

    container.addEventListener("wheel", handleWheel, { passive: false });
    return () => {
      container.removeEventListener("wheel", handleWheel);
    };
  }, [setPdfScale]);

  // Load PDF.js library
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

        let matchStart = pageLower.indexOf(cleanSnippet);
        let matchEnd = -1;

        if (matchStart !== -1) {
          matchEnd = matchStart + cleanSnippet.length;
        } else {
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
      const context = canvas.getContext("2d", { alpha: false });

      if (!context) return;

      const outputScale =
        typeof window !== "undefined"
          ? Math.min(Math.max(window.devicePixelRatio || 1, 2), 3)
          : 2;

      const displayWidth = Math.floor(viewport.width);
      const displayHeight = Math.floor(viewport.height);

      canvas.width = Math.floor(viewport.width * outputScale);
      canvas.height = Math.floor(viewport.height * outputScale);
      canvas.style.width = `${displayWidth}px`;
      canvas.style.height = `${displayHeight}px`;

      context.imageSmoothingEnabled = true;
      context.imageSmoothingQuality = "high";

      currentPageObjRef.current = page;
      currentViewportRef.current = viewport;

      const transform =
        outputScale !== 1 ? [outputScale, 0, 0, outputScale, 0, 0] : undefined;

      const renderTask = page.render({
        canvasContext: context,
        canvas,
        viewport,
        transform,
      });
      renderTaskRef.current = renderTask;

      await renderTask.promise;

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

    if (
      targetSnippet &&
      targetPage === currentPage &&
      currentPageObjRef.current &&
      currentViewportRef.current
    ) {
      computeBoundingBoxes(currentPageObjRef.current, currentViewportRef.current, targetSnippet);
    }
  }, [activeVisualHighlight, highlightedCitation, currentPage, computeBoundingBoxes]);

  const goToPage = (page: number) => {
    if (page >= 1 && page <= totalPages) {
      setCurrentPage(page);
    }
  };

  const zoomIn = () => setPdfScale(Number(Math.min(pdfScale + 0.1, 2.0).toFixed(2)));
  const zoomOut = () => setPdfScale(Number(Math.max(pdfScale - 0.1, 0.3).toFixed(2)));
  const fitWidth = () => {
    if (containerRef.current && currentViewportRef.current && pdfScale > 0) {
      const containerWidth = containerRef.current.clientWidth - 48;
      const unscaledWidth = currentViewportRef.current.width / (pdfScale * 1.5);
      if (unscaledWidth > 0) {
        const idealScale = Math.max(0.4, Math.min(1.5, containerWidth / (unscaledWidth * 1.5)));
        setPdfScale(Number(idealScale.toFixed(2)));
        return;
      }
    }
    setPdfScale(0.85);
  };

  if (!sessionId) return null;

  if (!activeDocumentName) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center text-center p-6 bg-[var(--bg-canvas)]">
        <FileText className="w-8 h-8 text-[var(--text-muted)] mb-2 opacity-50" />
        <p className="text-xs text-[var(--text-muted)] font-mono-data">
          Select a document from the corpus sidebar to inspect
        </p>
      </div>
    );
  }

  const activeSnippet =
    activeVisualHighlight?.snippet || highlightedCitation?.highlighted_text || "";
  const activeSeverity = activeVisualHighlight?.severity || "citation";
  const activeLabel =
    activeVisualHighlight?.label ||
    (highlightedCitation ? `Cited Source [Page ${highlightedCitation.page}]` : "");

  return (
    <div className="flex flex-col h-full bg-[var(--bg-canvas)] select-none text-[var(--text-primary)]">
      {/* Viewer Toolbar: Dense, Crisp, Professional */}
      <div className="flex items-center justify-between px-3 py-1.5 border-b border-[var(--border-subtle)] bg-[var(--bg-surface)] shrink-0">
        <div className="flex items-center gap-1 text-xs">
          <button
            type="button"
            onClick={() => goToPage(currentPage - 1)}
            disabled={currentPage <= 1}
            className="p-1 rounded text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-subtle)] disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
          >
            <ChevronLeft className="w-4 h-4" />
          </button>

          <div className="flex items-center gap-1 px-1 font-mono-data text-xs">
            <input
              type="number"
              value={currentPage}
              onChange={(e) => goToPage(parseInt(e.target.value) || 1)}
              className="w-8 text-center text-xs bg-[var(--bg-canvas)] border border-[var(--border-subtle)] rounded py-0.5 focus:outline-none focus:border-[var(--color-accent)]"
              min={1}
              max={totalPages}
            />
            <span className="text-[var(--text-muted)]">/ {totalPages}</span>
          </div>

          <button
            type="button"
            onClick={() => goToPage(currentPage + 1)}
            disabled={currentPage >= totalPages}
            className="p-1 rounded text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-subtle)] disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
          >
            <ChevronRight className="w-4 h-4" />
          </button>
        </div>

        {/* Visual Grounding Status Pill */}
        {activeSnippet && (
          <div className="hidden sm:flex items-center gap-1 px-2 py-0.5 rounded border border-[var(--color-accent-border)] bg-[var(--color-accent-subtle)] text-[10.5px] font-mono-data font-semibold text-[var(--color-accent)]">
            <Target className="w-3 h-3" />
            <span>Pixel Grounding Active</span>
          </div>
        )}

        <div className="flex items-center gap-1 text-xs">
          <button
            type="button"
            onClick={zoomOut}
            className="p-1 rounded text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-subtle)] transition-colors"
            title="Zoom out"
          >
            <ZoomOut className="w-3.5 h-3.5" />
          </button>

          <span className="text-[11px] font-mono-data text-[var(--text-muted)] px-1 min-w-[2.5rem] text-center">
            {Math.round(pdfScale * 100)}%
          </span>

          <button
            type="button"
            onClick={zoomIn}
            className="p-1 rounded text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-subtle)] transition-colors"
            title="Zoom in"
          >
            <ZoomIn className="w-3.5 h-3.5" />
          </button>

          <div className="w-px h-3.5 bg-[var(--border-subtle)] mx-1" />

          <button
            type="button"
            onClick={fitWidth}
            className="p-1 rounded text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-subtle)] transition-colors"
            title="Fit width"
          >
            <Maximize2 className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* PDF Canvas Stage */}
      <div
        ref={containerRef}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUpOrLeave}
        onMouseLeave={handleMouseUpOrLeave}
        onContextMenu={handleContextMenu}
        className="flex-1 overflow-auto flex p-4 cursor-grab active:cursor-grabbing select-none bg-[var(--bg-canvas)]"
      >
        <div className="relative m-auto">
          {pdfDoc ? (
            <>
              <canvas
                ref={canvasRef}
                className="shadow-sm border border-[var(--border-default)] rounded block"
                style={{
                  background: "white",
                  imageRendering: "auto",
                }}
              />

              {/* Exact Bounding Box Highlights & Anchored Badge */}
              {activeSnippet && (
                <>
                  {highlightAnchor && (
                    <div
                      style={{
                        position: "absolute",
                        top: `${Math.max(6, highlightAnchor.top - 36)}px`,
                        left: `${Math.max(6, highlightAnchor.left)}px`,
                        zIndex: 40,
                      }}
                      className="pointer-events-none flex items-center gap-1.5 px-2.5 py-1 rounded border border-[var(--border-strong)] bg-[var(--bg-surface-raised)] text-[var(--text-primary)] text-[11px] font-mono-data font-semibold shadow-md"
                    >
                      <span className="w-1.5 h-1.5 rounded-full bg-[var(--color-accent)]" />
                      <span>{activeLabel}:</span>
                      <span className="italic truncate max-w-[220px] text-[var(--text-secondary)]">
                        &quot;{activeSnippet}&quot;
                      </span>
                    </div>
                  )}

                  {boundingBoxes.map((box, i) => (
                    <div
                      key={`bbox-${i}`}
                      style={{
                        position: "absolute",
                        left: `${box.x}px`,
                        top: `${box.y}px`,
                        width: `${box.width}px`,
                        height: `${box.height}px`,
                        zIndex: 35,
                      }}
                      className="pointer-events-none citation-highlight-box citation-flash-active"
                    />
                  ))}
                </>
              )}

              {rendering && (
                <div className="absolute inset-0 flex items-center justify-center bg-black/20">
                  <div className="w-5 h-5 border-2 border-[var(--color-accent)] border-t-transparent rounded-full animate-spin" />
                </div>
              )}
            </>
          ) : isLoadingDoc && sessionId !== "demo-session" ? (
            <div
              style={{
                width: `${Math.floor(612 * pdfScale * 1.5)}px`,
                minHeight: `${Math.floor(792 * pdfScale * 1.5)}px`,
              }}
              className="bg-[var(--bg-surface)] border border-[var(--border-subtle)] rounded-lg flex flex-col items-center justify-center p-8 select-none"
            >
              <FileText className="w-6 h-6 text-[var(--color-accent)] animate-pulse mb-2" />
              <p className="text-xs font-semibold text-[var(--text-primary)] mb-0.5">
                Loading {activeDocumentName}...
              </p>
              <p className="text-[11px] text-[var(--text-muted)] font-mono-data">
                Preparing pages & coordinates
              </p>
            </div>
          ) : (
            /* Interactive Demo Document: Authentic Document Sheet */
            <div
              style={{
                width: `${Math.floor(612 * pdfScale * 1.5)}px`,
                minHeight: `${Math.floor(792 * pdfScale * 1.5)}px`,
                fontSize: `${13 * pdfScale * 1.5}px`,
              }}
              className="bg-white text-gray-900 shadow-sm border border-gray-300 rounded p-8 sm:p-12 transition-all relative select-text"
            >
              <div className="border-b border-gray-200 pb-3 mb-5">
                <div className="flex items-center justify-between text-[11px] text-gray-500 font-mono-data mb-1.5">
                  <span className="uppercase font-semibold tracking-wider">
                    {activeDocumentName.replace(".pdf", "").replace(/_/g, " ")}
                  </span>
                  <span>PAGE {currentPage} OF 3</span>
                </div>
                <h2 className="text-base font-serif-doc font-bold text-gray-900 tracking-tight">
                  {activeDocumentName.includes("2024")
                    ? "MASTER SAAS & SERVICES AGREEMENT (2024 BASELINE)"
                    : activeDocumentName.includes("2025")
                    ? "AMENDED MASTER SERVICES AGREEMENT (2025 REVISION)"
                    : "VERIDOCS TECHNICAL ARCHITECTURE & BENCHMARK REPORT"}
                </h2>
              </div>

              {/* Document Text Body */}
              <div className="space-y-4 leading-relaxed text-gray-700 text-xs sm:text-sm">
                {activeDocumentName.includes("2024") ? (
                  <>
                    {currentPage === 1 && (
                      <div className="space-y-3">
                        <h3 className="font-serif-doc font-bold text-gray-900 text-sm">
                          Section 4. Financial & Payment Terms
                        </h3>
                        <div
                          className={`p-2.5 rounded transition-all relative ${
                            activeSnippet.includes("30 days")
                              ? "bg-amber-50/60 border border-[var(--color-accent)] ring-1 ring-[var(--color-accent)]"
                              : "bg-gray-50/50 border border-gray-200"
                          }`}
                        >
                          {activeSnippet.includes("30 days") && (
                            <div className="absolute -top-2.5 left-2 px-1.5 py-0.2 rounded bg-[var(--color-accent)] text-white text-[9px] font-mono-data font-semibold flex items-center gap-1 shadow-sm">
                              <span>4.1 Net 30 Term</span>
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
                        <h3 className="font-serif-doc font-bold text-gray-900 text-sm">
                          Section 8. Limitation of Liability
                        </h3>
                        <div
                          className={`p-2.5 rounded transition-all relative ${
                            activeSnippet.includes("1,000,000")
                              ? "bg-amber-50/60 border border-[var(--color-accent)] ring-1 ring-[var(--color-accent)]"
                              : "bg-gray-50/50 border border-gray-200"
                          }`}
                        >
                          {activeSnippet.includes("1,000,000") && (
                            <div className="absolute -top-2.5 left-2 px-1.5 py-0.2 rounded bg-[var(--color-accent)] text-white text-[9px] font-mono-data font-semibold flex items-center gap-1 shadow-sm">
                              <span>8.1 $1M Liability Cap</span>
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
                        <h3 className="font-serif-doc font-bold text-gray-900 text-sm">
                          Schedule B: Service Level Agreement (SLA)
                        </h3>
                        <div
                          className={`p-2.5 rounded transition-all relative ${
                            activeSnippet.includes("99.95%")
                              ? "bg-amber-50/60 border border-[var(--color-accent)] ring-1 ring-[var(--color-accent)]"
                              : "bg-gray-50/50 border border-gray-200"
                          }`}
                        >
                          {activeSnippet.includes("99.95%") && (
                            <div className="absolute -top-2.5 left-2 px-1.5 py-0.2 rounded bg-[var(--color-accent)] text-white text-[9px] font-mono-data font-semibold flex items-center gap-1 shadow-sm">
                              <span>B.1 99.95% Availability</span>
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
                        <h3 className="font-serif-doc font-bold text-gray-900 text-sm">
                          Section 4. Settlement Schedule
                        </h3>
                        <div
                          className={`p-2.5 rounded transition-all relative ${
                            activeSnippet.includes("60 calendar days")
                              ? "bg-amber-50/60 border border-[var(--color-accent)] ring-1 ring-[var(--color-accent)]"
                              : "bg-gray-50/50 border border-gray-200"
                          }`}
                        >
                          {activeSnippet.includes("60 calendar days") && (
                            <div className="absolute -top-2.5 left-2 px-1.5 py-0.2 rounded bg-[var(--color-accent)] text-white text-[9px] font-mono-data font-semibold flex items-center gap-1 shadow-sm">
                              <span>4.1 Net 60 Term</span>
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
                        <h3 className="font-serif-doc font-bold text-gray-900 text-sm">
                          Section 8. Damages & Indemnity
                        </h3>
                        <div
                          className={`p-2.5 rounded transition-all relative ${
                            activeSnippet.includes("250,000")
                              ? "bg-amber-50/60 border border-[var(--color-accent)] ring-1 ring-[var(--color-accent)]"
                              : "bg-gray-50/50 border border-gray-200"
                          }`}
                        >
                          {activeSnippet.includes("250,000") && (
                            <div className="absolute -top-2.5 left-2 px-1.5 py-0.2 rounded bg-[var(--color-accent)] text-white text-[9px] font-mono-data font-semibold flex items-center gap-1 shadow-sm">
                              <span>8.1 $250k Cap</span>
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
                        <h3 className="font-serif-doc font-bold text-gray-900 text-sm">
                          Schedule B: Availability Target
                        </h3>
                        <div
                          className={`p-2.5 rounded transition-all relative ${
                            activeSnippet.includes("99.5%")
                              ? "bg-amber-50/60 border border-[var(--color-accent)] ring-1 ring-[var(--color-accent)]"
                              : "bg-gray-50/50 border border-gray-200"
                          }`}
                        >
                          {activeSnippet.includes("99.5%") && (
                            <div className="absolute -top-2.5 left-2 px-1.5 py-0.2 rounded bg-[var(--color-accent)] text-white text-[9px] font-mono-data font-semibold flex items-center gap-1 shadow-sm">
                              <span>B.1 99.5% Target</span>
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
                  <>
                    {currentPage === 1 && (
                      <div className="space-y-3">
                        <div
                          className={`p-2.5 rounded transition-all relative ${
                            activeSnippet.includes("two-stage hybrid")
                              ? "bg-amber-50/60 border border-[var(--color-accent)] ring-1 ring-[var(--color-accent)]"
                              : ""
                          }`}
                        >
                          <p className="font-medium text-gray-900">
                            Veridocs implements a two-stage hybrid retrieval architecture fusing BM25 lexical indexing with dense semantic vector representations.
                          </p>
                        </div>
                        <p>
                          Full-text search captures exact lexical entities, codes, and numerical values, while sentence embeddings capture high-level semantic intent. By indexing both PostgreSQL full-text tsvector indexes and HNSW pgvector clusters, the candidate generator achieves high recall across technical terminology and conversational queries.
                        </p>
                      </div>
                    )}

                    {currentPage === 2 && (
                      <div className="space-y-3">
                        <div
                          className={`p-2.5 rounded transition-all relative ${
                            activeSnippet.includes("cross-encoder")
                              ? "bg-amber-50/60 border border-[var(--color-accent)] ring-1 ring-[var(--color-accent)]"
                              : ""
                          }`}
                        >
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
                          className={`p-2.5 rounded transition-all relative ${
                            activeSnippet.includes("factual alignment") ||
                            activeSnippet.includes("entailment")
                              ? "bg-amber-50/60 border border-[var(--color-accent)] ring-1 ring-[var(--color-accent)]"
                              : ""
                          }`}
                        >
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

              <div className="mt-10 pt-4 border-t border-gray-200 flex items-center justify-between text-[11px] text-gray-400 font-mono-data">
                <span>Veridocs Document Verification</span>
                <span>Page {currentPage} of 3</span>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Bottom Thumbnail Strip */}
      {totalPages > 0 && totalPages <= 50 && (
        <div className="flex items-center gap-1 px-3 py-1.5 border-t border-[var(--border-subtle)] bg-[var(--bg-surface)] shrink-0 overflow-x-auto">
          {Array.from({ length: Math.min(totalPages, 20) }, (_, i) => (
            <button
              key={i + 1}
              type="button"
              onClick={() => goToPage(i + 1)}
              className={`
                min-w-[1.75rem] h-6 rounded text-[11px] font-mono-data font-medium transition-colors
                ${
                  currentPage === i + 1
                    ? "bg-[var(--color-accent)] text-white font-semibold"
                    : "bg-[var(--bg-subtle)] text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-hover)]"
                }
              `}
            >
              {i + 1}
            </button>
          ))}
          {totalPages > 20 && (
            <span className="text-[10px] text-[var(--text-muted)] font-mono-data px-1">
              +{totalPages - 20} more
            </span>
          )}
        </div>
      )}
    </div>
  );
}
