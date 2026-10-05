import type { WorkflowNode } from "../../api/client";
import { useTranslation, type TranslationKey } from "../../i18n";
import { useWorkflowBuilderStore } from "../store/workflowBuilderStore";
import { InputMappingEditor } from "../mapping/InputMappingEditor";
import { Field, NumberField, SectionTitle, TextField } from "./fields";

const TOOL_LABEL_KEYS: Record<string, TranslationKey> = {
  shell: "palette.shell.label",
  git: "palette.git.label",
  test_command: "palette.test.label",
};

export function ToolInspector({ node }: { node: WorkflowNode }) {
  const { t } = useTranslation();
  const updateNode = useWorkflowBuilderStore((state) => state.updateNode);
  const readOnly = useWorkflowBuilderStore((state) => state.readOnly);

  function setConfig(patch: Record<string, unknown>) {
    updateNode(node.id, { config: { ...node.config, ...patch } });
  }

  const toolLabelKey = TOOL_LABEL_KEYS[node.subtype];
  const toolLabel = toolLabelKey ? t(toolLabelKey) : t("palette.category.tool");

  return (
    <>
      <SectionTitle>{t("inspector.basicInfo")}</SectionTitle>
      <Field label={t("inspector.nodeName")}>
        <input className="input" value={node.name} disabled={readOnly} onChange={(event) => updateNode(node.id, { name: event.target.value })} />
      </Field>

      <SectionTitle>{toolLabel}</SectionTitle>
      <Field label={t("inspector.command")}>
        <TextField
          value={(node.config.command as string) ?? ""}
          onChange={(command) => setConfig({ command })}
          disabled={readOnly}
          placeholder={node.subtype === "git" ? "git status" : "pytest"}
        />
      </Field>
      <Field label={t("inspector.runnerId")} hint={t("inspector.runnerIdHint")}>
        <TextField
          value={(node.config.runner_id as string) ?? ""}
          onChange={(runner_id) => setConfig({ runner_id: runner_id || null })}
          disabled={readOnly}
          placeholder={t("inspector.runnerIdPlaceholder")}
        />
      </Field>
      <Field label={t("inspector.workingDirectory")} hint={t("inspector.workingDirectoryHint")}>
        <TextField
          value={(node.config.working_directory as string) ?? ""}
          onChange={(working_directory) => setConfig({ working_directory: working_directory || null })}
          disabled={readOnly}
          placeholder="/path/to/repo"
        />
      </Field>
      <Field label={t("inspector.timeout")}>
        <NumberField value={(node.config.timeout_seconds as number) ?? 600} onChange={(timeout_seconds) => setConfig({ timeout_seconds: Number.isFinite(timeout_seconds) ? timeout_seconds : 600 })} disabled={readOnly} min={1} />
      </Field>

      <SectionTitle>{t("inspector.inputMapping")}</SectionTitle>
      <InputMappingEditor mapping={node.input_mapping} onChange={(input_mapping) => updateNode(node.id, { input_mapping })} disabled={readOnly} />
    </>
  );
}
