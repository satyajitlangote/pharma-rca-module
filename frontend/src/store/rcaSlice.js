/**
 * rcaSlice — the single source of truth for the RCA screen.
 *
 * Groups: health, samples, input (AI panel tabs), extraction preview, the
 * investigation draft (form), field origins (AI badge), live analysis steps,
 * saved-investigation list, audit, UI (modals/notices).
 *
 * Design rules:
 *  - AI output only ever lands in the draft via applyExtraction / analysisSucceeded.
 *  - A failed analysis leaves the draft untouched (never fabricate into the form).
 *  - Every AI-generated item carries origin:"ai" + review_state:"pending" until
 *    the user accepts/edits/rejects it (QP sign-off is blocked while pending).
 */
import { createAsyncThunk, createSlice } from "@reduxjs/toolkit";
import * as api from "../api/client";

/* ----------------------------- constants -------------------------------- */

// extraction field -> investigation column (mirrors backend EXTRACT_TO_FORM)
export const EXTRACT_TO_FORM = {
  deviation_reference: "reference",
  title: "title",
  product_name: "product_name",
  batch_number: "batch_number",
  manufacturing_stage: "stage",
  equipment_or_area: "equipment_area",
  incident_datetime: "incident_datetime",
  reported_by: "reported_by",
  severity_suggested: "severity",
  description: "description",
  immediate_containment: "immediate_containment",
  detected_by: "detected_by",
  quantity_affected: "quantity_affected",
};

// LangGraph node order shown live in the stepper.
export const ANALYSIS_NODES = [
  ["intake_extraction", "Extract intake"],
  ["validate_extraction", "Validate extraction"],
  ["five_whys", "5 Whys chain"],
  ["fishbone", "Fishbone (6M)"],
  ["root_cause_synthesis", "Root cause synthesis"],
  ["evidence_gap_check", "Evidence gap check"],
  ["capa_generation", "CAPA generation"],
  ["final_validation", "Final validation"],
];

export const EMPTY_DRAFT = {
  id: null,
  reference: "",
  title: "",
  product_name: "",
  batch_number: "",
  stage: "",
  equipment_area: "",
  incident_datetime: "",
  reported_by: "",
  severity: "",
  description: "",
  immediate_containment: "",
  detected_by: "",
  quantity_affected: "",
  five_whys: [],
  fishbone: { factors: [] },
  root_cause: null,
  contributing_factors: [],
  missing_evidence: [],
  capas: [],
  source_document_text: "",
  source_document_name: "",
  ai_summary: "",
  status: "Draft",
  is_qp_verified: false,
  qp_name: null,
  qp_role: null,
  qp_comments: null,
  qp_signed_at: null,
  created_at: null,
  updated_at: null,
};

const SECTIONS = [
  "five_whys",
  "fishbone",
  "root_cause",
  "contributing_factors",
  "missing_evidence",
  "capas",
];

const emptySteps = () =>
  ANALYSIS_NODES.map(([node]) => ({
    node,
    status: "pending",
    details: null,
    model: null,
    ts: null,
    error: null,
  }));

/* ------------------------------ helpers --------------------------------- */

function normalizeSeverity(value) {
  if (!value) return null;
  const v = value.toLowerCase();
  if (v.includes("critical")) return "Critical";
  if (v.includes("major")) return "Major";
  if (v.includes("minor")) return "Minor";
  return null; // not a standard severity -> do not guess; user must pick
}

function toDatetimeLocal(value) {
  if (!value) return "";
  const s = String(value).replace(" ", "T");
  if (/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/.test(s)) return s.slice(0, 16);
  if (/^\d{4}-\d{2}-\d{2}$/.test(s)) return `${s}T00:00`;
  return value;
}

function listOf(draft, section) {
  if (section === "fishbone") return draft.fishbone.factors;
  if (section === "root_cause") return draft.root_cause ? [draft.root_cause] : [];
  return draft[section] || [];
}

