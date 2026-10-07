import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { ApiError, deleteAgent, getAgents, getCredentials, getRunners, testAgent, updateAgent, type Agent } from "../../api/client";
import { Modal } from "../../components/Modal";
import { ResourceEmptyState } from "../../components/ResourceEmptyState";
import { StatusBadge } from "../../components/StatusBadge";
import { useTranslation } from "../../i18n";
import { AgentForm } from "./AgentForm";

function statusTone(status: Agent["status"]): "success" | "warning" | "danger" | "neutral" {
  return status === "healthy" ? "success" : status === "unhealthy" ? "danger" : "neutral";
}

export function AgentsPage() {
  const { t, tStatus, locale } = useTranslation();
  const queryClient = useQueryClient();
  const agents = useQuery({ queryKey: ["agents"], queryFn: getAgents });
  const credentials = useQuery({ queryKey: ["credentials"], queryFn: getCredentials });
  const runners = useQuery({ queryKey: ["runners"], queryFn: () => getRunners() });
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
      setNotice(result.message ?? t("agents.connectionStatus", { status: tStatus(result.status) }));
      void queryClient.invalidateQueries({ queryKey: ["agents"] });
    },
    onError: (value) => setNotice(value instanceof ApiError ? value.message : t("common.connectionTestFailed")),
  });
  const toggleMutation = useMutation({
    mutationFn: ({ agent }: { agent: Agent }) => updateAgent(agent.id, { enabled: !agent.enabled }),
    onSuccess: refresh,
    onError: (value) => setNotice(value instanceof ApiError ? value.message : t("common.updateFailed")),
  });
  const deleteMutation = useMutation({
    mutationFn: deleteAgent,
    onSuccess: () => { setShowDelete(null); setSelected(null); refresh(); },
    onError: (value) => setNotice(value instanceof ApiError ? value.message : t("common.deleteFailed")),
  });

  if (agents.isLoading) return <div className="loading-state">{t("agents.loading")}</div>;
  if (agents.isError) return <div className="inline-error">{t("agents.loadError")}</div>;

  const list = agents.data ?? [];
  return (
    <div className="resource-page">
      <div className="page-toolbar">
        <div><p className="eyebrow">{t("agents.eyebrow")}</p><h3>{t("agents.title")}</h3><p className="page-description">{t("agents.description")}</p></div>
        <button className="button button--primary" type="button" onClick={() => { setEditing(undefined); setShowForm(true); }}>{t("agents.connect")}</button>
      </div>
      {notice && <button className="notice" type="button" onClick={() => setNotice(null)}>{notice} · {t("common.dismiss")}</button>}
      {list.length === 0 ? <ResourceEmptyState title={t("agents.emptyTitle")} message={t("agents.emptyMessage")} actionLabel={t("agents.connectAction")} onAction={() => setShowForm(true)} /> : <div className="resource-layout">
        <div className="resource-list">
          {list.map((agent) => <button className={selected?.id === agent.id ? "resource-row resource-row--selected" : "resource-row"} key={agent.id} type="button" onClick={() => setSelected(agent)}>
            <span className="resource-row-main"><strong>{agent.name}</strong><small>{agent.connector_type.toUpperCase()} · {t("agents.capabilities", { count: agent.capabilities.length })}</small></span>
            <span className="resource-row-meta"><StatusBadge label={tStatus(agent.status)} tone={statusTone(agent.status)} /><small>{agent.enabled ? t("common.enabled") : t("common.disabled")}</small></span>
          </button>)}
        </div>
        {selected ? <section className="detail-card">
          <div className="detail-header"><div><p className="eyebrow">{t("agents.detailEyebrow")}</p><h3>{selected.name}</h3><p>{selected.description || t("common.noDescription")}</p></div><StatusBadge label={tStatus(selected.status)} tone={statusTone(selected.status)} /></div>
          <div className="detail-actions"><button className="button button--small" type="button" onClick={() => testMutation.mutate(selected.id)} disabled={testMutation.isPending}>{testMutation.isPending ? t("common.testing") : t("agents.testConnection")}</button><button className="button button--small" type="button" onClick={() => { setEditing(selected); setShowForm(true); }}>{t("common.edit")}</button><button className="button button--small" type="button" onClick={() => toggleMutation.mutate({ agent: selected })}>{selected.enabled ? t("common.disable") : t("common.enable")}</button><button className="button button--small button--danger" type="button" onClick={() => setShowDelete(selected)}>{t("common.delete")}</button></div>
          <div className="detail-grid"><div><span className="detail-label">{t("agents.connector")}</span><strong>{selected.connector_type.toUpperCase()}</strong></div><div><span className="detail-label">{t("agents.endpointExecutable")}</span><strong className="truncate">{selected.endpoint || selected.executable || "—"}</strong></div><div><span className="detail-label">{t("agents.runner")}</span><strong className="truncate">{selected.runner_id || "—"}</strong></div><div><span className="detail-label">{t("agents.lastCheck")}</span><strong>{selected.last_checked_at ? new Date(selected.last_checked_at).toLocaleString(locale) : t("common.notChecked")}{selected.last_latency_ms !== null ? ` · ${selected.last_latency_ms} ms` : ""}</strong></div></div>
          {selected.last_error && <div className="detail-warning">{selected.last_error}</div>}
          <div className="contract-grid"><div><span className="detail-label">{t("agents.capabilitiesLabel")}</span><pre>{JSON.stringify(selected.capabilities, null, 2)}</pre></div><div><span className="detail-label">{t("agents.inputSchema")}</span><pre>{JSON.stringify(selected.input_schema, null, 2)}</pre></div><div><span className="detail-label">{t("agents.outputSchema")}</span><pre>{JSON.stringify(selected.output_schema, null, 2)}</pre></div></div>
        </section> : <div className="select-state">{t("agents.selectState")}</div>}
      </div>}
      {showForm && <AgentForm agent={editing} credentials={credentials.data ?? []} runners={runners.data?.items ?? []} onClose={() => { setShowForm(false); setEditing(undefined); }} onSaved={refresh} />}
      {showDelete && <Modal title={t("agents.deleteTitle")} eyebrow={t("common.confirmAction")} onClose={() => setShowDelete(null)}><div className="confirm-copy"><p>{t("agents.deleteConfirm", { name: showDelete.name })}</p><p>{t("agents.deleteNote")}</p></div><div className="modal-actions"><button className="button" type="button" onClick={() => setShowDelete(null)}>{t("common.cancel")}</button><button className="button button--danger" type="button" disabled={deleteMutation.isPending} onClick={() => deleteMutation.mutate(showDelete.id)}>{t("agents.deleteAction")}</button></div></Modal>}
    </div>
  );
}
