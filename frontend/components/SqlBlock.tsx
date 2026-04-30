"use client";

// Lightweight SQL keyword highlighter — no external dependency
function highlightSql(sql: string): string {
  const keywords = /\b(SELECT|FROM|WHERE|JOIN|LEFT|RIGHT|INNER|OUTER|ON|GROUP\s+BY|ORDER\s+BY|HAVING|LIMIT|OFFSET|INSERT|INTO|VALUES|UPDATE|SET|DELETE|CREATE|TABLE|INDEX|DROP|ALTER|ADD|COLUMN|AS|AND|OR|NOT|IN|IS|NULL|LIKE|BETWEEN|CASE|WHEN|THEN|ELSE|END|DISTINCT|COUNT|SUM|AVG|MAX|MIN|COALESCE|IFNULL|IF|CAST|CONVERT|DATE|YEAR|MONTH|DAY|NOW|INTERVAL|WITH|UNION|ALL|EXISTS|OVER|PARTITION\s+BY|ROW_NUMBER|RANK|DENSE_RANK|LEAD|LAG|FIRST_VALUE|LAST_VALUE)\b/gi;
  const strings = /(')((?:[^'\\]|\\.)*)(')/g;
  const numbers = /\b(\d+(?:\.\d+)?)\b/g;
  const comments = /(--[^\n]*)/g;

  return sql
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(comments, '<span class="sql-comment">$1</span>')
    .replace(strings, '<span class="sql-string">$1$2$3</span>')
    .replace(numbers, '<span class="sql-number">$1</span>')
    .replace(keywords, '<span class="sql-keyword">$&</span>');
}

type SqlBlockProps = {
  sql: string;
};

export default function SqlBlock({ sql }: SqlBlockProps) {
  const content = sql?.trim() || "-- 无 SQL --";
  const highlighted = highlightSql(content);

  return (
    <pre
      className="sql-block mt-2 overflow-x-auto rounded-lg p-3 text-xs leading-5"
      dangerouslySetInnerHTML={{ __html: highlighted }}
    />
  );
}