export function selectPendingAiCount(state) {
  const d = state.rca.draft;
  return SECTIONS.reduce(
    (total, section) =>
      total +
      listOf(d, section).filter((i) => i && i.origin === "ai" && i.review_state === "pending").length,
    0
  );
}

/** Non-empty context values; lets the graph reuse applied form data. */
function draftContext(draft) {
  const context = {};
  for (const col of Object.values(EXTRACT_TO_FORM)) {
    const v = draft[col];
    if (typeof v === "string" && v.trim()) context[col] = v;
  }
  return context;
}

function buildPayload(draft, actorType) {
  const s = (v) => (typeof v === "string" && v.trim() ? v.trim() : null);
  return {
    reference: s(draft.reference),
    title: s(draft.title),
    product_name: s(draft.product_name),
    batch_number: s(draft.batch_number),
    stage: s(draft.stage),
    equipment_area: s(draft.equipment_area),
    incident_datetime: draft.incident_datetime || null,
    reported_by: s(draft.reported_by),
    severity: draft.severity || null,
    description: s(draft.description),
    immediate_containment: s(draft.immediate_containment),
    detected_by: s(draft.detected_by),
    quantity_affected: s(draft.quantity_affected),
    five_whys: draft.five_whys,
    fishbone: draft.fishbone,
    root_cause: draft.root_cause,
    contributing_factors: draft.contributing_factors,
    missing_evidence: draft.missing_evidence,
    capas: draft.capas,
    source_document_text: s(draft.source_document_text),
    source_document_name: s(draft.source_document_name),
    ai_summary: s(draft.ai_summary),
    actor: actorType === "AI" ? "AI Copilot" : "Investigator",
    actor_type: actorType, // audit trail: AI-applied vs human saves
  };
}

/** Server response -> draft shape (never trusts client-blocked QP fields: server is authority). */
function fromServer(r) {
  return {
    ...EMPTY_DRAFT,
    id: r.id,
    reference: r.reference ?? "",
    title: r.title ?? "",
    product_name: r.product_name ?? "",
    batch_number: r.batch_number ?? "",
    stage: r.stage ?? "",
    equipment_area: r.equipment_area ?? "",
    incident_datetime: r.incident_datetime ? toDatetimeLocal(r.incident_datetime) : "",
    reported_by: r.reported_by ?? "",
    severity: r.severity ?? "",
    description: r.description ?? "",
    immediate_containment: r.immediate_containment ?? "",
    detected_by: r.detected_by ?? "",
    quantity_affected: r.quantity_affected ?? "",
    five_whys: r.five_whys ?? [],
    fishbone: r.fishbone ?? { factors: [] },
    root_cause: r.root_cause ?? null,
    contributing_factors: r.contributing_factors ?? [],
    missing_evidence: r.missing_evidence ?? [],
    capas: r.capas ?? [],
    source_document_text: r.source_document_text ?? "",
    source_document_name: r.source_document_name ?? "",
    ai_summary: r.ai_summary ?? "",
    status: r.status ?? "Draft",
    is_qp_verified: !!r.is_qp_verified,
    qp_name: r.qp_name ?? null,
    qp_role: r.qp_role ?? null,
    qp_comments: r.qp_comments ?? null,
    qp_signed_at: r.qp_signed_at ?? null,
    created_at: r.created_at ?? null,
    updated_at: r.updated_at ?? null,
  };
}

function aiSummaryFrom(results, summary, model) {
  const rc = results.root_cause;
  if (!rc) return "";
  const counts = summary?.counts || {};
  const supported = (results.five_whys || []).filter((w) => w.status === "Supported").length;
  return (
    `AI-suggested root cause (${model}, pending QP confirmation): ` +
    `${rc.primary_root_cause} [${rc.category}, confidence ${rc.confidence}]. ` +
    `${rc.justification} ` +
    `Analysis: ${supported}/${results.five_whys?.length || 0} causal steps supported, ` +
    `${counts.fishbone_factors ?? 0} fishbone factors, ` +
    `${counts.missing_evidence ?? 0} evidence gaps, ${counts.capas ?? 0} CAPAs.`
  );
}

