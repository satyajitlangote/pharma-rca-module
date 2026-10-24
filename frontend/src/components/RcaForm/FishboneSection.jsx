import { nanoid } from "@reduxjs/toolkit";
import { useDispatch, useSelector } from "react-redux";
import { addItem, editItem, removeItem } from "../../store/rcaSlice";
import { quoteInSource } from "../../lib/evidence";
import EmptyState from "../common/EmptyState";
import Section from "../common/Section";
import AcceptReject, { DeleteBtn, OriginBadge, ReviewBadge } from "./ReviewBits";

const SIX_M = [
  ["Man", "people, training, human factors"],
  ["Machine", "equipment, utilities, maintenance"],
  ["Material", "starting materials, packaging, solvents"],
  ["Method", "procedure, recipe, parameters"],
  ["Measurement", "analytical method, calibration, sampling"],
  ["Environment", "facility, utilities, conditions"],
];

/** Section 3 — interactive Fishbone (Ishikawa) 6M diagram. */
export default function FishboneSection() {
  const dispatch = useDispatch();
  const factors = useSelector((s) => s.rca.draft.fishbone.factors);
  const source = useSelector((s) => s.rca.draft.source_document_text);

  const edit = (id, patch) => dispatch(editItem({ section: "fishbone", id, patch }));
  const editQuote = (id, quote) => {
    const supported = !!quote && quoteInSource(quote, source);
    edit(id, {
      evidence_quote: quote,
      supported_by_document: supported,
      label: supported ? "Document-supported" : "Needs investigation",
      // a factor can only be a root-cause candidate when the document supports it
      ...(supported ? {} : { root_cause_candidate: false }),
    });
  };
  const addFactor = (category) =>
    dispatch(
      addItem({
        section: "fishbone",
        item: {
          id: nanoid(10),
          category,
          cause: "",
          subcauses: [],
          impact: "",
          evidence_quote: null,
          supported_by_document: false,
          label: "Needs investigation",
          root_cause_candidate: false,
          origin: "user",
          review_state: "accepted",
        },
      })
    );

  const supportedCount = factors.filter((f) => f.supported_by_document).length;

  return (
    <Section
      step={3}
      title="Fishbone / Ishikawa — 6M"
      subtitle={`${factors.length} factors · ${supportedCount} document-supported · unsupported ones stay "Needs investigation"`}
      actions={
        <span className="text-[11px] text-slate-400">★ = root-cause candidate</span>
      }
    >
      {factors.length === 0 ? (
        <EmptyState title="No fishbone factors yet" hint="Run the investigation to map causes across the 6M categories." />
      ) : (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {SIX_M.map(([category, hint]) => {
            const own = factors.filter((f) => f.category === category);
            return (
              <div key={category} className="print-block flex flex-col rounded-lg border border-slate-200 bg-slate-50/60">
                <div className="flex items-center justify-between rounded-t-lg border-b border-slate-200 bg-white px-2.5 py-1.5">
                  <div>
                    <span className="text-xs font-bold text-indigo-700">{category}</span>
                    <span className="ml-1.5 text-[9px] uppercase tracking-wide text-slate-400">M</span>
                    <div className="text-[9px] text-slate-400">{hint}</div>
                  </div>
                  <button
                    type="button"
                    onClick={() => addFactor(category)}
                    className="rounded border border-slate-300 px-1.5 py-0.5 text-[11px] font-medium text-slate-500 hover:border-indigo-400 hover:text-indigo-700"
                    title={`Add ${category} factor`}
                  >
                    + Add
                  </button>
                </div>

                <div className="flex-1 space-y-2 p-2">
                  {own.length === 0 && (
                    <div className="py-2 text-center text-[10px] text-slate-400">no factors</div>
                  )}
                  {own.map((f) => {
                    const rejected = f.review_state === "rejected";
                    return (
                      <div
                        key={f.id}
                        className={`rounded border bg-white p-2 ${rejected ? "border-rose-100 opacity-70" : f.supported_by_document ? "border-emerald-200" : "border-amber-200"}`}
                      >
                        <div className="mb-1 flex items-center justify-between gap-1">
                          <div className="flex flex-wrap items-center gap-1">
                            <OriginBadge item={f} />
                            <ReviewBadge item={f} />
                            <span
                              className={`rounded-full border px-1.5 py-0.5 text-[9px] font-medium ${f.supported_by_document ? "border-emerald-200 bg-emerald-50 text-emerald-700" : "border-amber-200 bg-amber-50 text-amber-700"}`}
                              title={f.evidence_quote ? `“${f.evidence_quote}”` : "No supporting quote in the document"}
                            >
                              {f.label}
                            </span>
                          </div>
                          <div className="flex items-center gap-1">
                            <button
                              type="button"
                              onClick={() => edit(f.id, { root_cause_candidate: !f.root_cause_candidate })}
                              title="Mark as root-cause candidate"
                              className={`text-sm ${f.root_cause_candidate ? "text-amber-500" : "text-slate-300 hover:text-amber-400"}`}
                            >
                              ★
                            </button>
                            <DeleteBtn onClick={() => dispatch(removeItem({ section: "fishbone", id: f.id }))} />
                          </div>
                        </div>

                        <input
                          value={f.cause}
                          onChange={(e) => edit(f.id, { cause: e.target.value })}
                          placeholder="Cause"
                          className="mb-1 w-full rounded border border-transparent bg-slate-50 px-1.5 py-1 text-xs font-medium text-slate-800 hover:border-slate-200 focus:border-indigo-400 focus:bg-white focus:outline-none"
                        />
                        <input
                          value={(f.subcauses || []).join(", ")}
                          onChange={(e) =>
                            edit(f.id, {
                              subcauses: e.target.value.split(",").map((s) => s.trim()).filter(Boolean),
                            })
                          }
                          placeholder="Sub-causes (comma separated)"
                          className="mb-1 w-full rounded border border-transparent bg-slate-50 px-1.5 py-1 text-[11px] text-slate-600 hover:border-slate-200 focus:border-indigo-400 focus:bg-white focus:outline-none"
                        />
                        <input
                          value={f.impact}
                          onChange={(e) => edit(f.id, { impact: e.target.value })}
                          placeholder="Impact"
                          className="w-full rounded border border-transparent bg-slate-50 px-1.5 py-1 text-[11px] text-slate-600 hover:border-slate-200 focus:border-indigo-400 focus:bg-white focus:outline-none"
                        />
                        <textarea
                          value={f.evidence_quote || ""}
                          rows={2}
                          onChange={(e) => editQuote(f.id, e.target.value)}
                          placeholder="Evidence quote (verbatim from document)"
                          className="mt-1 w-full resize-y rounded border border-slate-200 bg-slate-50/60 px-1.5 py-1 font-mono text-[10px] leading-snug text-slate-500 focus:border-indigo-400 focus:bg-white focus:outline-none"
                        />
                        <div className="mt-1">
                          <AcceptReject section="fishbone" item={f} />
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </Section>
  );
}
