import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { ApiError, deleteAgent, getAgents, getCredentials, getRunners, testAgent, updateAgent, type Agent } from "../../api/client";
import { Modal } from "../../components/Modal";
import { ResourceEmptyState } from "../../components/ResourceEmptyState";
import { StatusBadge } from "../../components/StatusBadge";
import { AgentForm } from "./AgentForm";

function statusTone(status: Agent["status"]): "success" | "warning" | "danger" | "neutral" {
  return status === "healthy" ? "success" : status === "unhealthy" ? "danger" : "neutral";
}

function formatDate(value: string | null) {
  return value ? new Date(value).toLocaleString() : "Not checked";
}

export function AgentsPage() {
  const queryClient = useQueryClient();
  const agents = useQuery({ queryKey: ["agents"], queryFn: getAgents });
  const credentials = useQuery({ queryKey: ["credentials"], queryFn: getCredentials });
  const runners = useQuery({ queryKey: ["runners"], queryFn: getRunners });
  const [selected, setSelected] = useState<Agent | null>(null);
  const [editing, setEditing] = useState<Agent | undefined>();
  const [showForm, setShowForm] = useState(false);
  const [showDelete, setShowDelete] = useState<Agent | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const refresh = () => {
    setShowForm(false);
    setEditing(undefined);
    void queryClient.invalidateQueries({ queryKey: ["agents"] });
  };
  const testMutation = useMutation({
    mutationFn: testAgent,
    onSuccess: (result) => {
      setNotice(result.message ?? `Connection ${result.status}`);
      void queryClient.invalidateQueries({ queryKey: ["agents"] });
    },
    onError: (value) => setNotice(value instanceof ApiError ? value.message : "Connection test failed"),
  });
  const toggleMutation = useMutation({
    mutationFn: ({ agent }: { agent: Agent }) => updateAgent(agent.id, { enabled: !agent.enabled }),
    onSuccess: refresh,
    onError: (value) => setNotice(value instanceof ApiError ? value.message : "Update failed"),
  });
  const deleteMutation = useMutation({
    mutationFn: deleteAgent,
    onSuccess: () => { setShowDelete(null); setSelected(null); refresh(); },
    onError: (value) => setNotice(value instanceof ApiError ? value.message : "Delete failed"),
  });

  if (agents.isLoading) return <div className="loading-state">Loading connected agents...</div>;
  if (agents.isError) return <div className="inline-error">Unable to load Agents. Start the FastAPI backend and retry.</div>;

  const list = agents.data ?? [];
  return (
    <div className="resource-page">
      <div className="page-toolbar">
        <div><p className="eyebrow">AGENT REGISTRY</p><h3>Existing agents</h3><p className="page-description">Connect and manage invocation metadata for agents you already operate.</p></div>
        <button className="button button--primary" type="button" onClick={() => { setEditing(undefined); setShowForm(true); }}>+ Connect Agent</button>
      </div>
      {notice && <button className="notice" type="button" onClick={() => setNotice(null)}>{notice} · dismiss</button>}
      {list.length === 0 ? <ResourceEmptyState title="No agents connected yet." message="Connect your first existing HTTP agent to make it available to future Workflow Nodes." actionLabel="Connect Agent" onAction={() => setShowForm(true)} /> : <div className="resource-layout">
        <div className="resource-list">
          {list.map((agent) => <button className={selected?.id === agent.id ? "resource-row resource-row--selected" : "resource-row"} key={agent.id} type="button" onClick={() => setSelected(agent)}>
            <span className="resource-row-main"><strong>{agent.name}</strong><small>{agent.connector_type.toUpperCase()} · {agent.capabilities.length} capabilities</small></span>
            <span className="resource-row-meta"><StatusBadge label={agent.status.toUpperCase()} tone={statusTone(agent.status)} /><small>{agent.enabled ? "Enabled" : "Disabled"}</small></span>
          </button>)}
        </div>
        {selected ? <section className="detail-card">
          <div className="detail-header"><div><p className="eyebrow">AGENT DETAIL</p><h3>{selected.name}</h3><p>{selected.description || "No description"}</p></div><StatusBadge label={selected.status.toUpperCase()} tone={statusTone(selected.status)} /></div>
          <div className="detail-actions"><button className="button button--small" type="button" onClick={() => testMutation.mutate(selected.id)} disabled={testMutation.isPending}>{testMutation.isPending ? "Testing..." : "Test connection"}</button><button className="button button--small" type="button" onClick={() => { setEditing(selected); setShowForm(true); }}>Edit</button><button className="button button--small" type="button" onClick={() => toggleMutation.mutate({ agent: selected })}>{selected.enabled ? "Disable" : "Enable"}</button><button className="button button--small button--danger" type="button" onClick={() => setShowDelete(selected)}>Delete</button></div>
          <div className="detail-grid"><div><span className="detail-label">Connector</span><strong>{selected.connector_type.toUpperCase()}</strong></div><div><span className="detail-label">Endpoint / executable</span><strong className="truncate">{selected.endpoint || selected.executable || "—"}</strong></div><div><span className="detail-label">Runner</span><strong className="truncate">{selected.runner_id || "—"}</strong></div><div><span className="detail-label">Last check</span><strong>{formatDate(selected.last_checked_at)}{selected.last_latency_ms !== null ? ` · ${selected.last_latency_ms} ms` : ""}</strong></div></div>
          {selected.last_error && <div className="detail-warning">{selected.last_error}</div>}
          <div className="contract-grid"><div><span className="detail-label">Capabilities</span><pre>{JSON.stringify(selected.capabilities, null, 2)}</pre></div><div><span className="detail-label">Input schema</span><pre>{JSON.stringify(selected.input_schema, null, 2)}</pre></div><div><span className="detail-label">Output schema</span><pre>{JSON.stringify(selected.output_schema, null, 2)}</pre></div></div>
        </section> : <div className="select-state">Select an Agent to inspect its connection and invocation contract.</div>}
      </div>}
      {showForm && <AgentForm agent={editing} credentials={credentials.data ?? []} runners={runners.data ?? []} onClose={() => { setShowForm(false); setEditing(undefined); }} onSaved={refresh} />}
      {showDelete && <Modal title="Delete Agent" eyebrow="CONFIRM ACTION" onClose={() => setShowDelete(null)}><div className="confirm-copy"><p>Remove <strong>{showDelete.name}</strong> from the Agent Registry?</p><p>This does not delete or modify the external Agent.</p></div><div className="modal-actions"><button className="button" type="button" onClick={() => setShowDelete(null)}>Cancel</button><button className="button button--danger" type="button" disabled={deleteMutation.isPending} onClick={() => deleteMutation.mutate(showDelete.id)}>Delete Agent</button></div></Modal>}
    </div>
  );
}
