import type { WorkflowNode } from "../../api/client";
import { useWorkflowBuilderStore } from "../store/workflowBuilderStore";
import { InputMappingEditor } from "../mapping/InputMappingEditor";
import { Field, NumberField, SectionTitle, TextField } from "./fields";

const TOOL_LABELS: Record<string, string> = {
  shell: "Shell",
  git: "Git",
  test_command: "Test Command",
};

export function ToolInspector({ node }: { node: WorkflowNode }) {
  const updateNode = useWorkflowBuilderStore((state) => state.updateNode);
  const readOnly = useWorkflowBuilderStore((state) => state.readOnly);

  function setConfig(patch: Record<string, unknown>) {
    updateNode(node.id, { config: { ...node.config, ...patch } });
  }

  return (
    <>
      <SectionTitle>Basic information</SectionTitle>
      <Field label="Node name">
        <input className="input" value={node.name} disabled={readOnly} onChange={(event) => updateNode(node.id, { name: event.target.value })} />
      </Field>

      <SectionTitle>{TOOL_LABELS[node.subtype] ?? "Tool"}</SectionTitle>
      <Field label="Command">
        <TextField
          value={(node.config.command as string) ?? ""}
          onChange={(command) => setConfig({ command })}
          disabled={readOnly}
          placeholder={node.subtype === "git" ? "git status" : "pytest"}
        />
      </Field>
      <Field label="Runner ID" hint="Required before a Tool node can run. Pin local commands to the Runner that owns the working directory.">
        <TextField
          value={(node.config.runner_id as string) ?? ""}
          onChange={(runner_id) => setConfig({ runner_id: runner_id || null })}
          disabled={readOnly}
          placeholder="Runner ID from the Runners page"
        />
      </Field>
      <Field label="Working directory" hint="Optional. Paths must remain inside the assigned Runner Root.">
        <TextField
          value={(node.config.working_directory as string) ?? ""}
          onChange={(working_directory) => setConfig({ working_directory: working_directory || null })}
          disabled={readOnly}
          placeholder="/path/to/repo"
        />
      </Field>
      <Field label="Timeout (seconds)">
        <NumberField value={(node.config.timeout_seconds as number) ?? 600} onChange={(timeout_seconds) => setConfig({ timeout_seconds: Number.isFinite(timeout_seconds) ? timeout_seconds : 600 })} disabled={readOnly} min={1} />
      </Field>

      <SectionTitle>Input mapping</SectionTitle>
      <InputMappingEditor mapping={node.input_mapping} onChange={(input_mapping) => updateNode(node.id, { input_mapping })} disabled={readOnly} />
    </>
  );
}
