import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  ApiError,
  cancelWorkflowRun,
  getRunEvents,
  getRunExecutionTasks,
  getWorkflowRun,
  pauseWorkflowRun,
  resumeWorkflowRun,
  startWorkflowRun,
  type ExecutionTask,
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

function ExecutionTasksSection({ runId }: { runId: string }) {
  const tasks = useQuery({ queryKey: ["execution-tasks", runId], queryFn: () => getRunExecutionTasks(runId) });
  if (tasks.isLoading) return <div className="loading-state">Loading execution tasks...</div>;
  const list = tasks.data ?? [];
  if (list.length === 0) return null;
  const waitingForWorker = list.some((task) => task.status === "pending" && task.started_at === null);
  return (
    <div className="actions-section">
      <div className="section-heading">
        <div><p className="eyebrow">EXECUTION QUEUE</p><h4>Execution tasks · read only</h4></div>
      </div>
      {waitingForWorker && <div className="detail-warning">Waiting for worker — start one with ./run-worker.sh</div>}
      <div className="action-list">
        {list.map((task: ExecutionTask) => (
          <div className="action-row" key={task.id}>
            <span className="method-pill">{task.attempt}/{task.max_attempts}</span>
            <div className="action-copy">
              <strong>{task.status.toUpperCase()}</strong>
              <span>node {String(task.payload.node_id ?? "")} · worker {task.locked_by ?? "—"}</span>
            </div>
            <span className="action-copy">
              <small>available {new Date(task.available_at).toLocaleString()}</small>
              <small>{task.last_error ? `error: ${String(task.last_error.code)}` : ""}</small>
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

function RunTimeline({ runId }: { runId: string }) {
  const events = useQuery({ queryKey: ["run-events", runId], queryFn: () => getRunEvents(runId) });
  if (events.isLoading) return <div className="loading-state">Loading events...</div>;
  const list = events.data ?? [];
  return (
    <div className="actions-section">
      <div className="section-heading">
        <div><p className="eyebrow">EVENT TIMELINE</p><h4>Execution trace</h4></div>
      </div>
      {list.length === 0 ? (
        <div className="mini-empty">No trace events yet.</div>
      ) : (
        <div className="action-list">
          {list.map((event) => (
            <div className="action-row" key={event.id}>
              <span className="method-pill">{new Date(event.created_at).toLocaleTimeString()}</span>
              <div className="action-copy">
                <strong>{event.event_type.toUpperCase()}</strong>
                <span>{event.message ?? ""}</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function RunDetailPage({ runId, onBack }: RunDetailPageProps) {
  const queryClient = useQueryClient();
  const [selectedNodeRunId, setSelectedNodeRunId] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const runQuery = useQuery({
    queryKey: ["workflow-run", runId],
    queryFn: () => getWorkflowRun(runId),
    refetchInterval: 4000,
  });

  // Live SSE: the API emits named lifecycle events and EventSource carries
  // Last-Event-ID automatically after reconnecting.
  useEffect(() => {
    if (typeof EventSource === "undefined") return;
    const source = new EventSource(`/api/workflow-runs/${runId}/events/stream`);
    const refreshFromEvent = () => {
      void queryClient.invalidateQueries({ queryKey: ["workflow-run", runId] });
      void queryClient.invalidateQueries({ queryKey: ["run-events", runId] });
    };
    const eventTypes = [
      "workflow_started", "workflow_waiting", "workflow_resumed", "workflow_completed", "workflow_failed", "workflow_cancelled",
      "node_queued", "node_started", "node_retrying", "node_waiting", "node_resumed", "node_completed", "node_failed", "node_skipped", "node_cancelled",
    ];
    source.onmessage = refreshFromEvent;
    eventTypes.forEach((eventType) => source.addEventListener(eventType, refreshFromEvent));
    return () => {
      eventTypes.forEach((eventType) => source.removeEventListener(eventType, refreshFromEvent));
      source.close();
    };
  }, [runId, queryClient]);

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

      <ExecutionTasksSection runId={runId} />
      <RunTimeline runId={runId} />
    </div>
  );
}
