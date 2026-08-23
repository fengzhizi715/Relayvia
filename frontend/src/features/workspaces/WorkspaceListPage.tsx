import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { getWorkspaces, releaseWorkspace, type Workspace } from "../../api/client";
import { StatusBadge } from "../../components/StatusBadge";

function statusTone(status: Workspace["status"]): "success" | "warning" | "danger" | "neutral" {
  if (status === "ready") return "success";
  if (status === "failed") return "danger";
  if (status === "creating" || status === "in_use") return "warning";
  return "neutral";
}

function workspaceType(type: Workspace["workspace_type"]): string {
  return type === "worktree" || type === "git_worktree" ? "Git worktree" : "Local repository";
}

export function WorkspaceListPage() {
  const queryClient = useQueryClient();
  const workspaces = useQuery({ queryKey: ["workspaces"], queryFn: () => getWorkspaces(), refetchInterval: 5000 });
  const release = useMutation({
    mutationFn: releaseWorkspace,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["workspaces"] }),
  });

  if (workspaces.isLoading) return <div className="loading-state">Loading workspaces...</div>;
  if (workspaces.isError) return <div className="inline-error">Unable to load Workspaces. Start the FastAPI backend and retry.</div>;

  const list = workspaces.data ?? [];
  return (
    <div className="resource-page">
      <div className="page-toolbar">
        <div>
          <p className="eyebrow">WORKSPACE MANAGER</p>
          <h3>Runner workspaces</h3>
          <p className="page-description">Isolated execution contexts prepared on registered Runners. Active workspaces are released by the Runtime after their task finishes.</p>
        </div>
      </div>
      {list.length === 0 ? (
        <div className="empty-state"><div className="empty-icon">W</div><h3>No workspaces yet.</h3><p>Workspaces appear when a Runner-backed Tool or Coding Agent uses a repository.</p></div>
      ) : (
        <div className="resource-list">
          {list.map((workspace) => {
            const canRelease = workspace.status === "ready" || workspace.status === "failed";
            return (
              <div className="resource-row" key={workspace.id}>
                <span className="resource-row-main">
                  <strong>{workspace.name}</strong>
                  <small>{workspaceType(workspace.workspace_type)} · {workspace.repository}</small>
                  <small>Branch: {workspace.branch ?? "—"} · Runner: {workspace.runner_id ?? "Unassigned"}</small>
                  {workspace.path ? <small>Path: {workspace.path}</small> : null}
                </span>
                <span className="resource-row-meta">
                  <span className="action-copy">
                    <span>Run: {workspace.workflow_run_id} · Node: {workspace.node_run_id}</span>
                    <small>Updated {new Date(workspace.updated_at).toLocaleString()}</small>
                  </span>
                  <StatusBadge label={workspace.status.replace("_", " ").toUpperCase()} tone={statusTone(workspace.status)} />
                  {canRelease ? (
                    <button
                      className="button button--danger"
                      disabled={release.isPending}
                      onClick={() => {
                        if (window.confirm(`Release workspace “${workspace.name}”? Its Runner files are not deleted by this action.`)) release.mutate(workspace.id);
                      }}
                      type="button"
                    >
                      Release
                    </button>
                  ) : null}
                </span>
              </div>
            );
          })}
        </div>
      )}
      {release.isError ? <div className="inline-error">Unable to release this Workspace. Active workspaces must finish first.</div> : null}
    </div>
  );
}
