import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { getRunners, revokeRunner, rotateRunnerToken, setRunnerEnabled, type Runner } from "../../api/client";
import { StatusBadge } from "../../components/StatusBadge";

function statusTone(status: Runner["status"]): "success" | "danger" | "neutral" {
  return status === "online" ? "success" : status === "offline" ? "danger" : "neutral";
}

export function RunnerListPage() {
  const queryClient = useQueryClient();
  const [rotatedToken, setRotatedToken] = useState<string | null>(null);
  const runners = useQuery({ queryKey: ["runners"], queryFn: getRunners, refetchInterval: 5000 });
  const updateStatus = useMutation({
    mutationFn: ({ id, enabled }: { id: string; enabled: boolean }) => setRunnerEnabled(id, enabled),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["runners"] }),
  });
  const revoke = useMutation({ mutationFn: revokeRunner, onSuccess: () => queryClient.invalidateQueries({ queryKey: ["runners"] }) });
  const rotate = useMutation({ mutationFn: rotateRunnerToken, onSuccess: (value) => setRotatedToken(value.enrollment_token) });

  if (runners.isLoading) return <div className="loading-state">Loading runners...</div>;
  if (runners.isError) return <div className="inline-error">Unable to load Runners. Start the FastAPI backend and retry.</div>;

  const list = runners.data ?? [];
  return (
    <div className="resource-page">
      <div className="page-toolbar">
        <div>
          <p className="eyebrow">RUNNER REGISTRY</p>
          <h3>Local execution runners</h3>
          <p className="page-description">Independently started components that pull and execute local capabilities (shell / git / test commands).</p>
        </div>
      </div>
      {rotatedToken ? <div className="inline-success">New Runner token (shown once): <code>{rotatedToken}</code></div> : null}
      {list.length === 0 ? (
        <div className="empty-state"><div className="empty-icon">R</div><h3>No runners connected.</h3><p>Start one with ./run-runner.sh on a machine that can run local commands.</p></div>
      ) : (
        <div className="resource-list">
          {list.map((runner) => (
            <div className="resource-row" key={runner.id}>
              <span className="resource-row-main">
                <strong>{runner.name}</strong>
                <small>{runner.hostname}{runner.platform ? ` · ${runner.platform}` : ""} · ID: {runner.id}</small>
              </span>
              <span className="resource-row-meta">
                <span className="action-copy">
                  <span>{runner.capabilities.map((cap) => cap.toUpperCase()).join(" · ")}</span>
                  <small>Last seen {runner.last_seen_at ? new Date(runner.last_seen_at).toLocaleString() : "—"}</small>
                </span>
                <StatusBadge label={runner.status.toUpperCase()} tone={statusTone(runner.status)} />
                <button className="button button--secondary" disabled={updateStatus.isPending} onClick={() => updateStatus.mutate({ id: runner.id, enabled: runner.status === "disabled" })} type="button">
                  {runner.status === "disabled" ? "Enable" : "Disable"}
                </button>
                <button className="button button--secondary" disabled={rotate.isPending} onClick={() => { if (window.confirm(`Rotate token for ${runner.name}? The current Runner process will be disconnected.`)) rotate.mutate(runner.id); }} type="button">Rotate token</button>
                <button className="button button--danger" disabled={revoke.isPending} onClick={() => { if (window.confirm(`Revoke ${runner.name}? This immediately invalidates its token and disables it.`)) revoke.mutate(runner.id); }} type="button">Revoke</button>
              </span>
            </div>
          ))}
        </div>
      )}
      {updateStatus.isError || revoke.isError || rotate.isError ? <div className="inline-error">Unable to update this Runner.</div> : null}
    </div>
  );
}
