"use client";

import { Icon } from "./AppIcons";

type SearchFieldProps = {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  disabled?: boolean;
  className?: string;
};

export default function SearchField({
  value,
  onChange,
  placeholder = "搜索…",
  disabled,
  className = "",
}: SearchFieldProps) {
  return (
    <div className={`app-field ${className}`.trim()}>
      <Icon name="search" className="app-field__adorn app-field__adorn--start h-3.5 w-3.5" />
      <input
        type="search"
        className="app-input app-input--adorn-start w-full text-sm"
        placeholder={placeholder}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled}
      />
    </div>
  );
}
