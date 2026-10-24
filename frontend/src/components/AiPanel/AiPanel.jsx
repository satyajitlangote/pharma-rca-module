import { useState } from "react";
import { useDispatch, useSelector } from "react-redux";
import {
  abortAnalysis,
  applyToForm,
  extractDocument,
  fileChanged,
  modelChanged,
  runAnalysis,
  sampleLoaded,
  selectAiBanner,
  selectHealth,
  selectNodeLabels,
  tabChanged,
  testAiKey,
  textChanged,
  keyTestDismissed,
} from "../../store/rcaSlice";
import Banner from "../common/Banner";
import Badge from "../common/Badge";
import Spinner from "../common/Spinner";
import ExtractPreview from "./ExtractPreview";
import Stepper from "./Stepper";

const TABS = [
  ["pdf", "Upload PDF"],
  ["text", "Paste text"],
  ["email", "Paste email"],
];

const MODELS = [
  { value: "openai/gpt-oss-20b", label: "gpt-oss-20b (default, verified)" },
  { value: "openai/gpt-oss-120b", label: "gpt-oss-120b (larger)" },
  { value: "qwen/qwen3.8-27b", label: "qwen3.8-27b" },
];

/**
 * AI Copilot panel (right column, sticky).
 * Workflow: give document -> Extract (preview) -> Apply to form -> Run investigation.
 * Every failure path shows a banner and LEAVES THE FORM UNTOUCHED.
 */
