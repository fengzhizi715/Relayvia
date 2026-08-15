import type { WorkflowNode } from "../../api/client";
import { findPaletteItem } from "../factories/nodeFactory";
import { useWorkflowBuilderStore, useWorkflowEdge, useWorkflowNode } from "../store/workflowBuilderStore";
import { AgentInspector } from "./AgentInspector";
import { DataInspector } from "./DataInspector";
import { EdgeInspector } from "./EdgeInspector";
import { HumanInspector } from "./HumanInspector";
import { IssueList } from "./fields";
import { LogicInspector } from "./LogicInspector";
import { ServiceInspector } from "./ServiceInspector";
import { ToolInspector } from "./ToolInspector";
import { useNodeIssueList } from "./useNodeIssueList";

function nodeCategoryLabel(node: WorkflowNode): string {
  return findPaletteItem(node.type, node.subtype)?.label ?? node.type;
}

function InspectorByType({ node }: { node: WorkflowNode }) {
  switch (node.type) {
    case "agent":
      return <AgentInspector node={node} />;
    case "service":
      return <ServiceInspector node={node} />;
    case "tool":
      return <ToolInspector node={node} />;
    case "logic":
      return <LogicInspector node={node} />;
    case "human":
      return <HumanInspector node={node} />;
    case "data":
      return <DataInspector node={node} />;
    default:
      return null;
  }
}

function NodeConfigInspector({ node }: { node: WorkflowNode }) {
  const readOnly = useWorkflowBuilderStore((state) => state.readOnly);
  const graph = useWorkflowBuilderStore((state) => state.graph);
  const removeNode = useWorkflowBuilderStore((state) => state.removeNode);
  const issues = useNodeIssueList(node);

  const edgeCount = graph?.edges.filter((edge) => edge.source === node.id || edge.target === node.id).length ?? 0;

  function onDelete() {
    if (edgeCount > 0 && !window.confirm(`Deleting this node will also remove ${edgeCount} connection${edgeCount === 1 ? "" : "s"}.`)) return;
    removeNode(node.id);
  }

  return (
    <div className="inspector-content">
      <div className="inspector-header">
        <div>
          <p className="eyebrow">NODE INSPECTOR</p>
          <h4>{nodeCategoryLabel(node)}</h4>
        </div>
        {!readOnly && (
          <button className="icon-button icon-button--danger" type="button" aria-label={`Delete node ${node.name}`} onClick={onDelete}>
            ×
          </button>
        )}
      </div>
      <IssueList issues={issues} />
      <div className="inspector-form">
        <InspectorByType node={node} />
      </div>
      <div className="inspector-advanced">
        <span className="detail-label">Node ID</span>
        <code>{node.id}</code>
      </div>
    </div>
  );
}

export function NodeInspector() {
  const selectedNodeId = useWorkflowBuilderStore((state) => state.selectedNodeId);
  const selectedEdgeId = useWorkflowBuilderStore((state) => state.selectedEdgeId);
  const node = useWorkflowNode(selectedNodeId ?? "");
  const edge = useWorkflowEdge(selectedEdgeId ?? "");

  if (selectedNodeId && node) return <NodeConfigInspector key={node.id} node={node} />;
  if (selectedEdgeId && edge) return <EdgeInspector key={edge.id} edge={edge} />;

  return (
    <div className="inspector-content">
      <div className="inspector-empty">
        <p className="eyebrow">INSPECTOR</p>
        <h4>Nothing selected</h4>
        <p>Select a Node or an Edge on the canvas to configure it.</p>
      </div>
    </div>
  );
}
