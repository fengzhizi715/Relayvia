import { createContext, useContext, useMemo } from "react";
import { Background, BackgroundVariant, Controls, Handle, Position, ReactFlow, type Node, type NodeProps } from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import type { NodeRun, WorkflowGraph, WorkflowNode } from "../../api/client";
import { graphToReactFlow, nodeReactFlowType, type WorkflowReactFlowNodeData } from "../../workflow/adapters/graphToReactFlow";
import { NodeRunStatusBadge } from "./RunStatusBadge";

const NodeRunsContext = createContext<Record<string, NodeRun>>({});

const CATEGORY_META: Record<string, { category: string; glyph: string }> = {
  agent: { category: "Agent", glyph: "AG" },
  service: { category: "Service", glyph: "SV" },
  tool: { category: "Tool", glyph: "TL" },
  condition: { category: "Condition", glyph: "IF" },
  parallel: { category: "Parallel", glyph: "∥" },
  merge: { category: "Merge", glyph: "⨝" },
  router: { category: "Router", glyph: "→" },
  wait: { category: "Wait", glyph: "⏸" },
  human: { category: "Human", glyph: "HM" },
  data: { category: "Data", glyph: "DT" },
};

function RuntimeHandles({ node }: { node: WorkflowNode }) {
  const isInput = node.type === "data" && node.subtype === "input";
  const isOutput = node.type === "data" && node.subtype === "output";

  if (node.type === "logic" && node.subtype === "condition") {
    return (
      <>
        <Handle className="workflow-handle" type="target" position={Position.Left} />
        <Handle className="workflow-handle workflow-handle--true" type="source" position={Position.Right} id="true" style={{ top: "38%" }} />
        <Handle className="workflow-handle workflow-handle--false" type="source" position={Position.Right} id="false" style={{ top: "72%" }} />
      </>
    );
  }
  return (
    <>
      {!isInput && <Handle className="workflow-handle" type="target" position={Position.Left} />}
      {!isOutput && <Handle className="workflow-handle" type="source" position={Position.Right} />}
    </>
  );
}

function RuntimeNode({ id, data }: NodeProps<Node<WorkflowReactFlowNodeData>>) {
  const nodeRuns = useContext(NodeRunsContext);
  const node = data.workflowNode;
  const rfType = nodeReactFlowType(node);
  const meta = CATEGORY_META[rfType] ?? { category: node.type, glyph: node.type.slice(0, 2).toUpperCase() };
  const status = nodeRuns[id]?.status ?? "pending";

  return (
    <div className="workflow-node-root">
      <div className={`workflow-node workflow-node--${node.type}`}>
        <div className="workflow-node-header">
          <span className="workflow-node-glyph" aria-hidden="true">
            {meta.glyph}
          </span>
          <div className="workflow-node-title">
            <span className="workflow-node-category">{meta.category}</span>
            <strong className="workflow-node-name">{node.name || node.id}</strong>
          </div>
        </div>
        <div className="workflow-node-summary">
          <NodeRunStatusBadge status={status} />
        </div>
      </div>
      <RuntimeHandles node={node} />
    </div>
  );
}

const RUNTIME_NODE_TYPES = {
  agent: RuntimeNode,
  service: RuntimeNode,
  tool: RuntimeNode,
  condition: RuntimeNode,
  parallel: RuntimeNode,
  merge: RuntimeNode,
  router: RuntimeNode,
  wait: RuntimeNode,
  human: RuntimeNode,
  data: RuntimeNode,
};

/**
 * Readonly render of a Run's Graph Snapshot with NodeRun status decoration.
 * Uses the same graphToReactFlow adapter as the Builder but never mutates the
 * Graph and is fully decoupled from the Builder store.
 */
export function RunGraph({ graph, nodeRuns }: { graph: WorkflowGraph; nodeRuns: Record<string, NodeRun> }) {
  const { nodes, edges } = useMemo(() => graphToReactFlow(graph), [graph]);

  return (
    <div className="workflow-canvas run-graph">
      <NodeRunsContext.Provider value={nodeRuns}>
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={RUNTIME_NODE_TYPES}
          fitView
          fitViewOptions={{ padding: 0.15 }}
          colorMode="dark"
          nodesDraggable={false}
          nodesConnectable={false}
          edgesFocusable={false}
          elementsSelectable
          deleteKeyCode={null}
        >
          <Background variant={BackgroundVariant.Dots} gap={24} size={1.4} color="#22324c" />
          <Controls showInteractive={false} />
        </ReactFlow>
      </NodeRunsContext.Provider>
    </div>
  );
}
