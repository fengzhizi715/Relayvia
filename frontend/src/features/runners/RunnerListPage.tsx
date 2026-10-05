import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { getRunners, revokeRunner, rotateRunnerToken, setRunnerEnabled, type Runner } from "../../api/client";
import { StatusBadge } from "../../components/StatusBadge";
import { useTranslation } from "../../i18n";

function statusTone(status: Runner["status"]): "success" | "danger" | "neutral" {
  return status === "online" ? "success" : status === "offline" ? "danger" : "neutral";
}

export function RunnerListPage() {
  const { t, tStatus, locale } = useTranslation();
  const queryClient = useQueryClient();
  const [rotatedToken, setRotatedToken] = useState<string | null>(null);
  const runners = useQuery({ queryKey: ["runners"], queryFn: getRunners, refetchInterval: 5000 });
  const updateStatus = useMutation({
    mutationFn: ({ id, enabled }: { id: string; enabled: boolean }) => setRunnerEnabled(id, enabled),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["runners"] }),
  });
  const revoke = useMutation({ mutationFn: revokeRunner, onSuccess: () => queryClient.invalidateQueries({ queryKey: ["runners"] }) });
  const rotate = useMutation({ mutationFn: rotateRunnerToken, onSuccess: (value) => setRotatedToken(value.enrollment_token) });

  if (runners.isLoading) return <div className="loading-state">{t("runners.loading")}</div>;
  if (runners.isError) return <div className="inline-error">{t("runners.loadError")}</div>;

  const list = runners.data ?? [];
  return (
    <div className="resource-page">
      <div className="page-toolbar">
        <div>
          <p className="eyebrow">{t("runners.eyebrow")}</p>
          <h3>{t("runners.title")}</h3>
          <p className="page-description">{t("runners.description")}</p>
        </div>
      </div>
      {rotatedToken ? <div className="inline-success">{t("runners.newToken")} <code>{rotatedToken}</code></div> : null}
      {list.length === 0 ? (
        <div className="empty-state"><div className="empty-icon">R</div><h3>{t("runners.emptyTitle")}</h3><p>{t("runners.emptyMessage")}</p></div>
      ) : (
        <div className="resource-list">
          {list.map((runner) => (
            <div className="resource-row" key={runner.id}>
              <span className="resource-row-main">
                <strong>{runner.name}</strong>
                <small>{runner.hostname}{runner.platform ? ` · ${runner.platform}` : ""} · ID: {runner.id}</small>
              </span>
              <span className="resource-row-meta">
                <span className="action-copy">
                  <span>{runner.capabilities.map((cap) => cap.toUpperCase()).join(" · ")}</span>
                  <small>{t("runners.lastSeen", { time: runner.last_seen_at ? new Date(runner.last_seen_at).toLocaleString(locale) : "—" })}</small>
                </span>
                <StatusBadge label={tStatus(runner.status)} tone={statusTone(runner.status)} />
                <button className="button button--secondary" disabled={updateStatus.isPending} onClick={() => updateStatus.mutate({ id: runner.id, enabled: runner.status === "disabled" })} type="button">
                  {runner.status === "disabled" ? t("common.enable") : t("common.disable")}
                </button>
                <button className="button button--secondary" disabled={rotate.isPending} onClick={() => { if (window.confirm(t("runners.rotateConfirm", { name: runner.name }))) rotate.mutate(runner.id); }} type="button">{t("runners.rotateToken")}</button>
                <button className="button button--danger" disabled={revoke.isPending} onClick={() => { if (window.confirm(t("runners.revokeConfirm", { name: runner.name }))) revoke.mutate(runner.id); }} type="button">{t("runners.revoke")}</button>
              </span>
            </div>
          ))}
        </div>
      )}
      {updateStatus.isError || revoke.isError || rotate.isError ? <div className="inline-error">{t("runners.updateError")}</div> : null}
    </div>
  );
}
