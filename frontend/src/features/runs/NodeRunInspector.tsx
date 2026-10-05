import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { approveNodeRun, rejectNodeRun, submitNodeRun, type NodeRun } from "../../api/client";
import { useTranslation } from "../../i18n";
import { NodeRunStatusBadge } from "./RunStatusBadge";

export function NodeRunInspector({ nodeRun }: { nodeRun: NodeRun }) {
  const { t, tStatus, locale } = useTranslation();
  const queryClient = useQueryClient();
  const [submitText, setSubmitText] = useState("{\n  \n}");
  const [error, setError] = useState<string | null>(null);

  const refresh = () => void queryClient.invalidateQueries({ queryKey: ["workflow-run", nodeRun.workflow_run_id] });

  const action = useMutation({
    mutationFn: (kind: "approve" | "reject") => (kind === "approve" ? approveNodeRun(nodeRun.id) : rejectNodeRun(nodeRun.id)),
    onSuccess: () => {
      setError(null);
      refresh();
    },
    onError: (value) => setError(value instanceof Error ? value.message : t("nodeRun.actionFailed")),
  });

  const submit = useMutation({
    mutationFn: () => {
      const parsed = JSON.parse(submitText) as Record<string, unknown>;
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) throw new Error(t("nodeRun.invalidSubmit"));
      return submitNodeRun(nodeRun.id, parsed);
    },
    onSuccess: () => {
      setError(null);
      refresh();
    },
    onError: (value) => setError(value instanceof Error ? value.message : t("nodeRun.submitFailed")),
  });

  const waiting = nodeRun.status === "waiting";
  const isApproval = nodeRun.node_type === "human" && nodeRun.node_subtype === "approval";
  const isHumanInput = nodeRun.node_type === "human" && nodeRun.node_subtype === "input";
  const isWait = nodeRun.node_type === "logic" && nodeRun.node_subtype === "wait";
  const canReject = nodeRun.waiting_metadata?.allow_reject !== false;
  const resumeAt = nodeRun.waiting_metadata?.resume_at ? String(nodeRun.waiting_metadata.resume_at) : null;

  return (
    <div className="detail-card">
      <div className="detail-header">
        <div>
          <p className="eyebrow">{t("nodeRun.eyebrow")}</p>
          <h3>{nodeRun.node_name_snapshot}</h3>
          <p>
            {nodeRun.node_type}.{nodeRun.node_subtype} · {nodeRun.node_id}
          </p>
        </div>
        <NodeRunStatusBadge status={nodeRun.status} />
      </div>
      <div className="detail-grid">
        <div><span className="detail-label">{t("nodeRun.status")}</span><strong>{tStatus(nodeRun.status)}</strong></div>
        <div><span className="detail-label">{t("nodeRun.attempt")}</span><strong>{nodeRun.attempt}</strong></div>
        <div><span className="detail-label">{t("nodeRun.started")}</span><strong>{nodeRun.started_at ? new Date(nodeRun.started_at).toLocaleString(locale) : t("common.notStarted")}</strong></div>
        <div><span className="detail-label">{t("nodeRun.finished")}</span><strong>{nodeRun.finished_at ? new Date(nodeRun.finished_at).toLocaleString(locale) : t("common.notFinished")}</strong></div>
      </div>

      {waiting && isApproval && (
        <div className="detail-actions">
          <button className="button button--small button--primary" type="button" disabled={action.isPending} onClick={() => action.mutate("approve")}>
            {action.isPending ? t("nodeRun.approving") : t("nodeRun.approve")}
          </button>
          {canReject && <button className="button button--small button--danger" type="button" disabled={action.isPending} onClick={() => action.mutate("reject")}>
            {action.isPending ? t("nodeRun.rejecting") : t("nodeRun.reject")}
          </button>}
        </div>
      )}

      {waiting && isHumanInput && (
        <div className="detail-actions">
          <textarea className="input code-input" rows={4} value={submitText} onChange={(event) => setSubmitText(event.target.value)} spellCheck={false} />
          <button className="button button--small button--primary" type="button" disabled={submit.isPending} onClick={() => submit.mutate()}>
            {submit.isPending ? t("nodeRun.submitting") : t("nodeRun.submit")}
          </button>
        </div>
      )}

      {waiting && isWait && resumeAt && (
        <div className="detail-warning">{t("nodeRun.waitingUntil", { time: new Date(resumeAt).toLocaleString(locale) })}</div>
      )}

      {error && <div className="detail-warning">{error}</div>}

      <div className="contract-grid">
        <div><span className="detail-label">{t("nodeRun.input")}</span><pre>{JSON.stringify(nodeRun.input, null, 2)}</pre></div>
        <div><span className="detail-label">{t("nodeRun.output")}</span><pre>{JSON.stringify(nodeRun.output ?? null, null, 2)}</pre></div>
        <div><span className="detail-label">{t("nodeRun.executionMetadata")}</span><pre>{JSON.stringify(nodeRun.execution_metadata, null, 2)}</pre></div>
        <div><span className="detail-label">{t("nodeRun.artifacts")}</span>
          {nodeRun.artifacts?.length ? (
            <div className="action-list">
              {nodeRun.artifacts.map((artifact, index) => {
                const uri = typeof artifact.uri === "string" ? artifact.uri : "";
                const artifactId = uri.startsWith("artifact://") ? uri.slice("artifact://".length) : null;
                return (
                  <div className="action-row" key={index}>
                    <div className="action-copy">
                      <strong>{String(artifact.name ?? artifact.type ?? t("nodeRun.artifactFallback"))}</strong>
                      <span>{uri}</span>
                    </div>
                    {artifactId && <a className="text-button" href={`/api/artifacts/${artifactId}/content`} download>{t("nodeRun.download")}</a>}
                  </div>
                );
              })}
            </div>
          ) : (
            <pre>{JSON.stringify(nodeRun.artifacts ?? [], null, 2)}</pre>
          )}
        </div>
        <div><span className="detail-label">{t("nodeRun.error")}</span><pre>{JSON.stringify(nodeRun.error ?? null, null, 2)}</pre></div>
      </div>
    </div>
  );
}
