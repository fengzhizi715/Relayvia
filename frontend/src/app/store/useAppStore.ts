import { create } from "zustand";

export type AppSection = "overview" | "agents" | "services" | "credentials" | "workflows" | "runs" | "runners";

type AppStore = {
  activeSection: AppSection;
  setActiveSection: (section: AppSection) => void;
  pendingRunId: string | null;
  setPendingRunId: (runId: string | null) => void;
};

export const useAppStore = create<AppStore>((set) => ({
  activeSection: "overview",
  setActiveSection: (activeSection) => set({ activeSection }),
  pendingRunId: null,
  setPendingRunId: (pendingRunId) => set({ pendingRunId }),
}));
