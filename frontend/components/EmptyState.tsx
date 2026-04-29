"use client";

type EmptyStateProps = {
  title: string;
  description: string;
  actionLabel?: string;
  onAction?: () => void;
};

export default function EmptyState({ title, description, actionLabel, onAction }: EmptyStateProps) {
  return (
    <div className="app-surface-panel rounded-2xl px-4 py-8 text-center">
      <p className="text-base font-semibold text-[#111827]">{title}</p>
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
