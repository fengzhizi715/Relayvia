import { useState } from "react";
import { useMutation } from "@tanstack/react-query";

import { ApiError, createAction, type HTTPMethod, type ServiceAction, type ServiceActionPayload, updateAction } from "../../api/client";
import { JsonEditor } from "../../components/JsonEditor";
import { Modal } from "../../components/Modal";

type ActionFormProps = {
  serviceId: string;
  action?: ServiceAction;
  onClose: () => void;
  onSaved: () => void;
};

function objectJson(value: unknown) { return JSON.stringify(value ?? {}, null, 2); }
function parseObject(value: string, label: string): Record<string, unknown> {
  try { const parsed = JSON.parse(value); if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) throw new Error(); return parsed as Record<string, unknown>; } catch { throw new Error(`${label} must be a JSON object.`); }
}
function parseHeaders(value: string): Record<string, string> {
  const parsed = parseObject(value, "Headers");
  if (Object.values(parsed).some((item) => typeof item !== "string")) throw new Error("Header values must all be strings.");
  return parsed as Record<string, string>;
}

export function ActionForm({ serviceId, action, onClose, onSaved }: ActionFormProps) {
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
      mutation.mutate({ name, description, method, path, headers: parseHeaders(headers), query_schema: parseObject(querySchema, "Query schema"), path_schema: parseObject(pathSchema, "Path schema"), input_schema: parseObject(inputSchema, "Input schema"), output_schema: parseObject(outputSchema, "Output schema"), timeout_seconds: Number(timeout), retry_policy: { max_retries: Number(maxRetries), backoff_seconds: Number(backoff), retry_on_status: statuses }, enabled: action?.enabled ?? true, metadata: parseObject(metadata, "Metadata") });
    } catch (value) { setError((value as Error).message); }
  }

  return <Modal title={action ? "Edit Service Action" : "Add Service Action"} eyebrow="SERVICE ACTION" onClose={onClose}>
    <form className="form-stack" onSubmit={submit}>
      <div className="form-section"><p className="form-section-title">Request</p><div className="form-grid"><label className="field"><span>Name</span><input className="input" required value={name} onChange={(event) => setName(event.target.value)} placeholder="Start Training" /></label><label className="field"><span>Method</span><select className="input" value={method} onChange={(event) => setMethod(event.target.value as HTTPMethod)}>{["GET", "POST", "PUT", "PATCH", "DELETE"].map((item) => <option key={item}>{item}</option>)}</select></label></div><label className="field"><span>Path</span><input className="input" required value={path} onChange={(event) => setPath(event.target.value)} placeholder="/training/jobs" /></label><label className="field"><span>Description</span><textarea className="input" rows={2} value={description} onChange={(event) => setDescription(event.target.value)} /></label><JsonEditor label="Headers" value={headers} onChange={setHeaders} rows={3} /></div>
      <div className="form-section"><p className="form-section-title">Parameter contracts</p><JsonEditor label="Path parameters schema" value={pathSchema} onChange={setPathSchema} rows={5} /><JsonEditor label="Query parameters schema" value={querySchema} onChange={setQuerySchema} rows={5} /><JsonEditor label="Body input schema" value={inputSchema} onChange={setInputSchema} rows={6} /><JsonEditor label="Output schema" value={outputSchema} onChange={setOutputSchema} rows={6} /></div>
      <div className="form-section"><p className="form-section-title">Execution metadata</p><div className="form-grid"><label className="field"><span>Timeout (seconds)</span><input className="input" min={1} type="number" value={timeout} onChange={(event) => setTimeout(event.target.value)} /></label><label className="field"><span>Max retries</span><input className="input" min={0} type="number" value={maxRetries} onChange={(event) => setMaxRetries(event.target.value)} /></label><label className="field"><span>Backoff (seconds)</span><input className="input" min={0} type="number" value={backoff} onChange={(event) => setBackoff(event.target.value)} /></label><label className="field field--wide"><span>Retry on HTTP status</span><input className="input" value={retryStatuses} onChange={(event) => setRetryStatuses(event.target.value)} placeholder="429, 500, 502, 503, 504" /></label></div><JsonEditor label="Metadata" value={metadata} onChange={setMetadata} rows={4} /></div>
      {error && <div className="inline-error">{error}</div>}
      <div className="modal-actions"><button className="button" type="button" onClick={onClose}>Cancel</button><button className="button button--primary" disabled={mutation.isPending} type="submit">{mutation.isPending ? "Saving..." : action ? "Save changes" : "Add Action"}</button></div>
    </form>
  </Modal>;
}

