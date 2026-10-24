# aivoa-rca — AI Root Cause Analysis for Pharma API Manufacturing

An AI-powered **Root Cause Analysis (RCA) module** covering the *Deviation → RCA → CAPA* workflow:
paste or upload an incident document, let an LLM extract the deviation context and build a
5-Whys chain / Fishbone (6M) / root cause / evidence gaps / CAPA plan — with every causal claim
carrying a **verbatim evidence quote that is verified in code**, and a **QP electronic sign-off**
that locks the record behind an audit trail.

**Design principle: never fabricate.** If a value or quote is not in the document, the system
says *"Not stated in document"* or downgrades the claim to *Hypothesis* — it never invents data,
record IDs, or canned analyses.

---

## 1. Architecture

```
┌────────────────────────────────────────────────────────────────────────┐
│ Frontend  (React + Vite + Redux Toolkit + Tailwind CSS)                │
│                                                                        │
│  Two-column screen:                                                    │
│   LEFT  — RCA form (6 sections, per-item accept/reject/edit,           │
│           AI badges, QP sign-off gating, print export)                 │
│   RIGHT — AI Copilot panel (sticky):                                   │
│           tabs Upload PDF / Paste text / Paste email                   │
│           → Extract → preview table (quote + confidence)               │
│           → Apply to form → Run investigation (live SSE stepper)        │
│                                                                        │
│  All AI state lives in one Redux slice (src/store/rcaSlice.js).        │
│  No API keys ever reach the browser.                                   │
└───────────────┬────────────────────────────────────────────────────────┘
                │ /api  (Vite dev proxy → http://127.0.0.1:8000)
┌───────────────▼────────────────────────────────────────────────────────┐
│ Backend   (Python 3.11 + FastAPI + Pydantic v2 + SQLAlchemy 2.x)       │
│                                                                        │
│  routers/ai.py             POST /api/ai/extract (preview, never writes)│
│                            POST /api/ai/analyze/stream (SSE)           │
│                            POST /api/ai/validate-key                   │
│  routers/investigations.py CRUD + signoff/reopen/audit (409 lock)      │
│  routers/samples.py        GET  /api/samples (live pypdf/email parse)  │
│  ai/groq_client.py         the ONLY LLM entry point (503 on failure)   │
│  ai/graph.py + nodes.py    LangGraph workflow (8 nodes, retry edges)   │
│  utils/evidence.py         quote/value verification (Supported vs      │
│                            Hypothesis) — computed in code, never by the │
│                            model                                       │
└───────────────┬────────────────────────────────────────────────────────┘
                │
      ┌─────────▼──────────┐          ┌─────────────────────┐
      │ PostgreSQL (5434)  │          │ Groq API (optional) │
      │ docker compose     │          │ openai/gpt-oss-    │
      │ investigations +   │          │ 120b (default)      │
      │ audit_logs (JSONB) │          │ gpt-oss-20b · qwen  │
      └────────────────────┘          └─────────────────────┘
```

**Trust boundaries**

| Layer | Responsibility |
|---|---|
| LLM (Groq) | Proposes values, quotes, causal chains — *suggestions only* |
| Backend code | Verifies every value/quote against the source text; computes `Supported`/`Hypothesis`; filters present evidence from gaps; redacts invented IDs; computes CAPA dates from the real clock |
| Frontend | Renders origin (`AI`/`user`) + review state per item; persists the post-validation sections carried by the terminal `END` event |
| QP sign-off | The only step that makes an analysis authoritative; locks the record (PUT → 409). Enforced server-side: pending AI items or missing attestations → 409/422 |

---

## 2. Setup

### Prerequisites
- Python 3.11, Node.js 18+, Docker (for PostgreSQL)
- A Groq API key from <https://console.groq.com/keys> (optional — without it the UI runs and shows an *AI unavailable* banner)

### 1) Database

```bash
docker compose up -d --wait   # PostgreSQL 16 on host port 5434, blocks until healthy
```

> Port 5434 avoids clashing with a local PostgreSQL on 5432. Override with
> `POSTGRES_PORT=5432 docker compose up -d` if your 5432 is free.
>
> **SQLite fallback:** if `DATABASE_URL` is unset the backend uses an explicit
> SQLite file and the UI shows a visible amber warning. Dev only.

### 2) Backend

```bash
cd backend
python -m venv venv
venv\Scripts\activate          # Windows (use source venv/bin/activate on Unix)
pip install -r requirements.txt
copy .env.example .env         # then set GROQ_API_KEY=...
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

### 3) Frontend

```bash
cd frontend
npm install
npm run dev                    # http://localhost:5173 (proxies /api → :8000)
```

> If 5173 is taken, Vite automatically falls back to the next free port
> (e.g. `http://localhost:5174`) — check the terminal for the actual URL.

