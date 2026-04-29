"use client";

type ToastProps = {
  message: string;
  tone?: "success" | "error" | "info";
  onClose: () => void;
};

export default function Toast({ message, tone = "success", onClose }: ToastProps) {
  if (!message) return null;
  const toneClass =
    tone === "error"
      ? "border-rose-300/60 bg-rose-50 text-rose-700"
      : tone === "info"
        ? "border-sky-300/60 bg-sky-50 text-sky-700"
        : "border-emerald-300/60 bg-emerald-50 text-emerald-700";

  return (
    <div className="pointer-events-none fixed right-4 top-4 z-[150]">
      <div className={`app-surface-panel pointer-events-auto flex max-w-md items-start gap-3 rounded-xl px-3 py-2 text-sm backdrop-blur ${toneClass}`}>
        <p className="flex-1 break-words">{message}</p>
        <button className="app-control-button !min-h-0 !px-1.5 !py-0.5" onClick={onClose} aria-label="关闭提示">
          关闭
        </button>
      </div>
    </div>
  );
}
