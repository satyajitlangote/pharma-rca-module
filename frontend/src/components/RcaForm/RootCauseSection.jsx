import { useDispatch, useSelector } from "react-redux";
import { editItem, removeItem } from "../../store/rcaSlice";
import Badge from "../common/Badge";
import EmptyState from "../common/EmptyState";
import Section from "../common/Section";
import AcceptReject, { DeleteBtn, OriginBadge, ReviewBadge } from "./ReviewBits";

const CATEGORIES = [
  "Equipment/Metrology",
  "Material",
  "Method/Procedure",
  "Human factors",
  "Environment",
  "Quality system",
];

const CONFIDENCE = {
  High: "green",
  Medium: "amber",
  Low: "red",
};

/** Section 4 — synthesized root cause + contributing factors. */
export default function RootCauseSection() {
  const dispatch = useDispatch();
  const root = useSelector((s) => s.rca.draft.root_cause);
  const contributing = useSelector((s) => s.rca.draft.contributing_factors);

  const editRoot = (patch) => dispatch(editItem({ section: "root_cause", id: root?.id, patch }));
  const editCf = (id, patch) => dispatch(editItem({ section: "contributing_factors", id, patch }));

  return (
    <Section
      step={4}
      title="Root cause & contributing factors"
      subtitle="AI-suggested root cause — pending QP confirmation until a qualified person signs off"
    >
      {!root ? (
        <EmptyState
          title="No root cause yet"
          hint="Run the investigation — the root cause is synthesized from the causal chain and always carries its evidence."
        />
      ) : (
        <div className="print-block rounded-lg border border-slate-200 bg-white p-3">
          <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
            <div className="flex flex-wrap items-center gap-1.5">
              <OriginBadge item={root} />
              <ReviewBadge item={root} />
              <Badge tone={CONFIDENCE[root.confidence] || "slate"} title="Confidence (capped by evidence coverage)">
                {root.confidence} confidence
              </Badge>
              <Badge tone="slate">{root.category}</Badge>
            </div>
            <div className="flex items-center gap-1.5">
              <AcceptReject section="root_cause" item={root} />
              <DeleteBtn
                label="Remove root cause"
                onClick={() => dispatch(removeItem({ section: "root_cause", id: root.id }))}
              />
            </div>
          </div>

          <textarea
            value={root.primary_root_cause}
            rows={2}
            onChange={(e) => editRoot({ primary_root_cause: e.target.value })}
            className="mb-2 w-full resize-y rounded border border-transparent bg-slate-50 px-2 py-1.5 text-sm font-medium text-slate-800 hover:border-slate-200 focus:border-indigo-400 focus:bg-white focus:outline-none"
          />

          <div className="mb-2 grid gap-2 sm:grid-cols-2">
            <label className="text-[10px] font-semibold uppercase tracking-wide text-slate-400">
              Category
              <select
                value={root.category}
                onChange={(e) => editRoot({ category: e.target.value })}
                className="mt-0.5 block w-full rounded border border-slate-300 bg-white px-2 py-1.5 text-xs font-medium normal-case tracking-normal text-slate-700 focus:border-indigo-400 focus:outline-none"
              >
                {CATEGORIES.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            </label>
            <div>
              <div className="text-[10px] font-semibold uppercase tracking-wide text-slate-400">
                Root-cause candidate (fishbone)
              </div>
              <div className="mt-1 text-xs italic text-slate-600">“{root.label}”</div>
            </div>
          </div>

          <div className="rounded border-l-2 border-indigo-300 bg-indigo-50/50 px-2 py-1.5">
            <div className="text-[10px] font-semibold uppercase tracking-wide text-indigo-500">
              Justification (computed in code from verified steps)
            </div>
            <div className="mt-0.5 text-[11px] leading-snug text-slate-600">{root.justification}</div>
          </div>

          {(root.supporting_evidence || []).length > 0 && (
            <div className="mt-2">
              <div className="text-[10px] font-semibold uppercase tracking-wide text-slate-400">
                Supporting evidence (verbatim quotes verified in document)
              </div>
              <ul className="mt-1 space-y-1">
                {root.supporting_evidence.map((q, i) => (
                  <li
                    key={i}
                    className="rounded border-l-2 border-emerald-400 bg-emerald-50/60 px-2 py-1 font-mono text-[11px] leading-snug text-slate-600"
                  >
                    “{q}”
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      <div className="mt-4">
        <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">
          Contributing factors
        </div>
        {contributing.length === 0 ? (
          <p className="text-[11px] text-slate-400">None proposed.</p>
        ) : (
          <div className="space-y-2">
            {contributing.map((cf) => (
              <div
                key={cf.id}
                className={`print-block rounded border p-2 ${cf.review_state === "rejected" ? "border-rose-100 bg-rose-50/40 opacity-70" : "border-slate-200 bg-white"}`}
              >
                <div className="mb-1 flex flex-wrap items-center justify-between gap-2">
                  <div className="flex flex-wrap items-center gap-1.5">
                    <OriginBadge item={cf} />
                    <ReviewBadge item={cf} />
                    <Badge tone="slate">{cf.category}</Badge>
                    <Badge
                      tone={cf.supported ? "green" : "amber"}
                      title={
                        cf.evidence_quote
                          ? `“${cf.evidence_quote}”`
                          : "No verbatim evidence in the document"
                      }
                    >
                      {cf.supported ? "Document-supported" : "Needs investigation"}
                    </Badge>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <AcceptReject section="contributing_factors" item={cf} />
                    <DeleteBtn
                      onClick={() => dispatch(removeItem({ section: "contributing_factors", id: cf.id }))}
                    />
                  </div>
                </div>
                <textarea
                  value={cf.text}
                  rows={2}
                  onChange={(e) => editCf(cf.id, { text: e.target.value })}
                  className="w-full resize-y rounded border border-transparent bg-slate-50 px-2 py-1 text-xs text-slate-800 hover:border-slate-200 focus:border-indigo-400 focus:bg-white focus:outline-none"
                />
                {cf.evidence_quote && (
                  <div className="mt-1 rounded border-l-2 border-emerald-400 bg-emerald-50/60 px-2 py-1 font-mono text-[10px] leading-snug text-slate-500">
                    “{cf.evidence_quote}”
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </Section>
  );
}
