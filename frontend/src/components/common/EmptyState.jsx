export default function EmptyState({ title, hint, children }) {
  return (
    <div className="rounded-lg border border-dashed border-slate-300 bg-slate-50 px-4 py-6 text-center">
      <div className="text-sm font-medium text-slate-600">{title}</div>
      {hint && <div className="mt-1 text-xs text-slate-500">{hint}</div>}
      {children && <div className="mt-2">{children}</div>}
    </div>
  );
}
