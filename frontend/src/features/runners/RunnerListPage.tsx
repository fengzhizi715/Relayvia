import { useQuery } from "@tanstack/react-query";

import { getRunners, type Runner } from "../../api/client";
import { StatusBadge } from "../../components/StatusBadge";

function statusTone(status: Runner["status"]): "success" | "danger" | "neutral" {
  return status === "online" ? "success" : status === "offline" ? "danger" : "neutral";
}

export function RunnerListPage() {
  const runners = useQuery({ queryKey: ["runners"], queryFn: getRunners, refetchInterval: 5000 });

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
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
