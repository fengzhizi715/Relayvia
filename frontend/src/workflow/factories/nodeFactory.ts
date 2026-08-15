import type { WorkflowNode } from "../../api/client";

export type WorkflowNodeType = WorkflowNode["type"];

export type PaletteCategory = "Data" | "Agent" | "Service" | "Tool" | "Logic" | "Human";

export type PaletteItem = {
  type: WorkflowNodeType;
  subtype: string;
  label: string;
  description: string;
  category: PaletteCategory;
  defaultName: string;
  createConfig: () => Record<string, unknown>;
};

const RETRY_DEFAULT = { max_retries: 0 };

/**
 * Single source of truth for "what can be added to a Canvas" and "what the
 * default Config of a newly created Node is". Every factory-produced Node
 * matches Graph Contract 1.0.
 */
export const PALETTE_ITEMS: PaletteItem[] = [
  {
    category: "Data",
    type: "data",
    subtype: "input",
    label: "Input",
    description: "Declare Workflow input schema",
    defaultName: "Input",
    createConfig: () => ({ schema: { type: "object", properties: {} } }),
  },
  {
    category: "Data",
    type: "data",
    subtype: "transform",
    label: "Transform",
    description: "Map, select or constant values",
    defaultName: "Transform",
    createConfig: () => ({ mappings: {} }),
  },
  {
    category: "Data",
    type: "data",
    subtype: "output",
    label: "Output",
    description: "Publish Workflow output mapping",
    defaultName: "Output",
    createConfig: () => ({ output_mapping: {} }),
  },
  {
    category: "Agent",
    type: "agent",
    subtype: "agent",
    label: "Agent",
    description: "Call an existing connected Agent",
    defaultName: "Agent",
    createConfig: () => ({ agent_id: "", role: "", task_template: "", timeout_seconds: 600, retry: RETRY_DEFAULT }),
  },
  {
    category: "Service",
    type: "service",
    subtype: "http",
    label: "Service",
    description: "Call an existing Service Action",
    defaultName: "Service",
    createConfig: () => ({ service_id: "", service_action_id: "", timeout_seconds: 60, retry: RETRY_DEFAULT }),
  },
  {
    category: "Tool",
    type: "tool",
    subtype: "shell",
    label: "Shell",
    description: "Run a shell command",
    defaultName: "Shell",
    createConfig: () => ({ command: "", working_directory: null, timeout_seconds: 600 }),
  },
  {
    category: "Tool",
    type: "tool",
    subtype: "git",
    label: "Git",
    description: "Run a git command",
    defaultName: "Git",
    createConfig: () => ({ command: "", working_directory: null, timeout_seconds: 600 }),
  },
  {
    category: "Tool",
    type: "tool",
    subtype: "test_command",
    label: "Test Command",
    description: "Run a test command",
    defaultName: "Test",
    createConfig: () => ({ command: "", working_directory: null, timeout_seconds: 600 }),
  },
  {
    category: "Logic",
    type: "logic",
    subtype: "condition",
    label: "Condition",
    description: "Branch on a comparison",
    defaultName: "Condition",
    createConfig: () => ({ expression: { left: "", operator: ">=", right: 0 } }),
  },
  {
    category: "Logic",
    type: "logic",
    subtype: "parallel",
    label: "Parallel",
    description: "Fan out to multiple branches",
    defaultName: "Parallel",
    createConfig: () => ({}),
  },
  {
    category: "Logic",
    type: "logic",
    subtype: "merge",
    label: "Merge",
    description: "Join branches",
    defaultName: "Merge",
    createConfig: () => ({ strategy: "all" }),
  },
  {
    category: "Logic",
    type: "logic",
    subtype: "wait",
    label: "Wait",
    description: "Wait for a duration",
    defaultName: "Wait",
    createConfig: () => ({ mode: "duration", duration_seconds: 60 }),
  },
  {
    category: "Human",
    type: "human",
    subtype: "approval",
    label: "Approval",
    description: "Request human approval",
    defaultName: "Approval",
    createConfig: () => ({ title: "", description: "", allow_reject: true }),
  },
  {
    category: "Human",
    type: "human",
    subtype: "input",
    label: "Human Input",
    description: "Request human-provided values",
    defaultName: "Human Input",
    createConfig: () => ({ form_schema: { type: "object", properties: {} } }),
  },
];

const PALETTE_INDEX = new Map<string, PaletteItem>();
for (const item of PALETTE_ITEMS) PALETTE_INDEX.set(`${item.type}.${item.subtype}`, item);

export function findPaletteItem(type: WorkflowNodeType, subtype: string): PaletteItem | null {
  return PALETTE_INDEX.get(`${type}.${subtype}`) ?? null;
}

let idCounter = 0;

function nextIdSuffix(): string {
  idCounter += 1;
  return `${Date.now().toString(36)}${idCounter.toString(36)}${Math.random().toString(36).slice(2, 6)}`;
}

export function generateNodeId(): string {
  return `node_${nextIdSuffix()}`;
}

export function generateEdgeId(): string {
  return `edge_${nextIdSuffix()}`;
}

/**
 * Create a Graph Contract 1.0 compliant Node. The Node ID is unique and
 * decoupled from the Workflow / database entity IDs; `name` is display-only
 * and is never used as a reference.
 */
export function createWorkflowNode(
  type: WorkflowNodeType,
  subtype: string,
  position: { x: number; y: number },
): WorkflowNode {
  const item = findPaletteItem(type, subtype);
  if (!item) throw new Error(`No Workflow Node definition for ${type}.${subtype}`);
  return {
    id: generateNodeId(),
    type,
    subtype,
    name: item.defaultName,
    position: { x: position.x, y: position.y },
    config: item.createConfig(),
    input_mapping: {},
    metadata: {},
  };
}
