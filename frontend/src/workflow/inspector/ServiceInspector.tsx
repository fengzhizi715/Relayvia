import type { WorkflowNode } from "../../api/client";
import { useTranslation } from "../../i18n";
import { useServiceActions, useServices } from "../registry/useRegistry";
import { useWorkflowBuilderStore } from "../store/workflowBuilderStore";
import { InputMappingEditor } from "../mapping/InputMappingEditor";
import { Field, NumberField, SectionTitle, SelectField } from "./fields";

export function ServiceInspector({ node }: { node: WorkflowNode }) {
  const { t } = useTranslation();
  const updateNode = useWorkflowBuilderStore((state) => state.updateNode);
  const readOnly = useWorkflowBuilderStore((state) => state.readOnly);
  const { services } = useServices();

  const serviceId = (node.config.service_id as string) ?? "";
  const { actions } = useServiceActions(serviceId || null);
  const actionId = (node.config.service_action_id as string) ?? "";
  const retry = (node.config.retry as { max_retries?: number } | undefined) ?? { max_retries: 0 };

  function setConfig(patch: Record<string, unknown>) {
    updateNode(node.id, { config: { ...node.config, ...patch } });
  }

  function onServiceChange(value: string) {
    setConfig({ service_id: value, service_action_id: "" });
  }

  return (
    <>
      <SectionTitle>{t("inspector.basicInfo")}</SectionTitle>
      <Field label={t("inspector.nodeName")}>
        <input className="input" value={node.name} disabled={readOnly} onChange={(event) => updateNode(node.id, { name: event.target.value })} />
      </Field>

      <SectionTitle>{t("inspector.service")}</SectionTitle>
      <Field label={t("inspector.service")} hint={t("inspector.serviceHint")}>
        <SelectField value={serviceId} onChange={onServiceChange} disabled={readOnly} placeholder={t("inspector.selectService")}>
          {services.map((service) => (
            <option key={service.id} value={service.id}>
              {service.name}
              {service.enabled ? "" : ` · ${t("common.disabled").toLowerCase()}`}
            </option>
          ))}
        </SelectField>
      </Field>
      <Field label={t("inspector.serviceAction")}>
        <SelectField
          value={actionId}
          onChange={(value) => setConfig({ service_action_id: value })}
          disabled={readOnly || !serviceId}
          placeholder={serviceId ? t("inspector.selectAction") : t("inspector.selectServiceFirst")}
        >
          {actions.map((action) => (
            <option key={action.id} value={action.id}>
              {action.name} · {action.method} {action.path}
              {action.enabled ? "" : ` · ${t("common.disabled").toLowerCase()}`}
            </option>
          ))}
        </SelectField>
      </Field>
      <div className="inspector-grid">
        <Field label={t("inspector.timeout")}>
          <NumberField value={(node.config.timeout_seconds as number) ?? 60} onChange={(timeout_seconds) => setConfig({ timeout_seconds: Number.isFinite(timeout_seconds) ? timeout_seconds : 60 })} disabled={readOnly} min={1} />
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
