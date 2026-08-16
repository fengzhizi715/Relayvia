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
      setNotice(formMode === "create" ? "Workflow created." : "Workflow renamed.");
      refresh();
      if (formMode === "create") setBuilder({ workflowId: workflow.id });
    },
    onError: (value) => setError(value instanceof ApiError ? `${value.message} (${value.code})` : "Workflow update failed"),
  });
  const graphMutation = useMutation({
    mutationFn: (value: WorkflowGraph) => updateWorkflowGraph(selectedId!, value),
    onSuccess: () => { setError(null); setNotice("Draft saved."); refresh(); },
    onError: (value) => setError(value instanceof ApiError ? `${value.message} (${value.code})` : "Draft save failed"),
  });
  const versionMutation = useMutation({
    mutationFn: () => createWorkflowVersion(selectedId!),
    onSuccess: (version) => { setNotice(`Created Workflow Version v${version.version}.`); refresh(); },
    onError: (value) => setError(value instanceof ApiError ? `${value.message} (${value.code})` : "Version creation failed"),
  });
  const archiveMutation = useMutation({
    mutationFn: () => updateWorkflow(selectedId!, { status: "archived" }),
    onSuccess: () => { setSelectedId(null); setSelectedVersion(null); setNotice("Workflow archived."); refresh(); },
    onError: (value) => setError(value instanceof ApiError ? `${value.message} (${value.code})` : "Archive failed"),
  });
  const runMutation = useMutation({
    mutationFn: (runInput: Record<string, unknown>) => createWorkflowRun(selectedId!, { input: runInput }),
    onSuccess: (run) => {
      setRunModal(false);
      setRunError(null);
      setActiveSection("runs");
      setPendingRunId(run.id);
    },
    onError: (value) => setRunError(value instanceof ApiError ? `${value.message} (${value.code})` : "Run creation failed"),
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
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) throw new Error("Workflow input must be a JSON object.");
      runMutation.mutate(parsed as Record<string, unknown>);
    } catch (value) {
      setRunError(value instanceof Error ? value.message : "Workflow input must be valid JSON.");
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
    if (hasUnsavedBuilderChanges() && !window.confirm("You have unsaved Builder changes that will be lost. Continue?")) return;
    setSelectedId(workflowId);
    setSelectedVersion(null);
    setError(null);
    setBuilder({ workflowId, version });
  }

  function saveGraph() {
    try {
      const value = JSON.parse(graphText) as WorkflowGraph;
      if (!value || value.schema_version !== "1.0" || !Array.isArray(value.nodes) || !Array.isArray(value.edges)) throw new Error("Graph must be a Graph Schema 1.0 object.");
      graphMutation.mutate(value);
    } catch (value) {
      setError(value instanceof Error ? value.message : "Graph must be valid JSON.");
    }
  }

  if (workflows.isLoading) return <div className="loading-state">Loading workflows...</div>;
  if (workflows.isError) return <div className="inline-error">Unable to load Workflows. Start the FastAPI backend and retry.</div>;
  if (builder) return <WorkflowBuilderPage workflowId={builder.workflowId} version={builder.version} onBack={() => setBuilder(null)} />;
  const list = workflows.data ?? [];

  return <div className="resource-page">
    <div className="page-toolbar"><div><p className="eyebrow">WORKFLOW CONTRACT</p><h3>Workflow definitions</h3><p className="page-description">Save editable Draft Graphs and explicitly create immutable Workflow Versions.</p></div><button className="button button--primary" type="button" onClick={openCreate}>+ Create Workflow</button></div>
    {notice && <button className="notice" type="button" onClick={() => setNotice(null)}>{notice} · dismiss</button>}
    {error && <button className="notice notice--error" type="button" onClick={() => setError(null)}>{error} · dismiss</button>}
    {list.length === 0 ? <ResourceEmptyState title="No workflows yet." message="Create a Workflow definition to save and inspect its Graph Contract." actionLabel="Create Workflow" onAction={openCreate} /> : <div className="resource-layout">
      <div className="resource-list">{list.map((workflow) => <button className={selectedId === workflow.id ? "resource-row resource-row--selected" : "resource-row"} key={workflow.id} type="button" onClick={() => { setSelectedId(workflow.id); setSelectedVersion(null); setError(null); }}><span className="resource-row-main"><strong>{workflow.name}</strong><small>{workflow.current_version ? `v${workflow.current_version}` : "Draft only"} · {workflow.draft_graph.nodes.length} nodes</small></span><span className="resource-row-meta"><StatusBadge label={workflow.status.toUpperCase()} tone={statusTone(workflow.status)} /></span></button>)}</div>
      {selected ? <section className="detail-card workflow-detail"><div className="detail-header"><div><p className="eyebrow">WORKFLOW DETAIL</p><h3>{selected.name}</h3><p>{selected.description || "No description"}</p></div><StatusBadge label={selected.status.toUpperCase()} tone={statusTone(selected.status)} /></div>
        <div className="detail-actions"><button className="button button--small button--primary" type="button" onClick={() => openBuilder(selected.id)}>Open Builder</button>{selected.current_version ? <button className="button button--small" type="button" onClick={openRun}>Run v{selected.current_version}</button> : null}<button className="button button--small" type="button" onClick={openRename}>Rename</button><button className="button button--small button--danger" type="button" onClick={() => archiveMutation.mutate()} disabled={archiveMutation.isPending}>{archiveMutation.isPending ? "Archiving..." : "Archive"}</button></div>
        <div className="detail-grid"><div><span className="detail-label">Schema</span><strong>{selected.graph_schema_version}</strong></div><div><span className="detail-label">Current version</span><strong>{selected.current_version ? `v${selected.current_version}` : "Not published"}</strong></div><div><span className="detail-label">Draft nodes</span><strong>{selected.draft_graph.nodes.length}</strong></div><div><span className="detail-label">Draft edges</span><strong>{selected.draft_graph.edges.length}</strong></div></div>
        <div className="graph-debug"><div className="section-heading"><div><p className="eyebrow">DRAFT GRAPH</p><h4>{selectedVersion ? `Version v${selectedVersion.version} · read only` : "Graph Schema 1.0 JSON"}</h4></div>{!selectedVersion && <div className="detail-actions"><button className="button button--small" type="button" onClick={saveGraph} disabled={graphMutation.isPending}>{graphMutation.isPending ? "Saving..." : "Save Draft"}</button><button className="button button--small button--primary" type="button" onClick={() => versionMutation.mutate()} disabled={versionMutation.isPending}>{versionMutation.isPending ? "Creating..." : "Create Version"}</button></div>}</div><JsonEditor label="Graph JSON" value={graphText} onChange={setGraphText} rows={18} readOnly={Boolean(selectedVersion)} hint={selectedVersion ? "Historical Workflow Versions cannot be edited." : "Draft saves do not create a Version. Create a Version explicitly when the graph is ready."} />{graph.data?.warnings.map((warning) => <div className="detail-warning" key={warning.code}>{warning.message}</div>)}</div>
        <div className="actions-section"><div className="section-heading"><div><p className="eyebrow">HISTORY</p><h4>Immutable versions</h4></div>{selectedVersion && <button className="text-button" type="button" onClick={() => { setSelectedVersion(null); if (graph.data) setGraphText(JSON.stringify(graph.data.graph, null, 2)); }}>Back to Draft</button>}</div>{versions.isLoading ? <div className="loading-state">Loading versions...</div> : versions.data?.length ? <div className="version-list">{versions.data.map((version) => <div className={selectedVersion?.version === version.version ? "version-row version-row--selected" : "version-row"} key={version.id}><button className="version-row-main" type="button" onClick={() => { setSelectedVersion(version); setGraphText(JSON.stringify(version.graph, null, 2)); }}><span><strong>v{version.version}</strong><small>{version.change_note || "No change note"}</small></span><small>{new Date(version.created_at).toLocaleString()}</small></button><button className="button button--small" type="button" onClick={() => openBuilder(selected.id, version.version)}>View in Builder</button></div>)}</div> : <div className="mini-empty">No immutable versions yet. Save a Draft, then create the first Version.</div>}</div>
      </section> : <div className="select-state">Select a Workflow to inspect its Draft Graph and Version history.</div>}
    </div>}
    {formMode && <Modal title={formMode === "create" ? "Create Workflow" : "Rename Workflow"} eyebrow="WORKFLOW DEFINITION" onClose={() => setFormMode(null)}><form className="form-stack" onSubmit={(event) => { event.preventDefault(); setError(null); workflowMutation.mutate(); }}><label className="field"><span>Name</span><input className="input" required value={formName} onChange={(event) => setFormName(event.target.value)} placeholder="Coding Agent Showcase" /></label><label className="field"><span>Description</span><textarea className="input" rows={3} value={formDescription} onChange={(event) => setFormDescription(event.target.value)} placeholder="What this Workflow definition orchestrates" /></label>{error && <div className="inline-error">{error}</div>}<div className="modal-actions"><button className="button" type="button" onClick={() => setFormMode(null)}>Cancel</button><button className="button button--primary" type="submit" disabled={workflowMutation.isPending}>{workflowMutation.isPending ? "Saving..." : formMode === "create" ? "Create Workflow" : "Save name"}</button></div></form></Modal>}
    {runModal && <Modal title="Run Workflow" eyebrow="NEW WORKFLOW RUN" onClose={() => setRunModal(false)}><form className="form-stack" onSubmit={submitRun}><p className="page-description">Running the current immutable Version v{selected?.current_version}. Workflow input is validated against the Data Input schema.</p><label className="field"><span>Workflow input</span><textarea className="input code-input" rows={6} value={runInputText} onChange={(event) => setRunInputText(event.target.value)} spellCheck={false} /></label>{runError && <div className="inline-error">{runError}</div>}<div className="modal-actions"><button className="button" type="button" onClick={() => setRunModal(false)}>Cancel</button><button className="button button--primary" type="submit" disabled={runMutation.isPending}>{runMutation.isPending ? "Creating..." : "Create & Run"}</button></div></form></Modal>}
  </div>;
}
