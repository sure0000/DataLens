"use client";

interface CategorySectionProps {
  name: string;
  count: number;
  itemKeys: Set<string>;
  selectedIds: Set<string>;
  onSelectAll: (checked: boolean) => void;
  children: React.ReactNode;
}

export default function CategorySection({
  name,
  count,
  itemKeys,
  selectedIds,
  onSelectAll,
  children,
}: CategorySectionProps) {
  const allSelected = itemKeys.size > 0 && itemKeys.size === selectedIds.size;

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between px-1">
        <h3 className="text-sm font-semibold text-app-primary">
          {name === "__uncategorized__" ? "未分类" : name}
          <span className="ml-1.5 text-xs text-app-muted font-normal">({count})</span>
        </h3>
        {itemKeys.size > 0 && (
          <label className="flex items-center gap-1.5 text-xs text-app-muted cursor-pointer select-none">
            <input
              type="checkbox"
              className="accent-indigo-500"
              checked={allSelected}
              onChange={() => onSelectAll(!allSelected)}
            />
            全选
          </label>
        )}
      </div>
      {children}
    </div>
  );
}
