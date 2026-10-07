import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Workspace } from "../../api/client";
import { WorkspaceListPage } from "./WorkspaceListPage";

const api = vi.hoisted(() => ({
  getWorkspaces: vi.fn(),
  releaseWorkspace: vi.fn(),
}));

vi.mock("../../api/client", () => api);

function workspaceOf(id: string, status: Workspace["status"] = "ready"): Workspace {
  return {
    id, name: `workspace-${id}`, runner_id: "runner-1", repository: "/repos/project", path: `/worktrees/${id}`, branch: "relayvia/a", base_branch: null,
    workspace_type: "worktree", status, workflow_run_id: "run-1", node_run_id: `node-${id}`, metadata: {}, created_at: "2026-08-15T00:00:00Z", updated_at: "2026-08-15T00:00:00Z",
  };
}

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
    api.getWorkspaces.mockResolvedValue({ items: [], total: 0 });
    renderUi();
    expect(await screen.findByText("No workspaces yet.")).toBeInTheDocument();
  });

  it("only offers release for inactive workspaces", async () => {
    api.getWorkspaces.mockResolvedValue({
      items: [workspaceOf("ready", "ready"), workspaceOf("active", "in_use")],
      total: 2,
    });
    api.releaseWorkspace.mockResolvedValue({});
    const user = userEvent.setup();
    renderUi();

    expect(await screen.findByText("workspace-ready")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Release" })).toHaveLength(1);
    await user.click(screen.getByRole("button", { name: "Release" }));
    expect(api.releaseWorkspace).toHaveBeenCalledWith("ready", expect.anything());
  });

  it("loads the next page through the API offset", async () => {
    const firstPage = Array.from({ length: 20 }, (_, index) => workspaceOf(`p1-${index}`));
    api.getWorkspaces.mockImplementation((_runId?: string, page?: { offset?: number }) =>
      Promise.resolve(page?.offset === 20
        ? { items: [workspaceOf("p2-0")], total: 21 }
        : { items: firstPage, total: 21 }),
    );
    const user = userEvent.setup();
    renderUi();

    expect(await screen.findByText("workspace-p1-0")).toBeInTheDocument();
    expect(screen.queryByText("workspace-p2-0")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Next" }));
    expect(await screen.findByText("workspace-p2-0")).toBeInTheDocument();
    expect(api.getWorkspaces).toHaveBeenLastCalledWith(undefined, { limit: 20, offset: 20 });
  });
});
