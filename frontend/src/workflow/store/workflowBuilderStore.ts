import { create } from "zustand";

import type { ValidationResult, WorkflowEdge, WorkflowGraph, WorkflowNode } from "../../api/client";
import { createWorkflowNode, generateEdgeId } from "../factories/nodeFactory";

export type BuilderMode = { kind: "draft" } | { kind: "version"; version: number; changeNote: string | null };

export type WorkflowNodePatch = Partial<Pick<WorkflowNode, "name" | "config" | "input_mapping" | "metadata">>;
export type WorkflowEdgePatch = Partial<Pick<WorkflowEdge, "label" | "source" | "target" | "source_handle" | "target_handle">>;

export type ValidationState = {
  valid: boolean;
  issues: Array<{ code: string; severity: "error" | "warning"; message: string; node_id: string | null; edge_id: string | null; field: string | null; details: Record<string, unknown> }>;
  validatedAt: string;
};

type WorkflowBuilderState = {
  workflowId: string | null;
  workflowName: string;
  mode: BuilderMode;
  graph: WorkflowGraph | null;
  readOnly: boolean;
  initialized: boolean;

  selectedNodeId: string | null;
  selectedEdgeId: string | null;

  isDirty: boolean;
  isSaving: boolean;
  saveError: string | null;
  lastSavedAt: string | null;

  validation: ValidationState | null;
  isValidating: boolean;
  validationStale: boolean;

  initialize: (params: {
    workflowId: string;
    workflowName: string;
    graph: WorkflowGraph;
    mode: BuilderMode;
    readOnly: boolean;
  }) => void;
  reset: () => void;

  setGraph: (graph: WorkflowGraph) => void;
  markSaved: (updatedAt: string) => void;
  setSaving: (saving: boolean) => void;
  setSaveError: (error: string | null) => void;

  setValidation: (result: ValidationResult, validatedAt: string) => void;
  setValidating: (validating: boolean) => void;
  markValidationStale: () => void;

  addNode: (type: WorkflowNode["type"], subtype: string, position: { x: number; y: number }) => string;
  updateNode: (id: string, patch: WorkflowNodePatch) => void;
  removeNode: (id: string) => void;
  moveNode: (id: string, position: { x: number; y: number }) => void;

  addEdge: (source: string, target: string, sourceHandle?: string | null) => void;
  updateEdge: (id: string, patch: WorkflowEdgePatch) => void;
  removeEdge: (id: string) => void;

  selectNode: (id: string | null) => void;
  selectEdge: (id: string | null) => void;
};

const EMPTY_STATE = {
  workflowId: null,
  workflowName: "",
  mode: { kind: "draft" } as BuilderMode,
  graph: null,
  readOnly: false,
  initialized: false,
  selectedNodeId: null,
  selectedEdgeId: null,
  isDirty: false,
  isSaving: false,
  saveError: null,
  lastSavedAt: null,
  validation: null,
  isValidating: false,
  validationStale: true,
};

function replaceNode(graph: WorkflowGraph, id: string, updater: (node: WorkflowNode) => WorkflowNode): WorkflowGraph {
  return { ...graph, nodes: graph.nodes.map((node) => (node.id === id ? updater(node) : node)) };
}

function replaceEdge(graph: WorkflowGraph, id: string, updater: (edge: WorkflowEdge) => WorkflowEdge): WorkflowGraph {
  return { ...graph, edges: graph.edges.map((edge) => (edge.id === id ? updater(edge) : edge)) };
}

