import { useDispatch, useSelector } from "react-redux";
import { closedModal } from "../../store/rcaSlice";
import Badge from "../common/Badge";
import EmptyState from "../common/EmptyState";
import Modal from "../common/Modal";
import Spinner from "../common/Spinner";

const ACTOR_TONE = { AI: "purple", User: "blue", QP: "green" };
const ACTION_TONE = { create: "green", update: "blue", signoff: "green", reopen: "amber", delete: "red" };

/** Format a diff value for display (long JSON is collapsed). */
function fmt(value) {
  if (value == null || value === "") return "—";
  const s = typeof value === "string" ? value : JSON.stringify(value);
  return s.length > 160 ? `${s.slice(0, 160)}…` : s;
}

/** Audit trail: one entry per write, with field-level diffs. */
export default function AuditModal() {
  const dispatch = useDispatch();
  const open = useSelector((s) => s.rca.ui.modals.audit);
  const audit = useSelector((s) => s.rca.audit);
  const reference = useSelector((s) => s.rca.draft.reference);

  return (
    <Modal
      open={open}
      title={`Audit trail${reference ? ` — ${reference}` : ""}`}
      onClose={() => dispatch(closedModal("audit"))}
      width="max-w-3xl"
    >
      {audit.status === "loading" ? (
        <div className="flex justify-center py-8"><Spinner /></div>
      ) : audit.status === "error" ? (
        <div className="text-xs text-rose-700">{audit.error}</div>
      ) : audit.entries.length === 0 ? (
        <EmptyState title="No audit entries" hint="Every save, sign-off and reopen writes an entry." />
      ) : (
        <ol className="space-y-3">
          {audit.entries.map((e) => (
            <li key={e.id} className="print-block rounded-lg border border-slate-200 p-3">
              <div className="mb-1 flex flex-wrap items-center justify-between gap-2">
                <div className="flex flex-wrap items-center gap-1.5">
                  <Badge tone={ACTION_TONE[e.action] || "slate"}>{e.action}</Badge>
                  <Badge tone={ACTOR_TONE[e.actor_type] || "slate"}>{e.actor_type}</Badge>
                  <span className="text-xs font-medium text-slate-700">{e.actor}</span>
                </div>
                <span className="font-mono text-[11px] text-slate-400">
                  {e.timestamp ? new Date(e.timestamp).toLocaleString() : "—"}
                </span>
              </div>
              {e.diff?.length > 0 ? (
                <table className="mt-1 w-full text-left text-[11px]">
                  <thead>
                    <tr className="text-[10px] uppercase tracking-wide text-slate-400">
                      <th className="py-1 pr-2">Field</th>
                      <th className="py-1 pr-2">Old value</th>
                      <th className="py-1">New value</th>
                    </tr>
                  </thead>
                  <tbody>
                    {e.diff.map((d, i) => (
                      <tr key={i} className="border-t border-slate-100 align-top">
                        <td className="py-1 pr-2 font-mono text-slate-600">{d.field}</td>
                        <td className="py-1 pr-2 text-rose-700 break-words">{fmt(d.old)}</td>
                        <td className="py-1 text-emerald-700 break-words">{fmt(d.new)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                <div className="text-[11px] text-slate-400">No field changes (baseline entry).</div>
              )}
            </li>
          ))}
        </ol>
      )}
    </Modal>
  );
}
