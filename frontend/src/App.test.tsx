import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("./api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./api/client")>();
  return { ...actual, getHealth: vi.fn().mockRejectedValue(new Error("offline")) };
});

import App from "./App";
import { useI18nStore } from "./i18n";

describe("App language switch", () => {
  beforeEach(() => {
    useI18nStore.getState().setLanguage("en");
  });

  it("switches the navigation and overview copy to Chinese", async () => {
    const user = userEvent.setup();
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<QueryClientProvider client={queryClient}><App /></QueryClientProvider>);

    expect(screen.getByRole("button", { name: "Agents" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "中文" }));

    expect(screen.getByRole("button", { name: "智能体" })).toBeInTheDocument();
    expect(screen.getByText("编排平台")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Agents" })).not.toBeInTheDocument();
  });
});