/* ------------------------------- thunks --------------------------------- */

// Module-level abort handle (kept out of Redux: non-serializable by design).
let analysisAbort = null;
export function abortAnalysis() {
  if (analysisAbort) analysisAbort.abort();
}

export const fetchHealth = createAsyncThunk("rca/fetchHealth", api.getHealth);

export const fetchSamples = createAsyncThunk("rca/fetchSamples", api.fetchSamples);

export const testAiKey = createAsyncThunk(
  "rca/testAiKey",
  async (model, { rejectWithValue }) => {
    try {
      return await api.validateKey(model);
    } catch (err) {
      return rejectWithValue({ message: err.message, errorType: err.errorType });
    }
  }
);

export const extractDocument = createAsyncThunk(
  "rca/extractDocument",
  async (_, { getState, rejectWithValue }) => {
    const { input } = getState().rca;
    if (!input.file && !input.text.trim()) {
      return rejectWithValue({ message: "Upload a file or paste document text first." });
    }
    try {
      return await api.extract({
        text: input.file ? undefined : input.text,
        file: input.file || undefined,
        sourceDocumentName: input.docName || undefined,
        model: input.model,
      });
    } catch (err) {
      return rejectWithValue({ message: err.message, status: err.status, errorType: err.errorType });
    }
  }
);

/** Apply preview -> form (Redux action), then persist as an AI-attributed save. */
export const applyToForm = createAsyncThunk("rca/applyToForm", async (_, { getState, dispatch }) => {
  dispatch(extractionApplied());
  const { draft } = getState().rca;
  if (draft.source_document_text && !draft.is_qp_verified) {
    try {
      await dispatch(saveInvestigation({ actorType: "AI" })).unwrap();
    } catch {
      /* saveError is already in state; the form stays populated */
    }
  }
  return true;
});

/** Live SSE investigation run. Results only merge when the graph completes. */
export const runAnalysis = createAsyncThunk(
  "rca/runAnalysis",
  async (_, { getState, dispatch, rejectWithValue }) => {
    const { draft, input } = getState().rca;
    if (!draft.source_document_text.trim()) {
      const message = "No source document yet — extract a document in the AI panel first.";
      dispatch(analysisFailed({ message, errorType: null }));
      return rejectWithValue({ message, errorType: null });
    }

    dispatch(analysisStarted());
    analysisAbort = new AbortController();
    const acc = {};
    let endEvent = null;

    try {
      await api.analyzeStream(
        {
          source_text: draft.source_document_text,
          source_document_name: draft.source_document_name || undefined,
          context: draftContext(draft),
          model: input.model,
        },
        (event) => {
          dispatch(analysisEvent(event));
          if (event.status === "completed" && event.node !== "END") {
            acc[event.node] = event.partial_result || {};
          }
          if (event.node === "END") endEvent = event;
        },
        analysisAbort.signal
      );
    } catch (err) {
      if (err.name === "AbortError") {
        dispatch(analysisCancelled());
        return rejectWithValue({ message: "Analysis cancelled.", aborted: true });
      }
      dispatch(analysisFailed({ message: err.message, errorType: err.errorType }));
      return rejectWithValue({ message: err.message, errorType: err.errorType });
    } finally {
      analysisAbort = null;
    }

    if (!endEvent || endEvent.status !== "completed") {
      const message =
        endEvent?.error || "The investigation failed — no results were applied to the form.";
      dispatch(analysisFailed({ message, errorType: null }));
      return rejectWithValue({ message, errorType: null });
    }

    // END carries the post-validation content (invented IDs redacted); the
    // per-node proposals accumulated in `acc` are only a fallback for servers
    // that do not send `results` yet.
    const finalResults = endEvent.partial_result?.results;
    const useServerResults = finalResults && SECTIONS.every((k) => k in finalResults);
    const results = useServerResults
      ? {
          five_whys: finalResults.five_whys ?? [],
          fishbone: finalResults.fishbone ?? { factors: [] },
          root_cause: finalResults.root_cause ?? null,
          contributing_factors: finalResults.contributing_factors ?? [],
          missing_evidence: finalResults.missing_evidence ?? [],
          capas: finalResults.capas ?? [],
        }
      : {
          five_whys: acc.five_whys?.five_whys ?? [],
          fishbone: acc.fishbone?.fishbone ?? { factors: [] },
          root_cause: acc.root_cause_synthesis?.root_cause ?? null,
          contributing_factors: acc.root_cause_synthesis?.contributing_factors ?? [],
          missing_evidence: acc.evidence_gap_check?.missing_evidence ?? [],
          capas: acc.capa_generation?.capas ?? [],
        };
    dispatch(analysisSucceeded({ results, summary: endEvent.partial_result, model: input.model }));

    // AI-authored content is persisted with actor_type "AI" (audited).
    if (getState().rca.draft.id) {
      try {
        await dispatch(saveInvestigation({ actorType: "AI" })).unwrap();
      } catch {
        /* save banner shows; results stay in the draft for manual save */
      }
    }
    return results;
  }
);

