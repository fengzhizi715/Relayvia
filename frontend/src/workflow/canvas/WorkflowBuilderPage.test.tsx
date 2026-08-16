import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { WorkflowGraph } from "../../api/client";
import { useWorkflowBuilderStore } from "../store/workflowBuilderStore";
import { WorkflowBuilderPage } from "./WorkflowBuilderPage";

const api = vi.hoisted(() => ({
  getWorkflow: vi.fn(),
  getWorkflowGraph: vi.fn(),
  getWorkflowVersion: vi.fn(),
  updateWorkflowGraph: vi.fn(),
  createWorkflowVersion: vi.fn(),
  validateWorkflow: vi.fn(),
  getAgents: vi.fn(),
  getServices: vi.fn(),
  getActions: vi.fn(),
  getCredentials: vi.fn(),
}));

vi.mock("../../api/client", () => ({
  ...api,
  ApiError: class ApiError extends Error {
    code: string;
    details: Record<string, unknown>;
    constructor(message: string, code = "X", details: Record<string, unknown> = {}) {
      super(message);
      this.code = code;
      this.details = details;
    }
  },
}));

const graph: WorkflowGraph = {
  schema_version: "1.0",
  nodes: [
    {
      id: "planner",
      type: "agent",
      subtype: "agent",
      name: "Planner",
      position: { x: 100, y: 100 },
      config: { agent_id: "agent-1" },
      input_mapping: {},
      metadata: {},
    },
  ],
  edges: [],
  variables: {},
  metadata: {},
};

const workflow = {
  id: "workflow-1",
  name: "Coding Showcase",
  description: null,
  status: "draft" as const,
  draft_graph: graph,
  graph_schema_version: "1.0",
  current_version: null,
  created_at: "2026-08-15T00:00:00Z",
  updated_at: "2026-08-15T00:00:00Z",
};

function renderBuilder(version?: number) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <WorkflowBuilderPage workflowId="workflow-1" version={version} onBack={vi.fn()} />
    </QueryClientProvider>,
  );
}

