"use client";

type Props = {
  page: number;
  pageSize: number;
  total: number;
  onPageChange: (next: number) => void;
  onPageSizeChange: (next: number) => void;
  pageSizeOptions?: number[];
};

export default function ListPagination({
  page,
  pageSize,
  total,
  onPageChange,
  onPageSizeChange,
  pageSizeOptions = [5, 10, 20, 50]
}: Props) {
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const safePage = Math.min(Math.max(1, page), totalPages);
  const start = total === 0 ? 0 : (safePage - 1) * pageSize + 1;
  const end = total === 0 ? 0 : Math.min(total, safePage * pageSize);

  return (
    <nav
      aria-label="分页导航"
      className="mt-3 flex flex-col gap-2 rounded-lg border border-app-border bg-app-card p-2.5 text-xs text-app-secondary sm:flex-row sm:items-center sm:justify-between"
    >
      <div className="flex flex-wrap items-center gap-2">
        <span className="app-text-muted">
          共 {total} 条（当前显示 {start}-{end}）
        </span>
        <span className="app-text-muted">每页</span>
        <select
          aria-label="每页条数"
          className="app-input w-[78px] !rounded-md !px-2 !py-1 text-xs"
          value={pageSize}
          onChange={(e) => onPageSizeChange(Number(e.target.value))}
        >
          {pageSizeOptions.map((size) => (
            <option key={size} value={size}>
              {size}
            </option>
          ))}
        </select>
      </div>

      <div className="flex items-center justify-between gap-2 sm:justify-end">
        <button
          aria-label="上一页"
          className="app-control-button"
          onClick={() => onPageChange(safePage - 1)}
          disabled={safePage <= 1}
        >
          上一页
        </button>
        <span aria-live="polite" className="min-w-[56px] text-center text-app-ink">
          {safePage} / {totalPages}
        </span>
        <button
          aria-label="下一页"
          className="app-control-button"
          onClick={() => onPageChange(safePage + 1)}
          disabled={safePage >= totalPages}
        >
          下一页
        </button>
      </div>
    </nav>
  );
}