export default function AiPanel() {
  const dispatch = useDispatch();
  const input = useSelector((s) => s.rca.input);
  const extraction = useSelector((s) => s.rca.extraction);
  const analysis = useSelector((s) => s.rca.analysis);
  const samples = useSelector((s) => s.rca.samples);
  const health = useSelector(selectHealth);
  const aiBanner = useSelector(selectAiBanner);
  const keyTest = useSelector((s) => s.rca.ui.keyTest);
  const hasDocument = useSelector((s) => !!s.rca.draft.source_document_text);
  const labels = useSelector(selectNodeLabels);
  const [keyBusy, setKeyBusy] = useState(false);

  const extracting = extraction.status === "loading";
  const running = analysis.status === "running";
  const canExtract = !!input.file || !!input.text.trim();
  const steps = analysis.steps.map((s) => ({ ...s, label: labels[s.node] || s.node }));

  const onExtract = () => dispatch(extractDocument()).unwrap().catch(() => {});
  const onApply = () => dispatch(applyToForm()).unwrap().catch(() => {});
  const onRun = () => dispatch(runAnalysis()).unwrap().catch(() => {});
  const onKeyTest = async () => {
    setKeyBusy(true);
    await dispatch(testAiKey(input.model));
    setKeyBusy(false);
  };
  const loadSample = (s) =>
    dispatch(sampleLoaded({ tab: s.tab, text: s.text, docName: s.filename, label: s.label }));

  return (
    <div className="flex max-h-[calc(100vh-6.5rem)] flex-col overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
      {/* header */}
      <div className="no-print flex items-center justify-between gap-2 border-b border-slate-200 bg-slate-800 px-3 py-2.5 text-white">
        <div>
          <div className="text-sm font-semibold">AI Copilot</div>
          <div className="text-[10px] text-slate-300">Extraction → analysis → CAPA suggestions</div>
        </div>
        <select
          value={input.model}
          onChange={(e) => dispatch(modelChanged(e.target.value))}
          title="AI model (allowlisted server-side)"
          className="rounded border border-slate-600 bg-slate-700 px-1.5 py-1 text-[11px] text-white focus:outline-none"
        >
          {MODELS.map((m) => (
            <option key={m.value} value={m.value}>
              {m.label}
            </option>
          ))}
        </select>
      </div>

      <div className="min-h-0 flex-1 space-y-3 overflow-y-auto p-3">
        {aiBanner && (
          <Banner tone="red" title="AI unavailable">
            {aiBanner}
          </Banner>
        )}

        {keyTest && (
          <Banner tone={keyTest.ok ? "green" : "red"} onClose={() => dispatch(keyTestDismissed())} title="Connection test">
            {keyTest.detail}
          </Banner>
        )}

        {/* --- 1. document input --- */}
        <div className="text-xs font-semibold uppercase tracking-wide text-slate-400">1 · Give the document</div>

        <div className="no-print flex gap-1 rounded-lg bg-slate-100 p-1">
          {TABS.map(([id, label]) => (
            <button
              key={id}
              type="button"
              onClick={() => dispatch(tabChanged(id))}
              className={`flex-1 rounded-md px-2 py-1.5 text-xs font-medium transition ${
                input.tab === id ? "bg-white text-indigo-700 shadow" : "text-slate-500 hover:text-slate-700"
              }`}
            >
              {label}
            </button>
          ))}
        </div>

        {input.tab === "pdf" && (
          <div className="rounded-lg border border-dashed border-slate-300 bg-slate-50 p-3 text-center">
            <input
              type="file"
              accept=".pdf,application/pdf"
              onChange={(e) => dispatch(fileChanged(e.target.files?.[0] || null))}
              className="no-print block w-full text-xs text-slate-600 file:mr-2 file:rounded file:border-0 file:bg-indigo-600 file:px-2 file:py-1 file:text-xs file:font-medium file:text-white"
            />
            <div className="mt-1.5 text-[10px] text-slate-500">
              PDF only · scanned/image-only PDFs are not supported
              {input.docName && <span className="ml-1 font-medium text-slate-700">({input.docName})</span>}
            </div>
          </div>
        )}

        {input.tab === "text" && (
          <textarea
            rows={9}
            value={input.text}
            onChange={(e) => dispatch(textChanged(e.target.value))}
            placeholder="Paste the incident / investigation document text here…"
            className="w-full resize-y rounded-lg border border-slate-300 bg-white p-2.5 font-mono text-xs text-slate-800 focus:border-indigo-400 focus:outline-none focus:ring-1 focus:ring-indigo-300"
          />
        )}

        {input.tab === "email" && (
          <div className="space-y-2">
            <div className="rounded-lg border border-dashed border-slate-300 bg-slate-50 p-2.5 text-center">
              <input
                type="file"
                accept=".eml,message/rfc822"
                onChange={(e) => dispatch(fileChanged(e.target.files?.[0] || null))}
                className="block w-full text-xs text-slate-600 file:mr-2 file:rounded file:border-0 file:bg-indigo-600 file:px-2 file:py-1 file:text-xs file:font-medium file:text-white"
              />
              <div className="mt-1 text-[10px] text-slate-500">…or paste the full email below</div>
            </div>
            <textarea
              rows={8}
              value={input.text}
              onChange={(e) => dispatch(textChanged(e.target.value))}
              placeholder={"From: …\nSubject: …\nDate: …\n\n<body>"}
              className="w-full resize-y rounded-lg border border-slate-300 bg-white p-2.5 font-mono text-xs text-slate-800 focus:border-indigo-400 focus:outline-none focus:ring-1 focus:ring-indigo-300"
            />
          </div>
        )}

        {input.sampleLabel && (
          <div className="text-[10px] text-slate-500">Sample loaded: {input.sampleLabel} (fill only — nothing ran yet)</div>
        )}

        {extraction.error && (
          <div className="rounded-lg border border-rose-300 bg-rose-50 px-3 py-2 text-xs text-rose-800">
            {extraction.error}
          </div>
        )}

        <button
          type="button"
          onClick={onExtract}
          disabled={!canExtract || extracting}
          className="flex w-full items-center justify-center gap-2 rounded-lg bg-indigo-600 px-3 py-2 text-sm font-semibold text-white hover:bg-indigo-700 disabled:cursor-not-allowed disabled:bg-slate-300"
        >
          {extracting && <Spinner />}
          {extracting ? "Extracting…" : "Extract"}
        </button>

        <ExtractPreview data={extraction.data} applied={extraction.applied} />

        {extraction.data && (
          <button
            type="button"
            onClick={onApply}
            disabled={extraction.applied}
            className="w-full rounded-lg border border-indigo-600 px-3 py-2 text-sm font-semibold text-indigo-700 hover:bg-indigo-50 disabled:cursor-not-allowed disabled:border-slate-200 disabled:text-slate-400"
          >
            {extraction.applied ? "✓ Applied to form" : "Apply to form"}
          </button>
        )}

        {/* --- 2. run investigation --- */}
        <div className="no-print border-t border-slate-100 pt-3 text-xs font-semibold uppercase tracking-wide text-slate-400">
          2 · Run investigation
        </div>

        <div className="flex gap-2">
          <button
            type="button"
            onClick={onRun}
            disabled={running || !hasDocument}
            className="flex-1 rounded-lg bg-slate-900 px-3 py-2 text-sm font-semibold text-white hover:bg-slate-700 disabled:cursor-not-allowed disabled:bg-slate-300"
            title={hasDocument ? "" : "Extract & apply a document first"}
          >
            {running ? "Running…" : "Run investigation"}
          </button>
          {running && (
            <button
              type="button"
              onClick={() => dispatch(abortAnalysis())}
              className="rounded-lg border border-slate-300 px-3 py-2 text-sm font-medium text-slate-600 hover:bg-slate-100"
            >
              Cancel
            </button>
          )}
        </div>
        {!hasDocument && (
          <div className="text-[11px] text-slate-400">
            Extract and apply a document first — the analysis always works from the source text.
          </div>
        )}

        {running && <div className="h-1 overflow-hidden rounded bg-slate-100"><div className="h-1 w-1/3 animate-pulse bg-indigo-500" /></div>}

        <div className="rounded-lg border border-slate-200 bg-slate-50/70 p-3">
          <Stepper steps={steps} status={analysis.status} />
        </div>

        {analysis.status === "done" && analysis.summary?.counts && (
          <div className="space-y-2">
            <div className="flex flex-wrap gap-1.5">
              <Badge tone="blue">{analysis.summary.counts.five_whys} whys</Badge>
              <Badge tone="blue">{analysis.summary.counts.fishbone_factors} factors</Badge>
              <Badge tone={analysis.summary.counts.missing_evidence ? "amber" : "green"}>
                {analysis.summary.counts.missing_evidence} evidence gaps
              </Badge>
              <Badge tone="blue">{analysis.summary.counts.capas} CAPAs</Badge>
              <Badge tone="purple">AI-suggested, pending QP confirmation</Badge>
            </div>
            {(analysis.warnings || []).map((w) => (
              <div key={w} className="rounded border border-amber-200 bg-amber-50 px-2 py-1.5 text-[11px] text-amber-800">
                ⚠ {w}
              </div>
            ))}
          </div>
        )}

        {analysis.status === "error" && (
          <div className="rounded-lg border border-rose-300 bg-rose-50 px-3 py-2 text-xs text-rose-800">
            <div className="font-semibold">Investigation failed</div>
            <div className="mt-0.5">{analysis.error}</div>
            <div className="mt-1 text-[10px] text-rose-500">The form was left untouched — no partial AI output was applied.</div>
          </div>
        )}

        {/* --- samples --- */}
        {samples.items.length > 0 && (
          <div className="no-print border-t border-slate-100 pt-3">
            <div className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-slate-400">
              Sample documents
            </div>
            <div className="space-y-1.5">
              {samples.items.map((s) => (
                <button
                  key={s.id}
                  type="button"
                  onClick={() => loadSample(s)}
                  title={s.description}
                  className="block w-full rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-left hover:border-indigo-300 hover:bg-indigo-50/50"
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-xs font-medium text-slate-700">{s.label}</span>
                    <span className="text-[10px] uppercase text-slate-400">{s.kind}</span>
                  </div>
                  <div className="truncate text-[10px] text-slate-500">{s.description}</div>
                </button>
              ))}
            </div>
          </div>
        )}

        <button
          type="button"
          onClick={onKeyTest}
          disabled={keyBusy}
          className="no-print w-full rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-medium text-slate-500 hover:bg-slate-50 disabled:opacity-50"
        >
          {keyBusy ? "Testing…" : "Test AI connection"}
        </button>
        {health.status === "ok" && !health.data.groq_configured && (
          <div className="text-center text-[10px] text-slate-400">No GROQ_API_KEY configured on the server.</div>
        )}
      </div>
    </div>
  );
}
