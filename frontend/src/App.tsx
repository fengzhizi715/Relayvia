import { useEffect } from "react";
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
import { LanguageSwitcher } from "./i18n/LanguageSwitcher";
import { useTranslation, type TranslationKey } from "./i18n";
import { useWorkflowBuilderStore } from "./workflow/store/workflowBuilderStore";

const SECTION_LABEL_KEYS: Record<AppSection, TranslationKey> = {
  overview: "nav.overview",
  agents: "nav.agents",
  services: "nav.services",
  credentials: "nav.credentials",
  workflows: "nav.workflows",
  runs: "nav.runs",
  runners: "nav.runners",
  workspaces: "nav.workspaces",
};

const SECTIONS: AppSection[] = ["overview", "agents", "services", "credentials", "workflows", "runs", "runners", "workspaces"];

export default function App() {
  const activeSection = useAppStore((state) => state.activeSection);
  const setActiveSection = useAppStore((state) => state.setActiveSection);
  const { t, language } = useTranslation();
  const health = useQuery({
    queryKey: ["health"],
    queryFn: getHealth,
    retry: false,
  });

  useEffect(() => {
    document.documentElement.lang = language === "zh" ? "zh-CN" : "en";
  }, [language]);

  function changeSection(section: AppSection) {
    if (activeSection === "workflows" && section !== "workflows") {
      const builder = useWorkflowBuilderStore.getState();
      if (builder.workflowId !== null && !builder.readOnly && builder.isDirty) {
        if (!window.confirm(t("app.confirmLeaveBuilder"))) return;
      }
    }
    setActiveSection(section);
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand-mark">R</div>
        <div>
          <p className="eyebrow">{t("app.orchestrationPlatform")}</p>
          <h1>Relayvia</h1>
        </div>
        <nav aria-label={t("app.primaryNavigation")}>
          {SECTIONS.map((section) => (
            <button
              className={activeSection === section ? "nav-item nav-item--active" : "nav-item"}
              key={section}
              onClick={() => changeSection(section)}
              type="button"
            >
              {t(SECTION_LABEL_KEYS[section])}
            </button>
          ))}
        </nav>
        <div className="sidebar-footer">
          <span className="pulse-dot" />
          {t("app.runtimeReady")}
        </div>
      </aside>

      <main className="main-content">
        <header className="topbar">
          <div>
            <p className="eyebrow">{t("app.controlPlane")}</p>
            <h2>{t(SECTION_LABEL_KEYS[activeSection])}</h2>
          </div>
          <div className="topbar-actions">
            <LanguageSwitcher />
            <StatusBadge
              label={health.isPending ? t("app.checkingApi") : health.isSuccess ? t("app.apiStatus", { status: health.data.status }) : t("app.apiOffline")}
              tone={health.isSuccess ? (health.data.status === "ok" ? "success" : "warning") : "neutral"}
            />
          </div>
        </header>

        {activeSection === "agents" ? <AgentsPage /> : activeSection === "services" ? <ServicesPage /> : activeSection === "credentials" ? <CredentialsPage /> : activeSection === "workflows" ? <WorkflowsPage /> : activeSection === "runs" ? <RunsPage /> : activeSection === "runners" ? <RunnerListPage /> : activeSection === "workspaces" ? <WorkspaceListPage /> : <>
        <section className="hero-card">
          <div>
            <p className="eyebrow">{t("app.foundationReady")}</p>
            <h3>{t("app.heroTitle")}</h3>
            <p className="hero-copy">{t("app.heroCopy")}</p>
          </div>
          <div className="hero-orbit" aria-hidden="true">
            <span>{t("app.heroAgent")}</span>
            <span>{t("app.heroWorkflow")}</span>
            <span>{t("app.heroTrace")}</span>
          </div>
        </section>

        <section className="status-grid" aria-label={t("app.platformStatus")}>
          <article className="status-card">
            <p className="eyebrow">{t("app.api")}</p>
            <h3>{health.isSuccess ? health.data.service : t("app.waitingForFastapi")}</h3>
            <p>{health.isSuccess ? t("app.database", { database: health.data.database }) : t("app.startBackend")}</p>
          </article>
          <article className="status-card">
            <p className="eyebrow">{t("app.nextLayer")}</p>
            <h3>{t("app.durableOrchestration")}</h3>
            <p>{t("app.durableOrchestrationCopy")}</p>
          </article>
          <article className="status-card status-card--accent">
            <p className="eyebrow">{t("app.runtimePrinciple")}</p>
            <h3>{t("app.existingCapabilityFirst")}</h3>
            <p>{t("app.connectorFlow")}</p>
          </article>
        </section>
        </>}
      </main>
    </div>
  );
}