export const saveInvestigation = createAsyncThunk(
  "rca/saveInvestigation",
  async ({ actorType = "User" } = {}, { getState, rejectWithValue }) => {
    const { draft } = getState().rca;
    const payload = buildPayload(draft, actorType);
    try {
      return draft.id
        ? await api.updateInvestigation(draft.id, payload)
        : await api.createInvestigation(payload);
    } catch (err) {
      return rejectWithValue({ message: err.message, status: err.status });
    }
  }
);

export const loadInvestigations = createAsyncThunk("rca/loadInvestigations", api.listInvestigations);

export const openInvestigation = createAsyncThunk("rca/openInvestigation", api.getInvestigation);

export const deleteInvestigation = createAsyncThunk("rca/deleteInvestigation", async (id, { dispatch }) => {
  await api.deleteInvestigation(id);
  dispatch(removedFromList(id));
  return id;
});

export const signOff = createAsyncThunk(
  "rca/signOff",
  async (body, { dispatch, rejectWithValue }) => {
    try {
      const saved = await api.signOffInvestigation(body.id, body);
      dispatch(loadAudit(body.id));
      return saved;
    } catch (err) {
      return rejectWithValue({ message: err.message, status: err.status });
    }
  }
);

export const reopen = createAsyncThunk("rca/reopen", async (body, { dispatch, rejectWithValue }) => {
  try {
    const saved = await api.reopenInvestigation(body.id, body);
    dispatch(loadAudit(body.id));
    return saved;
  } catch (err) {
    return rejectWithValue({ message: err.message, status: err.status });
  }
});

export const loadAudit = createAsyncThunk("rca/loadAudit", async (id, { dispatch }) => {
  const entries = await api.getAudit(id);
  dispatch(openedModal({ name: "audit" }));
  return entries;
});

/* -------------------------------- slice --------------------------------- */

const initialState = {
  health: { status: "idle", data: null, error: null },
  samples: { status: "idle", items: [] },
  input: {
    tab: "text",
    text: "",
    file: null,
    docName: null,
    sampleLabel: null,
    model: "openai/gpt-oss-20b",
  },
  extraction: { status: "idle", data: null, error: null, applied: false },
  draft: { ...EMPTY_DRAFT },
  fieldOrigins: {}, // field -> "ai" | "user" (session-scoped badge state)
  analysis: { status: "idle", steps: emptySteps(), error: null, warnings: [], summary: null },
  list: { status: "idle", items: [], saving: false, saveError: null, lastSavedAt: null },
  audit: { status: "idle", entries: [], error: null },
  ui: {
    modals: { list: false, signoff: false, audit: false, confirm: null },
    notice: null, // {tone, text}
    lastAiError: null,
    severityHint: null,
    keyTest: null,
    signoffError: null,
    reopenError: null,
  },
};