### 4) Backend supervisor (Windows, keeps uvicorn alive)

`backend/start_backend.ps1` runs uvicorn in a restart loop (re-launches it 5 s
after any exit). Both it and `start_uvicorn_once.cmd` resolve their paths from
their own folder, so they work from any checkout location without editing. Run
it in a terminal:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File backend\start_backend.ps1
```

Or register it as a Task Scheduler task so it survives editor/terminal
sessions. `backend/aivoa_backend_task.xml` is an export from the original
machine — it hardcodes that machine's checkout path and Windows user — so edit
those values before importing it elsewhere:

```powershell
schtasks /Create /TN "AIVOA-RCA-Backend" /XML backend\aivoa_backend_task.xml /F
```

Resilience is two-layer:

- **Inner loop (5 s):** the supervisor relaunches uvicorn after any crash/exit.
- **Outer heartbeat (60 s):** the task fires every minute with
  `MultipleInstancesPolicy=IgnoreNew` — if the supervisor is alive the tick is
  ignored; if it was killed (e.g. by a `Ctrl+C`/console event), the scheduler
  respawns it within 60 s. This heartbeat is used instead of
  `RestartOnFailure`, which Windows does **not** trigger for externally
  terminated instances.

```powershell
schtasks /Run   /TN "AIVOA-RCA-Backend"    # start (also started manually once)
schtasks /End   /TN "AIVOA-RCA-Backend"    # stop  (then kill any python on :8000)
schtasks /Delete /TN "AIVOA-RCA-Backend" /F # remove the task entirely
```

Backend log (appended): `%TEMP%\aivoa-rca\aivoa_uvicorn.log`.
If the backend is down the UI shows a red banner, and the Vite proxy answers
`502 {"detail":"Backend unreachable — FastAPI is not running on port 8000…"}`.

> The Groq SDK is synchronous, so every model call runs on a worker thread
> (`structured_call_async`). The event loop therefore keeps accepting
> connections while a node waits on Groq: `/api/health` still answers the
> supervisor's probe and SSE events flush as they are produced. Running the
> blocking call on the event loop made every run look like a hung server and
> the supervisor killed uvicorn mid-investigation.

### Environment variables (`backend/.env`)

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `DATABASE_URL` | ✅ (prod) | — | `postgresql+psycopg://user:pass@127.0.0.1:5434/aivoa_rca`. Unset ⇒ SQLite dev fallback (UI warns) |
| `GROQ_API_KEY` | ✅ for AI | `""` | Groq key. Missing/failing ⇒ HTTP 503 + "AI unavailable" banner; form untouched |
| `AI_MODEL` | — | `openai/gpt-oss-20b` | Default model. Allowlist: `openai/gpt-oss-20b`, `openai/gpt-oss-120b`, `qwen/qwen3.8-27b` (verified tool-calling), plus spec IDs `llama-3.3-70b-versatile` / `gemma2-9b-it` for keys that serve them |
| `EXTRACTION_TEMPERATURE` | — | `0` | Extraction is deterministic |
| `ANALYSIS_TEMPERATURE` | — | `0.1` | Low temperature for accuracy |
| `CORS_ORIGINS` | — | `http://localhost:5173,...` | Explicit origins — never `*` with credentials |
| `MAX_UPLOAD_BYTES` | — | `5242880` | PDF upload limit (5 MB) |
| `MAX_TEXT_CHARS` | — | `60000` | Documents beyond this are truncated *with a visible warning* |

Secrets live only in `backend/.env` (gitignored) — never in the frontend bundle.

---

