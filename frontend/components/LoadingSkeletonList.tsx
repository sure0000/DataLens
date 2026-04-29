"use client";

type LoadingSkeletonListProps = {
  count?: number;
};

export default function LoadingSkeletonList({ count = 3 }: LoadingSkeletonListProps) {
  return (
    <div className="space-y-3" aria-hidden="true">
      {Array.from({ length: count }).map((_, idx) => (
        <div key={`skeleton-${idx}`} className="app-card p-4">
          <div className="app-skeleton h-4 w-2/5 rounded" />
          <div className="app-skeleton mt-3 h-3 w-4/5 rounded" />
          <div className="app-skeleton mt-2 h-3 w-3/5 rounded" />
        </div>
      ))}
    </div>
  );
}
