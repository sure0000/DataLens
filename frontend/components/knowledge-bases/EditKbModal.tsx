"use client";

import { useEffect, useState } from "react";
import { useEscapeKey } from "../../hooks/useEscapeKey";

interface EditKbModalProps {
  open: boolean;
  kbName: string;
  kbDescription: string;
  onSave: (name: string, description: string) => Promise<void>;
  onClose: () => void;
}

export default function EditKbModal({ open, kbName, kbDescription, onSave, onClose }: EditKbModalProps) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (open) {
      setName(kbName);
      setDescription(kbDescription || "");
    }
  }, [open, kbName, kbDescription]);

  useEscapeKey(onClose, open);

  if (!open) return null;

  async function handleSave() {
    if (!name.trim()) return;
    setSaving(true);
    try {
      await onSave(name.trim(), description.trim());
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="app-modal-backdrop" role="presentation" onClick={onClose}>
      <div
        className="app-card w-full max-w-lg p-5"
        role="dialog"
        aria-modal="true"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-3 flex items-center justify-between">
          <h2 className="app-section-title">编辑知识库</h2>
          <button className="app-control-button" type="button" onClick={onClose}>
            关闭
          </button>
        </div>
        <label className="app-form-label">
          <span>名称</span>
          <input className="app-input" value={name} onChange={(e) => setName(e.target.value)} />
        </label>
        <label className="app-form-label mt-2">
          <span>描述</span>
          <textarea
            className="app-input min-h-[88px]"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
        </label>
        <div className="mt-3 flex gap-2">
          <button
            className={`app-button flex-1 ${saving ? "is-loading" : ""}`}
            type="button"
            onClick={handleSave}
            disabled={!name.trim() || saving}
          >
            保存
          </button>
          <button className="app-button-secondary flex-1" type="button" onClick={onClose}>
            取消
          </button>
        </div>
      </div>
    </div>
  );
}
