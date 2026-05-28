"use client";

import { useEffect, useMemo, useState } from "react";
import type { DocRow, Entry } from "./types";
import { buildGitFileTree, getGitTreeMatchingPaths, type GitFileTreeNode } from "./gitFileTree";
import { docStatusChip } from "./utils";

function highlightMatch(text: string, q: string): React.ReactNode {
  if (!q) return text;
  const idx = text.toLowerCase().indexOf(q.toLowerCase());
  if (idx === -1) return text;
  return (
    <>
      {text.slice(0, idx)}
      <mark className="bg-yellow-100 text-yellow-900 rounded-sm px-0.5 dark:bg-yellow-900/40 dark:text-yellow-100">
        {text.slice(idx, idx + q.length)}
      </mark>
      {text.slice(idx + q.length)}
    </>
  );
}

function TreeNodeRow({
  node,
  depth,
  expanded,
  selectedPath,
  onToggle,
  onSelectFile,
  searchQ,
  matchingPaths,
  docByEntryId,
}: {
  node: GitFileTreeNode;
  depth: number;
  expanded: Set<string>;
  selectedPath: string | null;
  onToggle: (path: string) => void;
  onSelectFile: (entry: Entry, path: string) => void;
  searchQ: string;
  matchingPaths: Set<string>;
  docByEntryId: Map<number, DocRow>;
}) {
  if (searchQ && !matchingPaths.has(node.path)) return null;

  const isExpanded = expanded.has(node.path) || (searchQ.length > 0 && matchingPaths.has(node.path));
  const isSelected = !node.isDir && node.path === selectedPath;

  return (
    <div>
      <div
        className={`flex items-center gap-1.5 rounded-md px-2 py-1 text-sm cursor-pointer select-none
          ${isSelected ? "bg-[var(--app-accent-muted)] text-app-primary" : node.isDir ? "text-app-primary hover:bg-app-hover" : "text-app-secondary hover:bg-app-hover"}`}
        style={{ paddingLeft: `${depth * 14 + 8}px` }}
        onClick={() => {
          if (node.isDir) onToggle(node.path);
          else if (node.entry) onSelectFile(node.entry, node.path);
        }}
      >
        {node.isDir ? (
          <>
            <svg
              width="14"
              height="14"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.8"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
              className="shrink-0 text-app-muted"
            >
              {isExpanded ? <polyline points="6 9 12 15 18 9" /> : <polyline points="9 18 15 12 9 6" />}
            </svg>
            <svg
              width="14"
              height="14"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.8"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
              className="shrink-0 text-amber-500"
            >
              <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />
            </svg>
            <span className="font-medium truncate">{highlightMatch(node.name, searchQ)}</span>
            <span className="ml-auto text-xs text-app-muted shrink-0">{node.fileCount}</span>
          </>
        ) : (
          <>
            <span className="w-[14px] shrink-0" />
            <svg
              width="14"
              height="14"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.8"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
              className="shrink-0 text-app-muted"
            >
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
              <polyline points="14 2 14 8 20 8" />
            </svg>
            <span className="truncate flex-1 min-w-0">{highlightMatch(node.name, searchQ)}</span>
            {node.entry && docByEntryId.has(node.entry.id) && (
              <span
                className={`shrink-0 inline-flex rounded-full border px-1 py-0 text-[9px] font-medium ${docStatusChip(docByEntryId.get(node.entry.id)!.status).className}`}
                title={docStatusChip(docByEntryId.get(node.entry.id)!.status).text}
              >
                {docStatusChip(docByEntryId.get(node.entry.id)!.status).text}
              </span>
            )}
          </>
        )}
      </div>
      {node.isDir && isExpanded && (
        <div>
          {node.children.map((child) => (
            <TreeNodeRow
              key={child.path}
              node={child}
              depth={depth + 1}
              expanded={expanded}
              selectedPath={selectedPath}
              onToggle={onToggle}
              onSelectFile={onSelectFile}
              searchQ={searchQ}
              matchingPaths={matchingPaths}
              docByEntryId={docByEntryId}
            />
          ))}
        </div>
      )}
    </div>
  );
}

type GitSourceFileTreeProps = {
  entries: Entry[];
  documents: DocRow[];
  selectedPath: string | null;
  onSelectFile: (entry: Entry, path: string) => void;
  className?: string;
};

export default function GitSourceFileTree({
  entries,
  documents,
  selectedPath,
  onSelectFile,
  className = "",
}: GitSourceFileTreeProps) {
  const [search, setSearch] = useState("");
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  const tree = useMemo(() => buildGitFileTree(entries), [entries]);
  const searchQ = search.trim().toLowerCase();
  const matchingPaths = useMemo(
    () => (searchQ ? getGitTreeMatchingPaths(tree, searchQ) : new Set<string>()),
    [tree, searchQ],
  );

  const docByEntryId = useMemo(() => {
    const m = new Map<number, DocRow>();
    for (const d of documents) {
      if (d.knowledge_entry_id != null) m.set(d.knowledge_entry_id, d);
    }
    return m;
  }, [documents]);

  useEffect(() => {
    const topDirs = tree.children.filter((c) => c.isDir).map((c) => c.path);
    setExpanded(new Set(topDirs));
  }, [tree]);

  function toggleDir(path: string) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  }

  return (
    <div className={`flex flex-col min-h-0 ${className}`}>
      <div className="shrink-0 px-2 py-2 border-b border-app-border">
        <div className="relative">
          <svg
            className="absolute left-2.5 top-1/2 -translate-y-1/2 text-app-muted pointer-events-none"
            width="14"
            height="14"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.8"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
          >
            <circle cx="11" cy="11" r="8" />
            <line x1="21" y1="21" x2="16.65" y2="16.65" />
          </svg>
          <input
            className="app-input pl-8 text-sm w-full"
            placeholder="搜索文件…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
      </div>
      <div className="flex-1 overflow-y-auto px-1 py-2 min-h-0">
        {entries.length === 0 ? (
          <p className="text-sm text-app-muted px-3 py-4">暂无已同步文件，请先在设置中执行「同步仓库」。</p>
        ) : searchQ && matchingPaths.size === 0 ? (
          <p className="text-sm text-app-muted px-3 py-4">未找到匹配「{search}」的文件。</p>
        ) : (
          tree.children.map((node) => (
            <TreeNodeRow
              key={node.path}
              node={node}
              depth={0}
              expanded={expanded}
              selectedPath={selectedPath}
              onToggle={toggleDir}
              onSelectFile={onSelectFile}
              searchQ={searchQ}
              matchingPaths={matchingPaths}
              docByEntryId={docByEntryId}
            />
          ))
        )}
      </div>
    </div>
  );
}