describe("WorkflowBuilderPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useWorkflowBuilderStore.getState().reset();
    api.getWorkflow.mockResolvedValue(workflow);
    api.getWorkflowGraph.mockResolvedValue({ workflow_id: "workflow-1", schema_version: "1.0", graph, warnings: [], updated_at: workflow.updated_at });
    api.getWorkflowVersion.mockResolvedValue({ id: "version-1", workflow_id: "workflow-1", version: 1, graph_schema_version: "1.0", graph, change_note: null, created_at: workflow.updated_at });
    api.getAgents.mockResolvedValue([{ id: "agent-1", name: "Codex", connector_type: "http", enabled: true }]);
    api.getServices.mockResolvedValue([]);
    api.getActions.mockResolvedValue([]);
    api.updateWorkflowGraph.mockResolvedValue({ workflow_id: "workflow-1", schema_version: "1.0", graph, warnings: [], updated_at: workflow.updated_at });
    api.createWorkflowVersion.mockResolvedValue({ id: "version-1", workflow_id: "workflow-1", version: 1, graph_schema_version: "1.0", graph, change_note: "first", created_at: workflow.updated_at });
    api.validateWorkflow.mockResolvedValue({ valid: true, errors: [], warnings: [] });
  });

  afterEach(() => cleanup());

  it("renders the draft toolbar, palette and a valid graph", async () => {
    renderBuilder();
    expect(await screen.findByText("Coding Showcase")).toBeInTheDocument();
    expect(screen.getByText("Add nodes")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Call an existing connected Agent/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save Draft" })).toBeInTheDocument();
  });

  it("adds a node from the palette into the builder graph", async () => {
    const user = userEvent.setup();
    renderBuilder();
    await screen.findByText("Coding Showcase");
    await user.click(screen.getByRole("button", { name: /Call an existing connected Agent/ }));
    const graph = useWorkflowBuilderStore.getState().graph;
    expect(graph?.nodes).toHaveLength(2);
    expect(useWorkflowBuilderStore.getState().isDirty).toBe(true);
  });

  it("saves a dirty valid draft through the Graph API", async () => {
    const user = userEvent.setup();
    renderBuilder();
    await screen.findByText("Coding Showcase");
    useWorkflowBuilderStore.getState().moveNode("planner", { x: 300, y: 300 });
    await user.click(screen.getByRole("button", { name: "Save Draft" }));
    expect(api.updateWorkflowGraph).toHaveBeenCalledWith("workflow-1", expect.objectContaining({ schema_version: "1.0", nodes: expect.any(Array) }));
  });

  it("creates a Version (saving first) through the Version API", async () => {
    const user = userEvent.setup();
    renderBuilder();
    await screen.findByText("Coding Showcase");
    useWorkflowBuilderStore.getState().moveNode("planner", { x: 150, y: 150 });
    await user.click(screen.getByRole("button", { name: "Create Version" }));
    const dialog = await screen.findByRole("dialog", { name: "Create Workflow Version" });
    await user.click(within(dialog).getByRole("button", { name: "Create Version" }));
    expect(api.updateWorkflowGraph).toHaveBeenCalled();
    expect(api.createWorkflowVersion).toHaveBeenCalledWith("workflow-1", undefined);
    expect(await screen.findByText(/Created Workflow Version v1/)).toBeInTheDocument();
  });

  it("blocks saving when local validation has errors", async () => {
    const user = userEvent.setup();
    renderBuilder();
    await screen.findByText("Coding Showcase");
    await user.click(screen.getByRole("button", { name: /Call an existing connected Agent/ }));
    const saveButton = screen.getByRole("button", { name: "Save Draft" }) as HTMLButtonElement;
    expect(saveButton.disabled).toBe(true);
  });

  it("renders a read-only canvas for a Version", async () => {
    renderBuilder(1);
    expect(await screen.findByText("READ ONLY")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Save Draft" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Create Version" })).not.toBeInTheDocument();
  });

  it("runs backend validation and renders issues in the panel", async () => {
    const user = userEvent.setup();
    api.validateWorkflow.mockResolvedValue({
      valid: false,
      errors: [{ code: "MISSING_OUTPUT_NODE", severity: "error", message: "Workflow requires at least one Data Output node", node_id: null, edge_id: null, field: "nodes[]", details: {} }],
      warnings: [{ code: "AGENT_UNHEALTHY", severity: "warning", message: "Agent is currently unhealthy", node_id: "planner", edge_id: null, field: "config.agent_id", details: {} }],
    });
    renderBuilder();
    await screen.findByText("Coding Showcase");
    await user.click(screen.getByRole("button", { name: "Validate" }));
    expect(await screen.findByText("Workflow requires at least one Data Output node")).toBeInTheDocument();
    expect(screen.getByText("Agent is currently unhealthy")).toBeInTheDocument();
    expect(api.validateWorkflow).toHaveBeenCalledWith("workflow-1", expect.objectContaining({ schema_version: "1.0" }));
  });

  it("focuses a node when a validation issue is clicked", async () => {
    const user = userEvent.setup();
    api.validateWorkflow.mockResolvedValue({
      valid: false,
      errors: [{ code: "AGENT_NOT_FOUND", severity: "error", message: "Agent is not registered", node_id: "planner", edge_id: null, field: "config.agent_id", details: {} }],
      warnings: [],
    });
    renderBuilder();
    await screen.findByText("Coding Showcase");
    await user.click(screen.getByRole("button", { name: "Validate" }));
    await user.click(await screen.findByText("Agent is not registered"));
    expect(useWorkflowBuilderStore.getState().selectedNodeId).toBe("planner");
  });

  it("blocks Create Version when backend validation fails", async () => {
    const user = userEvent.setup();
    api.validateWorkflow.mockResolvedValue({
      valid: false,
      errors: [{ code: "MISSING_OUTPUT_NODE", severity: "error", message: "Workflow requires at least one Data Output node", node_id: null, edge_id: null, field: "nodes[]", details: {} }],
      warnings: [],
    });
    renderBuilder();
    await screen.findByText("Coding Showcase");
    await user.click(screen.getByRole("button", { name: "Create Version" }));
    const dialog = await screen.findByRole("dialog", { name: "Create Workflow Version" });
    await user.click(within(dialog).getByRole("button", { name: "Create Version" }));
    expect(api.createWorkflowVersion).not.toHaveBeenCalled();
    expect(await screen.findByText(/Fix validation errors before creating a Version/)).toBeInTheDocument();
    expect(screen.getByText("Workflow requires at least one Data Output node")).toBeInTheDocument();
  });

  it("marks validation stale after a semantic graph change", async () => {
    const user = userEvent.setup();
    renderBuilder();
    await screen.findByText("Coding Showcase");
    await user.click(screen.getByRole("button", { name: "Validate" }));
    await screen.findByRole("button", { name: "Close validation panel" });
    expect(useWorkflowBuilderStore.getState().validationStale).toBe(false);
    useWorkflowBuilderStore.getState().updateNode("planner", { name: "Renamed" });
    expect(useWorkflowBuilderStore.getState().validationStale).toBe(true);
  });
});
