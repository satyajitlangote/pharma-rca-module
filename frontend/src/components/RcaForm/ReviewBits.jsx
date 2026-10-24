import { useDispatch } from "react-redux";
import { reviewItem } from "../../store/rcaSlice";
import Badge from "../common/Badge";

/** Provenance + review-state chips (origin & review live in the saved JSON). */
export function OriginBadge({ item }) {
  if (item?.origin !== "ai") return <Badge tone="slate">Entered by user</Badge>;
  return <Badge tone="purple" title="AI-generated — suggestion until reviewed and QP-confirmed">AI</Badge>;
}

const REVIEW_TONES = {
  pending: ["amber", "Pending review"],
  accepted: ["green", "Accepted"],
  edited: ["blue", "Edited by user"],
  rejected: ["red", "Rejected"],
};

export function ReviewBadge({ item }) {
  const [tone, label] = REVIEW_TONES[item?.review_state] || ["slate", item?.review_state || "—"];
  return <Badge tone={tone}>{label}</Badge>;
}

const BTN =
  "rounded border px-2 py-1 text-[11px] font-medium transition disabled:opacity-50";

/** Accept / Reject controls for one AI item. */
export default function AcceptReject({ section, item, className = "" }) {
  const dispatch = useDispatch();
  if (!item || item.origin !== "ai") return null;
  const accepted = item.review_state === "accepted";
  const rejected = item.review_state === "rejected";

  return (
    <div className={`no-print flex items-center gap-1.5 ${className}`}>
      <button
        type="button"
        onClick={() => dispatch(reviewItem({ section, id: item.id, action: "accept" }))}
        className={`${BTN} ${accepted ? "border-emerald-500 bg-emerald-50 text-emerald-700" : "border-slate-300 text-slate-600 hover:border-emerald-400"}`}
      >
        ✓ Accept
      </button>
      <button
        type="button"
        onClick={() => dispatch(reviewItem({ section, id: item.id, action: "reject" }))}
        className={`${BTN} ${rejected ? "border-rose-500 bg-rose-50 text-rose-700" : "border-slate-300 text-slate-600 hover:border-rose-400"}`}
      >
        ✕ Reject
      </button>
    </div>
  );
}

/** Small delete button (items are local until saved). */
export function DeleteBtn({ onClick, label = "Delete" }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="no-print rounded border border-slate-300 px-2 py-1 text-[11px] font-medium text-slate-500 hover:border-rose-400 hover:text-rose-600"
      title={label}
    >
      🗑
    </button>
  );
}

export function PendingChip({ count }) {
  if (!count) return <Badge tone="green">All AI items reviewed</Badge>;
  return <Badge tone="amber">{count} AI item{count > 1 ? "s" : ""} pending</Badge>;
}
