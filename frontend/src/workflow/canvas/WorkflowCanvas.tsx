import { useCallback, useEffect, useMemo, useRef } from "react";
import {
  Background,
  BackgroundVariant,
  Controls,
  ReactFlow,
  applyEdgeChanges,
  applyNodeChanges,
  useEdgesState,
  useNodesState,
  useReactFlow,
  type Connection,
  type Edge,
  type EdgeChange,
  type Node,
  type NodeChange,
  type OnConnect,
  type OnEdgesChange,
  type OnNodesChange,
  type OnSelectionChangeParams,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import type { WorkflowGraph } from "../../api/client";
import {
  graphToReactFlow,
  reconcileWorkflowEdges,
  reconcileWorkflowNodes,
  type WorkflowReactFlowEdgeData,
  type WorkflowReactFlowNodeData,
} from "../adapters/graphToReactFlow";
import { nodeTypes } from "../nodes";
import { useWorkflowBuilderStore } from "../store/workflowBuilderStore";

const EMPTY_GRAPH: WorkflowGraph = { schema_version: "1.0", nodes: [], edges: [], variables: {}, metadata: {} };

export function WorkflowCanvas() {
  const graph = useWorkflowBuilderStore((state) => state.graph);
  const readOnly = useWorkflowBuilderStore((state) => state.readOnly);
  const workflowKey = useWorkflowBuilderStore((state) => `${state.workflowId ?? ""}:${state.mode.kind}`);
  const moveNode = useWorkflowBuilderStore((state) => state.moveNode);
  const removeNode = useWorkflowBuilderStore((state) => state.removeNode);
  const removeEdge = useWorkflowBuilderStore((state) => state.removeEdge);
  const addEdge = useWorkflowBuilderStore((state) => state.addEdge);
  const selectNode = useWorkflowBuilderStore((state) => state.selectNode);
  const selectEdge = useWorkflowBuilderStore((state) => state.selectEdge);
  const { fitView } = useReactFlow();

  const initial = useMemo(() => graphToReactFlow(graph ?? EMPTY_GRAPH), []);
  const [nodes, setNodes] = useNodesState<Node<WorkflowReactFlowNodeData>>(initial.nodes);
  const [edges, setEdges] = useEdgesState<Edge<WorkflowReactFlowEdgeData>>(initial.edges);

  const fittedKey = useRef<string | null>(null);
  useEffect(() => {
    if (!graph || fittedKey.current === workflowKey) return;
    fittedKey.current = workflowKey;
    fitView({ padding: 0.15, duration: 0 });
  }, [graph, workflowKey, fitView]);

  useEffect(() => {
    if (!graph) return;
    setNodes((current) => reconcileWorkflowNodes(graph, current));
    setEdges((current) => reconcileWorkflowEdges(graph, current));
  }, [graph, setNodes, setEdges]);

  const onNodesChange: OnNodesChange = useCallback(
    (changes: NodeChange[]) => {
      setNodes((current) => applyNodeChanges(changes as NodeChange<Node<WorkflowReactFlowNodeData>>[], current));
      for (const change of changes) {
        if (change.type === "remove") removeNode(change.id);
      }
    },
    [setNodes, removeNode],
  );

  const onEdgesChange: OnEdgesChange = useCallback(
    (changes: EdgeChange[]) => {
      setEdges((current) => applyEdgeChanges(changes as EdgeChange<Edge<WorkflowReactFlowEdgeData>>[], current));
      for (const change of changes) {
        if (change.type === "remove") removeEdge(change.id);
      }
    },
    [setEdges, removeEdge],
  );

  const onConnect: OnConnect = useCallback(
    (connection: Connection) => {
      addEdge(connection.source, connection.target, connection.sourceHandle ?? null);
    },
    [addEdge],
  );

  const onNodeDragStop = useCallback((_event: unknown, node: Node) => moveNode(node.id, node.position), [moveNode]);

  const onSelectionChange = useCallback(
    (params: OnSelectionChangeParams) => {
      const firstNode = params.nodes[0];
      const firstEdge = params.edges[0];
      if (firstNode) {
        selectNode(firstNode.id);
      } else if (firstEdge) {
        selectEdge(firstEdge.id);
      } else {
        selectNode(null);
        selectEdge(null);
      }
    },
    [selectNode, selectEdge],
  );

  const onPaneClick = useCallback(() => {
    selectNode(null);
    selectEdge(null);
  }, [selectNode, selectEdge]);

  if (!graph) return null;

  const empty = graph.nodes.length === 0;

  return (
    <div className="workflow-canvas">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        onNodeDragStop={onNodeDragStop}
        onSelectionChange={onSelectionChange}
        onPaneClick={onPaneClick}
        nodesDraggable={!readOnly}
        nodesConnectable={!readOnly}
        edgesFocusable={!readOnly}
        elementsSelectable
        minZoom={0.2}
        maxZoom={2}
        deleteKeyCode={readOnly ? null : ["Delete", "Backspace"]}
        colorMode="dark"
      >
        <Background variant={BackgroundVariant.Dots} gap={24} size={1.4} color="#22324c" />
        <Controls showInteractive={false} />
      </ReactFlow>
      {empty && !readOnly && (
        <div className="canvas-empty-hint">
          <p className="eyebrow">EMPTY CANVAS</p>
          <h4>Start building</h4>
          <p>Add a node from the left panel to begin.</p>
        </div>
      )}
    </div>
  );
}
