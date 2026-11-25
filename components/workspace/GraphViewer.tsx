"use client";

import React, { useEffect, useState, useMemo } from "react";
import { useAppStore } from "../../lib/store";
import {
  fetchDocumentGraph,
  searchCrossDocumentGraph,
  GraphResult,
  GraphNodeData,
  GraphEdgeData,
} from "../../lib/api";

const NODE_COLORS: Record<string, { bg: string; border: string; text: string }> = {
  Document: { bg: "#1e3a8a", border: "#3b82f6", text: "#93c5fd" },
  Organization: { bg: "#064e3b", border: "#10b981", text: "#6ee7b7" },
  Party: { bg: "#064e3b", border: "#10b981", text: "#6ee7b7" },
  Person: { bg: "#4c1d95", border: "#8b5cf6", text: "#c4b5fd" },
  Date: { bg: "#78350f", border: "#f59e0b", text: "#fde68a" },
  Money: { bg: "#164e63", border: "#06b6d4", text: "#a5f3fc" },
  Clause: { bg: "#334155", border: "#64748b", text: "#cbd5e1" },
};

export default function GraphViewer({ documentId }: { documentId: string }) {
  const { documentGraphs, setDocumentGraph, setCurrentPage } = useAppStore();

  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [selectedNode, setSelectedNode] = useState<GraphNodeData | null>(null);
  const [selectedEdge, setSelectedEdge] = useState<GraphEdgeData | null>(null);
  const [crossGraph, setCrossGraph] = useState<GraphResult | null>(null);

  const activeGraph = crossGraph || documentGraphs[documentId];

  useEffect(() => {
    if (!documentId || crossGraph) return;
    if (documentGraphs[documentId]) return;

    let active = true;
    setLoading(true);
    fetchDocumentGraph(documentId, 50)
      .then((data) => {
        if (active) setDocumentGraph(documentId, data);
      })
      .catch((err) => {
        if (active) setError(err.message || "Failed to load document graph");
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => {
      active = false;
    };
  }, [documentId, crossGraph, documentGraphs, setDocumentGraph]);

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!searchQuery.trim()) {
      setCrossGraph(null);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const res = await searchCrossDocumentGraph(searchQuery.trim(), 50);
      setCrossGraph(res);
      setSelectedNode(null);
      setSelectedEdge(null);
    } catch (err: any) {
      setError(err.message || "Cross-document search failed");
    } finally {
      setLoading(false);
    }
  };

  const handleResetSearch = () => {
    setSearchQuery("");
    setCrossGraph(null);
    setSelectedNode(null);
    setSelectedEdge(null);
  };

  const nodes = activeGraph?.nodes || [];
  const edges = activeGraph?.edges || [];

  // Compute 2D node layout positions around center canvas
  const nodePositions = useMemo(() => {
    const width = 600;
    const height = 400;
    const centerX = width / 2;
    const centerY = height / 2;
    const radius = Math.min(width, height) * 0.38;

    const positions: Record<string, { x: number; y: number }> = {};
    const n = nodes.length;

    nodes.forEach((node, idx) => {
      if (node.label === "Document") {
        positions[node.id] = { x: centerX, y: centerY };
      } else {
        const angle = (2 * Math.PI * idx) / Math.max(n - 1, 1);
        positions[node.id] = {
          x: centerX + radius * Math.cos(angle) + (idx % 2 === 0 ? 15 : -15),
          y: centerY + radius * Math.sin(angle) + (idx % 3 === 0 ? 10 : -10),
        };
      }
    });

    return positions;
  }, [nodes]);

  return (
    <div className="flex flex-col h-full bg-slate-900 text-slate-100 overflow-hidden">
      {/* Top Controls Bar */}
      <div className="p-3 border-b border-slate-800 bg-slate-850 space-y-2">
        <div className="flex items-center justify-between">
          <h2 className="text-xs font-semibold text-slate-200 flex items-center gap-1.5">
            <span>🕸️</span> Knowledge Graph Explorer
          </h2>
          <span className="text-[10px] text-slate-400 bg-slate-800 px-2 py-0.5 rounded border border-slate-700">
            Capped at top 50 nodes for performance
          </span>
        </div>

        {/* Cross-Document Search Input */}
        <form onSubmit={handleSearch} className="flex gap-2">
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search entity connections across all contracts..."
            className="flex-1 text-xs bg-slate-900 border border-slate-700 rounded-lg px-2.5 py-1.5 text-slate-200 placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
          />
          <button
            type="submit"
            className="px-3 py-1.5 text-xs font-medium rounded-lg bg-blue-600 hover:bg-blue-500 text-white transition-colors"
          >
            Trace
          </button>
          {crossGraph && (
            <button
              type="button"
              onClick={handleResetSearch}
              className="px-2 py-1.5 text-xs text-slate-400 hover:text-white"
            >
              Reset
            </button>
          )}
        </form>
      </div>

      {/* Main Graph Canvas Area */}
      <div className="flex-1 relative bg-slate-950 overflow-hidden flex items-center justify-center">
        {loading && (
          <div className="absolute inset-0 bg-slate-950/70 z-20 flex items-center justify-center text-xs text-blue-400 font-medium animate-pulse">
            Constructing graph topology...
          </div>
        )}

        {nodes.length === 0 ? (
          <div className="text-center py-16 text-slate-500 text-xs">
            {error || "No graph entities or relationships extracted yet."}
          </div>
        ) : (
          <svg className="w-full h-full min-h-[360px]" viewBox="0 0 600 400">
            <defs>
              <marker
                id="arrowhead"
                markerWidth="8"
                markerHeight="6"
                refX="14"
                refY="3"
                orient="auto"
              >
                <polygon points="0 0, 8 3, 0 6" fill="#64748b" />
              </marker>
            </defs>

            {/* Edges */}
            {edges.map((edge, idx) => {
              const p1 = nodePositions[edge.source_id];
              const p2 = nodePositions[edge.target_id];
              if (!p1 || !p2) return null;

              const isSelected = selectedEdge?.id === edge.id;
              const midX = (p1.x + p2.x) / 2;
              const midY = (p1.y + p2.y) / 2;

              return (
                <g key={`edge-${idx}`} onClick={() => { setSelectedEdge(edge); setSelectedNode(null); }}>
                  <line
                    x1={p1.x}
                    y1={p1.y}
                    x2={p2.x}
                    y2={p2.y}
                    stroke={isSelected ? "#38bdf8" : "#475569"}
                    strokeWidth={isSelected ? "2.5" : "1.2"}
                    strokeDasharray={edge.verified ? undefined : "3,3"}
                    markerEnd="url(#arrowhead)"
                    className="cursor-pointer hover:stroke-blue-400 transition-colors"
                  />
                  <text
                    x={midX}
                    y={midY - 4}
                    fill="#94a3b8"
                    fontSize="8"
                    textAnchor="middle"
                    className="select-none pointer-events-none font-mono"
                  >
                    {edge.relation}
                  </text>
                </g>
              );
            })}

            {/* Nodes */}
            {nodes.map((node) => {
              const pos = nodePositions[node.id];
              if (!pos) return null;

              const color = NODE_COLORS[node.label] || { bg: "#1e293b", border: "#475569", text: "#e2e8f0" };
              const isSelected = selectedNode?.id === node.id;

              return (
                <g
                  key={node.id}
                  transform={`translate(${pos.x}, ${pos.y})`}
                  onClick={() => { setSelectedNode(node); setSelectedEdge(null); }}
                  className="cursor-pointer group"
                >
                  <circle
                    r={node.label === "Document" ? 22 : 16}
                    fill={color.bg}
                    stroke={isSelected ? "#ffffff" : color.border}
                    strokeWidth={isSelected ? 3 : 1.5}
                    className="transition-all duration-200 group-hover:scale-110"
                  />
                  <text
                    y={node.label === "Document" ? 30 : 25}
                    textAnchor="middle"
                    fill={color.text}
                    fontSize="9"
                    fontWeight="600"
                    className="select-none pointer-events-none drop-shadow"
                  >
                    {node.name.length > 18 ? node.name.slice(0, 16) + "…" : node.name}
                  </text>
                </g>
              );
            })}
          </svg>
        )}
      </div>

      {/* Inspector Details Drawer */}
      <div className="h-44 border-t border-slate-800 bg-slate-900 p-3 overflow-y-auto text-xs">
        {selectedNode ? (
          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <span className="font-semibold text-slate-200 flex items-center gap-2">
                <span className="px-1.5 py-0.5 text-[10px] uppercase font-bold rounded bg-slate-800 border border-slate-700">
                  {selectedNode.label}
                </span>
                {selectedNode.name}
              </span>
              <span className="text-[10px] text-slate-400 font-mono">
                Canonical: {selectedNode.canonical_name}
              </span>
            </div>

            {selectedNode.aliases && selectedNode.aliases.length > 0 && (
              <div className="text-[11px] text-slate-400">
                <span className="font-medium text-slate-300">Aliases: </span>
                {selectedNode.aliases.join(", ")}
              </div>
            )}

            <div className="text-[11px] text-slate-400">
              <span className="font-medium text-slate-300">Connected In: </span>
              {selectedNode.document_ids?.length || 1} Document(s)
            </div>
          </div>
        ) : selectedEdge ? (
          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <span className="font-semibold text-blue-300 flex items-center gap-1.5">
                <span>🔗</span> Relationship: {selectedEdge.relation}
              </span>
              {selectedEdge.page_number && (
                <button
                  onClick={() => setCurrentPage(selectedEdge.page_number!)}
                  className="px-2 py-0.5 rounded bg-blue-900 text-blue-200 text-[10px] font-semibold hover:bg-blue-700 transition-colors"
                >
                  Jump to Page {selectedEdge.page_number} ↗
                </button>
              )}
            </div>

            {selectedEdge.quote && (
              <div className="p-2 rounded bg-slate-950 border border-slate-800 text-[11px] text-slate-300 font-mono">
                &ldquo;{selectedEdge.quote}&rdquo;
              </div>
            )}

            <div className="text-[10px] text-slate-500">
              Status: {selectedEdge.verified ? "✅ Quote verified verbatim against document page text" : "⚠️ Unverified quote"}
            </div>
          </div>
        ) : (
          <div className="text-center py-6 text-slate-500 text-[11px]">
            Click any node to view canonical aliases and documents, or click an edge to jump directly to its verified source page.
          </div>
        )}
      </div>
    </div>
  );
}
