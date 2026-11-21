"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import {
  ChevronLeft,
  ChevronRight,
  ZoomIn,
  ZoomOut,
  Maximize2,
  FileText,
  Loader2,
} from "lucide-react";
import { useAppStore } from "@/lib/store";
import { fetchPdfBlobUrl } from "@/lib/api";

type PDFDocumentProxy = any;
type PDFPageProxy = any;

export default function PDFViewer() {
  const containerRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const renderTaskRef = useRef<any>(null);

  const {
    sessionId,
    activeDocumentName,
    currentPage,
    totalPages,
    pdfScale,
    highlightedCitation,
    localFileUrls,
    setCurrentPage,
    setTotalPages,
    setPdfScale,
    highlightCitation,
  } = useAppStore();

  const [pdfLib, setPdfLib] = useState<any>(null);
  const [pdfDoc, setPdfDoc] = useState<PDFDocumentProxy | null>(null);
  const [isLoadingDoc, setIsLoadingDoc] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [rendering, setRendering] = useState(false);

  // Lazy-load PDF.js
  useEffect(() => {
    let isMounted = true;
    async function loadPdfJs() {
      try {
        const lib = await import("pdfjs-dist");
        lib.GlobalWorkerOptions.workerSrc = new URL(
          "pdfjs-dist/build/pdf.worker.min.mjs",
          import.meta.url
        ).toString();
        if (isMounted) setPdfLib(lib);
      } catch (err) {
        console.error("Failed to load PDF.js library:", err);
      }
    }
    loadPdfJs();
    return () => {
      isMounted = false;
    };
  }, []);

  // Fetch and load PDF document into PDF.js
  useEffect(() => {
    if (!pdfLib || !sessionId || !activeDocumentName) {
      setPdfDoc(null);
      return;
    }

    let isMounted = true;
    let blobUrlToRevoke: string | null = null;
    setIsLoadingDoc(true);
    setErrorMsg(null);

    async function loadDocument() {
      try {
        let url = localFileUrls[activeDocumentName!];
        if (!url) {
          url = await fetchPdfBlobUrl(sessionId!, activeDocumentName!);
          blobUrlToRevoke = url;
        }

        const doc = await pdfLib.getDocument({ url }).promise;
        if (!isMounted) return;

        setPdfDoc(doc);
        setTotalPages(doc.numPages);

        // Default to fit-to-width on initial load
        try {
          const page = await doc.getPage(1);
          const defaultViewport = page.getViewport({ scale: 1.0 });
          if (containerRef.current && defaultViewport.width > 0) {
            const containerWidth = containerRef.current.clientWidth - 48;
            if (containerWidth > 0) {
              const targetScale = Math.min(Math.max(containerWidth / (defaultViewport.width * 1.5), 0.5), 2.5);
              setPdfScale(targetScale);
            }
          }
        } catch { }
      } catch (err: unknown) {
        if (!isMounted) return;
        console.error("PDF load error:", err);
        setErrorMsg("Failed to render PDF document.");
        setPdfDoc(null);
      } finally {
        if (isMounted) setIsLoadingDoc(false);
      }
    }

    loadDocument();

    return () => {
      isMounted = false;
      if (blobUrlToRevoke) {
        URL.revokeObjectURL(blobUrlToRevoke);
      }
    };
  }, [pdfLib, sessionId, activeDocumentName, localFileUrls, setTotalPages]);

  // Render active page on canvas
  const renderPage = useCallback(
    async (pageNumber: number) => {
      if (!pdfDoc || !canvasRef.current) return;

      if (renderTaskRef.current) {
        try {
          renderTaskRef.current.cancel();
        } catch { }
      }

      setRendering(true);
      try {
        const page: PDFPageProxy = await pdfDoc.getPage(pageNumber);
        const canvas = canvasRef.current;
        if (!canvas) return;

        const viewport = page.getViewport({ scale: pdfScale * 1.5 });
        const context = canvas.getContext("2d");
        if (!context) return;

        canvas.height = viewport.height;
        canvas.width = viewport.width;

        const renderContext = {
          canvasContext: context,
          viewport: viewport,
        };

        const renderTask = page.render(renderContext);
        renderTaskRef.current = renderTask;
        await renderTask.promise;
      } catch (err: any) {
        if (err?.name !== "RenderingCancelledException") {
          console.error("Canvas render error:", err);
        }
      } finally {
        setRendering(false);
      }
    },
    [pdfDoc, pdfScale]
  );

  useEffect(() => {
    if (pdfDoc && currentPage) {
      renderPage(currentPage);
    }
  }, [pdfDoc, currentPage, pdfScale, renderPage]);

  const goToPage = (p: number) => {
    const target = Math.max(1, Math.min(p, totalPages));
    setCurrentPage(target);
  };

  const zoomIn = () => setPdfScale(Math.min(pdfScale + 0.15, 2.5));
  const zoomOut = () => setPdfScale(Math.max(pdfScale - 0.15, 0.5));
  const fitWidth = useCallback(async () => {
    if (!pdfDoc || !containerRef.current) return;
    try {
      const page = await pdfDoc.getPage(currentPage || 1);
      const defaultViewport = page.getViewport({ scale: 1.0 });
      const containerWidth = containerRef.current.clientWidth - 48;
      if (containerWidth > 0 && defaultViewport.width > 0) {
        const targetScale = Math.min(Math.max(containerWidth / (defaultViewport.width * 1.5), 0.5), 2.5);
        setPdfScale(targetScale);
      }
    } catch { }
  }, [pdfDoc, currentPage, setPdfScale]);

  return (
    <div className="h-full flex flex-col bg-[var(--bg-canvas)] select-none overflow-hidden">
      {/* Control Toolbar */}
      <div className="h-10 px-3 border-b border-[var(--border-subtle)] bg-[var(--bg-surface)] flex items-center justify-between text-xs font-mono-data shrink-0">
        <div className="flex items-center gap-1.5">
          <button
            type="button"
            disabled={currentPage <= 1 || !pdfDoc}
            onClick={() => goToPage(currentPage - 1)}
            className="p-1 rounded text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-subtle)] disabled:opacity-40 transition-colors"
            title="Previous page"
          >
            <ChevronLeft className="w-4 h-4" />
          </button>

          <span className="text-[11px] text-[var(--text-secondary)] px-1">
            Page {pdfDoc ? currentPage : 0} of {pdfDoc ? totalPages : 0}
          </span>

          <button
            type="button"
            disabled={currentPage >= totalPages || !pdfDoc}
            onClick={() => goToPage(currentPage + 1)}
            className="p-1 rounded text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-subtle)] disabled:opacity-40 transition-colors"
            title="Next page"
          >
            <ChevronRight className="w-4 h-4" />
          </button>
        </div>

        {/* Zoom Controls */}
        <div className="flex items-center gap-1">
          <button
            type="button"
            disabled={!pdfDoc}
            onClick={zoomOut}
            className="p-1 rounded text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-subtle)] disabled:opacity-40 transition-colors"
            title="Zoom out"
          >
            <ZoomOut className="w-3.5 h-3.5" />
          </button>

          <span className="text-[10px] text-[var(--text-muted)] w-10 text-center font-mono-data">
            {Math.round(pdfScale * 100)}%
          </span>

          <button
            type="button"
            disabled={!pdfDoc}
            onClick={zoomIn}
            className="p-1 rounded text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-subtle)] disabled:opacity-40 transition-colors"
            title="Zoom in"
          >
            <ZoomIn className="w-3.5 h-3.5" />
          </button>

          <button
            type="button"
            disabled={!pdfDoc}
            onClick={fitWidth}
            className="p-1 rounded text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-subtle)] disabled:opacity-40 transition-colors ml-1"
            title="Fit to width"
          >
            <Maximize2 className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* PDF Stage: w-fit min-w-full prevents flex negative coordinate clipping */}
      <div
        ref={containerRef}
        className="flex-1 overflow-auto bg-[var(--bg-canvas)] p-6 relative"
      >
        <div className="w-fit min-w-full min-h-full flex flex-col items-center my-auto">
          {isLoadingDoc ? (
            <div className="flex flex-col items-center justify-center gap-2 p-8 text-center text-xs text-[var(--text-muted)] m-auto">
              <Loader2 className="w-6 h-6 text-[var(--color-accent)] animate-spin" />
              <span>Loading {activeDocumentName}...</span>
            </div>
          ) : errorMsg ? (
            <div className="p-6 text-center text-xs text-red-500 max-w-sm m-auto">
              <p className="font-semibold mb-1">Rendering Error</p>
              <p>{errorMsg}</p>
            </div>
          ) : pdfDoc ? (
            <div className="relative shadow-md border border-[var(--border-default)] rounded bg-white my-auto">
              <canvas ref={canvasRef} className="block" />
              {rendering && (
                <div className="absolute inset-0 bg-white/40 flex items-center justify-center">
                  <Loader2 className="w-5 h-5 text-[var(--color-accent)] animate-spin" />
                </div>
              )}
              {highlightedCitation && highlightedCitation.page === currentPage && (
                <div className="absolute top-3 right-3 bg-[var(--color-accent)] text-white text-[10px] font-mono-data font-semibold px-2 py-0.5 rounded shadow">
                  Citation on Page {currentPage}
                </div>
              )}
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center p-8 text-center max-w-xs text-[var(--text-muted)] m-auto">
              <FileText className="w-10 h-10 text-[var(--text-muted)] mb-3 opacity-60" />
              <p className="text-sm font-semibold text-[var(--text-primary)] mb-1">
                {activeDocumentName ? activeDocumentName : "No Document Loaded"}
              </p>
              <p className="text-xs">
                Upload a PDF or select a document from the left sidebar to view pages and citations.
              </p>
            </div>
          )}
        </div>

        {/* Floating Citation Excerpt Preview */}
        {highlightedCitation && highlightedCitation.page === currentPage && highlightedCitation.highlighted_text && (
          <div className="sticky bottom-0 mx-auto max-w-xl bg-[var(--bg-surface)]/95 backdrop-blur border border-[var(--color-accent)] rounded-lg p-3 shadow-xl text-xs z-10 animate-in fade-in slide-in-from-bottom-2">
            <div className="flex items-center justify-between text-[11px] font-mono-data font-semibold text-[var(--color-accent)] mb-1">
              <span>Cited Passage (Page {currentPage})</span>
              <button
                type="button"
                onClick={() => highlightCitation(null)}
                className="text-[var(--text-muted)] hover:text-[var(--text-primary)] px-1"
                title="Dismiss highlight"
              >
                ✕
              </button>
            </div>
            <p className="text-[var(--text-primary)] line-clamp-3 leading-relaxed italic text-[11.5px]">
              &ldquo;{highlightedCitation.highlighted_text}&rdquo;
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
