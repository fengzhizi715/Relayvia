import { useQuery } from "@tanstack/react-query";

import { getHealth } from "./api/client";
import { useAppStore, type AppSection } from "./app/store/useAppStore";
import { StatusBadge } from "./components/StatusBadge";
import { AgentsPage } from "./features/agents/AgentsPage";
import { CredentialsPage } from "./features/credentials/CredentialsPage";
import { RunsPage } from "./features/runs/RunsPage";
import { RunnerListPage } from "./features/runners/RunnerListPage";
import { ServicesPage } from "./features/services/ServicesPage";
import { WorkspaceListPage } from "./features/workspaces/WorkspaceListPage";
import { WorkflowsPage } from "./features/workflows/WorkflowsPage";
import { useWorkflowBuilderStore } from "./workflow/store/workflowBuilderStore";

const sections: Array<{ id: AppSection; label: string }> = [
  { id: "overview", label: "Overview" },
  { id: "agents", label: "Agents" },
  { id: "services", label: "Services" },
  { id: "credentials", label: "Credentials" },
  { id: "workflows", label: "Workflows" },
  { id: "runs", label: "Runs" },
  { id: "runners", label: "Runners" },
  { id: "workspaces", label: "Workspaces" },
];

export default function App() {
  const activeSection = useAppStore((state) => state.activeSection);
  const setActiveSection = useAppStore((state) => state.setActiveSection);
  const health = useQuery({
    queryKey: ["health"],
    queryFn: getHealth,
    retry: false,
  });

  function changeSection(section: AppSection) {
    if (activeSection === "workflows" && section !== "workflows") {
      const builder = useWorkflowBuilderStore.getState();
      if (builder.workflowId !== null && !builder.readOnly && builder.isDirty) {
        if (!window.confirm("You have unsaved Builder changes that will be lost. Leave anyway?")) return;
      }
    }
    setActiveSection(section);
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand-mark">R</div>
        <div>
          <p className="eyebrow">ORCHESTRATION PLATFORM</p>
          <h1>Relayvia</h1>
        </div>
        <nav aria-label="Primary navigation">
          {sections.map((section) => (
            <button
              className={activeSection === section.id ? "nav-item nav-item--active" : "nav-item"}
              key={section.id}
              onClick={() => changeSection(section.id)}
              type="button"
            >
              {section.label}
            </button>
          ))}
        </nav>
        <div className="sidebar-footer">
          <span className="pulse-dot" />
          Durable runtime ready
        </div>
      </aside>

      <main className="main-content">
        <header className="topbar">
          <div>
            <p className="eyebrow">CONTROL PLANE</p>
            <h2>{activeSection === "overview" ? "Overview" : activeSection}</h2>
          </div>
          <StatusBadge
            label={health.isPending ? "Checking API" : health.isSuccess ? `API ${health.data.status}` : "API offline"}
            tone={health.isSuccess ? (health.data.status === "ok" ? "success" : "warning") : "neutral"}
          />
        </header>

        {activeSection === "agents" ? <AgentsPage /> : activeSection === "services" ? <ServicesPage /> : activeSection === "credentials" ? <CredentialsPage /> : activeSection === "workflows" ? <WorkflowsPage /> : activeSection === "runs" ? <RunsPage /> : activeSection === "runners" ? <RunnerListPage /> : activeSection === "workspaces" ? <WorkspaceListPage /> : <>
        <section className="hero-card">
          <div>
            <p className="eyebrow">FOUNDATION READY</p>
            <h3>Connect capabilities. Orchestrate work.</h3>
            <p className="hero-copy">
              Relayvia connects existing Agents and Services so workflows can be validated, executed, and traced
              from one control plane.
            </p>
          </div>
          <div className="hero-orbit" aria-hidden="true">
            <span>Agent</span>
            <span>Workflow</span>
            <span>Trace</span>
          </div>
        </section>

        <section className="status-grid" aria-label="Platform status">
          <article className="status-card">
            <p className="eyebrow">API</p>
            <h3>{health.isSuccess ? health.data.service : "Waiting for FastAPI"}</h3>
            <p>{health.isSuccess ? `Database: ${health.data.database}` : "Start the backend on port 8000 to connect."}</p>
          </article>
          <article className="status-card">
            <p className="eyebrow">NEXT LAYER</p>
            <h3>Durable orchestration</h3>
            <p>Immutable workflow versions, validated graph contracts, durable queueing, and independent Workers are active.</p>
          </article>
          <article className="status-card status-card--accent">
            <p className="eyebrow">RUNTIME PRINCIPLE</p>
            <h3>Existing capability first</h3>
            <p>Connector → Execution Unit → Workflow Runtime → Trace</p>
          </article>
        </section>
        </>}
      </main>
    </div>
  );
}
