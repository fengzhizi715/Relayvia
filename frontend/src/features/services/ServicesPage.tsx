import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { ApiError, deleteAction, deleteService, getActions, getCredentials, getServices, testService, updateService, type Service, type ServiceAction } from "../../api/client";
import { Modal } from "../../components/Modal";
import { ResourceEmptyState } from "../../components/ResourceEmptyState";
import { StatusBadge } from "../../components/StatusBadge";
import { ActionForm } from "./ActionForm";
import { ServiceForm } from "./ServiceForm";

function statusTone(status: Service["status"]): "success" | "warning" | "danger" | "neutral" {
  return status === "healthy" ? "success" : status === "unhealthy" ? "danger" : "neutral";
}

export function ServicesPage() {
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
  const testMutation = useMutation({ mutationFn: testService, onSuccess: (result) => { setNotice(result.message ?? `Connection ${result.status}`); void queryClient.invalidateQueries({ queryKey: ["services"] }); }, onError: (value) => setNotice(value instanceof ApiError ? value.message : "Connection test failed") });
  const toggleMutation = useMutation({ mutationFn: ({ service }: { service: Service }) => updateService(service.id, { enabled: !service.enabled }), onSuccess: refreshServices, onError: (value) => setNotice(value instanceof ApiError ? value.message : "Update failed") });
  const deleteMutation = useMutation({ mutationFn: deleteService, onSuccess: () => { setShowDelete(null); setSelectedId(null); refreshServices(); }, onError: (value) => setNotice(value instanceof ApiError ? value.message : "Delete failed") });
  const deleteActionMutation = useMutation({ mutationFn: ({ serviceId, actionId }: { serviceId: string; actionId: string }) => deleteAction(serviceId, actionId), onSuccess: () => { setShowDeleteAction(null); refreshActions(); }, onError: (value) => setNotice(value instanceof ApiError ? value.message : "Delete failed") });

  if (services.isLoading) return <div className="loading-state">Loading connected services...</div>;
  if (services.isError) return <div className="inline-error">Unable to load Services. Start the FastAPI backend and retry.</div>;

  const list = services.data ?? [];
  return <div className="resource-page">
    <div className="page-toolbar"><div><p className="eyebrow">SERVICE REGISTRY</p><h3>Existing services</h3><p className="page-description">Connect business and technical services, then describe their callable Actions.</p></div><button className="button button--primary" type="button" onClick={() => { setEditing(undefined); setShowServiceForm(true); }}>+ Connect Service</button></div>
    {notice && <button className="notice" type="button" onClick={() => setNotice(null)}>{notice} · dismiss</button>}
    {list.length === 0 ? <ResourceEmptyState title="No services connected yet." message="Connect an HTTP service to start orchestrating existing capabilities." actionLabel="Connect Service" onAction={() => setShowServiceForm(true)} /> : <div className="resource-layout">
      <div className="resource-list">{list.map((service) => <button className={selectedId === service.id ? "resource-row resource-row--selected" : "resource-row"} key={service.id} type="button" onClick={() => setSelectedId(service.id)}><span className="resource-row-main"><strong>{service.name}</strong><small>HTTP · {service.actions_count} actions</small></span><span className="resource-row-meta"><StatusBadge label={service.status.toUpperCase()} tone={statusTone(service.status)} /><small>{service.enabled ? "Enabled" : "Disabled"}</small></span></button>)}</div>
      {selected ? <section className="detail-card"><div className="detail-header"><div><p className="eyebrow">SERVICE DETAIL</p><h3>{selected.name}</h3><p>{selected.description || "No description"}</p></div><StatusBadge label={selected.status.toUpperCase()} tone={statusTone(selected.status)} /></div><div className="detail-actions"><button className="button button--small" type="button" onClick={() => testMutation.mutate(selected.id)} disabled={testMutation.isPending}>{testMutation.isPending ? "Testing..." : "Test connection"}</button><button className="button button--small" type="button" onClick={() => { setEditing(selected); setShowServiceForm(true); }}>Edit</button><button className="button button--small" type="button" onClick={() => toggleMutation.mutate({ service: selected })}>{selected.enabled ? "Disable" : "Enable"}</button><button className="button button--small button--danger" type="button" onClick={() => setShowDelete(selected)}>Delete</button></div><div className="detail-grid"><div><span className="detail-label">Type</span><strong>HTTP</strong></div><div><span className="detail-label">Base URL</span><strong className="truncate">{selected.base_url}</strong></div><div><span className="detail-label">Credential</span><strong>{selected.credential_name || "None"}</strong></div><div><span className="detail-label">Actions</span><strong>{selected.actions_count}</strong></div><div><span className="detail-label">Last check</span><strong>{selected.last_checked_at ? `${new Date(selected.last_checked_at).toLocaleString()}${selected.last_latency_ms !== null ? ` · ${selected.last_latency_ms} ms` : ""}` : "Not checked"}</strong></div></div>{selected.last_error && <div className="detail-warning">{selected.last_error}</div>}
        <div className="actions-section"><div className="section-heading"><div><p className="eyebrow">SERVICE ACTIONS</p><h4>Callable operations</h4></div><button className="button button--small button--primary" type="button" onClick={() => { setEditingAction(undefined); setShowActionForm(true); }}>+ Add Action</button></div>{actions.isLoading ? <div className="loading-state">Loading actions...</div> : actions.data?.length ? <div className="action-list">{actions.data.map((action) => <div className="action-row" key={action.id}><div className="method-pill">{action.method}</div><div className="action-copy"><strong>{action.name}</strong><span>{action.path}</span></div><div className="action-row-buttons"><button className="text-button" type="button" onClick={() => { setEditingAction(action); setShowActionForm(true); }}>Edit</button><button className="text-button text-button--danger" type="button" onClick={() => setShowDeleteAction(action)}>Delete</button></div></div>)}</div> : <div className="mini-empty">No Actions defined for this Service yet.</div>}</div>
      </section> : <div className="select-state">Select a Service to inspect its health and manage Service Actions.</div>}
    </div>}
    {showServiceForm && <ServiceForm service={editing} credentials={credentials.data ?? []} onClose={() => { setShowServiceForm(false); setEditing(undefined); }} onSaved={refreshServices} />}
    {showActionForm && selected && <ActionForm serviceId={selected.id} action={editingAction} onClose={() => { setShowActionForm(false); setEditingAction(undefined); }} onSaved={refreshActions} />}
    {showDelete && <Modal title="Delete Service" eyebrow="CONFIRM ACTION" onClose={() => setShowDelete(null)}><div className="confirm-copy"><p>Remove <strong>{showDelete.name}</strong> and its Service Actions from the Registry?</p><p>This does not delete or modify the external Service.</p></div><div className="modal-actions"><button className="button" type="button" onClick={() => setShowDelete(null)}>Cancel</button><button className="button button--danger" type="button" disabled={deleteMutation.isPending} onClick={() => deleteMutation.mutate(showDelete.id)}>Delete Service</button></div></Modal>}
    {showDeleteAction && selected && <Modal title="Delete Service Action" eyebrow="CONFIRM ACTION" onClose={() => setShowDeleteAction(null)}><div className="confirm-copy"><p>Remove <strong>{showDeleteAction.name}</strong> from <strong>{selected.name}</strong>?</p></div><div className="modal-actions"><button className="button" type="button" onClick={() => setShowDeleteAction(null)}>Cancel</button><button className="button button--danger" type="button" disabled={deleteActionMutation.isPending} onClick={() => deleteActionMutation.mutate({ serviceId: selected.id, actionId: showDeleteAction.id })}>Delete Action</button></div></Modal>}
  </div>;
}
