import { nanoid } from "@reduxjs/toolkit";
import { useDispatch, useSelector } from "react-redux";
import { addItem, editItem, removeItem } from "../../store/rcaSlice";
import Badge from "../common/Badge";
import EmptyState from "../common/EmptyState";
import Section from "../common/Section";
import AcceptReject, { DeleteBtn, OriginBadge, ReviewBadge } from "./ReviewBits";

const TYPE_TONE = { Corrective: "blue", Preventive: "purple" };

/** Section 6 — corrective and preventive actions (target dates are real calendar dates). */
export default function CapaSection() {
  const dispatch = useDispatch();
  const capas = useSelector((s) => s.rca.draft.capas);

  const edit = (id, patch) => dispatch(editItem({ section: "capas", id, patch }));
  const addCapa = () =>
    dispatch(
      addItem({
        section: "capas",
        item: {
          id: nanoid(10),
          type: "Corrective",
          description: "",
          linked_cause: "",
          rationale: "",
          owner_role: "",
          department: "",
          // Today + 30 days as a sensible human default (editable).
          target_date: new Date(Date.now() + 30 * 864e5).toISOString().slice(0, 10),
          voe_plan: "",
          status: "Proposed",
          origin: "user",
          review_state: "accepted",
        },
      })
    );

  return (
    <Section
      step={6}
      title="Corrective & Preventive Actions (CAPA)"
      subtitle="Every action links to a specific cause — target dates are computed from the real current date"
      actions={
        <button
          type="button"
          onClick={addCapa}
          className="rounded-lg border border-slate-300 px-2.5 py-1 text-xs font-medium text-slate-600 hover:border-indigo-400 hover:text-indigo-700"
        >
          + Add CAPA
        </button>
      }
    >
      {capas.length === 0 ? (
        <EmptyState
          title="No CAPAs yet"
          hint="Run the investigation — corrective and preventive actions are proposed with owners, due dates and VOE plans."
        />
      ) : (
        <div className="space-y-3">
          {capas.map((c) => {
            const rejected = c.review_state === "rejected";
            return (
              <div
                key={c.id}
                className={`print-block rounded-lg border p-3 ${rejected ? "border-rose-100 bg-rose-50/40 opacity-70" : "border-slate-200 bg-white"}`}
              >
                <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                  <div className="flex flex-wrap items-center gap-1.5">
                    <OriginBadge item={c} />
                    <ReviewBadge item={c} />
                    <Badge tone={TYPE_TONE[c.type] || "slate"}>{c.type}</Badge>
                    <Badge tone="slate">{c.status}</Badge>
                    <Badge tone="slate" title="Target completion date">
                      due {c.target_date}
                    </Badge>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <AcceptReject section="capas" item={c} />
                    <DeleteBtn onClick={() => dispatch(removeItem({ section: "capas", id: c.id }))} />
                  </div>
                </div>

                <textarea
                  value={c.description}
                  rows={2}
                  onChange={(e) => edit(c.id, { description: e.target.value })}
                  placeholder="Action description"
                  className="mb-2 w-full resize-y rounded border border-transparent bg-slate-50 px-2 py-1.5 text-sm font-medium text-slate-800 hover:border-slate-200 focus:border-indigo-400 focus:bg-white focus:outline-none"
                />

                <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
                  <label className="text-[10px] font-semibold uppercase tracking-wide text-slate-400">
                    Type
                    <select
                      value={c.type}
                      onChange={(e) => edit(c.id, { type: e.target.value })}
                      className="mt-0.5 block w-full rounded border border-slate-300 bg-white px-2 py-1.5 text-xs normal-case tracking-normal text-slate-700 focus:border-indigo-400 focus:outline-none"
                    >
                      <option>Corrective</option>
                      <option>Preventive</option>
                    </select>
                  </label>
                  <label className="text-[10px] font-semibold uppercase tracking-wide text-slate-400">
                    Owner role
                    <input
                      value={c.owner_role}
                      onChange={(e) => edit(c.id, { owner_role: e.target.value })}
                      className="mt-0.5 block w-full rounded border border-slate-300 px-2 py-1.5 text-xs normal-case tracking-normal text-slate-700 focus:border-indigo-400 focus:outline-none"
                    />
                  </label>
                  <label className="text-[10px] font-semibold uppercase tracking-wide text-slate-400">
                    Department
                    <input
                      value={c.department}
                      onChange={(e) => edit(c.id, { department: e.target.value })}
                      className="mt-0.5 block w-full rounded border border-slate-300 px-2 py-1.5 text-xs normal-case tracking-normal text-slate-700 focus:border-indigo-400 focus:outline-none"
                    />
                  </label>
                  <label className="text-[10px] font-semibold uppercase tracking-wide text-slate-400">
                    Target date
                    <input
                      type="date"
                      value={c.target_date}
                      onChange={(e) => edit(c.id, { target_date: e.target.value })}
                      className="mt-0.5 block w-full rounded border border-slate-300 px-2 py-1.5 text-xs normal-case tracking-normal text-slate-700 focus:border-indigo-400 focus:outline-none"
                    />
                  </label>
                </div>

                <div className="mt-2 grid gap-2 sm:grid-cols-2">
                  <div>
                    <div className="text-[10px] font-semibold uppercase tracking-wide text-slate-400">
                      Linked cause (traceability)
                    </div>
                    <textarea
                      value={c.linked_cause}
                      rows={2}
                      onChange={(e) => edit(c.id, { linked_cause: e.target.value })}
                      className="mt-0.5 w-full resize-y rounded border border-slate-200 bg-slate-50/60 px-2 py-1.5 text-xs text-slate-700 focus:border-indigo-400 focus:bg-white focus:outline-none"
                    />
                  </div>
                  <div>
                    <div className="text-[10px] font-semibold uppercase tracking-wide text-slate-400">
                      Rationale
                    </div>
                    <textarea
                      value={c.rationale}
                      rows={2}
                      onChange={(e) => edit(c.id, { rationale: e.target.value })}
                      className="mt-0.5 w-full resize-y rounded border border-slate-200 bg-slate-50/60 px-2 py-1.5 text-xs text-slate-700 focus:border-indigo-400 focus:bg-white focus:outline-none"
                    />
                  </div>
                </div>

                <div className="mt-2">
                  <div className="text-[10px] font-semibold uppercase tracking-wide text-slate-400">
                    Verification of Effectiveness (VOE) plan
                  </div>
                  <textarea
                    value={c.voe_plan}
                    rows={2}
                    onChange={(e) => edit(c.id, { voe_plan: e.target.value })}
                    className="mt-0.5 w-full resize-y rounded border border-slate-200 bg-slate-50/60 px-2 py-1.5 text-xs text-slate-700 focus:border-indigo-400 focus:bg-white focus:outline-none"
                  />
                </div>
              </div>
            );
          })}
        </div>
      )}
    </Section>
  );
}
