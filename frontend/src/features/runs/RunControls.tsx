import type { WorkflowRunStatus } from "../../api/client";
import { useTranslation } from "../../i18n";

type RunControlsProps = {
  status: WorkflowRunStatus;
  pending: string | null;
  onStart: () => void;
  onPause: () => void;
  onResume: () => void;
  onCancel: () => void;
};

export function RunControls({ status, pending, onStart, onPause, onResume, onCancel }: RunControlsProps) {
  const { t } = useTranslation();
  const terminal = status === "completed" || status === "failed" || status === "cancelled";

  return (
    <div className="detail-actions">
      {status === "created" && (
        <button className="button button--small button--primary" type="button" onClick={onStart} disabled={pending !== null}>
          {pending === "start" ? t("runControls.starting") : t("runControls.start")}
        </button>
      )}
      {(status === "running" || status === "waiting") && (
        <button className="button button--small" type="button" onClick={onPause} disabled={pending !== null}>
          {pending === "pause" ? t("runControls.pausing") : t("runControls.pause")}
        </button>
      )}
      {status === "paused" && (
        <button className="button button--small" type="button" onClick={onResume} disabled={pending !== null}>
          {pending === "resume" ? t("runControls.resuming") : t("runControls.resume")}
        </button>
      )}
      {!terminal && (
        <button className="button button--small button--danger" type="button" onClick={onCancel} disabled={pending !== null}>
          {pending === "cancel" ? t("runControls.cancelling") : t("runControls.cancel")}
        </button>
      )}
      {terminal && <span className="field-hint">{t("runControls.terminal")}</span>}
    </div>
  );
}
