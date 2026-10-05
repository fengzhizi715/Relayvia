import { useState } from "react";
import { useMutation } from "@tanstack/react-query";

import {
  ApiError,
  createAgent,
  type Agent,
  type AgentPayload,
  type Credential,
  type Runner,
  type Capability,
  updateAgent,
} from "../../api/client";
import { JsonEditor } from "../../components/JsonEditor";
import { Modal } from "../../components/Modal";
import { useTranslation, type Translator } from "../../i18n";
import { credentialTypeLabel } from "../credentials/credentialType";

type AgentFormProps = {
  agent?: Agent;
  credentials: Credential[];
  runners: Runner[];
  onClose: () => void;
  onSaved: () => void;
};

const defaultSchema = "{\n  \"type\": \"object\",\n  \"properties\": {}\n}";

function objectJson(value: unknown) {
  return JSON.stringify(value ?? {}, null, 2);
}

function parseObject(value: string, label: string, t: Translator): Record<string, unknown> {
  let parsed: unknown;
  try {
    parsed = JSON.parse(value);
  } catch {
    throw new Error(t("parse.mustBeJsonObject", { label }));
  }
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error(t("parse.mustBeJsonObject", { label }));
  }
  return parsed as Record<string, unknown>;
}

function parseStringRecord(value: string, label: string, t: Translator): Record<string, string> {
  const parsed = parseObject(value, label, t);
  if (Object.values(parsed).some((item) => typeof item !== "string")) {
    throw new Error(t("parse.valuesMustBeStrings", { label }));
  }
  return parsed as Record<string, string>;
}

function parseCapabilities(value: string, t: Translator): Capability[] {
  let parsed: unknown;
  try {
    parsed = JSON.parse(value);
  } catch {
    throw new Error(t("agentForm.capabilitiesInvalidJson"));
  }
  if (!Array.isArray(parsed) || parsed.some((item) => !item || typeof item !== "object" || typeof (item as Capability).name !== "string")) {
    throw new Error(t("agentForm.capabilitiesInvalidShape"));
  }
  return parsed as Capability[];
}

