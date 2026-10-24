import { useEffect } from "react";
import { useDispatch, useSelector } from "react-redux";
import {
  fetchHealth,
  fetchSamples,
  loadAudit,
  openedModal,
  selectAiBanner,
  selectHealth,
  selectPendingAiCount,
  selectSqliteBanner,
  setNotice,
} from "./store/rcaSlice";
import Banner from "./components/common/Banner";
import AiPanel from "./components/AiPanel/AiPanel";
import RcaForm from "./components/RcaForm/RcaForm";
import SavedListModal from "./components/Modals/SavedListModal";
import SignoffModal from "./components/Modals/SignoffModal";
import AuditModal from "./components/Modals/AuditModal";

const BTN =
  "rounded-lg border border-slate-300 px-2.5 py-1.5 text-xs font-medium text-slate-600 hover:border-slate-400 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50";

/**
 * App shell: two-column RCA screen (form left, sticky AI panel right) with a
 * top toolbar (save list / sign-off / audit / print) and the two global
 * banners (SQLite fallback, AI unavailable).
 */
export default function App() {
  const dispatch = useDispatch();
  const health = useSelector(selectHealth);
  const sqliteBanner = useSelector(selectSqliteBanner);
  const aiBanner = useSelector(selectAiBanner);
  const notice = useSelector((s) => s.rca.ui.notice);
  const draft = useSelector((s) => s.rca.draft);
  const pending = useSelector(selectPendingAiCount);

  useEffect(() => {
    dispatch(fetchHealth());
    dispatch(fetchSamples());
  }, [dispatch]);

  // Poll health occasionally: catches a server restart / key change live.
  useEffect(() => {
    const t = setInterval(() => dispatch(fetchHealth()), 30_000);
    return () => clearInterval(t);
  }, [dispatch]);

  const canSignoff = !!draft.id && !draft.is_qp_verified;

  return (
    <div className="mx-auto min-h-screen max-w-[1500px] px-4 py-3">
      {/* ---------- top bar ---------- */}
      <header className="no-print mb-3 rounded-xl bg-slate-900 px-4 py-3 text-white shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-base font-semibold tracking-tight">
              AIVOA · Root Cause Analysis
            </h1>
            <p className="text-[11px] text-slate-300">
              Deviation → RCA → CAPA · every AI claim carries a verbatim evidence quote · QP
              sign-off required
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <span
              className={`rounded-full border px-2 py-0.5 text-[10px] font-medium ${
                health.status === "ok"
                  ? "border-emerald-500 bg-emerald-500/10 text-emerald-300"
                  : "border-rose-400 bg-rose-500/10 text-rose-300"
              }`}
              title={
                health.data
                  ? `DB: ${health.data.dialect} · Groq: ${health.data.groq_configured ? "configured" : "NOT configured"}`
                  : health.error || "checking…"
              }
            >
              {health.status === "ok"
                ? `API ok · ${health.data?.dialect || "?"}`
                : health.status === "loading"
                  ? "checking…"
                  : "API down"}
            </span>
            <button type="button" className={BTN} onClick={() => dispatch(openedModal("list"))}>
              Saved
            </button>
            <button
              type="button"
              className={BTN}
              disabled={!draft.id}
              title={draft.id ? "" : "Save the investigation first"}
              onClick={() => dispatch(loadAudit(draft.id))}
            >
              Audit trail
            </button>
            <button
              type="button"
              className={BTN}
              onClick={() => window.print()}
              title="Print / export PDF of the RCA record"
            >
              Print
            </button>
            <button
              type="button"
              disabled={!canSignoff}
              onClick={() => dispatch(openedModal("signoff"))}
              title={
                draft.is_qp_verified
                  ? "Signed — use Reopen in this dialog"
                  : pending > 0
                    ? `${pending} AI item(s) pending review — review them before sign-off`
                    : !draft.id
                      ? "Save the investigation first"
                      : "Request QP sign-off"
              }
              className="rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-emerald-700 disabled:cursor-not-allowed disabled:bg-slate-600"
            >
              {draft.is_qp_verified ? "Reopen…" : "QP sign-off"}
            </button>
          </div>
        </div>
      </header>

      {/* ---------- global banners ---------- */}
      {(sqliteBanner || aiBanner || notice) && (
        <div className="no-print mb-3 space-y-2">
          {sqliteBanner && <Banner tone="amber" title="Development fallback">{sqliteBanner}</Banner>}
          {aiBanner && <Banner tone="red" title="AI unavailable">{aiBanner}</Banner>}
          {notice && (
            <Banner
              tone={notice.tone === "ok" ? "green" : "blue"}
              onClose={() => dispatch(setNotice(null))}
            >
              {notice.text}
            </Banner>
          )}
        </div>
      )}

      {/* ---------- two-column layout ---------- */}
      <div className="app-grid grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1fr)_400px]">
        <RcaForm />
        <div className="no-print lg:sticky lg:top-3 lg:self-start">
          <AiPanel />
        </div>
      </div>

      {/* ---------- modals ---------- */}
      <SavedListModal />
      <SignoffModal />
      <AuditModal />
    </div>
  );
}
