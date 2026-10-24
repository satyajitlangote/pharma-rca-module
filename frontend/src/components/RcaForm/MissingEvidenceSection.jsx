import { nanoid } from "@reduxjs/toolkit";
import { useDispatch, useSelector } from "react-redux";
import { addItem, editItem, removeItem } from "../../store/rcaSlice";
import Badge from "../common/Badge";
import EmptyState from "../common/EmptyState";
import Section from "../common/Section";
import AcceptReject, { DeleteBtn, OriginBadge, ReviewBadge } from "./ReviewBits";

const PRIORITIES = { High: "red", Medium: "amber", Low: "slate" };

/** Section 5 — evidence gaps (what the document does NOT contain). */
export default function MissingEvidenceSection() {
  const dispatch = useDispatch();
  const gaps = useSelector((s) => s.rca.draft.missing_evidence);

  const edit = (id, patch) => dispatch(editItem({ section: "missing_evidence", id, patch }));
  const addGap = () =>
    dispatch(
      addItem({
        section: "missing_evidence",
        item: {
          id: nanoid(10),
          item: "",
          why_needed: "",
          suggested_action: "",
          priority: "Medium",
          status: "Missing",
          origin: "user",
          review_state: "accepted",
        },
      })
    );

  return (
    <Section
      step={5}
      title="Evidence gaps"
      subtitle="Only evidence genuinely absent from the document — already-present items are dropped in code"
      actions={
        <button
          type="button"
          onClick={addGap}
          className="rounded-lg border border-slate-300 px-2.5 py-1 text-xs font-medium text-slate-600 hover:border-indigo-400 hover:text-indigo-700"
        >
          + Add gap
        </button>
      }
    >
      {gaps.length === 0 ? (
        <EmptyState
          title="No evidence gaps listed"
          hint="The investigation lists every evidence type needed to confirm or refute the root cause."
        />
      ) : (
        <div className="space-y-2">
          {gaps.map((g) => (
            <div
              key={g.id}
              className={`print-block rounded-lg border p-3 ${g.review_state === "rejected" ? "border-rose-100 bg-rose-50/40 opacity-70" : "border-slate-200 bg-white"}`}
            >
              <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                <div className="flex flex-wrap items-center gap-1.5">
                  <OriginBadge item={g} />
                  <ReviewBadge item={g} />
                  <Badge tone={PRIORITIES[g.priority] || "slate"}>{g.priority} priority</Badge>
                  <Badge tone="amber">{g.status}</Badge>
                </div>
                <div className="flex items-center gap-1.5">
                  <AcceptReject section="missing_evidence" item={g} />
                  <DeleteBtn onClick={() => dispatch(removeItem({ section: "missing_evidence", id: g.id }))} />
                </div>
              </div>
              <input
                value={g.item}
                onChange={(e) => edit(g.id, { item: e.target.value })}
                placeholder="Evidence needed (e.g. HPLC sequence / audit trail)"
                className="mb-1.5 w-full rounded border border-transparent bg-slate-50 px-2 py-1.5 text-sm font-medium text-slate-800 hover:border-slate-200 focus:border-indigo-400 focus:bg-white focus:outline-none"
              />
              <textarea
                value={g.why_needed}
                rows={2}
                onChange={(e) => edit(g.id, { why_needed: e.target.value })}
                placeholder="Why this evidence is needed"
                className="mb-1.5 w-full resize-y rounded border border-transparent bg-slate-50 px-2 py-1.5 text-xs text-slate-700 hover:border-slate-200 focus:border-indigo-400 focus:bg-white focus:outline-none"
              />
              <textarea
                value={g.suggested_action}
                rows={2}
                onChange={(e) => edit(g.id, { suggested_action: e.target.value })}
                placeholder="Suggested action to obtain it"
                className="w-full resize-y rounded border border-transparent bg-slate-50 px-2 py-1.5 text-xs text-slate-700 hover:border-slate-200 focus:border-indigo-400 focus:bg-white focus:outline-none"
              />
            </div>
          ))}
        </div>
      )}
    </Section>
  );
}
