import { useEffect, useState } from "react";
import { useDispatch, useSelector } from "react-redux";
import { closedModal, reopen, selectPendingAiCount, signOff } from "../../store/rcaSlice";
import Modal from "../common/Modal";

const ATTESTATIONS = [
  "I reviewed every AI-generated item and the underlying evidence quotes.",
  "The root cause is supported by the investigation evidence.",
  "The CAPA plan is adequate and proportionate to the root cause.",
];

/**
 * QP electronic signature. Blocked while AI items are pending review; if the
 * record is already signed, this dialog switches to the audited reopen flow.
 */
export default function SignoffModal() {
  const dispatch = useDispatch();
  const open = useSelector((s) => s.rca.ui.modals.signoff);
  const draft = useSelector((s) => s.rca.draft);
  const pending = useSelector(selectPendingAiCount);
  const signoffError = useSelector((s) => s.rca.ui.signoffError);
  const reopenError = useSelector((s) => s.rca.ui.reopenError);

  const [name, setName] = useState("");
  const [role, setRole] = useState("");
  const [comments, setComments] = useState("");
  const [checked, setChecked] = useState(() => ATTESTATIONS.map(() => false));
  const [reason, setReason] = useState("");

  useEffect(() => {
    if (open) {
      setChecked(ATTESTATIONS.map(() => false));
      setReason("");
    }
  }, [open]);

  const close = () => dispatch(closedModal("signoff"));
  const allChecked = checked.every(Boolean);

  const submitSignoff = (e) => {
    e.preventDefault();
    dispatch(
      signOff({
        id: draft.id,
        verifier_name: name.trim(),
        role: role.trim(),
        comments: comments.trim(),
        attestations: ATTESTATIONS.filter((_, i) => checked[i]),
      })
    );
  };

  const submitReopen = (e) => {
    e.preventDefault();
    dispatch(reopen({ id: draft.id, reason: reason.trim() }));
  };

  // Signed record -> reopen dialog; otherwise the sign-off form.
  if (draft.is_qp_verified) {
    return (
      <Modal open={open} title="Reopen investigation (audited)" onClose={close} width="max-w-md">
        <div className="mb-3 rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-900">
          This record is signed and locked. Reopening clears the QP verification and writes an audited
          entry with your reason.
        </div>
        <form onSubmit={submitReopen}>
          <label className="mb-1 block text-xs font-medium text-slate-600">
            Reason for reopen (required, audited)
          </label>
          <textarea
            required
            rows={3}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            className="mb-2 w-full resize-y rounded-lg border border-slate-300 px-2.5 py-1.5 text-sm focus:border-indigo-400 focus:outline-none focus:ring-1 focus:ring-indigo-300"
          />
          {reopenError && <div className="mb-2 text-xs text-rose-700">{reopenError}</div>}
          <div className="flex justify-end gap-2">
            <button type="button" onClick={close} className="rounded-lg border border-slate-300 px-3 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-50">
              Cancel
            </button>
            <button type="submit" className="rounded-lg bg-amber-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-amber-700">
              Reopen
            </button>
          </div>
        </form>
      </Modal>
    );
  }

  return (
    <Modal open={open} title="QP sign-off" onClose={close} width="max-w-lg">
      {!draft.id ? (
        <p className="text-sm text-slate-600">Save the investigation before requesting sign-off.</p>
      ) : pending > 0 ? (
        <div className="rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900">
          <strong>{pending} AI item{pending > 1 ? "s" : ""} still pending review.</strong>
          <div className="mt-1 text-xs">
            Accept, edit or reject every AI-generated item before QP sign-off — nothing AI-authored is
            ever pre-accepted.
          </div>
        </div>
      ) : (
        <form onSubmit={submitSignoff}>
          <p className="mb-3 text-xs text-slate-500">
            Signing locks the investigation (subsequent edits return HTTP 409 until an audited reopen).
          </p>
          <div className="grid gap-2 sm:grid-cols-2">
            <label className="text-xs font-medium text-slate-600">
              QP name *
              <input
                required
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="mt-1 w-full rounded-lg border border-slate-300 px-2.5 py-1.5 text-sm focus:border-indigo-400 focus:outline-none focus:ring-1 focus:ring-indigo-300"
              />
            </label>
            <label className="text-xs font-medium text-slate-600">
              Role *
              <input
                required
                placeholder="e.g. Qualified Person"
                value={role}
                onChange={(e) => setRole(e.target.value)}
                className="mt-1 w-full rounded-lg border border-slate-300 px-2.5 py-1.5 text-sm focus:border-indigo-400 focus:outline-none focus:ring-1 focus:ring-indigo-300"
              />
            </label>
          </div>

          <div className="mt-3 text-xs font-semibold uppercase tracking-wide text-slate-400">
            Attestations
          </div>
          <div className="mt-1 space-y-1.5">
            {ATTESTATIONS.map((a, i) => (
              <label key={a} className="flex items-start gap-2 text-xs text-slate-600">
                <input
                  type="checkbox"
                  checked={checked[i]}
                  onChange={(e) => setChecked(checked.map((v, j) => (j === i ? e.target.checked : v)))}
                  className="mt-0.5"
                />
                {a}
              </label>
            ))}
          </div>

          <label className="mt-3 block text-xs font-medium text-slate-600">
            Comments
            <textarea
              rows={2}
              value={comments}
              onChange={(e) => setComments(e.target.value)}
              className="mt-1 w-full resize-y rounded-lg border border-slate-300 px-2.5 py-1.5 text-sm focus:border-indigo-400 focus:outline-none focus:ring-1 focus:ring-indigo-300"
            />
          </label>

          {signoffError && <div className="mt-2 text-xs text-rose-700">{signoffError}</div>}

          <div className="mt-3 flex justify-end gap-2">
            <button type="button" onClick={close} className="rounded-lg border border-slate-300 px-3 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-50">
              Cancel
            </button>
            <button
              type="submit"
              disabled={!allChecked || !name.trim() || !role.trim()}
              className="rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-emerald-700 disabled:cursor-not-allowed disabled:bg-slate-300"
              title={allChecked ? "" : "Tick every attestation to sign"}
            >
              Sign & lock
            </button>
          </div>
        </form>
      )}
    </Modal>
  );
}
