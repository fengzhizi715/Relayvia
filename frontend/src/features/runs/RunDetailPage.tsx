import { useEffect, useState } from "react";
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  ApiError,
  cancelWorkflowRun,
  getRunEvents,
  getRunExecutionTasks,
  getWorkflowRun,
  pauseWorkflowRun,
  resumeWorkflowRun,
  startWorkflowRun,
  streamRunEvents,
  type ExecutionTask,
  type NodeRun,
  type WorkflowRun,
} from "../../api/client";
import { useTranslation } from "../../i18n";
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
  const { t, tStatus, locale } = useTranslation();
  const tasks = useQuery({ queryKey: ["execution-tasks", runId], queryFn: () => getRunExecutionTasks(runId) });
  if (tasks.isLoading) return <div className="loading-state">{t("runDetail.loadingTasks")}</div>;
  const list = tasks.data ?? [];
  if (list.length === 0) return null;
  const waitingForWorker = list.some((task) => task.status === "pending" && task.started_at === null);
  return (
    <div className="actions-section">
      <div className="section-heading">
        <div><p className="eyebrow">{t("runDetail.executionQueue")}</p><h4>{t("runDetail.executionTasks")}</h4></div>
      </div>
      {waitingForWorker && <div className="detail-warning">{t("runDetail.waitingForWorker")}</div>}
      <div className="action-list">
        {list.map((task: ExecutionTask) => (
          <div className="action-row" key={task.id}>
            <span className="method-pill">{task.attempt}/{task.max_attempts}</span>
            <div className="action-copy">
              <strong>{tStatus(task.status)}</strong>
              <span>{t("runDetail.node", { node: String(task.payload.node_id ?? ""), worker: task.locked_by ?? "—" })}</span>
            </div>
            <span className="action-copy">
              <small>{t("runDetail.available", { time: new Date(task.available_at).toLocaleString(locale) })}</small>
              <small>{task.last_error ? t("runDetail.errorLabel", { code: String(task.last_error.code) }) : ""}</small>
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

function RunTimeline({ runId }: { runId: string }) {
  const { t, locale } = useTranslation();
  const pageSize = 200;
  const events = useInfiniteQuery({
    queryKey: ["run-events", runId],
    queryFn: ({ pageParam }) => getRunEvents(runId, pageParam, pageSize),
    initialPageParam: 0,
    getNextPageParam: (lastPage) => lastPage.length === pageSize ? lastPage[lastPage.length - 1]?.id : undefined,
    refetchInterval: 4000,
  });
  if (events.isLoading) return <div className="loading-state">{t("runDetail.loadingEvents")}</div>;
  const list = events.data?.pages.flat() ?? [];
  return (
    <div className="actions-section">
      <div className="section-heading">
        <div><p className="eyebrow">{t("runDetail.eventTimeline")}</p><h4>{t("runDetail.executionTrace")}</h4></div>
      </div>
      {list.length === 0 ? (
        <div className="mini-empty">{t("runDetail.noEvents")}</div>
      ) : (
        <div className="action-list">
          {list.map((event) => (
            <div className="action-row" key={event.id}>
              <span className="method-pill">{new Date(event.created_at).toLocaleTimeString(locale)}</span>
              <div className="action-copy">
                <strong>{event.event_type.toUpperCase()}</strong>
                <span>{event.message ?? ""}</span>
              </div>
            </div>
          ))}
        </div>
      )}
      {events.hasNextPage ? <button className="button button--secondary" disabled={events.isFetchingNextPage} onClick={() => void events.fetchNextPage()} type="button">{events.isFetchingNextPage ? t("common.loading") : t("runDetail.loadMore")}</button> : null}
    </div>
  );
}

export function RunDetailPage({ runId, onBack }: RunDetailPageProps) {
  const { t, tStatus, locale } = useTranslation();
  const queryClient = useQueryClient();
  const [selectedNodeRunId, setSelectedNodeRunId] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const runQuery = useQuery({
    queryKey: ["workflow-run", runId],
    queryFn: () => getWorkflowRun(runId),
    refetchInterval: 4000,
  });

  useEffect(() => {
    const status = runQuery.data?.status;
    if (status === "completed" || status === "failed" || status === "cancelled") return;
    const controller = new AbortController();
    const refreshFromEvent = () => {
      void queryClient.invalidateQueries({ queryKey: ["workflow-run", runId] });
      void queryClient.invalidateQueries({ queryKey: ["run-events", runId] });
    };
    void streamRunEvents(runId, { signal: controller.signal, onEvent: refreshFromEvent }).catch((error) => {
      if (!(error instanceof DOMException && error.name === "AbortError")) refreshFromEvent();
    });
    return () => {
      controller.abort();
    };
  }, [runId, queryClient, runQuery.data?.status]);

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
          return Promise.reject(new Error(t("runDetail.unknownAction")));
      }
    },
    onSuccess: () => {
      setNotice(null);
      refresh();
    },
    onError: (value) => setNotice(value instanceof ApiError ? `${value.message} (${value.code})` : t("runDetail.runActionFailed")),
  });

  if (runQuery.isLoading) return <div className="loading-state">{t("runDetail.loading")}</div>;
  if (runQuery.isError) return <div className="inline-error">{t("runDetail.loadError")}</div>;

  const run = runQuery.data!;
  const nodeRunMap: Record<string, NodeRun> = Object.fromEntries(run.node_runs.map((nodeRun) => [nodeRun.node_id, nodeRun]));
  const selectedNodeRun = run.node_runs.find((nodeRun) => nodeRun.id === selectedNodeRunId) ?? null;

  return (
    <div className="resource-page">
      <div className="page-toolbar">
        <div>
          <p className="eyebrow">{t("runDetail.eyebrow")}</p>
          <h3>{t("runDetail.title", { id: run.id.slice(0, 8) })}</h3>
          <p className="page-description">
            {t("runDetail.meta", { name: run.workflow_name ?? t("runs.workflowFallback"), version: run.version, time: new Date(run.created_at).toLocaleString(locale) })}
          </p>
        </div>
        <div className="detail-actions" style={{ margin: 0 }}>
          <button className="button button--small" type="button" onClick={onBack}>{t("runDetail.back")}</button>
          <WorkflowRunStatusBadge status={run.status} />
        </div>
      </div>

      {notice && <button className="notice notice--error" type="button" onClick={() => setNotice(null)}>{notice} · {t("common.dismiss")}</button>}

      <section className="detail-card">
        <div className="detail-grid">
          <div><span className="detail-label">{t("runDetail.status")}</span><strong>{tStatus(run.status)}</strong></div>
          <div><span className="detail-label">{t("runDetail.version")}</span><strong>v{run.version}</strong></div>
          <div><span className="detail-label">{t("runDetail.started")}</span><strong>{run.started_at ? new Date(run.started_at).toLocaleString(locale) : t("common.notStarted")}</strong></div>
          <div><span className="detail-label">{t("runDetail.duration")}</span><strong>⏱ {durationText(run.started_at, run.finished_at, t)}</strong></div>
          <div><span className="detail-label">{t("runDetail.finished")}</span><strong>{run.finished_at ? new Date(run.finished_at).toLocaleString(locale) : "—"}</strong></div>
          <div><span className="detail-label">{t("runDetail.waiting")}</span><strong>{run.waiting_reason ?? "—"}</strong></div>
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
          <div><p className="eyebrow">{t("runDetail.graphEyebrow")}</p><h4>{t("runDetail.graphTitle")}</h4></div>
        </div>
        <RunGraph graph={run.graph_snapshot} nodeRuns={nodeRunMap} />
      </div>

      <div className="actions-section">
        <div className="section-heading">
          <div><p className="eyebrow">{t("runDetail.nodeRunsEyebrow")}</p><h4>{t("runDetail.nodeRunsTitle")}</h4></div>
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
          {selectedNodeRun ? <NodeRunInspector nodeRun={selectedNodeRun} /> : <div className="select-state">{t("runDetail.selectNodeRun")}</div>}
        </div>
      </div>

      <ExecutionTasksSection runId={runId} />
      <RunTimeline runId={runId} />
    </div>
  );
}
