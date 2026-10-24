import { useEffect } from "react";
import { useDispatch, useSelector } from "react-redux";
import { closedModal, deleteInvestigation, loadInvestigations, openInvestigation, setConfirm } from "../../store/rcaSlice";
import Badge from "../common/Badge";
import EmptyState from "../common/EmptyState";
import Modal from "../common/Modal";
import Spinner from "../common/Spinner";

const SEVERITY_TONE = { Critical: "red", Major: "amber", Minor: "slate" };

/** Saved-investigations list: load / delete (delete asks for confirmation). */
export default function SavedListModal() {
  const dispatch = useDispatch();
  const open = useSelector((s) => s.rca.ui.modals.list);
  const list = useSelector((s) => s.rca.list);
  const confirm = useSelector((s) => s.rca.ui.modals.confirm);

  useEffect(() => {
    if (open) dispatch(loadInvestigations());
  }, [open, dispatch]);

  const askDelete = (row) =>
    dispatch(
      setConfirm({
        kind: "delete",
        id: row.id,
        title: "Void investigation?",
        message: `“${row.title || row.reference || row.id}” will be voided. The record and its audit trail stay on file and can no longer be edited.`,
      })
    );

  return (
    <>
      <Modal open={open} title="Saved investigations" onClose={() => dispatch(closedModal("list"))} width="max-w-3xl">
        {list.status === "loading" ? (
          <div className="flex justify-center py-8"><Spinner /></div>
        ) : list.items.length === 0 ? (
          <EmptyState title="Nothing saved yet" hint="Save an investigation from the form and it will appear here." />
        ) : (
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="border-b border-slate-200 text-[10px] uppercase tracking-wide text-slate-400">
                <th className="py-1.5 pr-2">Reference</th>
                <th className="py-1.5 pr-2">Product / batch</th>
                <th className="py-1.5 pr-2">Severity</th>
                <th className="py-1.5 pr-2">Status</th>
                <th className="py-1.5 pr-2">Updated</th>
                <th className="py-1.5" />
              </tr>
            </thead>
            <tbody>
              {list.items.map((row) => (
                <tr key={row.id} className="border-b border-slate-100 hover:bg-slate-50">
                  <td className="py-2 pr-2 font-medium text-slate-800">
                    {row.reference || <span className="text-slate-400">(no reference)</span>}
                    <div className="truncate text-[11px] font-normal text-slate-500" style={{ maxWidth: 260 }}>
                      {row.title}
                    </div>
                  </td>
                  <td className="py-2 pr-2 text-slate-600">
                    {row.product_name || "—"}
                    <div className="font-mono text-[10px] text-slate-400">{row.batch_number}</div>
                  </td>
                  <td className="py-2 pr-2">
                    {row.severity ? <Badge tone={SEVERITY_TONE[row.severity]}>{row.severity}</Badge> : "—"}
                  </td>
                  <td className="py-2 pr-2">
                    <div className="text-slate-600">{row.status}</div>
                    {row.is_qp_verified && <Badge tone="green">QP verified</Badge>}
                  </td>
                  <td className="py-2 pr-2 text-[11px] text-slate-500">
                    {row.updated_at ? new Date(row.updated_at).toLocaleString() : "—"}
                  </td>
                  <td className="py-2 text-right">
                    <div className="flex justify-end gap-1.5">
                      <button
                        type="button"
                        onClick={() => dispatch(openInvestigation(row.id))}
                        className="rounded border border-slate-300 px-2 py-1 text-[11px] font-medium text-slate-600 hover:border-indigo-400 hover:text-indigo-700"
                      >
                        Open
                      </button>
                      <button
                        type="button"
                        onClick={() => askDelete(row)}
                        className="rounded border border-slate-300 px-2 py-1 text-[11px] font-medium text-slate-500 hover:border-rose-400 hover:text-rose-600"
                      >
                        Void
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Modal>

      {/* delete confirmation (nested: stays above the list) */}
      <Modal
        open={!!confirm && confirm.kind === "delete"}
        title={confirm?.title || "Confirm"}
        onClose={() => dispatch(setConfirm(null))}
        width="max-w-md"
        footer={
          <div className="flex justify-end gap-2">
            <button type="button" onClick={() => dispatch(setConfirm(null))} className="rounded-lg border border-slate-300 px-3 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-50">
              Cancel
            </button>
            <button
              type="button"
              onClick={() => {
                dispatch(deleteInvestigation(confirm.id));
                dispatch(setConfirm(null));
              }}
              className="rounded-lg bg-rose-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-rose-700"
            >
              Void investigation
            </button>
          </div>
        }
      >
        <p className="text-sm text-slate-600">{confirm?.message}</p>
      </Modal>
    </>
  );
}
