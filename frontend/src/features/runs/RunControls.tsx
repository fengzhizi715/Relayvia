import type { WorkflowRunStatus } from "../../api/client";

type RunControlsProps = {
  status: WorkflowRunStatus;
  pending: string | null;
  onStart: () => void;
  onPause: () => void;
  onResume: () => void;
  onCancel: () => void;
};

export function RunControls({ status, pending, onStart, onPause, onResume, onCancel }: RunControlsProps) {
  const terminal = status === "completed" || status === "failed" || status === "cancelled";

  return (
    <div className="detail-actions">
      {status === "created" && (
        <button className="button button--small button--primary" type="button" onClick={onStart} disabled={pending !== null}>
          {pending === "start" ? "Starting..." : "Start"}
        </button>
      )}
      {(status === "running" || status === "waiting") && (
        <button className="button button--small" type="button" onClick={onPause} disabled={pending !== null}>
          {pending === "pause" ? "Pausing..." : "Pause"}
        </button>
      )}
      {status === "paused" && (
        <button className="button button--small" type="button" onClick={onResume} disabled={pending !== null}>
          {pending === "resume" ? "Resuming..." : "Resume"}
        </button>
      )}
      {!terminal && (
        <button className="button button--small button--danger" type="button" onClick={onCancel} disabled={pending !== null}>
          {pending === "cancel" ? "Cancelling..." : "Cancel"}
        </button>
      )}
      {terminal && <span className="field-hint">Run is in a terminal state. No control actions available.</span>}
    </div>
  );
}
