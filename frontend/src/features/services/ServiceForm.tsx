import { useState } from "react";
import { useMutation } from "@tanstack/react-query";

import { ApiError, createService, type Credential, type Service, type ServicePayload, updateService } from "../../api/client";
import { JsonEditor } from "../../components/JsonEditor";
import { Modal } from "../../components/Modal";
import { useTranslation, type Translator } from "../../i18n";
import { credentialTypeLabel } from "../credentials/credentialType";

type ServiceFormProps = {
  service?: Service;
  credentials: Credential[];
  onClose: () => void;
  onSaved: () => void;
};

function objectJson(value: unknown) {
  return JSON.stringify(value ?? {}, null, 2);
}

function parseObject(value: string, label: string, t: Translator): Record<string, unknown> {
  try {
    const parsed = JSON.parse(value);
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) throw new Error();
    return parsed as Record<string, unknown>;
  } catch {
    throw new Error(t("parse.mustBeJsonObject", { label }));
  }
}

export function ServiceForm({ service, credentials, onClose, onSaved }: ServiceFormProps) {
  const { t } = useTranslation();
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
      mutation.mutate({ name, description, service_type: "http", base_url: baseUrl, health_check_url: healthCheckUrl || undefined, credential_id: credentialId || null, enabled: service?.enabled ?? true, metadata: parseObject(metadata, t("agentForm.metadata"), t) });
    } catch (value) {
      setError((value as Error).message);
    }
  }

  return <Modal title={service ? t("serviceForm.editTitle") : t("serviceForm.connectTitle")} eyebrow={t("agentForm.eyebrow")} onClose={onClose}>
    <form className="form-stack" onSubmit={submit}>
      <div className="form-section"><p className="form-section-title">{t("agentForm.basicInfo")}</p><label className="field"><span>{t("agentForm.name")}</span><input className="input" required value={name} onChange={(event) => setName(event.target.value)} placeholder={t("serviceForm.namePlaceholder")} /></label><label className="field"><span>{t("agentForm.description")}</span><textarea className="input" rows={2} value={description} onChange={(event) => setDescription(event.target.value)} placeholder={t("serviceForm.descriptionPlaceholder")} /></label></div>
      <div className="form-section"><p className="form-section-title">{t("agentForm.connection")}</p><label className="field"><span>{t("serviceForm.serviceType")}</span><select className="input" disabled value="http"><option value="http">{t("agentForm.http")}</option></select></label><label className="field"><span>{t("services.baseUrl")}</span><input className="input" required value={baseUrl} onChange={(event) => setBaseUrl(event.target.value)} placeholder={t("serviceForm.baseUrlPlaceholder")} /></label><label className="field"><span>{t("agentForm.healthCheckUrl")}</span><input className="input" value={healthCheckUrl} onChange={(event) => setHealthCheckUrl(event.target.value)} placeholder={t("serviceForm.healthCheckPlaceholder")} /></label><label className="field"><span>{t("agentForm.credential")}</span><select className="input" value={credentialId} onChange={(event) => setCredentialId(event.target.value)}><option value="">{t("agentForm.noCredential")}</option>{credentials.map((credential) => <option key={credential.id} value={credential.id}>{credential.name} · {credentialTypeLabel(credential.type, t)}</option>)}</select></label></div>
      <JsonEditor label={t("agentForm.metadata")} value={metadata} onChange={setMetadata} rows={5} hint={t("serviceForm.metadataHint")} />
      {error && <div className="inline-error">{error}</div>}
      <div className="modal-actions"><button className="button" type="button" onClick={onClose}>{t("common.cancel")}</button><button className="button button--primary" disabled={mutation.isPending} type="submit">{mutation.isPending ? t("common.saving") : service ? t("common.saveChanges") : t("serviceForm.connectTitle")}</button></div>
    </form>
  </Modal>;
}
