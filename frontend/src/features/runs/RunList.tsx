import { useQuery } from "@tanstack/react-query";

import { getRuns, type WorkflowRunSummary } from "../../api/client";
import { ResourceEmptyState } from "../../components/ResourceEmptyState";
import { useTranslation, type Translator } from "../../i18n";
import { WorkflowRunStatusBadge } from "../runs/RunStatusBadge";

export function durationText(startedAt: string | null, finishedAt: string | null, t: Translator): string {
  if (!startedAt) return "—";
  const end = finishedAt ? new Date(finishedAt).getTime() : Date.now();
  const ms = Math.max(0, end - new Date(startedAt).getTime());
  if (ms < 1000) return t("runs.duration.lessThanSecond");
  const seconds = Math.floor(ms / 1000);
  if (seconds < 60) return t("runs.duration.seconds", { seconds });
  const minutes = Math.floor(seconds / 60);
  return t("runs.duration.minutes", { minutes, seconds: seconds % 60 });
}

export function RunList({ onSelect }: { onSelect: (runId: string) => void }) {
  const { t, locale } = useTranslation();
  const runs = useQuery({ queryKey: ["workflow-runs"], queryFn: () => getRuns() });

  if (runs.isLoading) return <div className="loading-state">{t("runs.loading")}</div>;
  if (runs.isError) return <div className="inline-error">{t("runs.loadError")}</div>;

  const list = runs.data ?? [];
  if (list.length === 0) {
    return (
      <ResourceEmptyState
        title={t("runs.emptyTitle")}
        message={t("runs.emptyMessage")}
        actionLabel={t("runs.goToWorkflows")}
        onAction={() => onSelect("")}
      />
    );
  }

  return (
    <div className="resource-layout">
      <div className="resource-list">
        {list.map((run: WorkflowRunSummary) => (
          <button
            className="resource-row"
            key={run.id}
            type="button"
            onClick={() => onSelect(run.id)}
          >
            <span className="resource-row-main">
              <strong>{run.workflow_name ?? t("runs.workflowFallback")}</strong>
              <small>
                {run.id.slice(0, 8)} · v{run.version} · {new Date(run.created_at).toLocaleString(locale)}
              </small>
            </span>
            <span className="resource-row-meta">
              <WorkflowRunStatusBadge status={run.status} />
              <small>⏱ {durationText(run.started_at, run.finished_at, t)}</small>
            </span>
          </button>
        ))}
      </div>
      <div className="select-state">{t("runs.selectState")}</div>
    </div>
  );
}
