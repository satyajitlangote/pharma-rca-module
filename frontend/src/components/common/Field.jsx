import { useId } from "react";

/**
 * Labeled form control. `ai` shows the subtle "AI" badge for fields that were
 * populated by the extraction until the user edits them (edit => origin user).
 */
export default function Field({
  label,
  value,
  onChange,
  type = "text",
  rows,
  options,
  ai = false,
  placeholder,
  hint,
  className = "",
  children,
}) {
  const id = useId();
  const base =
    "w-full rounded-lg border border-slate-300 bg-white px-2.5 py-1.5 text-sm text-slate-800 " +
    "placeholder:text-slate-400 focus:border-indigo-400 focus:outline-none focus:ring-1 focus:ring-indigo-300";

  return (
    <div className={className}>
      <label htmlFor={id} className="mb-1 flex items-center gap-1.5 text-xs font-medium text-slate-600">
        <span>{label}</span>
        {ai && (
          <span
            title="Populated by AI — edit to take ownership"
            className="rounded border border-indigo-200 bg-indigo-50 px-1 text-[9px] font-semibold uppercase tracking-wider text-indigo-600"
          >
            AI
          </span>
        )}
      </label>
      {options ? (
        <select id={id} value={value ?? ""} onChange={(e) => onChange(e.target.value)} className={base}>
          {options.map((o) =>
            typeof o === "string" ? (
              <option key={o} value={o}>
                {o || "—"}
              </option>
            ) : (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            )
          )}
        </select>
      ) : rows ? (
        <textarea
          id={id}
          rows={rows}
          value={value ?? ""}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          className={`${base} resize-y`}
        />
      ) : (
        <input
          id={id}
          type={type}
          value={value ?? ""}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          className={base}
        />
      )}
      {hint && <div className="mt-1 text-[11px] leading-snug text-slate-500">{hint}</div>}
      {children}
    </div>
  );
}