const rcaSlice = createSlice({
  name: "rca",
  initialState,
  reducers: {
    /* ---- AI panel input ---- */
    tabChanged(state, action) {
      if (state.input.tab !== action.payload) {
        state.input.tab = action.payload;
        state.input.file = null;      // each tab owns its own upload
        state.input.docName = null;
        state.input.sampleLabel = null;
        state.extraction = { status: "idle", data: null, error: null, applied: false };
      }
    },
    sampleLoaded(state, action) {
      // "Load sample" ONLY fills the input box (never extracts or analyzes).
      const { tab, text, docName, label } = action.payload;
      state.input.tab = tab;
      state.input.text = text;
      state.input.file = null;
      state.input.docName = docName;
      state.input.sampleLabel = label;
      state.extraction = { status: "idle", data: null, error: null, applied: false };
    },
    modelChanged(state, action) {
      state.input.model = action.payload;
    },
    textChanged(state, action) {
      state.input.text = action.payload;
      state.input.sampleLabel = null;
      state.extraction = { status: "idle", data: null, error: null, applied: false };
    },
    fileChanged(state, action) {
      const file = action.payload;
      state.input.file = file;
      state.input.docName = file ? file.name : null;
      state.input.sampleLabel = null;
      state.extraction = { status: "idle", data: null, error: null, applied: false };
    },

    /* ---- extraction preview -> form ---- */
    extractionApplied(state) {
      const { data } = state.extraction;
      if (!data) return;
      for (const [field, col] of Object.entries(EXTRACT_TO_FORM)) {
        const f = data.fields[field];
        if (!f) continue;
        if (f.value == null) {
          // Stale AI data for a now-missing field is cleared; user text is kept.
          if (state.fieldOrigins[col] === "ai") {
            state.draft[col] = col === "fishbone" ? { factors: [] } : "";
            delete state.fieldOrigins[col];
          }
          continue;
        }
        if (field === "severity_suggested") {
          const severity = normalizeSeverity(f.value);
          if (!severity) {
            state.ui.severityHint = f.value; // shown next to the select, not guessed
            continue;
          }
          state.draft.severity = severity;
          state.fieldOrigins.severity = "ai";
          continue;
        }
        state.draft[col] =
          field === "incident_datetime" ? toDatetimeLocal(f.value) : f.value;
        state.fieldOrigins[col] = "ai";
      }
      state.draft.source_document_text = data.source_text || "";
      state.draft.source_document_name = state.input.docName || null;
      state.extraction.applied = true;
      state.ui.severityHint = null;
      state.ui.notice = { tone: "ok", text: "Extraction applied to the form (fields marked AI)." };
    },

    /* ---- form editing ---- */
    setField(state, action) {
      const { field, value } = action.payload;
      state.draft[field] = value;
      state.fieldOrigins[field] = "user";
      if (field === "severity") state.ui.severityHint = null;
    },
    resetDraft(state) {
      state.draft = { ...EMPTY_DRAFT };
      state.fieldOrigins = {};
      state.extraction = { status: "idle", data: null, error: null, applied: false };
      state.analysis = { status: "idle", steps: emptySteps(), error: null, warnings: [], summary: null };
      state.list.saveError = null;
      state.ui.severityHint = null;
      state.ui.notice = null;
    },

    /* ---- per-item review (accept / reject / edit / add / delete) ---- */
    reviewItem(state, action) {
      const { section, id, action: review } = action.payload;
      const next = review === "accept" ? "accepted" : "rejected";
      if (section === "root_cause") {
        if (state.draft.root_cause) state.draft.root_cause.review_state = next;
        return;
      }
      const item = listOf(state.draft, section).find((x) => x.id === id);
      if (item) item.review_state = next;
    },
    editItem(state, action) {
      const { section, id, patch } = action.payload;
      if (section === "root_cause" && state.draft.root_cause) {
        Object.assign(state.draft.root_cause, patch);
        if (state.draft.root_cause.origin === "ai") state.draft.root_cause.review_state = "edited";
        return;
      }
      const item = listOf(state.draft, section).find((x) => x.id === id);
      if (item) {
        Object.assign(item, patch);
        if (item.origin === "ai") item.review_state = "edited";
      }
    },
    addItem(state, action) {
      const { section, item } = action.payload;
      if (section === "fishbone") state.draft.fishbone.factors.push(item);
      else if (section === "root_cause") state.draft.root_cause = item;
      else state.draft[section].push(item);
    },
    removeItem(state, action) {
      const { section, id } = action.payload;
      if (section === "root_cause") {
        state.draft.root_cause = null;
        return;
      }
      const list = listOf(state.draft, section);
      const idx = list.findIndex((x) => x.id === id);
      if (idx >= 0) list.splice(idx, 1);
    },
    acceptAllAi(state) {
      for (const section of SECTIONS) {
        for (const item of listOf(state.draft, section)) {
          if (item.origin === "ai" && item.review_state === "pending") item.review_state = "accepted";
        }
      }
    },

    /* ---- analysis lifecycle ---- */
    analysisStarted(state) {
      state.analysis = { status: "running", steps: emptySteps(), error: null, warnings: [], summary: null };
      state.ui.lastAiError = null;
    },
    analysisEvent(state, action) {
      const e = action.payload;
      if (e.node === "END") return;
      const step = state.analysis.steps.find((s) => s.node === e.node);
      if (!step) {
        // e.g. error_end (retry/terminal node) — surface it dynamically
        state.analysis.steps.push({
          node: e.node,
          status: e.status,
          details: e.details,
          model: e.model,
          ts: e.timestamp,
          error: e.error || null,
        });
        return;
      }
      step.status = e.status;
      if (e.details != null) step.details = e.details;
      if (e.model != null) step.model = e.model;
      step.ts = e.timestamp;
      step.error = e.error || null;
    },
    analysisSucceeded(state, action) {
      const { results, summary, model } = action.payload;
      state.analysis.status = "done";
      state.analysis.summary = summary || null;
      state.analysis.warnings = summary?.warnings || [];
      // Merge real analysis output into the form (each item origin:"ai").
      state.draft.five_whys = results.five_whys;
      state.draft.fishbone = results.fishbone;
      state.draft.root_cause = results.root_cause;
      state.draft.contributing_factors = results.contributing_factors;
      state.draft.missing_evidence = results.missing_evidence;
      state.draft.capas = results.capas;
      state.draft.ai_summary = aiSummaryFrom(results, summary, model);
      state.ui.notice = {
        tone: "ok",
        text: "Analysis complete — review every AI item, then save and request QP sign-off.",
      };
    },
    analysisFailed(state, action) {
      const { message, errorType } = action.payload;
      state.analysis.status = "error";
      state.analysis.error = message;
      if (errorType === "ai_unavailable") state.ui.lastAiError = message;
      // NOTE: draft untouched — failed AI must never modify the form.
    },
    analysisCancelled(state) {
      state.analysis.status = "idle";
      state.analysis.error = null;
    },

    /* ---- modals & notices ---- */
    openedModal(state, action) {
      const name = typeof action.payload === "string" ? action.payload : action.payload.name;
      state.ui.modals[name] = true;
      if (name === "signoff") state.ui.signoffError = null;
      if (name === "reopen") state.ui.reopenError = null;
    },
    closedModal(state, action) {
      const name = typeof action.payload === "string" ? action.payload : action.payload.name;
      if (name === "confirm") state.ui.modals.confirm = null;
      else state.ui.modals[name] = false;
    },
    setConfirm(state, action) {
      state.ui.modals.confirm = action.payload; // {kind, id, title, message}
    },
    setNotice(state, action) {
      state.ui.notice = action.payload;
    },
    dismissAiError(state) {
      state.ui.lastAiError = null;
    },
    keyTestDismissed(state) {
      state.ui.keyTest = null;
    },
    clearedSeverityHint(state) {
      state.ui.severityHint = null;
    },
    removedFromList(state, action) {
      const id = action.payload;
      state.list.items = state.list.items.filter((x) => x.id !== id);
      if (state.draft.id === id) {
        state.draft = { ...EMPTY_DRAFT };
        state.fieldOrigins = {};
      }
    },
  },

  extraReducers: (builder) => {
    builder
      /* health */
      .addCase(fetchHealth.pending, (state) => {
        state.health.status = "loading";
      })
      .addCase(fetchHealth.fulfilled, (state, action) => {
        state.health.status = "ok";
        state.health.data = action.payload;
      })
      .addCase(fetchHealth.rejected, (state, action) => {
        state.health.status = "error";
        state.health.error = action.error.message;
      })
      /* samples */
      .addCase(fetchSamples.fulfilled, (state, action) => {
        state.samples.status = "ok";
        state.samples.items = action.payload;
      })
      .addCase(fetchSamples.rejected, (state) => {
        state.samples.status = "error";
      })
      /* key test */
      .addCase(testAiKey.fulfilled, (state, action) => {
        state.ui.keyTest = action.payload;
        state.ui.lastAiError = null;
      })
      .addCase(testAiKey.rejected, (state, action) => {
        state.ui.keyTest = { ok: false, model: state.input.model, detail: action.payload.message };
        state.ui.lastAiError = action.payload.message;
      })
      /* extraction */
      .addCase(extractDocument.pending, (state) => {
        state.extraction.status = "loading";
        state.extraction.error = null;
        state.ui.lastAiError = null;
      })
      .addCase(extractDocument.fulfilled, (state, action) => {
        state.extraction.status = "done";
        state.extraction.data = action.payload;
        state.extraction.applied = false;
      })
      .addCase(extractDocument.rejected, (state, action) => {
        state.extraction.status = "error";
        state.extraction.error = action.payload?.message || action.error.message;
        if (action.payload?.errorType === "ai_unavailable") state.ui.lastAiError = state.extraction.error;
      })
      /* save */
      .addCase(saveInvestigation.pending, (state) => {
        state.list.saving = true;
        state.list.saveError = null;
      })
      .addCase(saveInvestigation.fulfilled, (state, action) => {
        state.list.saving = false;
        state.list.lastSavedAt = new Date().toISOString();
        state.draft = fromServer(action.payload);
        state.fieldOrigins = {}; // saved content is now the record's baseline
        const items = state.list.items;
        const idx = items.findIndex((x) => x.id === action.payload.id);
        const row = {
          id: action.payload.id,
          reference: action.payload.reference,
          title: action.payload.title,
          product_name: action.payload.product_name,
          batch_number: action.payload.batch_number,
          severity: action.payload.severity,
          status: action.payload.status,
          is_qp_verified: action.payload.is_qp_verified,
          updated_at: action.payload.updated_at,
        };
        if (idx >= 0) items[idx] = row;
        else items.unshift(row);
      })
      .addCase(saveInvestigation.rejected, (state, action) => {
        state.list.saving = false;
        state.list.saveError = action.payload?.message || action.error.message;
      })
      /* list */
      .addCase(loadInvestigations.pending, (state) => {
        state.list.status = "loading";
      })
      .addCase(loadInvestigations.fulfilled, (state, action) => {
        state.list.status = "ok";
        state.list.items = action.payload;
      })
      .addCase(loadInvestigations.rejected, (state, action) => {
        state.list.status = "error";
        state.list.error = action.error.message;
      })
      .addCase(openInvestigation.fulfilled, (state, action) => {
        state.draft = fromServer(action.payload);
        state.fieldOrigins = {};
        state.extraction = { status: "idle", data: null, error: null, applied: false };
        state.analysis = { status: "idle", steps: emptySteps(), error: null, warnings: [], summary: null };
        state.ui.modals.list = false;
        state.list.saveError = null;
        state.ui.notice = { tone: "ok", text: `Loaded ${action.payload.title || action.payload.reference || "investigation"}.` };
      })
      /* sign-off / reopen */
      .addCase(signOff.pending, (state) => {
        state.ui.signoffError = null;
      })
      .addCase(signOff.fulfilled, (state, action) => {
        state.draft = fromServer(action.payload);
        state.ui.modals.signoff = false;
        state.ui.notice = { tone: "ok", text: "QP sign-off recorded — investigation is locked." };
        const row = state.list.items.find((x) => x.id === action.payload.id);
        if (row) {
          row.status = action.payload.status;
          row.is_qp_verified = true;
          row.updated_at = action.payload.updated_at;
        }
      })
      .addCase(signOff.rejected, (state, action) => {
        state.ui.signoffError = action.payload?.message || action.error.message;
      })
      .addCase(reopen.fulfilled, (state, action) => {
        state.draft = fromServer(action.payload);
        state.ui.modals.signoff = false;
        state.ui.notice = { tone: "ok", text: "Investigation reopened (reason audited, verification cleared)." };
        const row = state.list.items.find((x) => x.id === action.payload.id);
        if (row) {
          row.status = action.payload.status;
          row.is_qp_verified = false;
        }
      })
      .addCase(reopen.rejected, (state, action) => {
        state.ui.reopenError = action.payload?.message || action.error.message;
      })
      /* audit */
      .addCase(loadAudit.pending, (state) => {
        state.audit.status = "loading";
        state.audit.error = null;
      })
      .addCase(loadAudit.fulfilled, (state, action) => {
        state.audit.status = "ok";
        state.audit.entries = action.payload;
      })
      .addCase(loadAudit.rejected, (state, action) => {
        state.audit.status = "error";
        state.audit.error = action.error.message;
      });
  },
});

