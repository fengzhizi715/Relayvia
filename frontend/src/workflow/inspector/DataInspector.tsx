import type { WorkflowNode } from "../../api/client";
import { useTranslation } from "../../i18n";
import { useWorkflowBuilderStore } from "../store/workflowBuilderStore";
import { InputMappingEditor } from "../mapping/InputMappingEditor";
import { Field, JsonConfigField, SectionTitle } from "./fields";

export function DataInspector({ node }: { node: WorkflowNode }) {
  const { t } = useTranslation();
  const updateNode = useWorkflowBuilderStore((state) => state.updateNode);
  const readOnly = useWorkflowBuilderStore((state) => state.readOnly);

  switch (node.subtype) {
    case "input":
      return (
        <>
          <SectionTitle>{t("inspector.workflowInput")}</SectionTitle>
          <Field label={t("inspector.nodeName")}>
            <input className="input" value={node.name} disabled={readOnly} onChange={(event) => updateNode(node.id, { name: event.target.value })} />
          </Field>
          <JsonConfigField
            label={t("inspector.inputSchema")}
            value={(node.config.schema as Record<string, unknown>) ?? {}}
            onChange={(schema) => updateNode(node.id, { config: { ...node.config, schema } })}
            rows={8}
            disabled={readOnly}
            hint={t("inspector.inputSchemaHint")}
          />
        </>
      );
    case "transform":
      return (
        <>
          <SectionTitle>{t("inspector.transform")}</SectionTitle>
          <Field label={t("inspector.nodeName")}>
            <input className="input" value={node.name} disabled={readOnly} onChange={(event) => updateNode(node.id, { name: event.target.value })} />
          </Field>
          <InputMappingEditor
            mapping={(node.config.mappings as Record<string, unknown>) ?? {}}
            onChange={(mappings) => updateNode(node.id, { config: { ...node.config, mappings } })}
            disabled={readOnly}
            hint={t("inspector.transformHint")}
          />
        </>
      );
    case "output":
      return (
        <>
          <SectionTitle>{t("inspector.workflowOutput")}</SectionTitle>
          <Field label={t("inspector.nodeName")}>
            <input className="input" value={node.name} disabled={readOnly} onChange={(event) => updateNode(node.id, { name: event.target.value })} />
          </Field>
          <InputMappingEditor
            mapping={(node.config.output_mapping as Record<string, unknown>) ?? {}}
            onChange={(output_mapping) => updateNode(node.id, { config: { ...node.config, output_mapping } })}
            disabled={readOnly}
            hint={t("inspector.outputMappingHint")}
          />
        </>
      );
    default:
      return null;
  }
}
