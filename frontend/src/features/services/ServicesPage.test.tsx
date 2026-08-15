import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({
  getServices: vi.fn(),
  getCredentials: vi.fn(),
  getActions: vi.fn(),
  testService: vi.fn(),
  updateService: vi.fn(),
  deleteService: vi.fn(),
  deleteAction: vi.fn(),
}));

vi.mock("../../api/client", () => ({
  ...api,
  ApiError: class ApiError extends Error {},
}));

import { ServicesPage } from "./ServicesPage";

const service = {
  id: "service-1",
  name: "YoloWebAgent",
  description: "Existing HTTP service",
  service_type: "http" as const,
  base_url: "http://localhost:8001/api",
  credential_id: null,
  credential_name: null,
  health_check_url: "http://localhost:8001/api/health",
  status: "unknown" as const,
  enabled: true,
  metadata: {},
  last_checked_at: null,
  last_latency_ms: null,
  last_error: null,
  actions_count: 0,
  created_at: "2026-08-15T00:00:00Z",
  updated_at: "2026-08-15T00:00:00Z",
};

describe("ServicesPage", () => {
  it("opens the Add Service Action form from a service detail", async () => {
    api.getServices.mockResolvedValue([service]);
    api.getCredentials.mockResolvedValue([]);
    api.getActions.mockResolvedValue([]);
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const user = userEvent.setup();
    render(<QueryClientProvider client={queryClient}><ServicesPage /></QueryClientProvider>);
    const serviceRow = (await screen.findByText("YoloWebAgent")).closest("button");
    expect(serviceRow).not.toBeNull();
    await user.click(serviceRow!);
    await user.click(screen.getByRole("button", { name: "+ Add Action" }));
    expect(screen.getByRole("dialog", { name: "Add Service Action" })).toBeInTheDocument();
    expect(screen.getByLabelText("Path")).toBeInTheDocument();
  });
});
