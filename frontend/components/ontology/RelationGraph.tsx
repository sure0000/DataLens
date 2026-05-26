"use client";

import { useMemo } from "react";

export interface GraphNode {
  id: string;
  label: string;
  type: string;
  status?: string;
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  type: string;
  label?: string;
}

interface RelationGraphProps {
  nodes: GraphNode[];
  edges: GraphEdge[];
  onNodeClick?: (node: GraphNode) => void;
  maxNodes?: number;
}

const TYPE_COLORS: Record<string, string> = {
  BusinessTerm: "#6366f1",
  Metric: "#f59e0b",
  Dimension: "#0891b2",
  PhysicalTable: "#10b981",
};

const FALLBACK_COLOR = "#8b5cf6";

export default function RelationGraph({
  nodes,
  edges,
  onNodeClick,
  maxNodes = 50,
}: RelationGraphProps) {
  const displayNodes = useMemo(() => nodes.slice(0, maxNodes), [nodes, maxNodes]);
  const nodeIds = useMemo(() => new Set(displayNodes.map((n) => n.id)), [displayNodes]);

  const displayEdges = useMemo(
    () =>
      edges
        .filter((e) => nodeIds.has(e.source) && nodeIds.has(e.target))
        .slice(0, maxNodes * 2),
    [edges, nodeIds, maxNodes],
  );

  if (nodes.length === 0) {
    return (
      <div className="app-card p-8 text-center text-sm text-app-muted">
        暂无关系数据。导入文档并同步到 RDF 后将自动构建语义关系图。
      </div>
    );
  }

  // Layout nodes in a simple grid arrangement
  const cols = Math.ceil(Math.sqrt(displayNodes.length));
  const cellW = 160;
  const cellH = 80;
  const gap = 20;
  const padding = 40;
  const svgW = cols * (cellW + gap) + padding * 2;
  const svgH = Math.ceil(displayNodes.length / cols) * (cellH + gap) + padding * 2;

  const nodePositions = useMemo(() => {
    const map = new Map<string, { x: number; y: number }>();
    displayNodes.forEach((node, i) => {
      const col = i % cols;
      const row = Math.floor(i / cols);
      map.set(node.id, {
        x: padding + col * (cellW + gap) + cellW / 2,
        y: padding + row * (cellH + gap) + cellH / 2,
      });
    });
    return map;
  }, [displayNodes, cols, cellW, cellH, gap, padding]);

  return (
    <div className="overflow-x-auto">
      <svg
        width={svgW}
        height={svgH}
        viewBox={`0 0 ${svgW} ${svgH}`}
        className="block mx-auto"
      >
        {/* Edges */}
        {displayEdges.map((edge) => {
          const src = nodePositions.get(edge.source);
          const tgt = nodePositions.get(edge.target);
          if (!src || !tgt) return null;

          return (
            <g key={edge.id}>
              <line
                x1={src.x}
                y1={src.y}
                x2={tgt.x}
                y2={tgt.y}
                stroke="rgba(139, 92, 246, 0.25)"
                strokeWidth={1.5}
              />
              {edge.label && (
                <text
                  x={(src.x + tgt.x) / 2}
                  y={(src.y + tgt.y) / 2 - 4}
                  textAnchor="middle"
                  className="fill-app-muted text-[9px]"
                >
                  {edge.label}
                </text>
              )}
            </g>
          );
        })}

        {/* Nodes */}
        {displayNodes.map((node) => {
          const pos = nodePositions.get(node.id);
          if (!pos) return null;

          const color = TYPE_COLORS[node.type] || FALLBACK_COLOR;
          const label = node.label || node.id.split("/").pop() || node.id;
          const displayLabel = label.length > 20 ? label.slice(0, 19) + "…" : label;

          return (
            <g
              key={node.id}
              transform={`translate(${pos.x - cellW / 2 + 8}, ${pos.y - cellH / 2 + 8})`}
              className="cursor-pointer transition-opacity hover:opacity-80"
              onClick={() => onNodeClick?.(node)}
            >
              <rect
                width={cellW - 16}
                height={cellH - 16}
                rx={10}
                fill={`${color}15`}
                stroke={`${color}50`}
                strokeWidth={1.5}
              />
              <text
                x={(cellW - 16) / 2}
                y={20}
                textAnchor="middle"
                className="fill-app-primary font-medium text-[11px]"
              >
                {displayLabel}
              </text>
              <text
                x={(cellW - 16) / 2}
                y={40}
                textAnchor="middle"
                className="fill-app-muted text-[10px]"
              >
                {node.type.replace("dl:", "").replace(/([a-z])([A-Z])/g, "$1 $2")}
              </text>
              {node.status && (
                <text
                  x={(cellW - 16) / 2}
                  y={56}
                  textAnchor="middle"
                  className="fill-app-muted text-[9px]"
                >
                  {node.status}
                </text>
              )}
            </g>
          );
        })}
      </svg>

      {nodes.length > maxNodes && (
        <p className="text-center text-xs text-app-muted mt-3">
          仅显示前 {maxNodes} / {nodes.length} 个节点
        </p>
      )}
    </div>
  );
}
