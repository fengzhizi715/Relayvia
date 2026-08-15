import { useState } from "react";
import { useMutation } from "@tanstack/react-query";

import { ApiError, createService, type Credential, type Service, type ServicePayload, updateService } from "../../api/client";
import { JsonEditor } from "../../components/JsonEditor";
import { Modal } from "../../components/Modal";

type ServiceFormProps = {
  service?: Service;
  credentials: Credential[];
  onClose: () => void;
  onSaved: () => void;
};

function objectJson(value: unknown) {
  return JSON.stringify(value ?? {}, null, 2);
}

function parseObject(value: string, label: string): Record<string, unknown> {
  try {
    const parsed = JSON.parse(value);
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) throw new Error();
    return parsed as Record<string, unknown>;
  } catch {
    throw new Error(`${label} must be a JSON object.`);
  }
}

export function ServiceForm({ service, credentials, onClose, onSaved }: ServiceFormProps) {
  const [name, setName] = useState(service?.name ?? "");
  const [description, setDescription] = useState(service?.description ?? "");
  const [baseUrl, setBaseUrl] = useState(service?.base_url ?? "");
  const [healthCheckUrl, setHealthCheckUrl] = useState(service?.health_check_url ?? "");
  const [credentialId, setCredentialId] = useState(service?.credential_id ?? "");
  const [metadata, setMetadata] = useState(objectJson(service?.metadata));
  const [error, setError] = useState<string | null>(null);
  const mutation = useMutation({
    mutationFn: (payload: ServicePayload) => service ? updateService(service.id, payload) : createService(payload),
    onSuccess: onSaved,
    onError: (value) => setError(value instanceof ApiError ? `${value.message} (${value.code})` : (value as Error).message),
  });

  function submit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      mutation.mutate({ name, description, service_type: "http", base_url: baseUrl, health_check_url: healthCheckUrl || undefined, credential_id: credentialId || null, enabled: service?.enabled ?? true, metadata: parseObject(metadata, "Metadata") });
    } catch (value) {
      setError((value as Error).message);
    }
  }

  return <Modal title={service ? "Edit Service" : "Connect Service"} eyebrow="EXISTING CAPABILITY" onClose={onClose}>
    <form className="form-stack" onSubmit={submit}>
      <div className="form-section"><p className="form-section-title">Basic information</p><label className="field"><span>Name</span><input className="input" required value={name} onChange={(event) => setName(event.target.value)} placeholder="YoloWebAgent" /></label><label className="field"><span>Description</span><textarea className="input" rows={2} value={description} onChange={(event) => setDescription(event.target.value)} placeholder="Existing business or technical service" /></label></div>
      <div className="form-section"><p className="form-section-title">Connection</p><label className="field"><span>Service type</span><select className="input" disabled value="http"><option value="http">HTTP</option></select></label><label className="field"><span>Base URL</span><input className="input" required value={baseUrl} onChange={(event) => setBaseUrl(event.target.value)} placeholder="https://service.example.com/api" /></label><label className="field"><span>Health check URL</span><input className="input" value={healthCheckUrl} onChange={(event) => setHealthCheckUrl(event.target.value)} placeholder="https://service.example.com/api/health" /></label><label className="field"><span>Credential</span><select className="input" value={credentialId} onChange={(event) => setCredentialId(event.target.value)}><option value="">No credential</option>{credentials.map((credential) => <option key={credential.id} value={credential.id}>{credential.name} · {credential.type}</option>)}</select></label></div>
      <JsonEditor label="Metadata" value={metadata} onChange={setMetadata} rows={5} hint="Keep authentication secrets in a Credential, not metadata." />
      {error && <div className="inline-error">{error}</div>}
      <div className="modal-actions"><button className="button" type="button" onClick={onClose}>Cancel</button><button className="button button--primary" disabled={mutation.isPending} type="submit">{mutation.isPending ? "Saving..." : service ? "Save changes" : "Connect Service"}</button></div>
    </form>
  </Modal>;
}

