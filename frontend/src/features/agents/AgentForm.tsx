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

function parseObject(value: string, label: string): Record<string, unknown> {
  let parsed: unknown;
  try {
    parsed = JSON.parse(value);
  } catch {
    throw new Error(`${label} must be valid JSON.`);
  }
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error(`${label} must be a JSON object.`);
  }
  return parsed as Record<string, unknown>;
}

function parseStringRecord(value: string, label: string): Record<string, string> {
  const parsed = parseObject(value, label);
  if (Object.values(parsed).some((item) => typeof item !== "string")) {
    throw new Error(`${label} values must all be strings.`);
  }
  return parsed as Record<string, string>;
}

function parseCapabilities(value: string): Capability[] {
  let parsed: unknown;
  try {
    parsed = JSON.parse(value);
  } catch {
    throw new Error("Capabilities must be valid JSON.");
  }
  if (!Array.isArray(parsed) || parsed.some((item) => !item || typeof item !== "object" || typeof (item as Capability).name !== "string")) {
    throw new Error("Capabilities must be an array of objects with a name.");
  }
  return parsed as Capability[];
}

export function AgentForm({ agent, credentials, runners, onClose, onSaved }: AgentFormProps) {
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
        headers: parseStringRecord(headers, "Headers"),
        capabilities: parseCapabilities(capabilities),
        input_schema: parseObject(inputSchema, "Input schema"),
        output_schema: parseObject(outputSchema, "Output schema"),
        credential_id: credentialId || null,
        runner_id: runnerId || undefined,
        executable: executable || undefined,
        timeout_seconds: Number(timeout),
        enabled: agent?.enabled ?? true,
        metadata: parseObject(metadata, "Metadata"),
      };
      mutation.mutate(payload);
    } catch (value) {
      setError((value as Error).message);
    }
  }

  return (
    <Modal title={agent ? "Edit Agent" : "Connect Agent"} eyebrow="EXISTING CAPABILITY" onClose={onClose}>
      <form className="form-stack" onSubmit={submit}>
        <div className="form-section">
          <p className="form-section-title">Basic information</p>
          <div className="form-grid">
            <label className="field"><span>Name</span><input className="input" required value={name} onChange={(event) => setName(event.target.value)} placeholder="Code Review Agent" /></label>
            <label className="field"><span>Connector type</span><select className="input" value={connectorType} onChange={(event) => setConnectorType(event.target.value as typeof connectorType)}><option value="http">HTTP</option><option value="codex">Codex via Runner</option><option value="local">Local (metadata only)</option><option value="custom">Custom (metadata only)</option></select></label>
          </div>
          <label className="field"><span>Description</span><textarea className="input" rows={2} value={description} onChange={(event) => setDescription(event.target.value)} placeholder="What this existing agent does" /></label>
        </div>

        <div className="form-section">
          <p className="form-section-title">Connection</p>
          {connectorType === "http" ? <div className="form-grid">
            <label className="field field--wide"><span>Endpoint</span><input className="input" value={endpoint} onChange={(event) => setEndpoint(event.target.value)} placeholder="https://agent.example.com/invoke" /></label>
            <label className="field"><span>HTTP method</span><select className="input" value={httpMethod} onChange={(event) => setHttpMethod(event.target.value as typeof httpMethod)}><option>POST</option><option>GET</option><option>PUT</option><option>PATCH</option><option>DELETE</option></select></label>
            <label className="field field--wide"><span>Health check URL</span><input className="input" value={healthCheckUrl} onChange={(event) => setHealthCheckUrl(event.target.value)} placeholder="https://agent.example.com/health" /></label>
            <label className="field"><span>Timeout (seconds)</span><input className="input" min={1} max={3600} type="number" value={timeout} onChange={(event) => setTimeout(event.target.value)} /></label>
          </div> : connectorType === "codex" ? <div className="form-grid">
            <label className="field field--wide"><span>Runner</span><select className="input" required value={runnerId} onChange={(event) => setRunnerId(event.target.value)}><option value="">Select a Runner</option>{runners.map((runner) => <option key={runner.id} value={runner.id}>{runner.name} · {runner.status} · {runner.capabilities.join(", ")}</option>)}</select></label>
            <label className="field field--wide"><span>Codex executable</span><input className="input" value={executable} onChange={(event) => setExecutable(event.target.value)} placeholder="codex (default, resolved on the Runner)" /></label>
            <label className="field"><span>Timeout (seconds)</span><input className="input" min={1} max={3600} type="number" value={timeout} onChange={(event) => setTimeout(event.target.value)} /></label>
          </div> : <label className="field"><span>Timeout (seconds)</span><input className="input" min={1} max={3600} type="number" value={timeout} onChange={(event) => setTimeout(event.target.value)} /></label>}
          {connectorType === "http" && <><label className="field"><span>Credential</span><select className="input" value={credentialId} onChange={(event) => setCredentialId(event.target.value)}><option value="">No credential</option>{credentials.map((credential) => <option key={credential.id} value={credential.id}>{credential.name} · {credential.type}</option>)}</select></label><JsonEditor label="Headers" value={headers} onChange={setHeaders} rows={3} hint="Do not put API keys or bearer tokens here; use a Credential." /></>}
        </div>

        <div className="form-section">
          <p className="form-section-title">Invocation contract</p>
          <JsonEditor label="Capabilities" value={capabilities} onChange={setCapabilities} rows={4} hint='Example: [{"name":"code_review","description":"Review source code"}]' />
          <JsonEditor label="Input schema" value={inputSchema} onChange={setInputSchema} />
          <JsonEditor label="Output schema" value={outputSchema} onChange={setOutputSchema} />
          <JsonEditor label="Metadata" value={metadata} onChange={setMetadata} rows={4} />
        </div>

        {error && <div className="inline-error">{error}</div>}
        <div className="modal-actions"><button className="button" type="button" onClick={onClose}>Cancel</button><button className="button button--primary" disabled={mutation.isPending} type="submit">{mutation.isPending ? "Saving..." : agent ? "Save changes" : "Connect Agent"}</button></div>
      </form>
    </Modal>
  );
}
