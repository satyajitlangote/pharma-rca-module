import Badge from "../common/Badge";
import Spinner from "../common/Spinner";

const ICONS = {
  pending: <span className="h-3.5 w-3.5 rounded-full border-2 border-slate-300" />,
  started: <Spinner className="h-3.5 w-3.5 text-indigo-600" />,
  completed: (
    <span className="flex h-3.5 w-3.5 items-center justify-center rounded-full bg-emerald-500 text-[9px] font-bold text-white">
      ✓
    </span>
  ),
  failed: (
    <span className="flex h-3.5 w-3.5 items-center justify-center rounded-full bg-rose-500 text-[9px] font-bold text-white">
      ✕
    </span>
  ),
};

/**
 * Live stepper: one row per LangGraph node, fed by real SSE events
 * ({node, status, details, model, timestamp}).
 */
export default function Stepper({ steps, status }) {
  return (
    <ol className="space-y-1.5">
      {steps.map((s, i) => (
        <li key={s.node} className="flex items-start gap-2.5">
          <div className="flex h-5 flex-col items-center">
            <span className="mt-1 flex h-4 w-4 items-center justify-center">{ICONS[s.status] || ICONS.pending}</span>
            {i < steps.length - 1 && (
              <span className={`mt-0.5 w-px flex-1 ${s.status === "completed" ? "bg-emerald-300" : "bg-slate-200"}`} />
            )}
          </div>
          <div className="min-w-0 flex-1 pb-1">
            <div
              className={`flex items-center gap-1.5 text-xs font-medium ${
                s.status === "failed"
                  ? "text-rose-700"
                  : s.status === "completed"
                    ? "text-slate-700"
                    : s.status === "started"
                      ? "text-indigo-700"
                      : "text-slate-400"
              }`}
            >
              {s.label || s.node}
              {s.model && s.status === "completed" && <Badge tone="slate">{s.model}</Badge>}
            </div>
            {s.details && (
              <div
                className={`mt-0.5 break-words text-[11px] leading-snug ${
                  s.status === "failed" ? "text-rose-600" : "text-slate-500"
                }`}
              >
                {s.details}
              </div>
            )}
          </div>
        </li>
      ))}
      {status === "idle" && (
        <li className="pl-6 pt-1 text-[11px] text-slate-400">Not started</li>
      )}
    </ol>
  );
}
