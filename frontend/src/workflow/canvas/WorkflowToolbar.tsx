import { useReactFlow } from "@xyflow/react";

import { StatusBadge } from "../../components/StatusBadge";
import { useTranslation } from "../../i18n";
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
  const { t, locale } = useTranslation();
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
    label = t("toolbar.readOnly");
  } else if (isSaving) {
    tone = "neutral";
    label = t("common.saving");
  } else if (saveError) {
    tone = "danger";
    label = t("toolbar.saveFailed");
  } else if (isDirty) {
    tone = "warning";
    label = t("toolbar.unsavedChanges");
  } else {
    label = lastSavedAt ? t("toolbar.savedAt", { time: new Date(lastSavedAt).toLocaleTimeString(locale) }) : t("toolbar.saved");
  }

  let validationLabel: string | null = null;
  let validationTone: "success" | "warning" | "danger" | "neutral" = "neutral";
  if (isValidating) {
    validationLabel = t("toolbar.validating");
  } else if (validation) {
    const errors = validation.issues.filter((issue) => issue.severity === "error").length;
    const warnings = validation.issues.filter((issue) => issue.severity === "warning").length;
    if (errors > 0) {
      validationLabel = t(errors === 1 ? "toolbar.errorOne" : "toolbar.errorMany", { count: errors });
      validationTone = "danger";
    } else if (warnings > 0) {
      validationLabel = t(warnings === 1 ? "toolbar.warningOne" : "toolbar.warningMany", { count: warnings });
      validationTone = "warning";
    } else {
      validationLabel = t("toolbar.valid");
      validationTone = "success";
    }
  }

  const versionSuffix = readOnly && mode.kind === "version" ? ` · v${mode.version}` : "";

  return (
    <header className="builder-toolbar">
      <div className="builder-toolbar-title">
        <button className="text-button builder-back" type="button" onClick={onBack}>
          {t("toolbar.back")}
        </button>
        <div>
          <p className="eyebrow">{readOnly ? t("toolbar.workflowVersion") : t("toolbar.workflowDraft")}</p>
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
              {t("toolbar.fitView")}
            </button>
            <button className="button button--small" type="button" onClick={onValidate} disabled={isValidating} title={validationStale && validation ? t("toolbar.staleHint") : undefined}>
              {t("toolbar.validate")}
            </button>
            {validationLabel ? <StatusBadge label={validationLabel} tone={validationTone} /> : null}
            <button
              className="button button--small"
              type="button"
              onClick={onSave}
              disabled={!isDirty || isSaving || !canSave}
              title={blockedReasons.join("\n")}
            >
              {t("workflows.saveDraft")}
            </button>
            <button
              className="button button--small button--primary"
              type="button"
              onClick={onCreateVersion}
              disabled={isSaving || !canSave}
              title={blockedReasons.join("\n")}
            >
              {t("workflows.createVersion")}
            </button>
          </>
        )}
        {saveError && <span className="builder-save-error">{saveError}</span>}
      </div>
    </header>
  );
}
