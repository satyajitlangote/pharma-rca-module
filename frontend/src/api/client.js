/**
 * All backend communication. No API keys ever reach the browser: Groq lives
 * in backend/.env and every AI call is proxied to FastAPI (/api -> :8000).
 */

async function handle(res) {
  if (res.ok) return res.status === 204 ? null : res.json();
  let detail = `Request failed (HTTP ${res.status})`;
  let errorType = null;
  try {
    const data = await res.json();
    if (typeof data.detail === "string") detail = data.detail;
    errorType = data.error_type || null;
  } catch {
    /* non-JSON error body */
  }
  const err = new Error(detail);
  err.status = res.status;
  err.errorType = errorType || (res.status === 503 ? "ai_unavailable" : null);
  throw err;
}

/** fetch() wrapper: turn a network-level failure into a readable Error. */
async function request(url, init) {
  try {
    return await fetch(url, init); // NOTE: the real fetch — not recursive
  } catch (err) {
    if (err && err.name === "AbortError") throw err; // user cancelled — not an error
    const e = new Error(
      "Cannot reach the server — the dev server appears to be down. " +
        "Refresh the page; if it persists, restart `npm run dev` in frontend/."
    );
    e.errorType = "network_error";
    throw e;
  }
}

const JSON_HEADERS = { "Content-Type": "application/json" };

/* ---------------------------- health & AI ------------------------------- */

export async function getHealth() {
  return handle(await request("/api/health"));
}

export async function fetchSamples() {
  return (await handle(await request("/api/samples"))).samples;
}

export async function validateKey(model) {
  return handle(
    await request("/api/ai/validate-key", {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify({ model }),
    })
  );
}

/** Extraction preview: multipart when a file is given, JSON text otherwise. */
export async function extract({ text, file, sourceDocumentName, model }) {
  let res;
  if (file) {
    const form = new FormData();
    form.append("file", file);
    if (sourceDocumentName) form.append("source_document_name", sourceDocumentName);
    if (model) form.append("model", model);
    res = await request("/api/ai/extract", { method: "POST", body: form });
  } else {
    res = await request("/api/ai/extract", {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify({ text, source_document_name: sourceDocumentName, model }),
    });
  }
  return handle(res);
}

/**
 * POST /api/ai/analyze/stream — parse SSE frames from the fetch body and
 * invoke onEvent(event) for every {node,status,details,model,timestamp,...}.
 */
export async function analyzeStream(payload, onEvent, signal) {
  const res = await request("/api/ai/analyze/stream", {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify(payload),
    signal,
  });
  if (!res.ok) await handle(res); // throws with detail / error_type

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let idx;
    while ((idx = buffer.indexOf("\n\n")) !== -1) {
      const frame = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);
      for (const line of frame.split("\n")) {
        if (!line.startsWith("data: ")) continue;
        const json = line.slice(6).trim();
        if (!json) continue;
        try {
          onEvent(JSON.parse(json));
        } catch {
          /* ignore malformed frame */
        }
      }
    }
  }
}

/* --------------------------- investigations ----------------------------- */

export async function listInvestigations() {
  return handle(await request("/api/investigations"));
}

export async function getInvestigation(id) {
  return handle(await request(`/api/investigations/${id}`));
}

export async function createInvestigation(payload) {
  return handle(
    await request("/api/investigations", {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify(payload),
    })
  );
}

export async function updateInvestigation(id, payload) {
  return handle(
    await request(`/api/investigations/${id}`, {
      method: "PUT",
      headers: JSON_HEADERS,
      body: JSON.stringify(payload),
    })
  );
}

export async function deleteInvestigation(id) {
  return handle(await request(`/api/investigations/${id}`, { method: "DELETE" }));
}

export async function signOffInvestigation(id, body) {
  return handle(
    await request(`/api/investigations/${id}/signoff`, {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify(body),
    })
  );
}

export async function reopenInvestigation(id, body) {
  return handle(
    await request(`/api/investigations/${id}/reopen`, {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify(body),
    })
  );
}

export async function getAudit(id) {
  return handle(await request(`/api/investigations/${id}/audit`));
}
