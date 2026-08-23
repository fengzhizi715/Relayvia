import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { WorkspaceListPage } from "./WorkspaceListPage";

const api = vi.hoisted(() => ({
  getWorkspaces: vi.fn(),
  releaseWorkspace: vi.fn(),
}));

vi.mock("../../api/client", () => api);

function renderUi() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}><WorkspaceListPage /></QueryClientProvider>);
}

describe("WorkspaceListPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.spyOn(window, "confirm").mockReturnValue(true);
  });
  afterEach(() => cleanup());

  it("shows an empty state", async () => {
    api.getWorkspaces.mockResolvedValue([]);
    renderUi();
    expect(await screen.findByText("No workspaces yet.")).toBeInTheDocument();
  });

  it("only offers release for inactive workspaces", async () => {
    api.getWorkspaces.mockResolvedValue([
      {
        id: "ready", name: "ready-worktree", runner_id: "runner-1", repository: "/repos/project", path: "/worktrees/ready", branch: "relayvia/a", base_branch: null,
        workspace_type: "worktree", status: "ready", workflow_run_id: "run-1", node_run_id: "node-1", metadata: {}, created_at: "2026-08-15T00:00:00Z", updated_at: "2026-08-15T00:00:00Z",
      },
      {
        id: "active", name: "active-worktree", runner_id: "runner-1", repository: "/repos/project", path: null, branch: "relayvia/b", base_branch: null,
        workspace_type: "worktree", status: "in_use", workflow_run_id: "run-2", node_run_id: "node-2", metadata: {}, created_at: "2026-08-15T00:00:00Z", updated_at: "2026-08-15T00:00:00Z",
      },
    ]);
    api.releaseWorkspace.mockResolvedValue({});
    const user = userEvent.setup();
    renderUi();

    expect(await screen.findByText("ready-worktree")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Release" })).toHaveLength(1);
    await user.click(screen.getByRole("button", { name: "Release" }));
    expect(api.releaseWorkspace).toHaveBeenCalledWith("ready", expect.anything());
  });
});