export const {
  tabChanged,
  sampleLoaded,
  modelChanged,
  textChanged,
  fileChanged,
  extractionApplied,
  setField,
  resetDraft,
  reviewItem,
  editItem,
  addItem,
  removeItem,
  acceptAllAi,
  analysisStarted,
  analysisEvent,
  analysisSucceeded,
  analysisFailed,
  analysisCancelled,
  openedModal,
  closedModal,
  setConfirm,
  setNotice,
  dismissAiError,
  keyTestDismissed,
  clearedSeverityHint,
  removedFromList,
} = rcaSlice.actions;

/* ------------------------------ selectors -------------------------------- */

export const selectHealth = (s) => s.rca.health;
export const selectSqliteBanner = (s) =>
  s.rca.health.data?.db_fallback
    ? `Using SQLite dev fallback (${s.rca.health.data.dialect}) — run "docker compose up -d" and set DATABASE_URL for PostgreSQL.`
    : null;
export const selectAiBanner = (s) => {
  if (s.rca.ui.lastAiError) return `AI unavailable — ${s.rca.ui.lastAiError}`;
  if (s.rca.health.status === "ok" && !s.rca.health.data?.groq_configured)
    return "AI unavailable — GROQ_API_KEY is not configured on the server (backend/.env). Extraction and analysis are disabled; the form is untouched.";
  return null;
};
// Stable map (module constant => stable selector reference, no re-render churn).
export const NODE_LABELS = Object.fromEntries(ANALYSIS_NODES);
export const selectNodeLabels = () => NODE_LABELS;
export const selectIsSigned = (s) => s.rca.draft.is_qp_verified;
export const selectHasDraft = (s) => !!s.rca.draft.id || !!s.rca.draft.source_document_text;

export default rcaSlice.reducer;
