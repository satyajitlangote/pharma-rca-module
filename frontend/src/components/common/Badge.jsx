const TONES = {
  green: "bg-emerald-50 text-emerald-700 border-emerald-200",
  amber: "bg-amber-50 text-amber-700 border-amber-200",
  red: "bg-rose-50 text-rose-700 border-rose-200",
  blue: "bg-sky-50 text-sky-700 border-sky-200",
  slate: "bg-slate-100 text-slate-600 border-slate-200",
  purple: "bg-violet-50 text-violet-700 border-violet-200",
};

export default function Badge({ tone = "slate", children, title, className = "" }) {
  return (
    <span
      title={title}
      className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium ${TONES[tone] || TONES.slate} ${className}`}
    >
      {children}
    </span>
  );
}
