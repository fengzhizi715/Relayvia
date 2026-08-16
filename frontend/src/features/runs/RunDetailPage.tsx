import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  ApiError,
  cancelWorkflowRun,
  getWorkflowRun,
  pauseWorkflowRun,
  resumeWorkflowRun,
  startWorkflowRun,
  type NodeRun,
  type WorkflowRun,
} from "../../api/client";
import { NodeRunInspector } from "./NodeRunInspector";
import { RunControls } from "./RunControls";
import { RunGraph } from "./RunGraph";
import { durationText } from "./RunList";
import { WorkflowRunStatusBadge } from "./RunStatusBadge";

type RunDetailPageProps = {
  runId: string;
  onBack: () => void;
};

export function RunDetailPage({ runId, onBack }: RunDetailPageProps) {
  const queryClient = useQueryClient();
  const [selectedNodeRunId, setSelectedNodeRunId] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const runQuery = useQuery({
    queryKey: ["workflow-run", runId],
    queryFn: () => getWorkflowRun(runId),
    refetchInterval: 4000,
  });

  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: ["workflow-run", runId] });
    void queryClient.invalidateQueries({ queryKey: ["workflow-runs"] });
  };

  const controlMutation = useMutation({
    mutationFn: (action: string): Promise<WorkflowRun> => {
      switch (action) {
        case "start":
          return startWorkflowRun(runId);
        case "pause":
          return pauseWorkflowRun(runId);
        case "resume":
          return resumeWorkflowRun(runId);
        case "cancel":
          return cancelWorkflowRun(runId);
        default:
          return Promise.reject(new Error("Unknown action"));
      }
    },
    onSuccess: () => {
      setNotice(null);
      refresh();
    },
    onError: (value) => setNotice(value instanceof ApiError ? `${value.message} (${value.code})` : "Run action failed"),
  });

  if (runQuery.isLoading) return <div className="loading-state">Loading Run...</div>;
  if (runQuery.isError) return <div className="inline-error">Unable to load this Run. Start the FastAPI backend and retry.</div>;

  const run = runQuery.data!;
  const nodeRunMap: Record<string, NodeRun> = Object.fromEntries(run.node_runs.map((nodeRun) => [nodeRun.node_id, nodeRun]));
  const selectedNodeRun = run.node_runs.find((nodeRun) => nodeRun.id === selectedNodeRunId) ?? null;

  return (
    <div className="resource-page">
      <div className="page-toolbar">
        <div>
          <p className="eyebrow">WORKFLOW RUN</p>
          <h3>Run {run.id.slice(0, 8)}</h3>
          <p className="page-description">
            {run.workflow_name ?? "Workflow"} · v{run.version} · created {new Date(run.created_at).toLocaleString()}
          </p>
        </div>
        <div className="detail-actions" style={{ margin: 0 }}>
          <button className="button button--small" type="button" onClick={onBack}>← Back to Runs</button>
          <WorkflowRunStatusBadge status={run.status} />
        </div>
      </div>

      {notice && <button className="notice notice--error" type="button" onClick={() => setNotice(null)}>{notice} · dismiss</button>}

      <section className="detail-card">
        <div className="detail-grid">
          <div><span className="detail-label">Status</span><strong>{run.status}</strong></div>
          <div><span className="detail-label">Version</span><strong>v{run.version}</strong></div>
          <div><span className="detail-label">Started</span><strong>{run.started_at ? new Date(run.started_at).toLocaleString() : "Not started"}</strong></div>
          <div><span className="detail-label">Duration</span><strong>⏱ {durationText(run.started_at, run.finished_at)}</strong></div>
          <div><span className="detail-label">Finished</span><strong>{run.finished_at ? new Date(run.finished_at).toLocaleString() : "—"}</strong></div>
          <div><span className="detail-label">Waiting</span><strong>{run.waiting_reason ?? "—"}</strong></div>
        </div>
        <RunControls
          status={run.status}
          pending={controlMutation.isPending ? controlMutation.variables : null}
          onStart={() => controlMutation.mutate("start")}
          onPause={() => controlMutation.mutate("pause")}
          onResume={() => controlMutation.mutate("resume")}
          onCancel={() => controlMutation.mutate("cancel")}
        />
      </section>

      <div className="graph-debug">
        <div className="section-heading">
          <div><p className="eyebrow">RUNTIME GRAPH</p><h4>Graph Snapshot · read only</h4></div>
        </div>
        <RunGraph graph={run.graph_snapshot} nodeRuns={nodeRunMap} />
      </div>

      <div className="actions-section">
        <div className="section-heading">
          <div><p className="eyebrow">NODE RUNS</p><h4>Execution instances</h4></div>
        </div>
        <div className="resource-layout">
          <div className="resource-list">
            {run.node_runs.map((nodeRun) => (
              <button
                className={selectedNodeRunId === nodeRun.id ? "resource-row resource-row--selected" : "resource-row"}
                key={nodeRun.id}
                type="button"
                onClick={() => setSelectedNodeRunId(nodeRun.id)}
              >
                <span className="resource-row-main">
                  <strong>{nodeRun.node_name_snapshot}</strong>
                  <small>{nodeRun.node_type}.{nodeRun.node_subtype} · {nodeRun.node_id}</small>
                </span>
                <span className="resource-row-meta"><WorkflowRunStatusBadge status={nodeRun.status} /></span>
              </button>
            ))}
          </div>
          {selectedNodeRun ? <NodeRunInspector nodeRun={selectedNodeRun} /> : <div className="select-state">Select a Node Run to inspect its runtime state.</div>}
        </div>
      </div>
    </div>
  );
}
