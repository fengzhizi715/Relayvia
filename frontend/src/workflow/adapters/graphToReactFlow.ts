import type { Edge, Node } from "@xyflow/react";

import type { WorkflowEdge, WorkflowGraph, WorkflowNode } from "../../api/client";

/**
 * WorkflowGraph 1.0 -> React Flow projection.
 *
 * React Flow Node `id` and Edge `id` reuse the Workflow Graph Node/Edge IDs
 * exactly. Node `data` holds a direct reference to the Relayvia domain Node so
 * React Flow never introduces a second domain model.
 */

export type WorkflowReactFlowNodeData = {
  workflowNode: WorkflowNode;
};

export type WorkflowReactFlowEdgeData = {
  workflowEdge: WorkflowEdge;
};

export type WorkflowNodeTypeName =
  | "agent"
  | "service"
  | "tool"
  | "condition"
  | "parallel"
  | "merge"
  | "router"
  | "wait"
  | "human"
  | "data";

export function nodeReactFlowType(node: WorkflowNode): WorkflowNodeTypeName {
  switch (node.type) {
    case "agent":
      return "agent";
    case "service":
      return "service";
    case "tool":
      return "tool";
    case "human":
      return "human";
    case "data":
      return "data";
    case "logic":
      switch (node.subtype) {
        case "condition":
          return "condition";
        case "parallel":
          return "parallel";
        case "merge":
          return "merge";
        case "wait":
          return "wait";
        default:
          return "router";
      }
  }
}

function toReactFlowNode(node: WorkflowNode): Node<WorkflowReactFlowNodeData> {
  return {
    id: node.id,
    type: nodeReactFlowType(node),
    position: { x: node.position.x, y: node.position.y },
    data: { workflowNode: node },
  };
}

function toReactFlowEdge(edge: WorkflowEdge): Edge<WorkflowReactFlowEdgeData> {
  return {
    id: edge.id,
    source: edge.source,
    target: edge.target,
    sourceHandle: edge.source_handle ?? undefined,
    targetHandle: edge.target_handle ?? undefined,
    label: edge.label ?? undefined,
    data: { workflowEdge: edge },
  };
}

export function graphToReactFlow(
  graph: WorkflowGraph,
  selection: { nodeId?: string | null; edgeId?: string | null } = {},
): { nodes: Node<WorkflowReactFlowNodeData>[]; edges: Edge<WorkflowReactFlowEdgeData>[] } {
  return {
    nodes: graph.nodes.map((node) => ({ ...toReactFlowNode(node), selected: selection.nodeId === node.id })),
    edges: graph.edges.map((edge) => ({ ...toReactFlowEdge(edge), selected: selection.edgeId === edge.id })),
  };
}

/**
 * Rebuild a React Flow projection from the domain graph, preserving
 * React-Flow-owned rendering state (measured dimensions, selection, dragging)
 * so re-syncing never resets layout.
 */
export function reconcileWorkflowNodes(
  graph: WorkflowGraph,
  current: Node<WorkflowReactFlowNodeData>[],
): Node<WorkflowReactFlowNodeData>[] {
  const byId = new Map(current.map((node) => [node.id, node]));
  return graph.nodes.map((node) => {
    const existing = byId.get(node.id);
    return {
      ...toReactFlowNode(node),
      measured: existing?.measured,
      selected: existing?.selected,
      dragging: existing?.dragging,
    };
  });
}

export function reconcileWorkflowEdges(
  graph: WorkflowGraph,
  current: Edge<WorkflowReactFlowEdgeData>[],
): Edge<WorkflowReactFlowEdgeData>[] {
  const byId = new Map(current.map((edge) => [edge.id, edge]));
  return graph.edges.map((edge) => {
    const existing = byId.get(edge.id);
    return {
      ...toReactFlowEdge(edge),
      selected: existing?.selected,
    };
  });
}
