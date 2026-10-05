import { useState } from "react";
import { useMutation } from "@tanstack/react-query";

import { ApiError, createAction, type HTTPMethod, type ServiceAction, type ServiceActionPayload, updateAction } from "../../api/client";
import { JsonEditor } from "../../components/JsonEditor";
import { Modal } from "../../components/Modal";
import { useTranslation, type Translator } from "../../i18n";

type ActionFormProps = {
  serviceId: string;
  action?: ServiceAction;
  onClose: () => void;
  onSaved: () => void;
};

function objectJson(value: unknown) { return JSON.stringify(value ?? {}, null, 2); }
function parseObject(value: string, label: string, t: Translator): Record<string, unknown> {
  try { const parsed = JSON.parse(value); if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) throw new Error(); return parsed as Record<string, unknown>; } catch { throw new Error(t("parse.mustBeJsonObject", { label })); }
}
function parseHeaders(value: string, t: Translator): Record<string, string> {
  const parsed = parseObject(value, t("actionForm.headers"), t);
  if (Object.values(parsed).some((item) => typeof item !== "string")) throw new Error(t("actionForm.headerValuesStrings"));
  return parsed as Record<string, string>;
}

export function ActionForm({ serviceId, action, onClose, onSaved }: ActionFormProps) {
  const { t } = useTranslation();
  const [name, setName] = useState(action?.name ?? "");
  const [description, setDescription] = useState(action?.description ?? "");
  const [method, setMethod] = useState<HTTPMethod>(action?.method ?? "POST");
  const [path, setPath] = useState(action?.path ?? "/");
  const [headers, setHeaders] = useState(objectJson(action?.headers));
  const [querySchema, setQuerySchema] = useState(objectJson(action?.query_schema));
  const [pathSchema, setPathSchema] = useState(objectJson(action?.path_schema));
  const [inputSchema, setInputSchema] = useState(objectJson(action?.input_schema));
  const [outputSchema, setOutputSchema] = useState(objectJson(action?.output_schema));
  const [timeout, setTimeout] = useState(String(action?.timeout_seconds ?? 30));
  const [maxRetries, setMaxRetries] = useState(String(action?.retry_policy.max_retries ?? 0));
  const [backoff, setBackoff] = useState(String(action?.retry_policy.backoff_seconds ?? 0));
  const [retryStatuses, setRetryStatuses] = useState((action?.retry_policy.retry_on_status ?? [429, 500, 502, 503, 504]).join(", "));
  const [metadata, setMetadata] = useState(objectJson(action?.metadata));
  const [error, setError] = useState<string | null>(null);
  const mutation = useMutation({
    mutationFn: (payload: ServiceActionPayload) => action ? updateAction(serviceId, action.id, payload) : createAction(serviceId, payload),
    onSuccess: onSaved,
    onError: (value) => setError(value instanceof ApiError ? `${value.message} (${value.code})` : (value as Error).message),
  });

  function submit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      const statuses = retryStatuses.split(",").map((value) => Number(value.trim())).filter((value) => Number.isInteger(value));
      mutation.mutate({ name, description, method, path, headers: parseHeaders(headers, t), query_schema: parseObject(querySchema, t("actionForm.querySchema"), t), path_schema: parseObject(pathSchema, t("actionForm.pathSchema"), t), input_schema: parseObject(inputSchema, t("actionForm.bodySchema"), t), output_schema: parseObject(outputSchema, t("actionForm.outputSchema"), t), timeout_seconds: Number(timeout), retry_policy: { max_retries: Number(maxRetries), backoff_seconds: Number(backoff), retry_on_status: statuses }, enabled: action?.enabled ?? true, metadata: parseObject(metadata, t("agentForm.metadata"), t) });
    } catch (value) { setError((value as Error).message); }
  }

  return <Modal title={action ? t("actionForm.editTitle") : t("actionForm.addTitle")} eyebrow={t("actionForm.eyebrow")} onClose={onClose}>
    <form className="form-stack" onSubmit={submit}>
      <div className="form-section"><p className="form-section-title">{t("actionForm.request")}</p><div className="form-grid"><label className="field"><span>{t("agentForm.name")}</span><input className="input" required value={name} onChange={(event) => setName(event.target.value)} placeholder={t("actionForm.namePlaceholder")} /></label><label className="field"><span>{t("actionForm.method")}</span><select className="input" value={method} onChange={(event) => setMethod(event.target.value as HTTPMethod)}>{["GET", "POST", "PUT", "PATCH", "DELETE"].map((item) => <option key={item}>{item}</option>)}</select></label></div><label className="field"><span>{t("actionForm.path")}</span><input className="input" required value={path} onChange={(event) => setPath(event.target.value)} placeholder={t("actionForm.pathPlaceholder")} /></label><label className="field"><span>{t("agentForm.description")}</span><textarea className="input" rows={2} value={description} onChange={(event) => setDescription(event.target.value)} /></label><JsonEditor label={t("actionForm.headers")} value={headers} onChange={setHeaders} rows={3} /></div>
      <div className="form-section"><p className="form-section-title">{t("actionForm.parameterContracts")}</p><JsonEditor label={t("actionForm.pathSchema")} value={pathSchema} onChange={setPathSchema} rows={5} /><JsonEditor label={t("actionForm.querySchema")} value={querySchema} onChange={setQuerySchema} rows={5} /><JsonEditor label={t("actionForm.bodySchema")} value={inputSchema} onChange={setInputSchema} rows={6} /><JsonEditor label={t("actionForm.outputSchema")} value={outputSchema} onChange={setOutputSchema} rows={6} /></div>
      <div className="form-section"><p className="form-section-title">{t("actionForm.executionMetadata")}</p><div className="form-grid"><label className="field"><span>{t("actionForm.timeout")}</span><input className="input" min={1} type="number" value={timeout} onChange={(event) => setTimeout(event.target.value)} /></label><label className="field"><span>{t("actionForm.maxRetries")}</span><input className="input" min={0} type="number" value={maxRetries} onChange={(event) => setMaxRetries(event.target.value)} /></label><label className="field"><span>{t("actionForm.backoff")}</span><input className="input" min={0} type="number" value={backoff} onChange={(event) => setBackoff(event.target.value)} /></label><label className="field field--wide"><span>{t("actionForm.retryOn")}</span><input className="input" value={retryStatuses} onChange={(event) => setRetryStatuses(event.target.value)} placeholder="429, 500, 502, 503, 504" /></label></div><JsonEditor label={t("agentForm.metadata")} value={metadata} onChange={setMetadata} rows={4} /></div>
      {error && <div className="inline-error">{error}</div>}
      <div className="modal-actions"><button className="button" type="button" onClick={onClose}>{t("common.cancel")}</button><button className="button button--primary" disabled={mutation.isPending} type="submit">{mutation.isPending ? t("common.saving") : action ? t("common.saveChanges") : t("actionForm.addAction")}</button></div>
    </form>
  </Modal>;
}
