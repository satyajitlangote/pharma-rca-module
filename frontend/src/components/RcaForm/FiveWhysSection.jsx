import { nanoid } from "@reduxjs/toolkit";
import { useDispatch, useSelector } from "react-redux";
import { addItem, editItem, removeItem } from "../../store/rcaSlice";
import { quoteInSource } from "../../lib/evidence";
import Badge from "../common/Badge";
import EmptyState from "../common/EmptyState";
import Section from "../common/Section";
import AcceptReject, { DeleteBtn, OriginBadge, ReviewBadge } from "./ReviewBits";

const STATUS = {
  Supported: ["green", "Supported — quote verified in document"],
  Hypothesis: ["amber", "Hypothesis — not verified in document"],
};

/** Section 2 — 5 Whys chain with per-step evidence verification badges. */
export default function FiveWhysSection() {
  const dispatch = useDispatch();
  const whys = useSelector((s) => s.rca.draft.five_whys);
  const source = useSelector((s) => s.rca.draft.source_document_text);

  const edit = (id, patch) => dispatch(editItem({ section: "five_whys", id, patch }));
  const editQuote = (id, quote) => {
    // Status is recomputed in code — it can only be Supported if the quote exists.
    const status = quote && quoteInSource(quote, source) ? "Supported" : "Hypothesis";
    edit(id, { evidence_quote: quote, status });
  };
  const addStep = () =>
    dispatch(
      addItem({
        section: "five_whys",
        item: {
          id: nanoid(10),
          level: whys.length + 1,
          question: "",
          answer: "",
          evidence_quote: null,
          status: "Hypothesis",
          origin: "user",
          review_state: "accepted",
        },
      })
    );

  return (
    <Section
      step={2}
      title="5 Whys chain"
      subtitle="Each step carries its evidence quote; status is set by code, not by the model"
      actions={
        <button
          type="button"
          onClick={addStep}
          className="rounded-lg border border-slate-300 px-2.5 py-1 text-xs font-medium text-slate-600 hover:border-indigo-400 hover:text-indigo-700"
        >
          + Add step
        </button>
      }
    >
      {whys.length === 0 ? (
        <EmptyState
          title="No causal chain yet"
          hint="Run the investigation in the AI panel — 3 to 6 steps are proposed depending on the evidence."
        />
      ) : (
        <ol className="space-y-3">
          {whys.map((w, index) => {
            const [tone, statusLabel] = STATUS[w.status] || STATUS.Hypothesis;
            const rejected = w.review_state === "rejected";
            return (
              <li
                key={w.id}
                className={`print-block rounded-lg border p-3 ${rejected ? "border-rose-100 bg-rose-50/40 opacity-70" : "border-slate-200 bg-white"}`}
              >
                <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-1.5">
                    <span className="flex h-5 w-5 items-center justify-center rounded-full bg-indigo-50 text-[11px] font-bold text-indigo-700">
                      {index + 1}
                    </span>
                    <span className="text-xs font-semibold text-slate-700">Why?</span>
                    <OriginBadge item={w} />
                    <ReviewBadge item={w} />
                    <Badge tone={tone} title={statusLabel}>
                      {w.status}
                    </Badge>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <AcceptReject section="five_whys" item={w} />
                    <DeleteBtn onClick={() => dispatch(removeItem({ section: "five_whys", id: w.id }))} />
                  </div>
                </div>

                <div className="grid gap-2">
                  <input
                    value={w.question}
                    onChange={(e) => edit(w.id, { question: e.target.value })}
                    placeholder="Why did this happen?"
                    className="w-full rounded border border-transparent bg-slate-50 px-2 py-1.5 text-sm text-slate-800 hover:border-slate-200 focus:border-indigo-400 focus:bg-white focus:outline-none"
                  />
                  <textarea
                    value={w.answer}
                    rows={2}
                    onChange={(e) => edit(w.id, { answer: e.target.value })}
                    placeholder="Answer grounded in the document"
                    className="w-full resize-y rounded border border-transparent bg-slate-50 px-2 py-1.5 text-sm text-slate-800 hover:border-slate-200 focus:border-indigo-400 focus:bg-white focus:outline-none"
                  />
                  <div>
                    <label className="mb-0.5 block text-[10px] font-semibold uppercase tracking-wide text-slate-400">
                      Evidence quote
                    </label>
                    <div
                      className={`rounded border-l-2 px-2 py-1.5 ${w.status === "Supported" ? "border-emerald-400 bg-emerald-50/60" : "border-amber-400 bg-amber-50/60"}`}
                    >
                      <textarea
                        value={w.evidence_quote || ""}
                        rows={2}
                        onChange={(e) => editQuote(w.id, e.target.value)}
                        placeholder="Verbatim quote from the source document (edit to update status)"
                        className="w-full resize-y bg-transparent font-mono text-[11px] leading-snug text-slate-600 focus:outline-none"
                      />
                      <div className={`mt-0.5 text-[10px] ${w.status === "Supported" ? "text-emerald-700" : "text-amber-700"}`}>
                        {w.status === "Supported" ? "✓ " : "⚠ "}
                        {statusLabel}
                      </div>
                    </div>
                  </div>
                </div>
              </li>
            );
          })}
        </ol>
      )}
    </Section>
  );
}