## 3. API

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/api/health` | Liveness + truthful env report (`dialect`, `db_fallback`, `groq_configured`) |
| `POST` | `/api/ai/extract` | Extraction preview (JSON text **or** multipart PDF/email). Never writes to form/DB |
| `POST` | `/api/ai/analyze/stream` | **SSE** investigation run (LangGraph) |
| `POST` | `/api/ai/validate-key` | Groq connectivity test |
| `GET` | `/api/samples` | Sample documents (parsed live with pypdf / email parser) |
| `POST` | `/api/investigations` | Create (client-supplied `is_qp_verified`/`qp_*`/`status` ignored) |
| `GET` | `/api/investigations` | List (compact rows) |
| `GET` | `/api/investigations/{id}` | Full record |
| `PUT` | `/api/investigations/{id}` | Partial update — **409 if QP-signed or voided** |
| `DELETE` | `/api/investigations/{id}` | **Void** (audited, row and trail retained) — **409 if QP-signed** |
| `POST` | `/api/investigations/{id}/signoff` | QP electronic signature (locks record) — **409 while AI items are pending review**, attestations required |
| `POST` | `/api/investigations/{id}/reopen` | Audited unlock (reason required) |
| `GET` | `/api/investigations/{id}/audit` | Field-level audit trail `[{field, old, new}]` |

**SSE event shape** (one `started` + one `completed` per node, then a terminal `END`):

```json
{"node": "five_whys", "status": "started|completed|failed",
 "details": "3 causal steps (2 document-supported)",
 "model": "openai/gpt-oss-20b",
 "timestamp": "2026-10-23T09:00:00+00:00",
 "partial_result": { }, "error": null}
```

**503 contract** (missing key *or* Groq failing after 2 retries):

```json
{"detail": "AI unavailable: GROQ_API_KEY is not configured ...",
 "error_type": "ai_unavailable", "ok": false}
```

---

## 4. LangGraph workflow

```
                        ┌──────────────────┐
                        │      START       │
                        └────────┬─────────┘
                                 ▼
                   ┌──────────────────────────┐
                   │   intake_extraction      │  extract fields (or reuse applied form)
                   └────────────┬─────────────┘
                                ▼
                   ┌──────────────────────────┐     retries ≤ 2
                   │   validate_extraction    │ ──────────────────► intake_extraction
                   └────────────┬─────────────┘        ▲
                        ok │          │ retries exhausted
                           ▼          ▼
                 ┌───────────────┐  ┌────────────┐
                 │  five_whys    │  │ error_end  │──► END (failed)
                 └───────┬───────┘  └────────────┘        ▲
                         ▼                                │
                 ┌───────────────┐                        │
                 │   fishbone    │   6M factors           │
                 └───────┬───────┘                        │
                         ▼                                │
                 ┌────────────────────┐                   │
                 │ root_cause_        │  confidence capped│
                 │ synthesis          │  by verified ratio│
                 └───────┬────────────┘                   │
                         ▼                                │
                 ┌────────────────────┐                   │
                 │ evidence_gap_check │  gaps filtered    │
                 │                    │  against document │
                 └───────┬────────────┘                   │
                         ▼                                │
                 ┌───────────────┐                        │
                 │ capa_generation│  real dates from today│
                 └───────┬───────┘                        │
                         ▼                                │
                 ┌────────────────────┐     retries ≤ 2   │
                 │  final_validation  │ ──────────────────► capa_generation
                 └───────┬────────────┘        ▲
                    ok │        │ retries exhausted
                       ▼        └──────────────────────────┘
                    ┌─────┐
                    │ END │   (completed — "AI-suggested, pending QP confirmation")
                    └─────┘
