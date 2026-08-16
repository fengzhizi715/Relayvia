import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { WorkflowRun, WorkflowRunSummary } from "../../api/client";
import { RunDetailPage } from "./RunDetailPage";
import { RunsPage } from "./RunsPage";

const api = vi.hoisted(() => ({
  getRuns: vi.fn(),
  getWorkflowRun: vi.fn(),
  startWorkflowRun: vi.fn(),
  pauseWorkflowRun: vi.fn(),
  resumeWorkflowRun: vi.fn(),
  cancelWorkflowRun: vi.fn(),
  getNodeRuns: vi.fn(),
  getNodeRun: vi.fn(),
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

const summary: WorkflowRunSummary = {
  id: "run-1",
  workflow_id: "wf-1",
  workflow_name: "Coding Showcase",
  workflow_version_id: "v-1",
  version: 1,
  status: "created",
  started_at: null,
  finished_at: null,
  created_at: "2026-08-15T00:00:00Z",
  updated_at: "2026-08-15T00:00:00Z",
};

function runOf(status: WorkflowRun["status"]): WorkflowRun {
  return {
    id: "run-1",
    workflow_id: "wf-1",
    workflow_name: "Coding Showcase",
    workflow_version_id: "v-1",
    version: 1,
    status,
    graph_schema_version: "1.0",
    graph_snapshot: { schema_version: "1.0", nodes: [], edges: [], variables: {}, metadata: {} },
    execution_snapshot: {},
    input: {},
    variables: {},
    error: null,
    waiting_reason: null,
    waiting_metadata: {},
    started_at: null,
    finished_at: null,
    paused_at: null,
    cancelled_at: null,
    created_at: "2026-08-15T00:00:00Z",
    updated_at: "2026-08-15T00:00:00Z",
    node_runs: [],
  };
}

function renderUi(ui: React.ReactNode) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

describe("Runs feature", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.getWorkflowRun.mockResolvedValue(runOf("created"));
  });
  afterEach(() => cleanup());

  it("renders the run list and opens a run detail", async () => {
    api.getRuns.mockResolvedValue([summary]);
    const user = userEvent.setup();
    renderUi(<RunsPage />);
    const row = await screen.findByText("Coding Showcase");
    await user.click(row);
    expect(await screen.findByText(/Run run-1/)).toBeInTheDocument();
    expect(api.getWorkflowRun).toHaveBeenCalledWith("run-1");
  });

  it("shows Start and Cancel for a created run and starts it", async () => {
    const user = userEvent.setup();
    api.startWorkflowRun.mockResolvedValue(runOf("running"));
    renderUi(<RunDetailPage runId="run-1" onBack={vi.fn()} />);
    const start = await screen.findByRole("button", { name: "Start" });
    expect(screen.getByRole("button", { name: "Cancel" })).toBeInTheDocument();
    await user.click(start);
    expect(api.startWorkflowRun).toHaveBeenCalledWith("run-1");
  });

  it("shows Pause/Cancel for running and Resume/Cancel for paused", async () => {
    api.getWorkflowRun.mockResolvedValueOnce(runOf("running"));
    const { unmount } = renderUi(<RunDetailPage runId="run-1" onBack={vi.fn()} />);
    expect(await screen.findByRole("button", { name: "Pause" })).toBeInTheDocument();
    unmount();

    api.getWorkflowRun.mockResolvedValue(runOf("paused"));
    renderUi(<RunDetailPage runId="run-1" onBack={vi.fn()} />);
    expect(await screen.findByRole("button", { name: "Resume" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Cancel" })).toBeInTheDocument();
  });

  it("shows no control actions for a terminal run", async () => {
    api.getWorkflowRun.mockResolvedValue(runOf("cancelled"));
    renderUi(<RunDetailPage runId="run-1" onBack={vi.fn()} />);
    expect(await screen.findByText(/terminal state/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Start" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Cancel" })).not.toBeInTheDocument();
  });

  it("surfaces backend action errors", async () => {
    const user = userEvent.setup();
    api.startWorkflowRun.mockRejectedValue(new Error("boom"));
    renderUi(<RunDetailPage runId="run-1" onBack={vi.fn()} />);
    await user.click(await screen.findByRole("button", { name: "Start" }));
    expect(await screen.findByText(/Run action failed/)).toBeInTheDocument();
  });
});
