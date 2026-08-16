import { StatusBadge } from "../../components/StatusBadge";
import { NODE_RUN_TONES, WORKFLOW_RUN_TONES } from "./status";

export function WorkflowRunStatusBadge({ status }: { status: string }) {
  return <StatusBadge label={status.toUpperCase()} tone={WORKFLOW_RUN_TONES[status as keyof typeof WORKFLOW_RUN_TONES] ?? "neutral"} />;
}

export function NodeRunStatusBadge({ status }: { status: string }) {
  return <StatusBadge label={status.toUpperCase()} tone={NODE_RUN_TONES[status as keyof typeof NODE_RUN_TONES] ?? "neutral"} />;
}
