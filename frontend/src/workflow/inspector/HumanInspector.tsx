import type { WorkflowNode } from "../../api/client";
import { useWorkflowBuilderStore } from "../store/workflowBuilderStore";
import { InputMappingEditor } from "../mapping/InputMappingEditor";
import { CheckboxField, Field, JsonConfigField, SectionTitle, TextAreaField, TextField } from "./fields";

export function HumanInspector({ node }: { node: WorkflowNode }) {
  const updateNode = useWorkflowBuilderStore((state) => state.updateNode);
  const readOnly = useWorkflowBuilderStore((state) => state.readOnly);

  if (node.subtype === "approval") {
    return (
      <>
        <SectionTitle>Approval</SectionTitle>
        <Field label="Node name">
          <input className="input" value={node.name} disabled={readOnly} onChange={(event) => updateNode(node.id, { name: event.target.value })} />
        </Field>
        <Field label="Title">
          <TextField value={(node.config.title as string) ?? ""} onChange={(title) => updateNode(node.id, { config: { ...node.config, title } })} disabled={readOnly} placeholder="Approve training?" />
        </Field>
        <Field label="Description">
          <TextAreaField value={(node.config.description as string) ?? ""} onChange={(description) => updateNode(node.id, { config: { ...node.config, description } })} disabled={readOnly} rows={3} placeholder="Review the hard samples before training." />
        </Field>
        <CheckboxField
          label="Allow reject"
          checked={Boolean(node.config.allow_reject)}
          onChange={(allow_reject) => updateNode(node.id, { config: { ...node.config, allow_reject } })}
          disabled={readOnly}
        />
        <SectionTitle>Input mapping</SectionTitle>
        <InputMappingEditor mapping={node.input_mapping} onChange={(input_mapping) => updateNode(node.id, { input_mapping })} disabled={readOnly} />
      </>
    );
  }

  return (
    <>
      <SectionTitle>Human Input</SectionTitle>
      <Field label="Node name">
        <input className="input" value={node.name} disabled={readOnly} onChange={(event) => updateNode(node.id, { name: event.target.value })} />
      </Field>
      <JsonConfigField
        label="Form schema"
        value={(node.config.form_schema as Record<string, unknown>) ?? {}}
        onChange={(form_schema) => updateNode(node.id, { config: { ...node.config, form_schema } })}
        rows={6}
        disabled={readOnly}
        hint="JSON Schema describing the fields collected from the human."
      />
      <SectionTitle>Input mapping</SectionTitle>
      <InputMappingEditor mapping={node.input_mapping} onChange={(input_mapping) => updateNode(node.id, { input_mapping })} disabled={readOnly} />
    </>
  );
}
