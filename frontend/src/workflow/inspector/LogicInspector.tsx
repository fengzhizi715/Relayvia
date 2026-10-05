import type { WorkflowNode } from "../../api/client";
import { useTranslation } from "../../i18n";
import { useWorkflowBuilderStore } from "../store/workflowBuilderStore";
import { ContextReferenceInput } from "../mapping/ContextReferenceInput";
import { Field, NumberField, SectionTitle, SelectField } from "./fields";

export const CONDITION_OPERATORS = ["==", "!=", ">", ">=", "<", "<=", "contains", "not_contains", "is_empty", "is_not_empty"];

export function LogicInspector({ node }: { node: WorkflowNode }) {
  const { t } = useTranslation();
  const updateNode = useWorkflowBuilderStore((state) => state.updateNode);
  const readOnly = useWorkflowBuilderStore((state) => state.readOnly);

  function setConfig(patch: Record<string, unknown>) {
    updateNode(node.id, { config: { ...node.config, ...patch } });
  }

  switch (node.subtype) {
    case "condition": {
      const expression = (node.config.expression as Record<string, unknown>) ?? {};
      return (
        <>
          <SectionTitle>{t("inspector.condition")}</SectionTitle>
          <Field label={t("inspector.leftValue")} hint={t("inspector.leftValueHint")}>
            <ContextReferenceInput value={String(expression.left ?? "")} onChange={(left) => setConfig({ expression: { ...expression, left } })} disabled={readOnly} />
          </Field>
          <Field label={t("inspector.operator")}>
            <SelectField value={String(expression.operator ?? "")} onChange={(operator) => setConfig({ expression: { ...expression, operator } })} disabled={readOnly}>
              {CONDITION_OPERATORS.map((operator) => (
                <option key={operator} value={operator}>
                  {operator}
                </option>
              ))}
            </SelectField>
          </Field>
          <Field label={t("inspector.rightValue")}>
            <ContextReferenceInput value={String(expression.right ?? "")} onChange={(right) => setConfig({ expression: { ...expression, right } })} disabled={readOnly} placeholder="0.8" />
          </Field>
          <p className="field-hint">{t("inspector.branchHint")}</p>
        </>
      );
    }
    case "wait":
      return (
        <>
          <SectionTitle>{t("inspector.wait")}</SectionTitle>
          <Field label={t("inspector.mode")}>
            <SelectField value={(node.config.mode as string) ?? "duration"} onChange={(mode) => setConfig({ mode })} disabled={readOnly || true}>
              <option value="duration">{t("inspector.durationMode")}</option>
            </SelectField>
          </Field>
          <Field label={t("inspector.durationSeconds")}>
            <NumberField value={(node.config.duration_seconds as number) ?? 60} onChange={(duration_seconds) => setConfig({ duration_seconds: Number.isFinite(duration_seconds) ? duration_seconds : 60 })} disabled={readOnly} min={1} />
          </Field>
        </>
      );
    case "merge":
      return (
        <>
          <SectionTitle>{t("inspector.merge")}</SectionTitle>
          <Field label={t("inspector.strategy")}>
            <SelectField value={(node.config.strategy as string) ?? "all"} onChange={(strategy) => setConfig({ strategy })} disabled={readOnly}>
              <option value="all">{t("inspector.allStrategy")}</option>
            </SelectField>
          </Field>
        </>
      );
    case "parallel":
      return (
        <>
          <SectionTitle>{t("inspector.parallel")}</SectionTitle>
          <p className="field-hint">{t("inspector.parallelHint")}</p>
        </>
      );
    case "router":
      return (
        <>
          <SectionTitle>{t("inspector.router")}</SectionTitle>
          <p className="field-hint">{t("inspector.routerHint")}</p>
        </>
      );
    default:
      return null;
  }
}
