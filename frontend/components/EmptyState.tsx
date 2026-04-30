"use client";

type IllustrationName = "default" | "search" | "datasource" | "domain";

function Illustration({ name }: { name: IllustrationName }) {
  const common = { stroke: "currentColor", strokeWidth: 1.4, strokeLinecap: "round" as const, strokeLinejoin: "round" as const, fill: "none" };
  if (name === "search") {
    return (
      <svg className="h-16 w-16 text-[#d1d5db]" viewBox="0 0 64 64" aria-hidden="true">
        <circle cx="28" cy="28" r="16" {...common} />
        <path d="M40 40l12 12" {...common} />
        <path d="M22 28h12M28 22v12" {...common} />
      </svg>
    );
  }
  if (name === "datasource") {
    return (
      <svg className="h-16 w-16 text-[#d1d5db]" viewBox="0 0 64 64" aria-hidden="true">
        <ellipse cx="32" cy="18" rx="18" ry="7" {...common} />
        <path d="M14 18v14c0 3.87 8.06 7 18 7s18-3.13 18-7V18" {...common} />
        <path d="M14 32v14c0 3.87 8.06 7 18 7s18-3.13 18-7V32" {...common} />
      </svg>
    );
  }
  if (name === "domain") {
    return (
      <svg className="h-16 w-16 text-[#d1d5db]" viewBox="0 0 64 64" aria-hidden="true">
        <rect x="8" y="12" width="20" height="18" rx="2" {...common} />
        <rect x="36" y="12" width="20" height="12" rx="2" {...common} />
        <rect x="36" y="30" width="20" height="22" rx="2" {...common} />
        <rect x="8" y="36" width="20" height="16" rx="2" {...common} />
      </svg>
    );
  }
  return (
    <svg className="h-16 w-16 text-[#d1d5db]" viewBox="0 0 64 64" aria-hidden="true">
      <rect x="8" y="16" width="48" height="36" rx="4" {...common} />
      <path d="M8 26h48" {...common} />
      <path d="M20 38h24M20 44h16" {...common} />
    </svg>
  );
}

type EmptyStateProps = {
  title: string;
  description: string;
  illustration?: IllustrationName;
  actionLabel?: string;
  onAction?: () => void;
};

export default function EmptyState({ title, description, illustration = "default", actionLabel, onAction }: EmptyStateProps) {
  return (
    <div className="app-surface-panel rounded-2xl px-4 py-10 text-center">
      <div className="mb-4 flex justify-center">
        <Illustration name={illustration} />
      </div>
      <p className="text-base font-semibold text-[var(--app-text-primary)]">{title}</p>
      <p className="app-text-muted mx-auto mt-2 max-w-2xl text-sm">{description}</p>
      {actionLabel && onAction && (
        <div className="mt-4">
          <button className="app-button-secondary app-button-xs" onClick={onAction}>
            {actionLabel}
          </button>
        </div>
      )}
    </div>
  );
}
