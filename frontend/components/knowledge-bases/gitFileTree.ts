import type { Entry } from "./types";

export type GitFileTreeNode = {
  name: string;
  path: string;
  isDir: boolean;
  children: GitFileTreeNode[];
  entry?: Entry;
  fileCount: number;
};

export function buildGitFileTree(entries: Entry[]): GitFileTreeNode {
  const root: GitFileTreeNode = { name: "", path: "", isDir: true, children: [], fileCount: 0 };

  for (const entry of entries) {
    const ref = entry.source_meta?.ref;
    if (!ref) continue;
    const parts = ref.split("/").filter(Boolean);
    let node = root;
    for (let i = 0; i < parts.length; i++) {
      const part = parts[i];
      const isLast = i === parts.length - 1;
      const fullPath = parts.slice(0, i + 1).join("/");
      let child = node.children.find((c) => c.name === part);
      if (!child) {
        child = {
          name: part,
          path: fullPath,
          isDir: !isLast,
          children: [],
          entry: isLast ? entry : undefined,
          fileCount: 0,
        };
        node.children.push(child);
      }
      node = child;
    }
  }

  function sortNode(n: GitFileTreeNode) {
    n.children.sort((a, b) => {
      if (a.isDir !== b.isDir) return a.isDir ? -1 : 1;
      return a.name.localeCompare(b.name);
    });
    for (const c of n.children) sortNode(c);
  }
  sortNode(root);

  function countFiles(n: GitFileTreeNode): number {
    if (!n.isDir) return 1;
    n.fileCount = n.children.reduce((s, c) => s + countFiles(c), 0);
    return n.fileCount;
  }
  countFiles(root);

  return root;
}

export function getGitTreeMatchingPaths(node: GitFileTreeNode, q: string): Set<string> {
  const matched = new Set<string>();
  function walk(n: GitFileTreeNode) {
    if (!n.isDir && n.name.toLowerCase().includes(q)) {
      const parts = n.path.split("/");
      for (let i = 1; i <= parts.length; i++) {
        matched.add(parts.slice(0, i).join("/"));
      }
    }
    for (const c of n.children) walk(c);
  }
  walk(node);
  return matched;
}
