import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Runner } from "../../api/client";
import { RunnerListPage } from "./RunnerListPage";

const api = vi.hoisted(() => ({
  getRunners: vi.fn(),
  setRunnerEnabled: vi.fn(),
  revokeRunner: vi.fn(),
  rotateRunnerToken: vi.fn(),
}));

vi.mock("../../api/client", () => api);

const runner: Runner = {
  id: "runner-1",
  name: "Mac-Mini",
  hostname: "mac-mini.local",
  platform: "darwin",
  status: "online",
  capabilities: ["codex", "git", "shell"],
  last_seen_at: "2026-08-15T00:00:00Z",
  metadata: {},
  created_at: "2026-08-15T00:00:00Z",
  updated_at: "2026-08-15T00:00:00Z",
};

function renderUi() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}><RunnerListPage /></QueryClientProvider>);
}

describe("RunnerListPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.spyOn(window, "confirm").mockReturnValue(true);
  });
  afterEach(() => cleanup());

  it("renders runner identity, capabilities, and status", async () => {
    api.getRunners.mockResolvedValue({ items: [runner], total: 1 });
    renderUi();
    expect(await screen.findByText("Mac-Mini")).toBeInTheDocument();
    expect(screen.getByText("CODEX")).toBeInTheDocument();
    expect(screen.getByText("Online")).toBeInTheDocument();
    expect(screen.getByText(/ID: runner-1/)).toBeInTheDocument();
  });

  it("disables, rotates, and revokes a runner", async () => {
    api.getRunners.mockResolvedValue({ items: [runner], total: 1 });
    api.setRunnerEnabled.mockResolvedValue({ ...runner, status: "disabled" });
    api.rotateRunnerToken.mockResolvedValue({ runner_id: "runner-1", enrollment_token: "token-1" });
    api.revokeRunner.mockResolvedValue({ ...runner, status: "disabled" });
    const user = userEvent.setup();
    renderUi();

    await user.click(await screen.findByRole("button", { name: "Disable" }));
    expect(api.setRunnerEnabled).toHaveBeenCalledWith("runner-1", false);

    await user.click(screen.getByRole("button", { name: "Rotate token" }));
    expect(api.rotateRunnerToken).toHaveBeenCalledWith("runner-1", expect.anything());
    expect(await screen.findByText("token-1")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Revoke" }));
    expect(api.revokeRunner).toHaveBeenCalledWith("runner-1", expect.anything());
  });
});
