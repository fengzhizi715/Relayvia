import { useCallback, useEffect, useMemo, useState } from "react";
import { ReactFlowProvider } from "@xyflow/react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  ApiError,
  createWorkflowVersion,
  getWorkflow,
  getWorkflowGraph,
  getWorkflowVersion,
  updateWorkflowGraph,
} from "../../api/client";
import { Modal } from "../../components/Modal";
import { NodeInspector } from "../inspector/NodeInspector";
import { useAgents, useServiceActionsForServices, useServices } from "../registry/useRegistry";
import { useWorkflowBuilderStore } from "../store/workflowBuilderStore";
import { edgeIssues, nodeIssues, type NodeIssue } from "../validation/localValidation";
import { NodePalette } from "./NodePalette";
import { WorkflowCanvas } from "./WorkflowCanvas";
import { WorkflowToolbar } from "./WorkflowToolbar";

type WorkflowBuilderPageProps = {
  workflowId: string;
  version?: number;
  onBack: () => void;
};

export function WorkflowBuilderPage({ workflowId, version, onBack }: WorkflowBuilderPageProps) {
  const queryClient = useQueryClient();
  const readOnly = version !== undefined;

  const workflowQuery = useQuery({ queryKey: ["workflow", workflowId], queryFn: () => getWorkflow(workflowId), staleTime: 30_000 });
  const graphQuery = useQuery({
    queryKey: ["workflow-graph", workflowId],
    queryFn: () => getWorkflowGraph(workflowId),
    enabled: !readOnly,
    staleTime: 30_000,
  });
  const versionQuery = useQuery({
    queryKey: ["workflow-version", workflowId, version],
    queryFn: () => getWorkflowVersion(workflowId, version!),
    enabled: readOnly,
    staleTime: 30_000,
  });

  const initialize = useWorkflowBuilderStore((state) => state.initialize);
  const reset = useWorkflowBuilderStore((state) => state.reset);
  const initialized = useWorkflowBuilderStore((state) => state.initialized);
  const storeWorkflowId = useWorkflowBuilderStore((state) => state.workflowId);
  const storeMode = useWorkflowBuilderStore((state) => state.mode);
  const readOnlyStore = useWorkflowBuilderStore((state) => state.readOnly);

  const isDirty = useWorkflowBuilderStore((state) => state.isDirty);
  const isSaving = useWorkflowBuilderStore((state) => state.isSaving);
  const saveError = useWorkflowBuilderStore((state) => state.saveError);
  const graph = useWorkflowBuilderStore((state) => state.graph);
  const setSaving = useWorkflowBuilderStore((state) => state.setSaving);
  const markSaved = useWorkflowBuilderStore((state) => state.markSaved);
  const setSaveError = useWorkflowBuilderStore((state) => state.setSaveError);

  const [versionModal, setVersionModal] = useState(false);
  const [changeNote, setChangeNote] = useState("");
  const [notice, setNotice] = useState<string | null>(null);
  const [dismissedWarnings, setDismissedWarnings] = useState(false);

  const modeKind = readOnly ? "version" : "draft";
  const versionNumber = version ?? null;
  const graphData = readOnly ? versionQuery.data?.graph : graphQuery.data?.graph;

  useEffect(() => {
    reset();
  }, [workflowId, version, reset]);

  useEffect(() => {
    if (!graphData) return;
    const matchesStore =
      initialized &&
      storeWorkflowId === workflowId &&
      storeMode.kind === modeKind &&
      (modeKind === "draft" || (storeMode.kind === "version" && storeMode.version === versionNumber));
    if (matchesStore) return;
    initialize({
      workflowId,
      workflowName: workflowQuery.data?.name ?? "",
      graph: graphData,
      mode: modeKind === "version" ? { kind: "version", version: versionNumber!, changeNote: versionQuery.data?.change_note ?? null } : { kind: "draft" },
      readOnly,
    });
  }, [graphData, workflowId, version, versionNumber, modeKind, readOnly, workflowQuery.data?.name, initialized, storeWorkflowId, storeMode, initialize]);

  const { agents } = useAgents();
  const { services } = useServices();
  const serviceIds = useMemo(
    () => Array.from(new Set((graph?.nodes ?? []).filter((node) => node.type === "service").map((node) => node.config.service_id as string).filter(Boolean))),
    [graph],
  );
  const { actionsById } = useServiceActionsForServices(serviceIds);

  const issues: NodeIssue[] = useMemo(() => {
    const all: NodeIssue[] = [];
    const nodeIds = new Set((graph?.nodes ?? []).map((node) => node.id));
    for (const node of graph?.nodes ?? []) all.push(...nodeIssues(node, agents, services, actionsById));
    for (const edge of graph?.edges ?? []) all.push(...edgeIssues(edge, nodeIds));
    return all;
  }, [graph, agents, services, actionsById]);
  const blockingErrors = issues.filter((issue) => issue.level === "error");
  const canSave = blockingErrors.length === 0;

  const saveMutation = useMutation({
    mutationFn: () => updateWorkflowGraph(workflowId, graph!),
    onSuccess: (response) => {
      markSaved(response.updated_at);
      void queryClient.invalidateQueries({ queryKey: ["workflow-graph", workflowId] });
      void queryClient.invalidateQueries({ queryKey: ["workflows"] });
    },
    onError: (value) => setSaveError(value instanceof ApiError ? `${value.message} (${value.code})` : "Draft save failed"),
  });

  const save = useCallback(() => {
    if (readOnly || !graph || !canSave || isSaving) return;
    setSaving(true);
    saveMutation.mutate();
  }, [readOnly, graph, canSave, isSaving, setSaving, saveMutation]);

  useEffect(() => {
    if (readOnly || !isDirty || !canSave || saveError) return;
    const timer = setTimeout(save, 1500);
    return () => clearTimeout(timer);
  }, [isDirty, canSave, saveError, readOnly, save]);

  const versionMutation = useMutation({
    mutationFn: async (note: string | undefined) => {
      if (isDirty && canSave && graph) {
        await updateWorkflowGraph(workflowId, graph);
        markSaved(new Date().toISOString());
        void queryClient.invalidateQueries({ queryKey: ["workflow-graph", workflowId] });
      }
      return createWorkflowVersion(workflowId, note || undefined);
    },
    onSuccess: (created) => {
      setVersionModal(false);
      setNotice(`Created Workflow Version v${created.version}.`);
      void queryClient.invalidateQueries({ queryKey: ["workflows"] });
      void queryClient.invalidateQueries({ queryKey: ["workflow-versions", workflowId] });
    },
    onError: (value) => setNotice(value instanceof ApiError ? `${value.message} (${value.code})` : "Version creation failed"),
  });

  function onCreateVersion() {
    if (!canSave) {
      setNotice(blockingErrors.length ? "Fix validation errors before creating a version." : "Unable to create version.");
      return;
    }
    setVersionModal(true);
  }

  const confirmLeave = useCallback((): boolean => {
    if (readOnly || !isDirty) return true;
    return window.confirm("You have unsaved changes. Leave the Builder anyway?");
  }, [readOnly, isDirty]);

  function handleBack() {
    if (confirmLeave()) onBack();
  }

  useEffect(() => {
    if (readOnly) return;
    const handler = (event: BeforeUnloadEvent) => {
      if (isDirty) {
        event.preventDefault();
        event.returnValue = "";
      }
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [isDirty, readOnly]);

  const ready = initialized && storeWorkflowId === workflowId && readOnlyStore === readOnly;
  const loading =
    workflowQuery.isLoading ||
    (readOnly ? versionQuery.isLoading : graphQuery.isLoading) ||
    !ready;
  const failed =
    workflowQuery.isError ||
    (readOnly ? versionQuery.isError : graphQuery.isError) ||
    (!graphData && !loading);

  if (failed) return <div className="inline-error">Unable to load this Workflow. Start the FastAPI backend and retry.</div>;
  if (loading) return <div className="loading-state">Loading Workflow...</div>;

  const warnings = readOnly ? [] : graphQuery.data?.warnings ?? [];

  return (
    <ReactFlowProvider>
      <div className="builder-shell">
        <WorkflowToolbar
          onBack={handleBack}
          onSave={save}
          onCreateVersion={onCreateVersion}
          canSave={canSave}
          blockedReasons={blockingErrors.map((issue) => issue.message)}
        />
        {notice && (
          <button className="notice" type="button" onClick={() => setNotice(null)}>
            {notice} · dismiss
          </button>
        )}
        {!readOnly && warnings.length > 0 && !dismissedWarnings && (
          <button className="notice notice--warning" type="button" onClick={() => setDismissedWarnings(true)}>
            {warnings.map((warning) => warning.message).join(" · ")} · dismiss
          </button>
        )}
        <div className="builder-body">
          <NodePalette />
          <WorkflowCanvas />
          <aside className="inspector-panel">
            <NodeInspector />
          </aside>
        </div>
        {versionModal && !readOnly && (
          <Modal title="Create Workflow Version" eyebrow="IMMUTABLE SNAPSHOT" onClose={() => setVersionModal(false)}>
            <form
              className="form-stack"
              onSubmit={(event) => {
                event.preventDefault();
                versionMutation.mutate(changeNote || undefined);
              }}
            >
              <label className="field">
                <span>Change note</span>
                <textarea className="input" rows={3} value={changeNote} onChange={(event) => setChangeNote(event.target.value)} placeholder="What changed in this version" />
              </label>
              <div className="modal-actions">
                <button className="button" type="button" onClick={() => setVersionModal(false)}>
                  Cancel
                </button>
                <button className="button button--primary" type="submit" disabled={versionMutation.isPending}>
                  {versionMutation.isPending ? "Creating..." : "Create Version"}
                </button>
              </div>
            </form>
          </Modal>
        )}
      </div>
    </ReactFlowProvider>
  );
}
