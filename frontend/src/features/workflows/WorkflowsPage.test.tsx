import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({
  getWorkflows: vi.fn(),
  createWorkflow: vi.fn(),
  updateWorkflow: vi.fn(),
  getWorkflowGraph: vi.fn(),
  updateWorkflowGraph: vi.fn(),
  getWorkflowVersions: vi.fn(),
  createWorkflowVersion: vi.fn(),
}));

vi.mock("../../api/client", () => ({
  ...api,
  ApiError: class ApiError extends Error {},
}));

vi.mock("../../workflow/canvas/WorkflowBuilderPage", () => ({
  WorkflowBuilderPage: () => <div>Builder stub</div>,
}));

import { WorkflowsPage } from "./WorkflowsPage";

const graph = { schema_version: "1.0" as const, nodes: [], edges: [], variables: {}, metadata: {} };
const version = { id: "version-1", workflow_id: "workflow-1", version: 1, graph_schema_version: "1.0", graph, change_note: null, created_at: "2026-08-15T00:00:00Z" };
const workflow = {
  id: "workflow-1",
  name: "Coding Showcase",
  description: "Graph contract",
  status: "draft" as const,
  draft_graph: graph,
  graph_schema_version: "1.0",
  current_version: null,
  created_at: "2026-08-15T00:00:00Z",
  updated_at: "2026-08-15T00:00:00Z",
};

describe("WorkflowsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.getWorkflowGraph.mockResolvedValue({ workflow_id: workflow.id, schema_version: "1.0", graph, warnings: [], updated_at: workflow.updated_at });
    api.getWorkflowVersions.mockResolvedValue([]);
  });
  afterEach(() => cleanup());

  it("creates a Workflow from the management page", async () => {
    api.getWorkflows.mockResolvedValue([]);
    api.createWorkflow.mockResolvedValue(workflow);
    const user = userEvent.setup();
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<QueryClientProvider client={queryClient}><WorkflowsPage /></QueryClientProvider>);
    await user.click(await screen.findByRole("button", { name: "+ Create Workflow" }));
    await user.type(screen.getByPlaceholderText("Coding Agent Showcase"), "Contract Workflow");
    await user.click(within(screen.getByRole("dialog", { name: "Create Workflow" })).getByRole("button", { name: "Create Workflow" }));
    expect(api.createWorkflow).toHaveBeenCalledWith({ name: "Contract Workflow", description: "" });
  });

  it("renames an existing Workflow", async () => {
    api.getWorkflows.mockResolvedValue([workflow]);
    api.getWorkflowGraph.mockResolvedValue({ workflow_id: workflow.id, schema_version: "1.0", graph, warnings: [], updated_at: workflow.updated_at });
    api.getWorkflowVersions.mockResolvedValue([]);
    api.updateWorkflow.mockResolvedValue({ ...workflow, name: "Renamed Workflow" });
    const user = userEvent.setup();
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<QueryClientProvider client={queryClient}><WorkflowsPage /></QueryClientProvider>);
    await user.click(await screen.findByRole("button", { name: /Coding Showcase/ }));
    await user.click(screen.getByRole("button", { name: "Rename" }));
    const nameInput = screen.getByDisplayValue("Coding Showcase");
    await user.clear(nameInput);
    await user.type(nameInput, "Renamed Workflow");
    await user.click(screen.getByRole("button", { name: "Save name" }));
    expect(api.updateWorkflow).toHaveBeenCalledWith("workflow-1", { name: "Renamed Workflow", description: "Graph contract" });
  });

  it("loads a draft, saves it, creates a version, and makes history read only", async () => {
    api.getWorkflows.mockResolvedValue([workflow]);
    api.getWorkflowGraph.mockResolvedValue({ workflow_id: workflow.id, schema_version: "1.0", graph, warnings: [], updated_at: workflow.updated_at });
    api.getWorkflowVersions.mockResolvedValueOnce([]).mockResolvedValue([version]);
    api.updateWorkflowGraph.mockResolvedValue({ workflow_id: workflow.id, schema_version: "1.0", graph, warnings: [], updated_at: workflow.updated_at });
    api.createWorkflowVersion.mockResolvedValue(version);
    const user = userEvent.setup();
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<QueryClientProvider client={queryClient}><WorkflowsPage /></QueryClientProvider>);

    const row = await screen.findByRole("button", { name: /Coding Showcase/ });
    expect(row).not.toBeNull();
    await user.click(row!);
    await screen.findByText("Graph Schema 1.0 JSON");
    await user.click(screen.getByRole("button", { name: "Save Draft" }));
    expect(api.updateWorkflowGraph).toHaveBeenCalledWith("workflow-1", graph);
    await user.click(screen.getByRole("button", { name: "Create Version" }));
    expect(api.createWorkflowVersion).toHaveBeenCalledWith("workflow-1");

    const versionRow = (await screen.findByText("v1")).closest("button");
    expect(versionRow).not.toBeNull();
    await user.click(versionRow!);
    expect(screen.getByRole("textbox")).toHaveProperty("readOnly", true);
    expect(screen.queryByRole("button", { name: "Save Draft" })).not.toBeInTheDocument();
  });
});