export function AgentForm({ agent, credentials, runners, onClose, onSaved }: AgentFormProps) {
  const { t } = useTranslation();
  const [name, setName] = useState(agent?.name ?? "");
  const [description, setDescription] = useState(agent?.description ?? "");
  const [connectorType, setConnectorType] = useState(agent?.connector_type ?? "http");
  const [endpoint, setEndpoint] = useState(agent?.endpoint ?? "");
  const [httpMethod, setHttpMethod] = useState(agent?.http_method ?? "POST");
  const [healthCheckUrl, setHealthCheckUrl] = useState(agent?.health_check_url ?? "");
  const [credentialId, setCredentialId] = useState(agent?.credential_id ?? "");
  const [runnerId, setRunnerId] = useState(agent?.runner_id ?? "");
  const [executable, setExecutable] = useState(agent?.executable ?? "");
  const [timeout, setTimeout] = useState(String(agent?.timeout_seconds ?? 30));
  const [headers, setHeaders] = useState(objectJson(agent?.headers));
  const [capabilities, setCapabilities] = useState(objectJson(agent?.capabilities ?? []));
  const [inputSchema, setInputSchema] = useState(objectJson(agent?.input_schema ?? JSON.parse(defaultSchema)));
  const [outputSchema, setOutputSchema] = useState(objectJson(agent?.output_schema ?? JSON.parse(defaultSchema)));
  const [metadata, setMetadata] = useState(objectJson(agent?.metadata));
  const [error, setError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: (payload: AgentPayload) => (agent ? updateAgent(agent.id, payload) : createAgent(payload)),
    onSuccess: onSaved,
    onError: (value) => setError(value instanceof ApiError ? `${value.message} (${value.code})` : (value as Error).message),
  });

  function submit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      const payload: AgentPayload = {
        name,
        description,
        connector_type: connectorType,
        endpoint: endpoint || undefined,
        http_method: httpMethod,
        health_check_url: healthCheckUrl || undefined,
        headers: parseStringRecord(headers, t("agentForm.headers"), t),
        capabilities: parseCapabilities(capabilities, t),
        input_schema: parseObject(inputSchema, t("agentForm.inputSchema"), t),
        output_schema: parseObject(outputSchema, t("agentForm.outputSchema"), t),
        credential_id: credentialId || null,
        runner_id: runnerId || undefined,
        executable: executable || undefined,
        timeout_seconds: Number(timeout),
        enabled: agent?.enabled ?? true,
        metadata: parseObject(metadata, t("agentForm.metadata"), t),
      };
      mutation.mutate(payload);
    } catch (value) {
      setError((value as Error).message);
    }
  }

  return (
    <Modal title={agent ? t("agentForm.editTitle") : t("agentForm.connectTitle")} eyebrow={t("agentForm.eyebrow")} onClose={onClose}>
      <form className="form-stack" onSubmit={submit}>
        <div className="form-section">
          <p className="form-section-title">{t("agentForm.basicInfo")}</p>
          <div className="form-grid">
            <label className="field"><span>{t("agentForm.name")}</span><input className="input" required value={name} onChange={(event) => setName(event.target.value)} placeholder={t("agentForm.namePlaceholder")} /></label>
            <label className="field"><span>{t("agentForm.connectorType")}</span><select className="input" value={connectorType} onChange={(event) => setConnectorType(event.target.value as typeof connectorType)}><option value="http">{t("agentForm.http")}</option><option value="codex">{t("agentForm.codexViaRunner")}</option><option value="local">{t("agentForm.localMetadata")}</option><option value="custom">{t("agentForm.customMetadata")}</option></select></label>
          </div>
          <label className="field"><span>{t("agentForm.description")}</span><textarea className="input" rows={2} value={description} onChange={(event) => setDescription(event.target.value)} placeholder={t("agentForm.descriptionPlaceholder")} /></label>
        </div>

        <div className="form-section">
          <p className="form-section-title">{t("agentForm.connection")}</p>
          {connectorType === "http" ? <div className="form-grid">
            <label className="field field--wide"><span>{t("agentForm.endpoint")}</span><input className="input" value={endpoint} onChange={(event) => setEndpoint(event.target.value)} placeholder="https://agent.example.com/invoke" /></label>
            <label className="field"><span>{t("agentForm.httpMethod")}</span><select className="input" value={httpMethod} onChange={(event) => setHttpMethod(event.target.value as typeof httpMethod)}><option>POST</option><option>GET</option><option>PUT</option><option>PATCH</option><option>DELETE</option></select></label>
            <label className="field field--wide"><span>{t("agentForm.healthCheckUrl")}</span><input className="input" value={healthCheckUrl} onChange={(event) => setHealthCheckUrl(event.target.value)} placeholder="https://agent.example.com/health" /></label>
            <label className="field"><span>{t("agentForm.timeoutSeconds")}</span><input className="input" min={1} max={3600} type="number" value={timeout} onChange={(event) => setTimeout(event.target.value)} /></label>
          </div> : connectorType === "codex" ? <div className="form-grid">
            <label className="field field--wide"><span>{t("agentForm.runner")}</span><select className="input" required value={runnerId} onChange={(event) => setRunnerId(event.target.value)}><option value="">{t("agentForm.selectRunner")}</option>{runners.map((runner) => <option key={runner.id} value={runner.id}>{runner.name} · {runner.status} · {runner.capabilities.join(", ")}</option>)}</select></label>
            <label className="field field--wide"><span>{t("agentForm.codexExecutable")}</span><input className="input" value={executable} onChange={(event) => setExecutable(event.target.value)} placeholder={t("agentForm.codexExecutablePlaceholder")} /></label>
            <label className="field"><span>{t("agentForm.timeoutSeconds")}</span><input className="input" min={1} max={3600} type="number" value={timeout} onChange={(event) => setTimeout(event.target.value)} /></label>
          </div> : <label className="field"><span>{t("agentForm.timeoutSeconds")}</span><input className="input" min={1} max={3600} type="number" value={timeout} onChange={(event) => setTimeout(event.target.value)} /></label>}
          {connectorType === "http" && <><label className="field"><span>{t("agentForm.credential")}</span><select className="input" value={credentialId} onChange={(event) => setCredentialId(event.target.value)}><option value="">{t("agentForm.noCredential")}</option>{credentials.map((credential) => <option key={credential.id} value={credential.id}>{credential.name} · {credentialTypeLabel(credential.type, t)}</option>)}</select></label><JsonEditor label={t("agentForm.headers")} value={headers} onChange={setHeaders} rows={3} hint={t("agentForm.headersHint")} /></>}
        </div>

        <div className="form-section">
          <p className="form-section-title">{t("agentForm.invocationContract")}</p>
          <JsonEditor label={t("agentForm.capabilities")} value={capabilities} onChange={setCapabilities} rows={4} hint={t("agentForm.capabilitiesHint")} />
          <JsonEditor label={t("agentForm.inputSchema")} value={inputSchema} onChange={setInputSchema} />
          <JsonEditor label={t("agentForm.outputSchema")} value={outputSchema} onChange={setOutputSchema} />
          <JsonEditor label={t("agentForm.metadata")} value={metadata} onChange={setMetadata} rows={4} />
        </div>

        {error && <div className="inline-error">{error}</div>}
        <div className="modal-actions"><button className="button" type="button" onClick={onClose}>{t("common.cancel")}</button><button className="button button--primary" disabled={mutation.isPending} type="submit">{mutation.isPending ? t("common.saving") : agent ? t("common.saveChanges") : t("agentForm.connectTitle")}</button></div>
      </form>
    </Modal>
  );
}
