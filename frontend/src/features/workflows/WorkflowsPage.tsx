import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  ApiError,
  createWorkflow,
  createWorkflowVersion,
  createWorkflowRun,
  getWorkflowGraph,
  getWorkflowVersions,
  getWorkflows,
  updateWorkflow,
  updateWorkflowGraph,
  type Workflow,
  type WorkflowGraph,
  type WorkflowVersion,
} from "../../api/client";
import { useAppStore } from "../../app/store/useAppStore";
import { JsonEditor } from "../../components/JsonEditor";
import { Modal } from "../../components/Modal";
import { ResourceEmptyState } from "../../components/ResourceEmptyState";
import { StatusBadge } from "../../components/StatusBadge";
import { useTranslation } from "../../i18n";
import { WorkflowBuilderPage } from "../../workflow/canvas/WorkflowBuilderPage";
import { useWorkflowBuilderStore } from "../../workflow/store/workflowBuilderStore";

const emptyGraph: WorkflowGraph = {
  schema_version: "1.0",
  nodes: [],
  edges: [],
  variables: {},
  metadata: {},
};

function statusTone(status: Workflow["status"]): "success" | "warning" | "neutral" {
  return status === "active" ? "success" : status === "archived" ? "warning" : "neutral";
}

export function WorkflowsPage() {
  const { t, tStatus, locale } = useTranslation();
  const queryClient = useQueryClient();
  const workflows = useQuery({ queryKey: ["workflows"], queryFn: () => getWorkflows() });
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selectedVersion, setSelectedVersion] = useState<WorkflowVersion | null>(null);
  const [graphText, setGraphText] = useState(JSON.stringify(emptyGraph, null, 2));
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [formMode, setFormMode] = useState<"create" | "rename" | null>(null);
  const [formName, setFormName] = useState("");
  const [formDescription, setFormDescription] = useState("");
  const [builder, setBuilder] = useState<{ workflowId: string; version?: number } | null>(null);
  const [runModal, setRunModal] = useState(false);
  const [runInputText, setRunInputText] = useState("{\n  \n}");
  const [runError, setRunError] = useState<string | null>(null);
  const setActiveSection = useAppStore((state) => state.setActiveSection);
  const setPendingRunId = useAppStore((state) => state.setPendingRunId);

  const selected = workflows.data?.find((workflow) => workflow.id === selectedId) ?? null;
  const graph = useQuery({ queryKey: ["workflow-graph", selectedId], queryFn: () => getWorkflowGraph(selectedId!), enabled: Boolean(selectedId) });
  const versions = useQuery({ queryKey: ["workflow-versions", selectedId], queryFn: () => getWorkflowVersions(selectedId!), enabled: Boolean(selectedId) });

  useEffect(() => {
    if (graph.data && !selectedVersion) setGraphText(JSON.stringify(graph.data.graph, null, 2));
  }, [graph.data, selectedVersion]);

  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: ["workflows"] });
    if (selectedId) {
      void queryClient.invalidateQueries({ queryKey: ["workflow-graph", selectedId] });
      void queryClient.invalidateQueries({ queryKey: ["workflow-versions", selectedId] });
    }
  };

  const workflowMutation = useMutation({
    mutationFn: () => formMode === "create" ? createWorkflow({ name: formName, description: formDescription }) : updateWorkflow(selectedId!, { name: formName, description: formDescription }),
    onSuccess: (workflow) => {
      setSelectedId(workflow.id);
      setSelectedVersion(null);
      setFormMode(null);
      setNotice(formMode === "create" ? t("workflows.created") : t("workflows.renamed"));
      refresh();
      if (formMode === "create") setBuilder({ workflowId: workflow.id });
    },
    onError: (value) => setError(value instanceof ApiError ? `${value.message} (${value.code})` : t("workflows.updateFailed")),
  });
  const graphMutation = useMutation({
    mutationFn: (value: WorkflowGraph) => updateWorkflowGraph(selectedId!, value),
    onSuccess: () => { setError(null); setNotice(t("workflows.draftSaved")); refresh(); },
    onError: (value) => setError(value instanceof ApiError ? `${value.message} (${value.code})` : t("workflows.draftSaveFailed")),
  });
  const versionMutation = useMutation({
    mutationFn: () => createWorkflowVersion(selectedId!),
    onSuccess: (version) => { setNotice(t("workflows.versionCreated", { version: version.version })); refresh(); },
    onError: (value) => setError(value instanceof ApiError ? `${value.message} (${value.code})` : t("workflows.versionCreateFailed")),
  });
  const archiveMutation = useMutation({
    mutationFn: () => updateWorkflow(selectedId!, { status: "archived" }),
    onSuccess: () => { setSelectedId(null); setSelectedVersion(null); setNotice(t("workflows.archived")); refresh(); },
    onError: (value) => setError(value instanceof ApiError ? `${value.message} (${value.code})` : t("workflows.archiveFailed")),
  });
  const runMutation = useMutation({
    mutationFn: (runInput: Record<string, unknown>) => createWorkflowRun(selectedId!, { input: runInput }),
    onSuccess: (run) => {
      setRunModal(false);
      setRunError(null);
      setActiveSection("runs");
      setPendingRunId(run.id);
    },
    onError: (value) => setRunError(value instanceof ApiError ? `${value.message} (${value.code})` : t("workflows.runCreateFailed")),
  });

  function openRun() {
    if (!selected?.current_version) return;
    setRunError(null);
    setRunInputText("{\n  \n}");
    setRunModal(true);
  }

  function submitRun(event: React.FormEvent) {
    event.preventDefault();
    setRunError(null);
    try {
      const parsed = JSON.parse(runInputText);
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) throw new Error(t("runModal.mustBeObject"));
      runMutation.mutate(parsed as Record<string, unknown>);
    } catch (value) {
      setRunError(value instanceof Error ? value.message : t("runModal.invalidJson"));
    }
  }

  function openCreate() {
    setError(null);
    setFormName("");
    setFormDescription("");
    setFormMode("create");
  }

  function openRename() {
    if (!selected) return;
    setError(null);
    setFormName(selected.name);
    setFormDescription(selected.description ?? "");
    setFormMode("rename");
  }

  function hasUnsavedBuilderChanges(): boolean {
    const state = useWorkflowBuilderStore.getState();
    return state.workflowId !== null && !state.readOnly && state.isDirty;
  }

  function openBuilder(workflowId: string, version?: number) {
    if (hasUnsavedBuilderChanges() && !window.confirm(t("workflows.unsavedBuilderConfirm"))) return;
    setSelectedId(workflowId);
    setSelectedVersion(null);
    setError(null);
    setBuilder({ workflowId, version });
  }

  function saveGraph() {
    try {
      const value = JSON.parse(graphText) as WorkflowGraph;
      if (!value || value.schema_version !== "1.0" || !Array.isArray(value.nodes) || !Array.isArray(value.edges)) throw new Error(t("workflows.graphInvalid"));
      graphMutation.mutate(value);
    } catch (value) {
      setError(value instanceof Error ? value.message : t("workflows.graphInvalidJson"));
    }
  }

  if (workflows.isLoading) return <div className="loading-state">{t("workflows.loading")}</div>;
  if (workflows.isError) return <div className="inline-error">{t("workflows.loadError")}</div>;
  if (builder) return <WorkflowBuilderPage workflowId={builder.workflowId} version={builder.version} onBack={() => setBuilder(null)} />;
  const list = workflows.data ?? [];

  return <div className="resource-page">
    <div className="page-toolbar"><div><p className="eyebrow">{t("workflows.eyebrow")}</p><h3>{t("workflows.title")}</h3><p className="page-description">{t("workflows.description")}</p></div><button className="button button--primary" type="button" onClick={openCreate}>{t("workflows.create")}</button></div>
    {notice && <button className="notice" type="button" onClick={() => setNotice(null)}>{notice} · {t("common.dismiss")}</button>}
    {error && <button className="notice notice--error" type="button" onClick={() => setError(null)}>{error} · {t("common.dismiss")}</button>}
    {list.length === 0 ? <ResourceEmptyState title={t("workflows.emptyTitle")} message={t("workflows.emptyMessage")} actionLabel={t("workflows.createAction")} onAction={openCreate} /> : <div className="resource-layout">
      <div className="resource-list">{list.map((workflow) => <button className={selectedId === workflow.id ? "resource-row resource-row--selected" : "resource-row"} key={workflow.id} type="button" onClick={() => { setSelectedId(workflow.id); setSelectedVersion(null); setError(null); }}><span className="resource-row-main"><strong>{workflow.name}</strong><small>{workflow.current_version ? `v${workflow.current_version}` : t("workflows.draftOnly")} · {t("workflows.nodesCount", { count: workflow.draft_graph.nodes.length })}</small></span><span className="resource-row-meta"><StatusBadge label={tStatus(workflow.status)} tone={statusTone(workflow.status)} /></span></button>)}</div>
      {selected ? <section className="detail-card workflow-detail"><div className="detail-header"><div><p className="eyebrow">{t("workflows.detailEyebrow")}</p><h3>{selected.name}</h3><p>{selected.description || t("common.noDescription")}</p></div><StatusBadge label={tStatus(selected.status)} tone={statusTone(selected.status)} /></div>
        <div className="detail-actions"><button className="button button--small button--primary" type="button" onClick={() => openBuilder(selected.id)}>{t("workflows.openBuilder")}</button>{selected.current_version ? <button className="button button--small" type="button" onClick={openRun}>{t("workflows.runVersion", { version: selected.current_version })}</button> : null}<button className="button button--small" type="button" onClick={openRename}>{t("workflows.rename")}</button><button className="button button--small button--danger" type="button" onClick={() => archiveMutation.mutate()} disabled={archiveMutation.isPending}>{archiveMutation.isPending ? t("workflows.archiving") : t("workflows.archive")}</button></div>
        <div className="detail-grid"><div><span className="detail-label">{t("workflows.schema")}</span><strong>{selected.graph_schema_version}</strong></div><div><span className="detail-label">{t("workflows.currentVersion")}</span><strong>{selected.current_version ? `v${selected.current_version}` : t("workflows.notPublished")}</strong></div><div><span className="detail-label">{t("workflows.draftNodes")}</span><strong>{selected.draft_graph.nodes.length}</strong></div><div><span className="detail-label">{t("workflows.draftEdges")}</span><strong>{selected.draft_graph.edges.length}</strong></div></div>
        <div className="graph-debug"><div className="section-heading"><div><p className="eyebrow">{t("workflows.draftGraph")}</p><h4>{selectedVersion ? t("workflows.versionReadOnly", { version: selectedVersion.version }) : t("workflows.graphSchemaJson")}</h4></div>{!selectedVersion && <div className="detail-actions"><button className="button button--small" type="button" onClick={saveGraph} disabled={graphMutation.isPending}>{graphMutation.isPending ? t("common.saving") : t("workflows.saveDraft")}</button><button className="button button--small button--primary" type="button" onClick={() => versionMutation.mutate()} disabled={versionMutation.isPending}>{versionMutation.isPending ? t("workflows.creating") : t("workflows.createVersion")}</button></div>}</div><JsonEditor label={t("workflows.graphJson")} value={graphText} onChange={setGraphText} rows={18} readOnly={Boolean(selectedVersion)} hint={selectedVersion ? t("workflows.historicalHint") : t("workflows.draftHint")} />{graph.data?.warnings.map((warning) => <div className="detail-warning" key={warning.code}>{warning.message}</div>)}</div>
        <div className="actions-section"><div className="section-heading"><div><p className="eyebrow">{t("workflows.historyEyebrow")}</p><h4>{t("workflows.immutableVersions")}</h4></div>{selectedVersion && <button className="text-button" type="button" onClick={() => { setSelectedVersion(null); if (graph.data) setGraphText(JSON.stringify(graph.data.graph, null, 2)); }}>{t("workflows.backToDraft")}</button>}</div>{versions.isLoading ? <div className="loading-state">{t("workflows.loadingVersions")}</div> : versions.data?.length ? <div className="version-list">{versions.data.map((version) => <div className={selectedVersion?.version === version.version ? "version-row version-row--selected" : "version-row"} key={version.id}><button className="version-row-main" type="button" onClick={() => { setSelectedVersion(version); setGraphText(JSON.stringify(version.graph, null, 2)); }}><span><strong>v{version.version}</strong><small>{version.change_note || t("workflows.noChangeNote")}</small></span><small>{new Date(version.created_at).toLocaleString(locale)}</small></button><button className="button button--small" type="button" onClick={() => openBuilder(selected.id, version.version)}>{t("workflows.viewInBuilder")}</button></div>)}</div> : <div className="mini-empty">{t("workflows.noVersions")}</div>}</div>
      </section> : <div className="select-state">{t("workflows.selectState")}</div>}
    </div>}
    {formMode && <Modal title={formMode === "create" ? t("workflowForm.createTitle") : t("workflowForm.renameTitle")} eyebrow={t("workflowForm.eyebrow")} onClose={() => setFormMode(null)}><form className="form-stack" onSubmit={(event) => { event.preventDefault(); setError(null); workflowMutation.mutate(); }}><label className="field"><span>{t("workflowForm.name")}</span><input className="input" required value={formName} onChange={(event) => setFormName(event.target.value)} placeholder={t("workflowForm.namePlaceholder")} /></label><label className="field"><span>{t("workflowForm.description")}</span><textarea className="input" rows={3} value={formDescription} onChange={(event) => setFormDescription(event.target.value)} placeholder={t("workflowForm.descriptionPlaceholder")} /></label>{error && <div className="inline-error">{error}</div>}<div className="modal-actions"><button className="button" type="button" onClick={() => setFormMode(null)}>{t("common.cancel")}</button><button className="button button--primary" type="submit" disabled={workflowMutation.isPending}>{workflowMutation.isPending ? t("common.saving") : formMode === "create" ? t("workflowForm.createTitle") : t("workflowForm.saveName")}</button></div></form></Modal>}
    {runModal && <Modal title={t("runModal.title")} eyebrow={t("runModal.eyebrow")} onClose={() => setRunModal(false)}><form className="form-stack" onSubmit={submitRun}><p className="page-description">{t("runModal.description", { version: selected?.current_version ?? "" })}</p><label className="field"><span>{t("runModal.input")}</span><textarea className="input code-input" rows={6} value={runInputText} onChange={(event) => setRunInputText(event.target.value)} spellCheck={false} /></label>{runError && <div className="inline-error">{runError}</div>}<div className="modal-actions"><button className="button" type="button" onClick={() => setRunModal(false)}>{t("common.cancel")}</button><button className="button button--primary" type="submit" disabled={runMutation.isPending}>{runMutation.isPending ? t("workflows.creating") : t("runModal.createAndRun")}</button></div></form></Modal>}
  </div>;
}
