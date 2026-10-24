import { useDispatch, useSelector } from "react-redux";
import { clearedSeverityHint, setField } from "../../store/rcaSlice";
import Field from "../common/Field";
import Section from "../common/Section";

const SEVERITY_OPTIONS = [
  { value: "", label: "— select —" },
  "Critical",
  "Major",
  "Minor",
];

/** Section 1 — deviation context (AI badges per field until edited). */
export default function DeviationSection() {
  const dispatch = useDispatch();
  const draft = useSelector((s) => s.rca.draft);
  const origins = useSelector((s) => s.rca.fieldOrigins);
  const severityHint = useSelector((s) => s.rca.ui.severityHint);

  const set = (field) => (value) => dispatch(setField({ field, value }));
  const ai = (field) => origins[field] === "ai";

  return (
    <Section
      step={1}
      title="Deviation context"
      subtitle="Populated from the incident document — AI badges disappear once you edit a field"
      actions={
        draft.reference ? (
          <span className="font-mono text-[11px] text-slate-400">{draft.reference}</span>
        ) : null
      }
    >
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
        <Field label="Deviation reference" value={draft.reference} onChange={set("reference")} ai={ai("reference")} placeholder="DEV-…" />
        <Field label="Product" value={draft.product_name} onChange={set("product_name")} ai={ai("product_name")} />
        <Field label="Batch number" value={draft.batch_number} onChange={set("batch_number")} ai={ai("batch_number")} />
        <Field label="Manufacturing stage" value={draft.stage} onChange={set("stage")} ai={ai("stage")} />
        <Field label="Equipment / area" value={draft.equipment_area} onChange={set("equipment_area")} ai={ai("equipment_area")} />
        <Field label="Incident date & time" type="datetime-local" value={draft.incident_datetime} onChange={set("incident_datetime")} ai={ai("incident_datetime")} />
        <Field label="Reported by" value={draft.reported_by} onChange={set("reported_by")} ai={ai("reported_by")} />
        <Field
          label="Severity"
          value={draft.severity}
          onChange={set("severity")}
          options={SEVERITY_OPTIONS}
          ai={ai("severity")}
          hint={
            severityHint ? (
              <span
                onClick={() => dispatch(clearedSeverityHint())}
                className="cursor-pointer text-amber-700"
                title="Click to dismiss"
              >
                ⚠ Document says “{severityHint}” — not Critical/Major/Minor, please select.
              </span>
            ) : null
          }
        />
        <Field label="Detected by" value={draft.detected_by} onChange={set("detected_by")} ai={ai("detected_by")} />
        <Field label="Quantity affected" value={draft.quantity_affected} onChange={set("quantity_affected")} ai={ai("quantity_affected")} />
        <Field label="Title" value={draft.title} onChange={set("title")} ai={ai("title")} className="sm:col-span-2 xl:col-span-2" />

        <Field
          label="Description"
          value={draft.description}
          onChange={set("description")}
          rows={3}
          ai={ai("description")}
          className="sm:col-span-2 xl:col-span-3"
          placeholder="Not stated in document → leave empty"
        />
        <Field
          label="Immediate containment"
          value={draft.immediate_containment}
          onChange={set("immediate_containment")}
          rows={2}
          ai={ai("immediate_containment")}
          className="sm:col-span-2 xl:col-span-3"
        />
      </div>
    </Section>
  );
}
