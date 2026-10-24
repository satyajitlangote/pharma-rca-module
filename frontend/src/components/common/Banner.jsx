const STYLES = {
  red: "border-rose-300 bg-rose-50 text-rose-900",
  amber: "border-amber-300 bg-amber-50 text-amber-900",
  blue: "border-sky-300 bg-sky-50 text-sky-900",
  green: "border-emerald-300 bg-emerald-50 text-emerald-900",
  slate: "border-slate-300 bg-slate-50 text-slate-800",
};

export default function Banner({ tone = "blue", title, children, actions, onClose }) {
  return (
    <div className={`flex items-start gap-3 rounded-lg border px-3 py-2 text-sm ${STYLES[tone] || STYLES.blue}`} role="status">
      <div className="min-w-0 flex-1">
        {title && <div className="font-semibold">{title}</div>}
        {children && <div className="mt-0.5 leading-snug">{children}</div>}
      </div>
      {actions}
      {onClose && (
        <button
          type="button"
          onClick={onClose}
          className="no-print shrink-0 rounded p-1 text-xs opacity-60 hover:opacity-100"
          aria-label="Dismiss"
        >
          ✕
        </button>
      )}
    </div>
  );
}
