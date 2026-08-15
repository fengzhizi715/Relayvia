import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({
  getAgents: vi.fn(),
  getCredentials: vi.fn(),
  testAgent: vi.fn(),
  updateAgent: vi.fn(),
  deleteAgent: vi.fn(),
}));

vi.mock("../../api/client", () => ({
  ...api,
  ApiError: class ApiError extends Error {},
}));

import { AgentsPage } from "./AgentsPage";

const agent = {
  id: "agent-1",
  name: "Review Agent",
  description: "Existing agent",
  connector_type: "http" as const,
  endpoint: "http://localhost:9001/agent",
  http_method: "POST" as const,
  health_check_url: "http://localhost:9001/health",
  headers: {},
  runner_id: null,
  capabilities: [],
  input_schema: {},
  output_schema: {},
  credential_id: null,
  credential_name: null,
  timeout_seconds: 30,
  status: "unknown" as const,
  enabled: true,
  metadata: {},
  last_checked_at: null,
  last_latency_ms: null,
  last_error: null,
  created_at: "2026-08-15T00:00:00Z",
  updated_at: "2026-08-15T00:00:00Z",
};

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={queryClient}><AgentsPage /></QueryClientProvider>);
}

describe("AgentsPage", () => {
  it("runs a connection test and confirms deletion", async () => {
    api.getAgents.mockResolvedValue([agent]);
    api.getCredentials.mockResolvedValue([]);
    api.testAgent.mockResolvedValue({ status: "healthy", latency_ms: 10, checked_at: "2026-08-15T00:00:00Z", error_code: null, message: "Connection successful" });
    api.updateAgent.mockResolvedValue({ ...agent, enabled: false });
    api.deleteAgent.mockResolvedValue(undefined);
    const user = userEvent.setup();
    renderPage();

    expect(await screen.findByText("Review Agent")).toBeInTheDocument();
    const agentRow = screen.getByText("Review Agent").closest("button");
    expect(agentRow).not.toBeNull();
    await user.click(agentRow!);
    await user.click(screen.getByRole("button", { name: "Test connection" }));
    expect(api.testAgent.mock.calls[0][0]).toBe("agent-1");
    await user.click(screen.getByRole("button", { name: "Disable" }));
    expect(api.updateAgent).toHaveBeenCalledWith("agent-1", { enabled: false });
    await user.click(screen.getByRole("button", { name: "Delete" }));
    expect(screen.getByRole("dialog", { name: "Delete Agent" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Delete Agent" }));
    expect(api.deleteAgent.mock.calls[0][0]).toBe("agent-1");
  });
});
