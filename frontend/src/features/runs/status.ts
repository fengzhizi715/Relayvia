import type { NodeRunStatus, WorkflowRunStatus } from "../../api/client";

export const WORKFLOW_RUN_TONES: Record<WorkflowRunStatus, "success" | "warning" | "danger" | "neutral"> = {
  created: "neutral",
  running: "warning",
  waiting: "neutral",
  paused: "warning",
  completed: "success",
  failed: "danger",
  cancelled: "danger",
};

export const NODE_RUN_TONES: Record<NodeRunStatus, "success" | "warning" | "danger" | "neutral"> = {
  pending: "neutral",
  queued: "neutral",
  running: "warning",
  waiting: "neutral",
  retrying: "warning",
  completed: "success",
  failed: "danger",
  skipped: "neutral",
  cancelled: "danger",
};

export type RunTone = "success" | "warning" | "danger" | "neutral";
