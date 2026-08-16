import { useQuery } from "@tanstack/react-query";

import { getRuns, type WorkflowRunSummary } from "../../api/client";
import { ResourceEmptyState } from "../../components/ResourceEmptyState";
import { WorkflowRunStatusBadge } from "../runs/RunStatusBadge";

export function durationText(startedAt: string | null, finishedAt: string | null): string {
  if (!startedAt) return "—";
  const end = finishedAt ? new Date(finishedAt).getTime() : Date.now();
  const ms = Math.max(0, end - new Date(startedAt).getTime());
  if (ms < 1000) return "<1s";
  const seconds = Math.floor(ms / 1000);
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  return `${minutes}m ${seconds % 60}s`;
}

export function RunList({ onSelect }: { onSelect: (runId: string) => void }) {
  const runs = useQuery({ queryKey: ["workflow-runs"], queryFn: () => getRuns() });

  if (runs.isLoading) return <div className="loading-state">Loading runs...</div>;
  if (runs.isError) return <div className="inline-error">Unable to load Runs. Start the FastAPI backend and retry.</div>;

  const list = runs.data ?? [];
  if (list.length === 0) {
    return (
      <ResourceEmptyState
        title="No runs yet."
        message="Run a Workflow Version from the Workflow page to start executing."
        actionLabel="Go to Workflows"
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
              <strong>{run.workflow_name ?? "Workflow"}</strong>
              <small>
                {run.id.slice(0, 8)} · v{run.version} · {new Date(run.created_at).toLocaleString()}
              </small>
            </span>
            <span className="resource-row-meta">
              <WorkflowRunStatusBadge status={run.status} />
              <small>⏱ {durationText(run.started_at, run.finished_at)}</small>
            </span>
          </button>
        ))}
      </div>
      <div className="select-state">Select a Run to inspect its Graph Snapshot and Node Runs.</div>
    </div>
  );
}
