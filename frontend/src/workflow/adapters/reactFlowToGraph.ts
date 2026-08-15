import type { Edge, Node } from "@xyflow/react";

import type { WorkflowGraph } from "../../api/client";

/**
 * React Flow projection -> WorkflowGraph 1.0.
 *
 * Only Graph Contract fields are pulled back: node positions and edge labels.
 * React-Flow-only state (selection, dragging, measured dimensions, viewport)
 * is intentionally dropped and never reaches the persisted Graph.
 */

export function reactFlowToGraph(graph: WorkflowGraph, rfNodes: Node[], rfEdges: Edge[]): WorkflowGraph {
  const positions = new Map(rfNodes.map((node) => [node.id, node.position]));
  const labels = new Map<string, string | undefined>(
    rfEdges.map((edge) => [edge.id, typeof edge.label === "string" ? edge.label : undefined]),
  );

  const nodes = graph.nodes.map((node) => {
    const position = positions.get(node.id);
    if (position && (position.x !== node.position.x || position.y !== node.position.y)) {
      return { ...node, position: { x: position.x, y: position.y } };
    }
    return node;
  });

  const edges = graph.edges.map((edge) => {
    const label = labels.get(edge.id);
    if (label !== undefined && label !== (edge.label ?? undefined)) {
      return { ...edge, label: label || null };
    }
    return edge;
  });

  return { ...graph, nodes, edges };
}
