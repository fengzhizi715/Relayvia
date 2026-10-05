import type { WorkflowNode } from "../../api/client";
import { useTranslation } from "../../i18n";
import { useAgents } from "../registry/useRegistry";
import { useWorkflowBuilderStore } from "../store/workflowBuilderStore";
import { InputMappingEditor } from "../mapping/InputMappingEditor";
import { Field, NumberField, SectionTitle, SelectField, TextAreaField, TextField } from "./fields";

export function AgentInspector({ node }: { node: WorkflowNode }) {
  const { t } = useTranslation();
  const updateNode = useWorkflowBuilderStore((state) => state.updateNode);
  const readOnly = useWorkflowBuilderStore((state) => state.readOnly);
  const { agents } = useAgents();

  const agentId = (node.config.agent_id as string) ?? "";
  const retry = (node.config.retry as { max_retries?: number } | undefined) ?? { max_retries: 0 };

  function setConfig(patch: Record<string, unknown>) {
    updateNode(node.id, { config: { ...node.config, ...patch } });
  }

  return (
    <>
      <SectionTitle>{t("inspector.basicInfo")}</SectionTitle>
      <Field label={t("inspector.nodeName")}>
        <TextField value={node.name} onChange={(name) => updateNode(node.id, { name })} disabled={readOnly} />
      </Field>

      <SectionTitle>{t("inspector.agent")}</SectionTitle>
      <Field label={t("inspector.agent")} hint={t("inspector.agentHint")}>
        <SelectField value={agentId} onChange={(value) => setConfig({ agent_id: value })} disabled={readOnly} placeholder={t("inspector.selectAgent")}>
          {agents.map((agent) => (
            <option key={agent.id} value={agent.id}>
              {agent.name} · {agent.connector_type.toUpperCase()}
              {agent.enabled ? "" : ` · ${t("common.disabled").toLowerCase()}`}
            </option>
          ))}
        </SelectField>
      </Field>
      <Field label={t("inspector.role")}>
        <TextField value={(node.config.role as string) ?? ""} onChange={(role) => setConfig({ role })} disabled={readOnly} placeholder={t("inspector.rolePlaceholder")} />
      </Field>
      <Field label={t("inspector.taskTemplate")} hint={t("inspector.taskTemplateHint")}>
        <TextAreaField value={(node.config.task_template as string) ?? ""} onChange={(task_template) => setConfig({ task_template })} disabled={readOnly} rows={3} placeholder={t("inspector.taskTemplatePlaceholder")} />
      </Field>
      <div className="inspector-grid">
        <Field label={t("inspector.timeout")}>
          <NumberField value={(node.config.timeout_seconds as number) ?? 600} onChange={(timeout_seconds) => setConfig({ timeout_seconds: Number.isFinite(timeout_seconds) ? timeout_seconds : 600 })} disabled={readOnly} min={1} />
        </Field>
        <Field label={t("inspector.maxRetries")}>
          <NumberField value={retry.max_retries ?? 0} onChange={(max_retries) => setConfig({ retry: { max_retries: Number.isFinite(max_retries) ? max_retries : 0 } })} disabled={readOnly} min={0} max={10} />
        </Field>
      </div>

      <SectionTitle>{t("inspector.inputMapping")}</SectionTitle>
      <InputMappingEditor mapping={node.input_mapping} onChange={(input_mapping) => updateNode(node.id, { input_mapping })} disabled={readOnly} />
    </>
  );
}
