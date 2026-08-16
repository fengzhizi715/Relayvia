import { useReactFlow } from "@xyflow/react";

import { StatusBadge } from "../../components/StatusBadge";
import { useWorkflowBuilderStore } from "../store/workflowBuilderStore";

type WorkflowToolbarProps = {
  onBack: () => void;
  onSave: () => void;
  onCreateVersion: () => void;
  onValidate: () => void;
  canSave: boolean;
  blockedReasons: string[];
};

export function WorkflowToolbar({ onBack, onSave, onCreateVersion, onValidate, canSave, blockedReasons }: WorkflowToolbarProps) {
  const workflowName = useWorkflowBuilderStore((state) => state.workflowName);
  const readOnly = useWorkflowBuilderStore((state) => state.readOnly);
  const mode = useWorkflowBuilderStore((state) => state.mode);
  const isDirty = useWorkflowBuilderStore((state) => state.isDirty);
  const isSaving = useWorkflowBuilderStore((state) => state.isSaving);
  const saveError = useWorkflowBuilderStore((state) => state.saveError);
  const lastSavedAt = useWorkflowBuilderStore((state) => state.lastSavedAt);
  const validation = useWorkflowBuilderStore((state) => state.validation);
  const validationStale = useWorkflowBuilderStore((state) => state.validationStale);
  const isValidating = useWorkflowBuilderStore((state) => state.isValidating);
  const { fitView } = useReactFlow();

  let tone: "success" | "warning" | "danger" | "neutral" = "success";
  let label: string;
  if (readOnly) {
    tone = "neutral";
    label = "READ ONLY";
  } else if (isSaving) {
    tone = "neutral";
    label = "Saving...";
  } else if (saveError) {
    tone = "danger";
    label = "Save failed";
  } else if (isDirty) {
    tone = "warning";
    label = "Unsaved changes";
  } else {
    label = lastSavedAt ? `Saved ${new Date(lastSavedAt).toLocaleTimeString()}` : "Saved";
  }

  let validationLabel: string | null = null;
  let validationTone: "success" | "warning" | "danger" | "neutral" = "neutral";
  if (isValidating) {
    validationLabel = "Validating...";
  } else if (validation) {
    const errors = validation.issues.filter((issue) => issue.severity === "error").length;
    const warnings = validation.issues.filter((issue) => issue.severity === "warning").length;
    if (errors > 0) {
      validationLabel = `${errors} error${errors === 1 ? "" : "s"}`;
      validationTone = "danger";
    } else if (warnings > 0) {
      validationLabel = `${warnings} warning${warnings === 1 ? "" : "s"}`;
      validationTone = "warning";
    } else {
      validationLabel = "Valid";
      validationTone = "success";
    }
  }

  const versionSuffix = readOnly && mode.kind === "version" ? ` · v${mode.version}` : "";

  return (
    <header className="builder-toolbar">
      <div className="builder-toolbar-title">
        <button className="text-button builder-back" type="button" onClick={onBack}>
          ← Back to Workflows
        </button>
        <div>
          <p className="eyebrow">{readOnly ? "WORKFLOW · VERSION" : "WORKFLOW DRAFT"}</p>
          <h3>
            {workflowName}
            <span className="builder-toolbar-version">{versionSuffix}</span>
          </h3>
        </div>
      </div>
      <div className="builder-toolbar-actions">
        <StatusBadge label={label} tone={tone} />
        {!readOnly && (
          <>
            <button className="button button--small" type="button" onClick={() => fitView()}>
              Fit view
            </button>
            <button className="button button--small" type="button" onClick={onValidate} disabled={isValidating} title={validationStale && validation ? "Graph changed since the last validation" : undefined}>
              Validate
            </button>
            {validationLabel ? <StatusBadge label={validationLabel} tone={validationTone} /> : null}
            <button
              className="button button--small"
              type="button"
              onClick={onSave}
              disabled={!isDirty || isSaving || !canSave}
              title={blockedReasons.join("\n")}
            >
              Save Draft
            </button>
            <button
              className="button button--small button--primary"
              type="button"
              onClick={onCreateVersion}
              disabled={isSaving || !canSave}
              title={blockedReasons.join("\n")}
            >
              Create Version
            </button>
          </>
        )}
        {saveError && <span className="builder-save-error">{saveError}</span>}
      </div>
    </header>
  );
}
