import { StatusBadge } from "../../components/StatusBadge";
import { useTranslation } from "../../i18n";
import { NODE_RUN_TONES, WORKFLOW_RUN_TONES } from "./status";

export function WorkflowRunStatusBadge({ status }: { status: string }) {
  const { tStatus } = useTranslation();
  return <StatusBadge label={tStatus(status)} tone={WORKFLOW_RUN_TONES[status as keyof typeof WORKFLOW_RUN_TONES] ?? "neutral"} />;
}

export function NodeRunStatusBadge({ status }: { status: string }) {
  const { tStatus } = useTranslation();
  return <StatusBadge label={tStatus(status)} tone={NODE_RUN_TONES[status as keyof typeof NODE_RUN_TONES] ?? "neutral"} />;
}
