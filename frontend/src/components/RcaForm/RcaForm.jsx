import { useDispatch, useSelector } from "react-redux";
import {
  acceptAllAi,
  resetDraft,
  saveInvestigation,
  selectPendingAiCount,
  setNotice,
} from "../../store/rcaSlice";
import Badge from "../common/Badge";
import Spinner from "../common/Spinner";
import DeviationSection from "./DeviationSection";
import FiveWhysSection from "./FiveWhysSection";
import FishboneSection from "./FishboneSection";
import RootCauseSection from "./RootCauseSection";
import MissingEvidenceSection from "./MissingEvidenceSection";
import CapaSection from "./CapaSection";
import { PendingChip } from "./ReviewBits";

/**
 * The full RCA form (left column). Sections 1-2 come from the document /
 * investigator, 3-6 from the investigation. AI items stay "pending" until
 * reviewed; QP sign-off is blocked while any remain (see Toolbar/SignoffModal).
 */
export default function RcaForm() {
  const dispatch = useDispatch();
  const draft = useSelector((s) => s.rca.draft);
  const pending = useSelector(selectPendingAiCount);
  const saving = useSelector((s) => s.rca.list.saving);
  const saveError = useSelector((s) => s.rca.list.saveError);

  const onSave = () => dispatch(saveInvestigation({ actorType: "User" }));
  const onNew = () => {
    dispatch(resetDraft());
    dispatch(setNotice({ tone: "ok", text: "Started a new investigation." }));
  };

  return (
    <div className="space-y-4">
      {/* sticky action bar: save state + review management */}
      <div className="no-print sticky top-0 z-20 flex flex-wrap items-center justify-between gap-2 rounded-xl border border-slate-200 bg-white/95 px-3 py-2 shadow-sm backdrop-blur">
        <div className="flex flex-wrap items-center gap-2">
          <PendingChip count={pending} />
          {draft.id ? (
            <span className="font-mono text-[11px] text-slate-400">
              #{String(draft.id).slice(0, 8)} · {draft.status}
            </span>
          ) : (
            <span className="text-[11px] text-slate-400">not saved yet</span>
          )}
          {saving && <Spinner />}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {pending > 0 && (
            <button
              type="button"
              onClick={() => dispatch(acceptAllAi())}
              className="rounded-lg border border-emerald-300 px-2.5 py-1 text-xs font-medium text-emerald-700 hover:bg-emerald-50"
            >
              Accept all AI items
            </button>
          )}
          <button
            type="button"
            onClick={onNew}
            className="rounded-lg border border-slate-300 px-2.5 py-1 text-xs font-medium text-slate-600 hover:border-slate-400"
          >
            New
          </button>
          <button
            type="button"
            onClick={onSave}
            disabled={saving}
            className="rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-indigo-700 disabled:opacity-50"
          >
            {saving ? "Saving…" : "Save"}
          </button>
        </div>
      </div>

      {saveError && (
        <div className="rounded-lg border border-rose-300 bg-rose-50 px-3 py-2 text-xs text-rose-800">
          Save failed: {saveError}
        </div>
      )}

      {draft.is_qp_verified && (
        <div className="rounded-lg border border-emerald-300 bg-emerald-50 px-3 py-2 text-xs text-emerald-900">
          <Badge tone="green">QP verified</Badge>
          <span className="ml-2">
            Signed by {draft.qp_name} ({draft.qp_role}) on{" "}
            {draft.qp_signed_at ? new Date(draft.qp_signed_at).toLocaleString() : "—"} — this record is
            locked. Use “Reopen” (audited) to make changes.
          </span>
        </div>
      )}

      <DeviationSection />
      <FiveWhysSection />
      <FishboneSection />
      <RootCauseSection />
      <MissingEvidenceSection />
      <CapaSection />
    </div>
  );
}