export const useWorkflowBuilderStore = create<WorkflowBuilderState>((set, get) => ({
  ...EMPTY_STATE,

  initialize: ({ workflowId, workflowName, graph, mode, readOnly }) =>
    set(() => ({
      workflowId,
      workflowName,
      graph,
      mode,
      readOnly,
      initialized: true,
      selectedNodeId: null,
      selectedEdgeId: null,
      isDirty: false,
      isSaving: false,
      saveError: null,
      lastSavedAt: null,
      validation: null,
      isValidating: false,
      validationStale: true,
    })),

  reset: () => set(() => ({ ...EMPTY_STATE })),

  setGraph: (graph) => set(() => ({ graph })),

  markSaved: (updatedAt) => set(() => ({ isDirty: false, isSaving: false, saveError: null, lastSavedAt: updatedAt })),

  setSaving: (isSaving) => set(() => ({ isSaving })),

  setSaveError: (saveError) => set(() => ({ saveError, isSaving: false })),

  setValidation: (result, validatedAt) =>
    set(() => ({
      validation: {
        valid: result.valid,
        issues: [...result.errors, ...result.warnings].map((issue) => ({
          code: issue.code,
          severity: issue.severity,
          message: issue.message,
          node_id: issue.node_id,
          edge_id: issue.edge_id,
          field: issue.field,
          details: issue.details,
        })),
        validatedAt,
      },
      validationStale: false,
      isValidating: false,
    })),

  setValidating: (isValidating) => set(() => ({ isValidating })),

  markValidationStale: () => set(() => ({ validationStale: true })),

  addNode: (type, subtype, position) => {
    const node = createWorkflowNode(type, subtype, position);
    set((state) => {
      if (!state.graph || state.readOnly) return state;
      return {
        graph: { ...state.graph, nodes: [...state.graph.nodes, node] },
        isDirty: true,
        saveError: null,
        validationStale: true,
        selectedNodeId: node.id,
        selectedEdgeId: null,
      };
    });
    return node.id;
  },

  updateNode: (id, patch) =>
    set((state) => {
      if (!state.graph || state.readOnly || !state.graph.nodes.some((node) => node.id === id)) return state;
      return {
        graph: replaceNode(state.graph, id, (node) => ({ ...node, ...patch })),
        isDirty: true,
        saveError: null,
        validationStale: true,
      };
    }),

  removeNode: (id) =>
    set((state) => {
      if (!state.graph || state.readOnly || !state.graph.nodes.some((node) => node.id === id)) return state;
      const graph = {
        ...state.graph,
        nodes: state.graph.nodes.filter((node) => node.id !== id),
        edges: state.graph.edges.filter((edge) => edge.source !== id && edge.target !== id),
      };
      return {
        graph,
        isDirty: true,
        saveError: null,
        validationStale: true,
        selectedNodeId: state.selectedNodeId === id ? null : state.selectedNodeId,
        selectedEdgeId: state.selectedEdgeId && graph.edges.some((edge) => edge.id === state.selectedEdgeId) ? state.selectedEdgeId : null,
      };
    }),

  moveNode: (id, position) =>
    set((state) => {
      if (!state.graph || state.readOnly) return state;
      const node = state.graph.nodes.find((item) => item.id === id);
      if (!node || (node.position.x === position.x && node.position.y === position.y)) return state;
      return {
        graph: replaceNode(state.graph, id, (item) => ({ ...item, position: { x: position.x, y: position.y } })),
        isDirty: true,
        saveError: null,
      };
    }),

  addEdge: (source, target, sourceHandle = null) =>
    set((state) => {
      if (!state.graph || state.readOnly) return state;
      if (!source || !target || source === target) return state;
      const sourceExists = state.graph.nodes.some((node) => node.id === source);
      const targetExists = state.graph.nodes.some((node) => node.id === target);
      if (!sourceExists || !targetExists) return state;
      const handle = sourceHandle ?? null;
      const edge: WorkflowEdge = {
        id: generateEdgeId(),
        source,
        target,
        source_handle: handle,
        target_handle: null,
        label: handle ?? null,
        condition: null,
        metadata: {},
      };
      return {
        graph: { ...state.graph, edges: [...state.graph.edges, edge] },
        isDirty: true,
        saveError: null,
        validationStale: true,
        selectedNodeId: null,
        selectedEdgeId: edge.id,
      };
    }),

  updateEdge: (id, patch) =>
    set((state) => {
      if (!state.graph || state.readOnly || !state.graph.edges.some((edge) => edge.id === id)) return state;
      return {
        graph: replaceEdge(state.graph, id, (edge) => ({ ...edge, ...patch })),
        isDirty: true,
        saveError: null,
        validationStale: true,
      };
    }),

  removeEdge: (id) =>
    set((state) => {
      if (!state.graph || state.readOnly || !state.graph.edges.some((edge) => edge.id === id)) return state;
      return {
        graph: { ...state.graph, edges: state.graph.edges.filter((edge) => edge.id !== id) },
        isDirty: true,
        saveError: null,
        validationStale: true,
        selectedEdgeId: state.selectedEdgeId === id ? null : state.selectedEdgeId,
      };
    }),

  selectNode: (selectedNodeId) =>
    set(() => ({ selectedNodeId, selectedEdgeId: null })),

  selectEdge: (selectedEdgeId) =>
    set(() => ({ selectedEdgeId, selectedNodeId: null })),
}));

export function useWorkflowNode(id: string): WorkflowNode | undefined {
  return useWorkflowBuilderStore((state) => state.graph?.nodes.find((node) => node.id === id));
}

export function useWorkflowEdge(id: string): WorkflowEdge | undefined {
  return useWorkflowBuilderStore((state) => state.graph?.edges.find((edge) => edge.id === id));
}
