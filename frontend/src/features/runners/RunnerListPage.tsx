import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { getRunners, revokeRunner, rotateRunnerToken, setRunnerEnabled, type Runner } from "../../api/client";
import { Pagination, usePageClamp } from "../../components/Pagination";
import { StatusBadge } from "../../components/StatusBadge";
import { useTranslation } from "../../i18n";

const PAGE_SIZE = 20;

function statusTone(status: Runner["status"]): "success" | "danger" | "neutral" {
  return status === "online" ? "success" : status === "offline" ? "danger" : "neutral";
}

export function RunnerListPage() {
  const { t, tStatus, locale } = useTranslation();
  const queryClient = useQueryClient();
  const [rotatedToken, setRotatedToken] = useState<string | null>(null);
  const [page, setPage] = useState(0);
  const runners = useQuery({
    queryKey: ["runners", page],
    queryFn: () => getRunners({ limit: PAGE_SIZE, offset: page * PAGE_SIZE }),
    refetchInterval: 5000,
  });
  const updateStatus = useMutation({
    mutationFn: ({ id, enabled }: { id: string; enabled: boolean }) => setRunnerEnabled(id, enabled),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["runners"] }),
  });
  const revoke = useMutation({ mutationFn: revokeRunner, onSuccess: () => queryClient.invalidateQueries({ queryKey: ["runners"] }) });
  const rotate = useMutation({ mutationFn: rotateRunnerToken, onSuccess: (value) => setRotatedToken(value.enrollment_token) });

  const list = runners.data?.items ?? [];
  const total = runners.data?.total;
  usePageClamp(page, PAGE_SIZE, total, setPage);

  if (runners.isLoading) return <div className="loading-state">{t("runners.loading")}</div>;
  if (runners.isError) return <div className="inline-error">{t("runners.loadError")}</div>;

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
        <>
        <div className="runner-list">
          {list.map((runner) => (
            <div className="runner-row" key={runner.id}>
              <span className="runner-identity">
                <span className={`runner-status-dot runner-status-dot--${runner.status}`} aria-hidden="true" />
                <span className="runner-identity-copy">
                  <strong>{runner.name}</strong>
                  <small>{runner.hostname}{runner.platform ? ` · ${runner.platform}` : ""}</small>
                  <small className="runner-id" title={runner.id}>ID: {runner.id}</small>
                </span>
              </span>
              <span className="runner-capabilities">
                {runner.capabilities.length > 0
                  ? runner.capabilities.map((capability) => <span className="chip" key={capability}>{capability.toUpperCase()}</span>)
                  : <small className="runner-muted">—</small>}
              </span>
              <span className="runner-controls">
                <span className="runner-presence">
                  <StatusBadge label={tStatus(runner.status)} tone={statusTone(runner.status)} />
                  <small>{t("runners.lastSeen", { time: runner.last_seen_at ? new Date(runner.last_seen_at).toLocaleString(locale) : "—" })}</small>
                </span>
                <span className="runner-actions">
                  <button className="button button--small button--secondary" disabled={updateStatus.isPending} onClick={() => updateStatus.mutate({ id: runner.id, enabled: runner.status === "disabled" })} type="button">
                    {runner.status === "disabled" ? t("common.enable") : t("common.disable")}
                  </button>
                  <button className="button button--small button--secondary" disabled={rotate.isPending} onClick={() => { if (window.confirm(t("runners.rotateConfirm", { name: runner.name }))) rotate.mutate(runner.id); }} type="button">{t("runners.rotateToken")}</button>
                  <button className="button button--small button--danger" disabled={revoke.isPending} onClick={() => { if (window.confirm(t("runners.revokeConfirm", { name: runner.name }))) revoke.mutate(runner.id); }} type="button">{t("runners.revoke")}</button>
                </span>
              </span>
            </div>
          ))}
        </div>
        <Pagination page={page} pageSize={PAGE_SIZE} total={total ?? 0} onPageChange={setPage} disabled={runners.isFetching} />
        </>
      )}
      {updateStatus.isError || revoke.isError || rotate.isError ? <div className="inline-error">{t("runners.updateError")}</div> : null}
    </div>
  );
}
