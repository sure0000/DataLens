"use client";

import { useState } from "react";
import { Icon } from "../AppIcons";

export interface HierarchyNode {
  iri: string;
  label: string;
  definition?: string;
  status?: string;
  confidence?: number;
  children: HierarchyNode[];
}

interface ConceptHierarchyTreeProps {
  roots: HierarchyNode[];
  onSelect?: (node: HierarchyNode) => void;
  selectedIri?: string;
  /** Max depth to expand by default (0 = roots only). Default 2. */
  defaultExpandDepth?: number;
}

export default function ConceptHierarchyTree({
  roots,
  onSelect,
  selectedIri,
  defaultExpandDepth = 2,
}: ConceptHierarchyTreeProps) {
  if (roots.length === 0) {
    return (
      <p className="text-sm text-app-muted px-3 py-4">
        暂无层级数据。导入文档并同步到 RDF 后将自动构建术语层级。
      </p>
    );
  }

  return (
    <ul className="space-y-0.5 text-sm select-none">
      {roots.map((node) => (
        <TreeNode
          key={node.iri}
          node={node}
          depth={0}
          defaultExpandDepth={defaultExpandDepth}
          onSelect={onSelect}
          selectedIri={selectedIri}
        />
      ))}
    </ul>
  );
}

function TreeNode({
  node,
  depth,
  defaultExpandDepth,
  onSelect,
  selectedIri,
}: {
  node: HierarchyNode;
  depth: number;
  defaultExpandDepth: number;
  onSelect?: (node: HierarchyNode) => void;
  selectedIri?: string;
}) {
  const [expanded, setExpanded] = useState(depth < defaultExpandDepth);
  const hasChildren = node.children.length > 0;
  const isSelected = selectedIri === node.iri;

  return (
    <li>
      <div
        className={`flex items-center gap-1.5 rounded-lg px-2 py-1.5 cursor-pointer transition-colors ${
          isSelected
            ? "bg-app-active-bg border border-app-active-border"
            : "hover:bg-app-surface-hover border border-transparent"
        }`}
        style={{ paddingLeft: `${8 + depth * 20}px` }}
        onClick={() => onSelect?.(node)}
      >
        <button
          type="button"
          className={`shrink-0 p-0.5 rounded hover:bg-app-surface-hover ${
            !hasChildren ? "invisible" : ""
          }`}
          aria-label={expanded ? "收起" : "展开"}
          onClick={(e) => {
            e.stopPropagation();
            if (hasChildren) setExpanded(!expanded);
          }}
        >
          {expanded ? (
            <Icon name="chevronDown" className="h-3.5 w-3.5 text-app-muted" />
          ) : (
            <Icon name="chevronRight" className="h-3.5 w-3.5 text-app-muted" />
          )}
        </button>

        <Icon name="dot" className="h-3 w-3 shrink-0 text-app-muted/60" aria-hidden />

        <div className="min-w-0 flex-1">
          <span className="text-sm font-medium text-app-primary block truncate">
            {node.label || node.iri.split("/").pop() || node.iri}
          </span>
          {node.definition && depth < 3 && (
            <span className="text-[11px] text-app-muted line-clamp-1 mt-0.5 block">
              {node.definition}
            </span>
          )}
        </div>

        {node.confidence !== undefined && (
          <span
            className={`shrink-0 text-[10px] font-medium px-1.5 py-0.5 rounded-full ${
              node.confidence >= 80
                ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
                : node.confidence >= 50
                  ? "bg-amber-500/10 text-amber-600 dark:text-amber-400"
                  : "bg-red-500/10 text-red-500"
            }`}
            title={`置信度 ${node.confidence}%`}
          >
            {node.confidence}%
          </span>
        )}

        {node.status && (
          <span className="shrink-0 text-[10px] text-app-muted bg-app-chip-bg rounded px-1.5 py-0.5">
            {node.status}
          </span>
        )}
      </div>

      {hasChildren && expanded && (
        <ul>
          {node.children.map((child) => (
            <TreeNode
              key={child.iri}
              node={child}
              depth={depth + 1}
              defaultExpandDepth={defaultExpandDepth}
              onSelect={onSelect}
              selectedIri={selectedIri}
            />
          ))}
        </ul>
      )}
    </li>
  );
}