```

- **Retry edges** (max 2, then `error_end`): extraction validation failure → re-extract; CAPA/required-field failure → re-generate.
- **Evidence rules in code** (`utils/evidence.py`, `nodes.py`): `Supported` only if the quote is located in the source text; model output can never claim verification.
- **Invented-ID guard** (`final_validation`): record IDs (DEV/CAPA/SOP/CAL/…) that don't exist in the source are replaced with `[not in source document]` and reported as a warning. The redacted sections are returned in the node's state update and in the terminal `END.results`, so the client persists the validated content — never the raw proposal.

---

## 5. Testing

```bash
cd backend
venv\Scripts\activate
pytest                     # 23 tests — Groq is fully mocked
```

The suite covers the accuracy contract:

1. fabricated extraction values dropped → *Not stated in document*
2. every node emits `started` + `completed` SSE events
3. fabricated quote ⇒ `Hypothesis` (never `Supported`), confidence capped
4. evidence already in the document filtered out of the gap list
5. CAPA target dates computed from the **real** current date
6. invented record IDs redacted (+ visible warning), with the redacted sections — not just the warning — returned to the client
7. missing/failing Groq key ⇒ HTTP 503 `error_type: ai_unavailable`, form untouched
8. Groq daily token cap (TPD) ⇒ one attempt, immediate actionable error (never retried)

Plus CRUD/audit/lock tests: hostile QP fields ignored, signed record → 409, audited reopen,
field-level diff trail (`create → signoff → reopen → update`), and the server-side review gate:
pending AI items → 409, attestations required → 422, and `DELETE` keeps the record and its trail
as a `Void`.

```bash
cd frontend
npm run build               # production build must pass
npm run lint                # ESLint must pass
```

---

## 6. Demo script (5–8 min)

> **Setup before the demo:** `docker compose up -d`, backend on `:8000`, frontend on `:5173`,
> `GROQ_API_KEY` set. Sample documents are built in — no files needed.

| # | Time | Action | Talking point |
|---|---|---|---|
| 1 | 0:00–0:30 | Show the empty screen: form left, **AI Copilot** right, top bar with API/DB chip | "Deviation → RCA → CAPA in one screen; AI is an assistant, never the authority" |
| 2 | 0:30–1:00 | Click **"Test AI connection"** in the panel | Green = Groq reachable. "No key in the browser — the key lives in `backend/.env`" |
| 3 | 1:00–1:45 | Panel → *Paste text* tab → **Load sample** → **Extract** | "Load sample only fills the input — nothing runs automatically" |
| 4 | 1:45–2:30 | Show the **preview table**: value, verbatim source quote, confidence, ✓/⚠ verified badges | "Every value was checked against the document *in code*; anything not stated shows *Not stated in document*" |
| 5 | 2:30–3:00 | Click **Apply to form** | Form fills, edited fields carry the **AI** badge; record auto-saves as `actor_type: AI` |
| 6 | 3:00–4:30 | Click **Run investigation** — watch the live stepper (8 nodes) | "Each step is a LangGraph node streaming SSE; the model can't claim *Supported* — our code verifies each quote" |
| 7 | 4:30–5:30 | Scroll the form: 5 Whys with Supported/Hypothesis badges, Fishbone 6M, root cause, evidence gaps, CAPA table with real dates | "Unsupported items stay *Hypothesis* / *Needs investigation*; gaps that are actually in the doc were filtered out" |
| 8 | 5:30–6:15 | **Reject** one AI item, edit a quote, then **Accept all AI items** | "Per-item review: accept / reject / edit, each keeps origin + review state" |
| 9 | 6:15–7:00 | Try **QP sign-off** *before* accepting items → blocked; after accepting → sign with attestations | "Nothing AI-authored is pre-accepted; QP e-signature is required" |
| 10 | 7:00–7:45 | Open **Audit trail** → show `create → update → signoff` with field diffs; then edit → 409 → **Reopen** with reason | "Signed = locked; changes only via audited reopen with a reason" |
| 11 | 7:45–8:00 | (If key removed) restart backend without `GROQ_API_KEY` → red **AI unavailable** banner, form untouched | "Missing key = 503, never a silent fallback or canned analysis" |

---

## 7. Code walkthrough (5–10 min)

Suggested reading order (start at the top, everything is commented for a fast tour):

| Order | File(s) | What to show | ~Time |
|---|---|---|---|
| 1 | `backend/app/main.py` | Lifespan (not `on_event`), explicit CORS origins, health endpoint reading `engine.dialect` | 2 min |
| 2 | `backend/app/routers/ai.py` | The **503 contract** (`_ai_unavailable`), extract = preview-only, SSE generator merging node-queue + graph chunks + `END` | 4 min |
| 3 | `backend/app/ai/graph.py` | The StateGraph: 8 nodes, two conditional retry edges (max 2) → `error_end` | 2 min |
| 4 | `backend/app/ai/nodes.py` | One node per step; **evidence rules in code** — `quote_in_text` decides `Supported`, gaps filtered, CAPA dates from `date.today()`, `_find_invented_ids` redaction | 5 min |
| 5 | `backend/app/utils/evidence.py` | Normalization + fuzzy containment — why a near-verbatim PDF quote still matches, and why fabricated text never does | 3 min |
| 6 | `backend/app/routers/investigations.py` | `extra="ignore"` blocks client QP fields; `_assert_unlocked` → 409; `_diff` → audit rows | 4 min |
| 7 | `frontend/src/store/rcaSlice.js` | Single source of truth: `analysisFailed` **never touches the draft**; `extractionApplied` marks AI origins; `signOff`/`reopen` thunks | 5 min |
| 8 | `frontend/src/components/AiPanel/AiPanel.jsx` | Extract → preview → Apply → Run workflow; every failure path shows a banner | 3 min |
| 9 | `frontend/src/components/RcaForm/` | 6 sections; `ReviewBits.jsx` = origin/review badges + accept/reject | 4 min |
| 10 | `backend/tests/` | 23 tests, `structured_call` mocked — the accuracy contract as executable spec | 3 min |

**Key invariants to point out while walking:**

- `groq_client.structured_call` is the **only** place the LLM is invoked — one choke point for retries (max 2), temperature, and the 503 mapping.
- `verify_extraction` re-checks every model value/wording against the raw text *independently of the model*.
- `status` ("Supported"/"Hypothesis") never appears in any prompt schema — the model literally cannot emit it.
- Signed records: Pydantic schemas don't even contain `is_qp_verified`, so the ORM never sees it from CRUD.
- The frontend mirrors quote verification in `src/lib/evidence.js` only for instant UI feedback; the backend verdict is authoritative.

---

## 8. Limitations

- **Groq key required for AI features** — without it the app is fully usable for manual entry, but extraction/analysis return HTTP 503 with a clear banner (by design: no silent fallback, no canned analysis).
- **Groq free-tier rate limits** — the 8000 TPM cap can slow a full investigation to ~1–2 minutes; `groq_client` honors Groq's suggested 429 wait (with backoff) so runs wait rather than fail, but on a very small quota consecutive runs may still exhaust the 2 retries and end with a clear 503 — nothing is fabricated or partially applied.
- **No hard delete** — `DELETE` voids a record (status `Void`): the row and its audit trail are
  retained for ALCOA+ review, the record is hidden from the saved list but still retrievable by id,
  and its `reference` stays reserved. Voided records are read-only.
- **No authentication / RBAC** — sign-off records the QP's name, role and attestations, but there is no login or identity provider; suitable as a module inside a larger authenticated system.
- **No Alembic migrations** — schema is created with `Base.metadata.create_all` at startup. Fine for a module/demo; use Alembic in production.
- **Text-based PDFs only** — `pypdf` extracts embedded text; scanned/image-only PDFs are rejected with a clear message (OCR is out of scope).
- **Single-document scope** — the analysis grounds every claim in *one* source document; cross-referencing batch records, OOS reports or trend data would need retrieval from a document store.
- **LLM quality varies** — evidence verification prevents *fabrication*, but it cannot make a weak model produce a *good* causal chain; the 5 Whys / fishbone still require investigator judgment (that's why per-item review and QP sign-off exist).
- **SQLite fallback is dev-only** — JSON columns and cascade deletes work, but it is not the supported production configuration (PostgreSQL via `docker compose` is).
- **No file export beyond print** — CAPA handover to a proper QMS CAPA tracker (e.g. via API) is out of scope.

---

## 9. Repository layout

```
aivoa-rca/
├── docker-compose.yml        # PostgreSQL 16 (host port 5434)
├── backend/
│   ├── .env / .env.example   # secrets (gitignored) + template
│   ├── requirements.txt
│   ├── pytest.ini
│   ├── app/
│   │   ├── main.py           # FastAPI app, lifespan, CORS, health
│   │   ├── config.py         # env settings (SQLite fallback flag)
│   │   ├── database.py       # SQLAlchemy 2.x engine/session
│   │   ├── models.py         # investigations + audit_logs (JSONB variant)
│   │   ├── schemas.py        # Pydantic v2: CRUD + AI + LangGraph contracts
│   │   ├── routers/          # ai.py · investigations.py · samples.py
│   │   ├── ai/               # groq_client · prompts · extraction · graph · nodes · state · domain
│   │   └── utils/            # evidence.py (verification) · documents.py (PDF/email/text)
│   └── tests/                # 23 pytest tests (Groq mocked)
├── frontend/
│   └── src/
│       ├── App.jsx           # two-column shell, toolbar, global banners
│       ├── store/rcaSlice.js # all RCA state
│       ├── api/client.js     # fetch helpers + SSE parser (no keys)
│       └── components/       # AiPanel · RcaForm · Modals · common
└── sample_data/              # 4 original scenarios + make_pdf.py
```

**Sample documents** (`/api/samples`, "Load sample" fills the input only):

| Sample | Scenario |
|---|---|
| `oos_impurity_valsartan.txt` | OOS impurity result during release testing |
| `particulate_contamination_metformin.eml` | Foreign particulate in an email thread |
| `yield_drop_incident.txt/.pdf` | Yield drop during workup (text + generated PDF) |
| `incomplete_incident_notification.txt` | **Deliberately incomplete** — shows *"Not stated in document"* behaviour |

---

## 10. Safety & compliance notes

- **Never push to a public repository** — `backend/.env` is gitignored; keep it that way.
- GMP context: this tool *supports* investigations; it does not replace the QP's release decision.
  Every record states **"AI-suggested, pending QP confirmation"** until a human signs it.
- Full field-level audit trail (`actor_type: AI | User | QP`) supports data-integrity (ALCOA+) review.
