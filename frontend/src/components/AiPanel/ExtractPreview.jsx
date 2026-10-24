import Badge from "../common/Badge";

const FIELD_LABELS = {
  deviation_reference: "Deviation reference",
  title: "Title",
  product_name: "Product",
  batch_number: "Batch number",
  manufacturing_stage: "Manufacturing stage",
  equipment_or_area: "Equipment / area",
  incident_datetime: "Incident date",
  reported_by: "Reported by",
  severity_suggested: "Severity",
  description: "Description",
  immediate_containment: "Immediate containment",
  detected_by: "Detected by",
  quantity_affected: "Quantity affected",
};

const CONF_TONE = { High: "green", Medium: "amber", Low: "slate" };

/**
 * Extraction preview: every field with value, verbatim source quote and
 * confidence. Values that are NOT in the document show amber
 * "Not stated in document" — never a fabricated placeholder.
 */
export default function ExtractPreview({ data, applied }) {
  if (!data) return null;
  const rows = Object.keys(FIELD_LABELS);

  return (
    <div className="rounded-lg border border-slate-200 bg-slate-50/70">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-200 px-3 py-2">
        <div className="text-xs font-semibold text-slate-700">Extraction preview</div>
        <div className="flex items-center gap-2 text-[10px] text-slate-500">
          <span>model: {data.model}</span>
          <span>·</span>
          <span>{data.text_length?.toLocaleString()} chars</span>
          {data.source_kind !== "text" && (
            <>
              <span>·</span>
              <span>{data.source_kind}</span>
            </>
          )}
        </div>
      </div>

      {data.warning && (
        <div className="border-b border-amber-200 bg-amber-50 px-3 py-1.5 text-[11px] text-amber-800">
          ⚠ {data.warning}
        </div>
      )}

      <div className="max-h-72 overflow-y-auto">
        <table className="w-full table-fixed border-collapse text-[11px]">
          <thead className="sticky top-0 bg-white text-left text-[10px] uppercase tracking-wide text-slate-400">
            <tr>
              <th className="w-[26%] px-2 py-1.5 font-semibold">Field</th>
              <th className="w-[34%] px-2 py-1.5 font-semibold">Value</th>
              <th className="w-[28%] px-2 py-1.5 font-semibold">Source quote</th>
              <th className="w-[12%] px-2 py-1.5 font-semibold">Conf.</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((field) => {
              const f = data.fields[field] || {};
              const missing = f.value == null;
              return (
                <tr key={field} className="border-t border-slate-200/80 align-top">
                  <td className="px-2 py-1.5 font-medium text-slate-600">{FIELD_LABELS[field]}</td>
                  <td className="px-2 py-1.5">
                    {missing ? (
                      <span className="rounded bg-amber-100 px-1.5 py-0.5 font-medium text-amber-800">
                        Not stated in document
                      </span>
                    ) : (
                      <span className="break-words text-slate-800">{f.value}</span>
                    )}
                    {missing && (
                      <div className="mt-0.5 text-[10px] text-amber-600">Please verify</div>
                    )}
                  </td>
                  <td className="px-2 py-1.5">
                    {f.source_quote ? (
                      <span
                        className="break-words font-mono text-[10px] leading-snug text-slate-500"
                        title="Verified verbatim in the source document"
                      >
                        “{f.source_quote}”
                      </span>
                    ) : (
                      <span className="text-slate-300">—</span>
                    )}
                  </td>
                  <td className="px-2 py-1.5">
                    <Badge tone={CONF_TONE[f.confidence] || "slate"}>{f.confidence}</Badge>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-2 border-t border-slate-200 bg-white px-3 py-2">
        <span className="text-[10px] text-slate-500">
          Values are verified against the document text — absent fields stay empty.
        </span>
        {applied ? (
          <span className="inline-flex items-center gap-1 text-xs font-medium text-emerald-700">
            ✓ Applied to form
          </span>
        ) : (
          <span className="text-[10px] text-slate-400">Use “Apply to form” below</span>
        )}
      </div>
    </div>
  );
}
