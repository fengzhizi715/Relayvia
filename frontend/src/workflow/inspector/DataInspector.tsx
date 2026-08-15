import type { WorkflowNode } from "../../api/client";
import { useWorkflowBuilderStore } from "../store/workflowBuilderStore";
import { InputMappingEditor } from "../mapping/InputMappingEditor";
import { Field, JsonConfigField, SectionTitle } from "./fields";

export function DataInspector({ node }: { node: WorkflowNode }) {
  const updateNode = useWorkflowBuilderStore((state) => state.updateNode);
  const readOnly = useWorkflowBuilderStore((state) => state.readOnly);

  switch (node.subtype) {
    case "input":
      return (
        <>
          <SectionTitle>Workflow input</SectionTitle>
          <Field label="Node name">
            <input className="input" value={node.name} disabled={readOnly} onChange={(event) => updateNode(node.id, { name: event.target.value })} />
          </Field>
          <JsonConfigField
            label="Input schema"
            value={(node.config.schema as Record<string, unknown>) ?? {}}
            onChange={(schema) => updateNode(node.id, { config: { ...node.config, schema } })}
            rows={8}
            disabled={readOnly}
            hint="JSON Schema describing the Workflow input."
          />
        </>
      );
    case "transform":
      return (
        <>
          <SectionTitle>Transform</SectionTitle>
          <Field label="Node name">
            <input className="input" value={node.name} disabled={readOnly} onChange={(event) => updateNode(node.id, { name: event.target.value })} />
          </Field>
          <InputMappingEditor
            mapping={(node.config.mappings as Record<string, unknown>) ?? {}}
            onChange={(mappings) => updateNode(node.id, { config: { ...node.config, mappings } })}
            disabled={readOnly}
            hint="Safe mappings only: map / select / constant. No arbitrary code is executed."
          />
        </>
      );
    case "output":
      return (
        <>
          <SectionTitle>Workflow output</SectionTitle>
          <Field label="Node name">
            <input className="input" value={node.name} disabled={readOnly} onChange={(event) => updateNode(node.id, { name: event.target.value })} />
          </Field>
          <InputMappingEditor
            mapping={(node.config.output_mapping as Record<string, unknown>) ?? {}}
            onChange={(output_mapping) => updateNode(node.id, { config: { ...node.config, output_mapping } })}
            disabled={readOnly}
            hint='Example: { "result": "{{nodes.agent_a.output.result}}" }'
          />
        </>
      );
    default:
      return null;
  }
}
