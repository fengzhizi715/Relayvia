import type { NodeRun } from "../../api/client";
import { NodeRunStatusBadge } from "./RunStatusBadge";

export function NodeRunInspector({ nodeRun }: { nodeRun: NodeRun }) {
  return (
    <div className="detail-card">
      <div className="detail-header">
        <div>
          <p className="eyebrow">NODE RUN</p>
          <h3>{nodeRun.node_name_snapshot}</h3>
          <p>
            {nodeRun.node_type}.{nodeRun.node_subtype} · {nodeRun.node_id}
          </p>
        </div>
        <NodeRunStatusBadge status={nodeRun.status} />
      </div>
      <div className="detail-grid">
        <div><span className="detail-label">Status</span><strong>{nodeRun.status}</strong></div>
        <div><span className="detail-label">Attempt</span><strong>{nodeRun.attempt}</strong></div>
        <div><span className="detail-label">Started</span><strong>{nodeRun.started_at ? new Date(nodeRun.started_at).toLocaleString() : "Not started"}</strong></div>
        <div><span className="detail-label">Finished</span><strong>{nodeRun.finished_at ? new Date(nodeRun.finished_at).toLocaleString() : "Not finished"}</strong></div>
      </div>
      <div className="contract-grid">
        <div><span className="detail-label">Input</span><pre>{JSON.stringify(nodeRun.input, null, 2)}</pre></div>
        <div><span className="detail-label">Output</span><pre>{JSON.stringify(nodeRun.output ?? null, null, 2)}</pre></div>
        <div><span className="detail-label">Execution metadata</span><pre>{JSON.stringify(nodeRun.execution_metadata, null, 2)}</pre></div>
        <div><span className="detail-label">Artifacts</span><pre>{JSON.stringify(nodeRun.artifacts, null, 2)}</pre></div>
        <div><span className="detail-label">Error</span><pre>{JSON.stringify(nodeRun.error ?? null, null, 2)}</pre></div>
      </div>
    </div>
  );
}
