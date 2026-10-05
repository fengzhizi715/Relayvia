import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { getWorkspaces, releaseWorkspace, type Workspace } from "../../api/client";
import { StatusBadge } from "../../components/StatusBadge";
import { useTranslation } from "../../i18n";

function statusTone(status: Workspace["status"]): "success" | "warning" | "danger" | "neutral" {
  if (status === "ready") return "success";
  if (status === "failed" || status === "cleanup_failed") return "danger";
  if (status === "creating" || status === "in_use" || status === "releasing" || status === "cleaning") return "warning";
  return "neutral";
}

export function WorkspaceListPage() {
  const { t, tStatus, locale } = useTranslation();
  const queryClient = useQueryClient();
  const workspaces = useQuery({ queryKey: ["workspaces"], queryFn: () => getWorkspaces(), refetchInterval: 5000 });
  const release = useMutation({
    mutationFn: releaseWorkspace,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["workspaces"] }),
  });

  if (workspaces.isLoading) return <div className="loading-state">{t("workspaces.loading")}</div>;
  if (workspaces.isError) return <div className="inline-error">{t("workspaces.loadError")}</div>;

  const list = workspaces.data ?? [];
  return (
    <div className="resource-page">
      <div className="page-toolbar">
        <div>
          <p className="eyebrow">{t("workspaces.eyebrow")}</p>
          <h3>{t("workspaces.title")}</h3>
          <p className="page-description">{t("workspaces.description")}</p>
        </div>
      </div>
      {list.length === 0 ? (
        <div className="empty-state"><div className="empty-icon">W</div><h3>{t("workspaces.emptyTitle")}</h3><p>{t("workspaces.emptyMessage")}</p></div>
      ) : (
        <div className="resource-list">
          {list.map((workspace) => {
            const canRelease = workspace.status === "ready" || workspace.status === "failed" || workspace.status === "cleanup_failed";
            return (
              <div className="resource-row" key={workspace.id}>
                <span className="resource-row-main">
                  <strong>{workspace.name}</strong>
                  <small>{workspace.workspace_type === "worktree" ? t("workspaces.gitWorktree") : t("workspaces.localRepository")} · {workspace.repository}</small>
                  <small>{t("workspaces.branch", { branch: workspace.branch ?? "—", runner: workspace.runner_id ?? t("workspaces.unassigned") })}</small>
                  {workspace.path ? <small>{t("workspaces.path", { path: workspace.path })}</small> : null}
                </span>
                <span className="resource-row-meta">
                  <span className="action-copy">
                    <span>{t("workspaces.runNode", { run: workspace.workflow_run_id, node: workspace.node_run_id })}</span>
                    <small>{t("workspaces.updated", { time: new Date(workspace.updated_at).toLocaleString(locale) })}</small>
                  </span>
                  <StatusBadge label={tStatus(workspace.status)} tone={statusTone(workspace.status)} />
                  {canRelease ? (
                    <button
                      className="button button--danger"
                      disabled={release.isPending}
                      onClick={() => {
                        if (window.confirm(t("workspaces.releaseConfirm", { name: workspace.name }))) release.mutate(workspace.id);
                      }}
                      type="button"
                    >
                      {t("workspaces.release")}
                    </button>
                  ) : null}
                </span>
              </div>
            );
          })}
        </div>
      )}
      {release.isError ? <div className="inline-error">{t("workspaces.releaseError")}</div> : null}
    </div>
  );
}
