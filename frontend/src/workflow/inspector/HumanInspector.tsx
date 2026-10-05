import type { WorkflowNode } from "../../api/client";
import { useTranslation } from "../../i18n";
import { useWorkflowBuilderStore } from "../store/workflowBuilderStore";
import { InputMappingEditor } from "../mapping/InputMappingEditor";
import { CheckboxField, Field, JsonConfigField, SectionTitle, TextAreaField, TextField } from "./fields";

export function HumanInspector({ node }: { node: WorkflowNode }) {
  const { t } = useTranslation();
  const updateNode = useWorkflowBuilderStore((state) => state.updateNode);
  const readOnly = useWorkflowBuilderStore((state) => state.readOnly);

  if (node.subtype === "approval") {
    return (
      <>
        <SectionTitle>{t("inspector.approval")}</SectionTitle>
        <Field label={t("inspector.nodeName")}>
          <input className="input" value={node.name} disabled={readOnly} onChange={(event) => updateNode(node.id, { name: event.target.value })} />
        </Field>
        <Field label={t("inspector.title")}>
          <TextField value={(node.config.title as string) ?? ""} onChange={(title) => updateNode(node.id, { config: { ...node.config, title } })} disabled={readOnly} placeholder={t("inspector.titlePlaceholder")} />
        </Field>
        <Field label={t("inspector.description")}>
          <TextAreaField value={(node.config.description as string) ?? ""} onChange={(description) => updateNode(node.id, { config: { ...node.config, description } })} disabled={readOnly} rows={3} placeholder={t("inspector.descriptionPlaceholder")} />
        </Field>
        <CheckboxField
          label={t("inspector.allowReject")}
          checked={Boolean(node.config.allow_reject)}
          onChange={(allow_reject) => updateNode(node.id, { config: { ...node.config, allow_reject } })}
          disabled={readOnly}
        />
        <SectionTitle>{t("inspector.inputMapping")}</SectionTitle>
        <InputMappingEditor mapping={node.input_mapping} onChange={(input_mapping) => updateNode(node.id, { input_mapping })} disabled={readOnly} />
      </>
    );
  }

  return (
    <>
      <SectionTitle>{t("inspector.humanInput")}</SectionTitle>
      <Field label={t("inspector.nodeName")}>
        <input className="input" value={node.name} disabled={readOnly} onChange={(event) => updateNode(node.id, { name: event.target.value })} />
      </Field>
      <JsonConfigField
        label={t("inspector.formSchema")}
        value={(node.config.form_schema as Record<string, unknown>) ?? {}}
        onChange={(form_schema) => updateNode(node.id, { config: { ...node.config, form_schema } })}
        rows={6}
        disabled={readOnly}
        hint={t("inspector.formSchemaHint")}
      />
      <SectionTitle>{t("inspector.inputMapping")}</SectionTitle>
      <InputMappingEditor mapping={node.input_mapping} onChange={(input_mapping) => updateNode(node.id, { input_mapping })} disabled={readOnly} />
    </>
  );
}
