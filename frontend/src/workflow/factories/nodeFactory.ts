import type { WorkflowNode } from "../../api/client";
import { t, type TranslationKey } from "../../i18n";

export type WorkflowNodeType = WorkflowNode["type"];

export type PaletteCategory = "Data" | "Agent" | "Service" | "Tool" | "Logic" | "Human";

export type PaletteItem = {
  type: WorkflowNodeType;
  subtype: string;
  labelKey: TranslationKey;
  descriptionKey: TranslationKey;
  defaultNameKey: TranslationKey;
  category: PaletteCategory;
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
    labelKey: "palette.input.label",
    descriptionKey: "palette.input.description",
    defaultNameKey: "palette.input.label",
    createConfig: () => ({ schema: { type: "object", properties: {} } }),
  },
  {
    category: "Data",
    type: "data",
    subtype: "transform",
    labelKey: "palette.transform.label",
    descriptionKey: "palette.transform.description",
    defaultNameKey: "palette.transform.label",
    createConfig: () => ({ mappings: {} }),
  },
  {
    category: "Data",
    type: "data",
    subtype: "output",
    labelKey: "palette.output.label",
    descriptionKey: "palette.output.description",
    defaultNameKey: "palette.output.label",
    createConfig: () => ({ output_mapping: {} }),
  },
  {
    category: "Agent",
    type: "agent",
    subtype: "agent",
    labelKey: "palette.agent.label",
    descriptionKey: "palette.agent.description",
    defaultNameKey: "palette.agent.label",
    createConfig: () => ({ agent_id: "", role: "", task_template: "", timeout_seconds: 600, retry: RETRY_DEFAULT }),
  },
  {
    category: "Service",
    type: "service",
    subtype: "http",
    labelKey: "palette.service.label",
    descriptionKey: "palette.service.description",
    defaultNameKey: "palette.service.label",
    createConfig: () => ({ service_id: "", service_action_id: "", timeout_seconds: 60, retry: RETRY_DEFAULT }),
  },
  {
    category: "Tool",
    type: "tool",
    subtype: "shell",
    labelKey: "palette.shell.label",
    descriptionKey: "palette.shell.description",
    defaultNameKey: "palette.shell.label",
    createConfig: () => ({ command: "", working_directory: null, timeout_seconds: 600 }),
  },
  {
    category: "Tool",
    type: "tool",
    subtype: "git",
    labelKey: "palette.git.label",
    descriptionKey: "palette.git.description",
    defaultNameKey: "palette.git.label",
    createConfig: () => ({ command: "", working_directory: null, timeout_seconds: 600 }),
  },
  {
    category: "Tool",
    type: "tool",
    subtype: "test_command",
    labelKey: "palette.test.label",
    descriptionKey: "palette.test.description",
    defaultNameKey: "palette.test.defaultName",
    createConfig: () => ({ command: "", working_directory: null, timeout_seconds: 600 }),
  },
  {
    category: "Logic",
    type: "logic",
    subtype: "condition",
    labelKey: "palette.condition.label",
    descriptionKey: "palette.condition.description",
    defaultNameKey: "palette.condition.label",
    createConfig: () => ({ expression: { left: "", operator: ">=", right: 0 } }),
  },
  {
    category: "Logic",
    type: "logic",
    subtype: "parallel",
    labelKey: "palette.parallel.label",
    descriptionKey: "palette.parallel.description",
    defaultNameKey: "palette.parallel.label",
    createConfig: () => ({}),
  },
  {
    category: "Logic",
    type: "logic",
    subtype: "merge",
    labelKey: "palette.merge.label",
    descriptionKey: "palette.merge.description",
    defaultNameKey: "palette.merge.label",
    createConfig: () => ({ strategy: "all" }),
  },
  {
    category: "Logic",
    type: "logic",
    subtype: "wait",
    labelKey: "palette.wait.label",
    descriptionKey: "palette.wait.description",
    defaultNameKey: "palette.wait.label",
    createConfig: () => ({ mode: "duration", duration_seconds: 60 }),
  },
  {
    category: "Human",
    type: "human",
    subtype: "approval",
    labelKey: "palette.approval.label",
    descriptionKey: "palette.approval.description",
    defaultNameKey: "palette.approval.label",
    createConfig: () => ({ title: "", description: "", allow_reject: true }),
  },
  {
    category: "Human",
    type: "human",
    subtype: "input",
    labelKey: "palette.humanInput.label",
    descriptionKey: "palette.humanInput.description",
    defaultNameKey: "palette.humanInput.label",
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
  if (!item) throw new Error(t("factory.unknownNode", { type, subtype }));
  return {
    id: generateNodeId(),
    type,
    subtype,
    name: t(item.defaultNameKey),
    position: { x: position.x, y: position.y },
    config: item.createConfig(),
    input_mapping: {},
    metadata: {},
  };
}
