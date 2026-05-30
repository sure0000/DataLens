"use client";

import { useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { buildGitFileTree, getGitTreeMatchingPaths, type GitFileTreeNode } from "./knowledge-bases/gitFileTree";
import { useEscapeKey } from "../hooks/useEscapeKey";
import SearchField from "./SearchField";

type Entry = {
  id: number;
  knowledge_base_id: number;
  title: string;
  summary?: string;
  body: string;
  sort_order: number;
  source_url?: string | null;
  source_meta?: Record<string, string>;
  created_at: string;
  updated_at: string;
};

type GitSource = {
  id: number;
  name: string;
  provider: string;
  owner: string;
  repo: string;
  branch: string;
  uses_default_branch?: boolean;
};

type TreeNode = GitFileTreeNode;

function highlightMatch(text: string, q: string): React.ReactNode {
  if (!q) return text;
  const idx = text.toLowerCase().indexOf(q.toLowerCase());
  if (idx === -1) return text;
  return (
    <>
      {text.slice(0, idx)}
      <mark className="bg-yellow-100 text-yellow-900 rounded-sm px-0.5">{text.slice(idx, idx + q.length)}</mark>
      {text.slice(idx + q.length)}
    </>
  );
}

function TreeNodeRow({
  node,
  depth,
  expanded,
  onToggle,
  onFileClick,
  searchQ,
  matchingPaths,
}: {
  node: TreeNode;
  depth: number;
  expanded: Set<string>;
  onToggle: (path: string) => void;
  onFileClick: (entry: Entry) => void;
  searchQ: string;
  matchingPaths: Set<string>;
}) {
  if (searchQ && !matchingPaths.has(node.path)) return null;

  const isExpanded = expanded.has(node.path) || (searchQ.length > 0 && matchingPaths.has(node.path));

  return (
    <div>
      <div
        className={`flex items-center gap-1.5 rounded-md px-2 py-1 text-sm cursor-pointer select-none
          ${node.isDir ? "text-app-primary hover:bg-app-hover" : "text-app-secondary hover:bg-app-hover"}`}
        style={{ paddingLeft: `${depth * 16 + 8}px` }}
        onClick={() => {
          if (node.isDir) {
            onToggle(node.path);
          } else if (node.entry) {
            onFileClick(node.entry);
          }
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
              {isExpanded ? (
                <polyline points="6 9 12 15 18 9" />
              ) : (
                <polyline points="9 18 15 12 9 6" />
              )}
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
            <span className="truncate">{highlightMatch(node.name, searchQ)}</span>
            {node.entry?.source_url ? (
              <a
                href={node.entry.source_url}
                target="_blank"
                rel="noopener noreferrer"
                className="ml-auto shrink-0 text-app-muted hover:text-app-primary"
                title="在 GitHub 中查看"
                onClick={(e) => e.stopPropagation()}
              >
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
                  <polyline points="15 3 21 3 21 9" />
                  <line x1="10" y1="14" x2="21" y2="3" />
                </svg>
              </a>
            ) : null}
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
              onToggle={onToggle}
              onFileClick={onFileClick}
              searchQ={searchQ}
              matchingPaths={matchingPaths}
            />
          ))}
        </div>
      )}
    </div>
  );
}

type GitFileBrowserProps = {
  source: GitSource;
  entries: Entry[];
  onClose: () => void;
  onViewEntry: (entry: Entry) => void;
};

export default function GitFileBrowser({ source, entries, onClose, onViewEntry }: GitFileBrowserProps) {
  const [search, setSearch] = useState("");
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  const sourceEntries = useMemo(
    () => entries.filter((e) => e.source_meta?.git_source_id === String(source.id)),
    [entries, source.id]
  );

  const tree = useMemo(() => buildGitFileTree(sourceEntries), [sourceEntries]);

  const searchQ = search.trim().toLowerCase();
  const matchingPaths = useMemo(
    () => (searchQ ? getGitTreeMatchingPaths(tree, searchQ) : new Set<string>()),
    [tree, searchQ]
  );

  // Expand top-level dirs by default
  useEffect(() => {
    const topDirs = tree.children.filter((c) => c.isDir).map((c) => c.path);
    setExpanded(new Set(topDirs));
  }, [tree]);

  useEscapeKey(onClose);

  function toggleDir(path: string) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  }

  const branchLabel = source.uses_default_branch || !source.branch?.trim() ? "默认分支" : source.branch;

  const surface = (
    <div
      className="app-modal-backdrop app-modal-backdrop--front"
      role="presentation"
      onClick={onClose}
    >
      <div
        className="app-modal-surface flex flex-col w-full max-w-2xl rounded-2xl overflow-hidden"
        style={{ maxHeight: "80vh" }}
        role="dialog"
        aria-modal="true"
        aria-label={`${source.name} 仓库文件`}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between gap-3 px-5 py-4 border-b border-app-border shrink-0">
          <div className="min-w-0">
            <h2 className="text-[15px] font-semibold text-app-primary truncate">
              {source.name} 仓库文件
            </h2>
            <p className="text-xs text-app-muted mt-0.5">
              {source.provider === "github" ? "GitHub" : "GitLab"} · {source.owner}/{source.repo} · {branchLabel} · {sourceEntries.length} 个文件
            </p>
          </div>
          <button
            className="app-control-button shrink-0"
            type="button"
            onClick={onClose}
            aria-label="关闭"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>

        {/* Search */}
        <div className="px-4 py-3 border-b border-app-border shrink-0">
          <SearchField
            placeholder="搜索文件名…"
            value={search}
            onChange={setSearch}
          />
        </div>

        {/* Tree */}
        <div className="flex-1 overflow-y-auto px-2 py-2">
          {sourceEntries.length === 0 ? (
            <p className="text-sm text-app-muted px-3 py-4">该代码源暂无已同步的文件，请先执行同步。</p>
          ) : searchQ && matchingPaths.size === 0 ? (
            <p className="text-sm text-app-muted px-3 py-4">未找到匹配「{search}」的文件。</p>
          ) : (
            tree.children.map((node) => (
              <TreeNodeRow
                key={node.path}
                node={node}
                depth={0}
                expanded={expanded}
                onToggle={toggleDir}
                onFileClick={(entry) => {
                  onClose();
                  onViewEntry(entry);
                }}
                searchQ={searchQ}
                matchingPaths={matchingPaths}
              />
            ))
          )}
        </div>

        {/* Footer hint */}
        <div className="px-5 py-2.5 border-t border-app-border shrink-0">
          <p className="text-xs text-app-muted">点击文件名查看正文内容；点击 <svg className="inline" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg> 在 {source.provider === "github" ? "GitHub" : "GitLab"} 中查看源文件</p>
        </div>
      </div>
    </div>
  );

  return typeof document !== "undefined" ? createPortal(surface, document.body) : null;
}
