"use client";

export type NavIcon =
  | "domain" | "database" | "book" | "bookOpen" | "spark" | "plus" | "search"
  | "chevronLeft" | "chevronRight" | "brand" | "more" | "settings"
  | "folder" | "chevronDown" | "copy" | "play" | "close" | "wrench"
  | "eye" | "eyeOff" | "dot" | "refresh" | "check" | "alertTriangle"
  | "shield" | "code" | "listTree" | "arrowRight" | "functionSquare"
  | "layers" | "network";

const _c = { stroke: "currentColor", strokeWidth: 1.8, strokeLinecap: "round" as const, strokeLinejoin: "round" as const };

export function Icon({ name, className = "h-4 w-4" }: { name: NavIcon; className?: string }) {
  if (name === "plus") return <svg className={className} viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M12 5v14M5 12h14" {..._c} /></svg>;
  if (name === "search") return <svg className={className} viewBox="0 0 24 24" fill="none" aria-hidden="true"><circle cx="11" cy="11" r="6" {..._c} /><path d="M16 16l4 4" {..._c} /></svg>;
  if (name === "chevronLeft") return <svg className={className} viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M15 6l-6 6 6 6" {..._c} /></svg>;
  if (name === "chevronRight") return <svg className={className} viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M9 6l6 6-6 6" {..._c} /></svg>;
  if (name === "chevronDown") return <svg className={className} viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M6 9l6 6 6-6" {..._c} /></svg>;
  if (name === "brand") return <svg className={className} viewBox="0 0 24 24" fill="none" aria-hidden="true"><circle cx="12" cy="12" r="8" {..._c} /><circle cx="12" cy="12" r="3.2" {..._c} /></svg>;
  if (name === "more") return <svg className={className} viewBox="0 0 24 24" fill="none" aria-hidden="true"><circle cx="6" cy="12" r="1.3" fill="currentColor" /><circle cx="12" cy="12" r="1.3" fill="currentColor" /><circle cx="18" cy="12" r="1.3" fill="currentColor" /></svg>;
  if (name === "domain") return <svg className={className} viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M4 5h7v6H4zM13 5h7v4h-7zM13 11h7v8h-7zM4 13h7v6H4z" {..._c} /></svg>;
  if (name === "database") return <svg className={className} viewBox="0 0 24 24" fill="none" aria-hidden="true"><ellipse cx="12" cy="6" rx="7" ry="3" {..._c} /><path d="M5 6v6c0 1.66 3.13 3 7 3s7-1.34 7-3V6M5 12v6c0 1.66 3.13 3 7 3s7-1.34 7-3v-6" {..._c} /></svg>;
  if (name === "book") return <svg className={className} viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M6 4h5a2 2 0 012 2v14a2 2 0 00-2-2H6V4zM13 4h5v14h-5a2 2 0 00-2 2V6a2 2 0 012-2z" {..._c} /></svg>;
  if (name === "settings") return <svg className={className} viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M12 15.5a3.5 3.5 0 100-7 3.5 3.5 0 000 7zM19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 01-2.83 2.83l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83-2.83l.06-.06a1.65 1.65 0 00.33-1.82 1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 012.83-2.83l.06.06A1.65 1.65 0 009 4.6a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 2.83l-.06.06a1.65 1.65 0 00-.33 1.82 1.65 1.65 0 001.51 1H21a2 2 0 010 4h-.09a1.65 1.65 0 00-1.51 1z" {..._c} /></svg>;
  if (name === "spark") return <svg className={className} viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M12 2l1.5 5.5L19 9l-5.5 1.5L12 16l-1.5-5.5L5 9l5.5-1.5z" {..._c} /><circle cx="6" cy="19" r="2.2" {..._c} /></svg>;
  if (name === "folder") return <svg className={className} viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M3 7.8c0-1.68 0-2.52.327-3.16a3 3 0 011.31-1.31C5.28 3 6.12 3 7.8 3h.94c.77 0 1.16 0 1.49.16a1.8 1.8 0 01.35.24c.27.24.52.58 1 1.26l.38.54c.23.32.34.48.48.59.12.1.26.17.41.21.16.05.34.05.68.05H18.2c1.12 0 1.68 0 2.11.22a2 2 0 01.87.87c.22.43.22.99.22 2.11V16.2c0 1.68 0 2.52-.33 3.16a3 3 0 01-1.31 1.31c-.64.33-1.48.33-3.16.33H7.8c-1.68 0-2.52 0-3.16-.33a3 3 0 01-1.31-1.31C3 18.72 3 17.88 3 16.2V7.8z" {..._c} /></svg>;
  if (name === "bookOpen") return <svg className={className} viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M2 6.5A2.5 2.5 0 014.5 4H10v16H4.5A2.5 2.5 0 012 17.5V6.5zM14 4h5.5A2.5 2.5 0 0122 6.5v11a2.5 2.5 0 01-2.5 2.5H14V4z" {..._c} /></svg>;
  if (name === "copy") return <svg className={className} viewBox="0 0 24 24" fill="none" aria-hidden="true"><rect x="9" y="9" width="13" height="13" rx="2" {..._c} /><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1" {..._c} /></svg>;
  if (name === "play") return <svg className={className} viewBox="0 0 24 24" fill="none" aria-hidden="true"><polygon points="8 5 19 12 8 19 8 5" fill="currentColor" stroke="none" /></svg>;
  if (name === "close") return <svg className={className} viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M18 6L6 18M6 6l12 12" {..._c} /></svg>;
  if (name === "wrench") return <svg className={className} viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M14.7 6.3a1 1 0 000 1.4l1.6 1.6a1 1 0 001.4 0l3.77-3.77a6 6 0 01-7.94 7.94l-6.91 6.91a2.12 2.12 0 01-3-3l6.91-6.91a6 6 0 017.94-7.94l-3.76 3.76z" {..._c} /></svg>;
  if (name === "eye") return <svg className={className} viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7-10-7-10-7z" {..._c} /><circle cx="12" cy="12" r="3" {..._c} /></svg>;
  if (name === "eyeOff") return <svg className={className} viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M17.94 17.94A10.07 10.07 0 0112 20c-7 0-10-8-10-8a18.45 18.45 0 015.06-5.94M9.9 4.24A9.12 9.12 0 0112 4c7 0 10 8 10 8a18.5 18.5 0 01-2.16 3.19M1 1l22 22" {..._c} /><path d="M9.9 9.9a3 3 0 104.24 4.24" {..._c} /></svg>;
  if (name === "dot") return <svg className={className} viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><circle cx="12" cy="12" r="3" /></svg>;
  if (name === "refresh") return <svg className={className} viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M21 12a9 9 0 11-2.64-6.36" {..._c} /><path d="M21 3v6h-6" {..._c} /></svg>;
  if (name === "check") return <svg className={className} viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M20 6L9 17l-5-5" {..._c} /></svg>;
  if (name === "alertTriangle") return <svg className={className} viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" {..._c} /><line x1="12" y1="9" x2="12" y2="13" {..._c} /><line x1="12" y1="17" x2="12.01" y2="17" {..._c} /></svg>;
  if (name === "shield") return <svg className={className} viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" {..._c} /></svg>;
  if (name === "code") return <svg className={className} viewBox="0 0 24 24" fill="none" aria-hidden="true"><polyline points="16 18 22 12 16 6" {..._c} /><polyline points="8 6 2 12 8 18" {..._c} /></svg>;
  if (name === "listTree") return <svg className={className} viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M21 12h-8M21 6H8M21 18H8M5 6v12" {..._c} /></svg>;
  if (name === "arrowRight") return <svg className={className} viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M5 12h14M13 6l6 6-6 6" {..._c} /></svg>;
  if (name === "functionSquare") return <svg className={className} viewBox="0 0 24 24" fill="none" aria-hidden="true"><rect x="4" y="4" width="16" height="16" rx="2" {..._c} /><path d="M9 9h.01M15 9h.01M9 15c.83-1 2.17-1 3 0s2.17 1 3 0" {..._c} /></svg>;
  if (name === "layers") return <svg className={className} viewBox="0 0 24 24" fill="none" aria-hidden="true"><polygon points="12 2 2 7 12 12 22 7 12 2" {..._c} /><polyline points="2 17 12 22 22 17" {..._c} /><polyline points="2 12 12 17 22 12" {..._c} /></svg>;
  if (name === "network") return <svg className={className} viewBox="0 0 24 24" fill="none" aria-hidden="true"><rect x="16" y="16" width="6" height="6" rx="1" {..._c} /><rect x="2" y="16" width="6" height="6" rx="1" {..._c} /><rect x="9" y="2" width="6" height="6" rx="1" {..._c} /><path d="M5 16v-3a1 1 0 011-1h12a1 1 0 011 1v3M12 12V8" {..._c} /></svg>;
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M6 5h12a2 2 0 012 2v10a2 2 0 01-2 2H6a2 2 0 01-2-2V7a2 2 0 012-2z" {..._c} />
      <circle cx="8.5" cy="10.5" r="1" fill="currentColor" />
      <path d="M6 15h12M10.5 7.5v11" {..._c} />
    </svg>
  );
}
