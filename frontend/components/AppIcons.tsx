"use client";

export type NavIcon =
  | "domain" | "database" | "book" | "spark" | "plus" | "search"
  | "chevronLeft" | "chevronRight" | "brand" | "more" | "settings"
  | "folder" | "chevronDown";

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
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M6 5h12a2 2 0 012 2v10a2 2 0 01-2 2H6a2 2 0 01-2-2V7a2 2 0 012-2z" {..._c} />
      <circle cx="8.5" cy="10.5" r="1" fill="currentColor" />
      <path d="M6 15h12M10.5 7.5v11" {..._c} />
    </svg>
  );
}
