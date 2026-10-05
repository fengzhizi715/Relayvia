import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { ApiError, deleteAction, deleteService, getActions, getCredentials, getServices, testService, updateService, type Service, type ServiceAction } from "../../api/client";
import { Modal } from "../../components/Modal";
import { ResourceEmptyState } from "../../components/ResourceEmptyState";
import { StatusBadge } from "../../components/StatusBadge";
import { useTranslation } from "../../i18n";
import { ActionForm } from "./ActionForm";
import { ServiceForm } from "./ServiceForm";

function statusTone(status: Service["status"]): "success" | "warning" | "danger" | "neutral" {
  return status === "healthy" ? "success" : status === "unhealthy" ? "danger" : "neutral";
}

export function ServicesPage() {
  const { t, tStatus, locale } = useTranslation();
  const queryClient = useQueryClient();
  const services = useQuery({ queryKey: ["services"], queryFn: getServices });
  const credentials = useQuery({ queryKey: ["credentials"], queryFn: getCredentials });
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [editing, setEditing] = useState<Service | undefined>();
  const [showServiceForm, setShowServiceForm] = useState(false);
  const [showActionForm, setShowActionForm] = useState(false);
  const [editingAction, setEditingAction] = useState<ServiceAction | undefined>();
  const [showDelete, setShowDelete] = useState<Service | null>(null);
  const [showDeleteAction, setShowDeleteAction] = useState<ServiceAction | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const selected = services.data?.find((service) => service.id === selectedId) ?? null;
  const actions = useQuery({ queryKey: ["service-actions", selectedId], queryFn: () => getActions(selectedId!), enabled: Boolean(selectedId) });

  const refreshServices = () => { setShowServiceForm(false); setEditing(undefined); void queryClient.invalidateQueries({ queryKey: ["services"] }); };
  const refreshActions = () => { setShowActionForm(false); setEditingAction(undefined); void queryClient.invalidateQueries({ queryKey: ["service-actions", selectedId] }); void queryClient.invalidateQueries({ queryKey: ["services"] }); };
  const testMutation = useMutation({ mutationFn: testService, onSuccess: (result) => { setNotice(result.message ?? t("agents.connectionStatus", { status: tStatus(result.status) })); void queryClient.invalidateQueries({ queryKey: ["services"] }); }, onError: (value) => setNotice(value instanceof ApiError ? value.message : t("common.connectionTestFailed")) });
  const toggleMutation = useMutation({ mutationFn: ({ service }: { service: Service }) => updateService(service.id, { enabled: !service.enabled }), onSuccess: refreshServices, onError: (value) => setNotice(value instanceof ApiError ? value.message : t("common.updateFailed")) });
  const deleteMutation = useMutation({ mutationFn: deleteService, onSuccess: () => { setShowDelete(null); setSelectedId(null); refreshServices(); }, onError: (value) => setNotice(value instanceof ApiError ? value.message : t("common.deleteFailed")) });
  const deleteActionMutation = useMutation({ mutationFn: ({ serviceId, actionId }: { serviceId: string; actionId: string }) => deleteAction(serviceId, actionId), onSuccess: () => { setShowDeleteAction(null); refreshActions(); }, onError: (value) => setNotice(value instanceof ApiError ? value.message : t("common.deleteFailed")) });

  if (services.isLoading) return <div className="loading-state">{t("services.loading")}</div>;
  if (services.isError) return <div className="inline-error">{t("services.loadError")}</div>;

  const list = services.data ?? [];
  return <div className="resource-page">
    <div className="page-toolbar"><div><p className="eyebrow">{t("services.eyebrow")}</p><h3>{t("services.title")}</h3><p className="page-description">{t("services.description")}</p></div><button className="button button--primary" type="button" onClick={() => { setEditing(undefined); setShowServiceForm(true); }}>{t("services.connect")}</button></div>
    {notice && <button className="notice" type="button" onClick={() => setNotice(null)}>{notice} · {t("common.dismiss")}</button>}
    {list.length === 0 ? <ResourceEmptyState title={t("services.emptyTitle")} message={t("services.emptyMessage")} actionLabel={t("services.connectAction")} onAction={() => setShowServiceForm(true)} /> : <div className="resource-layout">
      <div className="resource-list">{list.map((service) => <button className={selectedId === service.id ? "resource-row resource-row--selected" : "resource-row"} key={service.id} type="button" onClick={() => setSelectedId(service.id)}><span className="resource-row-main"><strong>{service.name}</strong><small>HTTP · {t("services.actionsCount", { count: service.actions_count })}</small></span><span className="resource-row-meta"><StatusBadge label={tStatus(service.status)} tone={statusTone(service.status)} /><small>{service.enabled ? t("common.enabled") : t("common.disabled")}</small></span></button>)}</div>
      {selected ? <section className="detail-card"><div className="detail-header"><div><p className="eyebrow">{t("services.detailEyebrow")}</p><h3>{selected.name}</h3><p>{selected.description || t("common.noDescription")}</p></div><StatusBadge label={tStatus(selected.status)} tone={statusTone(selected.status)} /></div><div className="detail-actions"><button className="button button--small" type="button" onClick={() => testMutation.mutate(selected.id)} disabled={testMutation.isPending}>{testMutation.isPending ? t("common.testing") : t("agents.testConnection")}</button><button className="button button--small" type="button" onClick={() => { setEditing(selected); setShowServiceForm(true); }}>{t("common.edit")}</button><button className="button button--small" type="button" onClick={() => toggleMutation.mutate({ service: selected })}>{selected.enabled ? t("common.disable") : t("common.enable")}</button><button className="button button--small button--danger" type="button" onClick={() => setShowDelete(selected)}>{t("common.delete")}</button></div><div className="detail-grid"><div><span className="detail-label">{t("services.type")}</span><strong>HTTP</strong></div><div><span className="detail-label">{t("services.baseUrl")}</span><strong className="truncate">{selected.base_url}</strong></div><div><span className="detail-label">{t("services.credential")}</span><strong>{selected.credential_name || t("common.none")}</strong></div><div><span className="detail-label">{t("services.actions")}</span><strong>{selected.actions_count}</strong></div><div><span className="detail-label">{t("services.lastCheck")}</span><strong>{selected.last_checked_at ? `${new Date(selected.last_checked_at).toLocaleString(locale)}${selected.last_latency_ms !== null ? ` · ${selected.last_latency_ms} ms` : ""}` : t("common.notChecked")}</strong></div></div>{selected.last_error && <div className="detail-warning">{selected.last_error}</div>}
        <div className="actions-section"><div className="section-heading"><div><p className="eyebrow">{t("services.actionsEyebrow")}</p><h4>{t("services.callableOperations")}</h4></div><button className="button button--small button--primary" type="button" onClick={() => { setEditingAction(undefined); setShowActionForm(true); }}>{t("services.addAction")}</button></div>{actions.isLoading ? <div className="loading-state">{t("services.loadingActions")}</div> : actions.data?.length ? <div className="action-list">{actions.data.map((action) => <div className="action-row" key={action.id}><div className="method-pill">{action.method}</div><div className="action-copy"><strong>{action.name}</strong><span>{action.path}</span></div><div className="action-row-buttons"><button className="text-button" type="button" onClick={() => { setEditingAction(action); setShowActionForm(true); }}>{t("common.edit")}</button><button className="text-button text-button--danger" type="button" onClick={() => setShowDeleteAction(action)}>{t("common.delete")}</button></div></div>)}</div> : <div className="mini-empty">{t("services.noActions")}</div>}</div>
      </section> : <div className="select-state">{t("services.selectState")}</div>}
    </div>}
    {showServiceForm && <ServiceForm service={editing} credentials={credentials.data ?? []} onClose={() => { setShowServiceForm(false); setEditing(undefined); }} onSaved={refreshServices} />}
    {showActionForm && selected && <ActionForm serviceId={selected.id} action={editingAction} onClose={() => { setShowActionForm(false); setEditingAction(undefined); }} onSaved={refreshActions} />}
    {showDelete && <Modal title={t("services.deleteTitle")} eyebrow={t("common.confirmAction")} onClose={() => setShowDelete(null)}><div className="confirm-copy"><p>{t("services.deleteConfirm", { name: showDelete.name })}</p><p>{t("services.deleteNote")}</p></div><div className="modal-actions"><button className="button" type="button" onClick={() => setShowDelete(null)}>{t("common.cancel")}</button><button className="button button--danger" type="button" disabled={deleteMutation.isPending} onClick={() => deleteMutation.mutate(showDelete.id)}>{t("services.deleteService")}</button></div></Modal>}
    {showDeleteAction && selected && <Modal title={t("services.deleteActionTitle")} eyebrow={t("common.confirmAction")} onClose={() => setShowDeleteAction(null)}><div className="confirm-copy"><p>{t("services.deleteActionConfirm", { name: showDeleteAction.name, service: selected.name })}</p></div><div className="modal-actions"><button className="button" type="button" onClick={() => setShowDeleteAction(null)}>{t("common.cancel")}</button><button className="button button--danger" type="button" disabled={deleteActionMutation.isPending} onClick={() => deleteActionMutation.mutate({ serviceId: selected.id, actionId: showDeleteAction.id })}>{t("services.deleteAction")}</button></div></Modal>}
  </div>;
}
