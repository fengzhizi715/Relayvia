export type AgentConnectorType = "http" | "local" | "custom";
export type AgentStatus = "unknown" | "healthy" | "unhealthy";
export type ServiceStatus = "unknown" | "healthy" | "unhealthy";
export type CredentialType = "api_key" | "bearer_token" | "basic_auth";
export type HTTPMethod = "GET" | "POST" | "PUT" | "PATCH" | "DELETE";

export type HealthResponse = {
  status: "ok" | "degraded";
  service: string;
  database: "connected" | "unavailable";
};

export type Capability = { name: string; description?: string | null };

export type Credential = {
  id: string;
  name: string;
  type: CredentialType;
  has_secret: boolean;
  created_at: string;
  updated_at: string;
};

export type CredentialCreate = {
  name: string;
  type: CredentialType;
  value?: string;
  username?: string;
  password?: string;
};

export type Agent = {
  id: string;
  name: string;
  description: string | null;
  connector_type: AgentConnectorType;
  endpoint: string | null;
  http_method: HTTPMethod;
  health_check_url: string | null;
  headers: Record<string, string>;
  runner_id: string | null;
  capabilities: Capability[];
  input_schema: Record<string, unknown>;
  output_schema: Record<string, unknown>;
  credential_id: string | null;
  credential_name: string | null;
  timeout_seconds: number;
  status: AgentStatus;
  enabled: boolean;
  metadata: Record<string, unknown>;
  last_checked_at: string | null;
  last_latency_ms: number | null;
  last_error: string | null;
  created_at: string;
  updated_at: string;
};

export type AgentPayload = {
  name: string;
  description?: string;
  connector_type: AgentConnectorType;
  endpoint?: string;
  http_method: HTTPMethod;
  health_check_url?: string;
  headers: Record<string, string>;
  runner_id?: string;
  capabilities: Capability[];
  input_schema: Record<string, unknown>;
  output_schema: Record<string, unknown>;
  credential_id?: string | null;
  timeout_seconds: number;
  enabled?: boolean;
  metadata: Record<string, unknown>;
};

export type Service = {
  id: string;
  name: string;
  description: string | null;
  service_type: "http";
  base_url: string;
  credential_id: string | null;
  credential_name: string | null;
  health_check_url: string | null;
  status: ServiceStatus;
  enabled: boolean;
  metadata: Record<string, unknown>;
  last_checked_at: string | null;
  last_latency_ms: number | null;
  last_error: string | null;
  actions_count: number;
  created_at: string;
  updated_at: string;
};

export type ServicePayload = {
  name: string;
  description?: string;
  service_type: "http";
  base_url: string;
  credential_id?: string | null;
  health_check_url?: string;
  enabled?: boolean;
  metadata: Record<string, unknown>;
};

export type RetryPolicy = {
  max_retries: number;
  backoff_seconds: number;
  retry_on_status: number[];
};

export type ServiceAction = {
  id: string;
  service_id: string;
  name: string;
  description: string | null;
  method: HTTPMethod;
  path: string;
  headers: Record<string, string>;
  query_schema: Record<string, unknown>;
  path_schema: Record<string, unknown>;
  input_schema: Record<string, unknown>;
  output_schema: Record<string, unknown>;
  timeout_seconds: number;
  retry_policy: RetryPolicy;
  enabled: boolean;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type ServiceActionPayload = {
  name: string;
  description?: string;
  method: HTTPMethod;
  path: string;
  headers: Record<string, string>;
  query_schema: Record<string, unknown>;
  path_schema: Record<string, unknown>;
  input_schema: Record<string, unknown>;
  output_schema: Record<string, unknown>;
  timeout_seconds: number;
  retry_policy: RetryPolicy;
  enabled?: boolean;
  metadata: Record<string, unknown>;
};

export type ConnectionTestResult = {
  status: "healthy" | "unhealthy" | "unsupported";
  latency_ms: number | null;
  checked_at: string;
  error_code: string | null;
  message: string | null;
};

export type WorkflowStatus = "draft" | "active" | "archived";
export type WorkflowNode = {
  id: string;
  type: "agent" | "service" | "tool" | "logic" | "human" | "data";
  subtype: string;
  name: string;
  position: { x: number; y: number };
  config: Record<string, unknown>;
  input_mapping: Record<string, unknown>;
  metadata: Record<string, unknown>;
};
export type WorkflowEdge = {
  id: string;
  source: string;
  target: string;
  source_handle: string | null;
  target_handle: string | null;
  label: string | null;
  condition: Record<string, unknown> | null;
  metadata: Record<string, unknown>;
};
export type WorkflowGraph = {
  schema_version: "1.0";
  nodes: WorkflowNode[];
  edges: WorkflowEdge[];
  variables: Record<string, { type: string; default?: unknown; description?: string | null }>;
  metadata: Record<string, unknown>;
};
export type Workflow = {
  id: string;
  name: string;
  description: string | null;
  status: WorkflowStatus;
  draft_graph: WorkflowGraph;
  graph_schema_version: string;
  current_version: number | null;
  created_at: string;
  updated_at: string;
};
export type WorkflowPayload = { name: string; description?: string; graph?: WorkflowGraph };
export type WorkflowGraphResponse = {
  workflow_id: string;
  schema_version: string;
  graph: WorkflowGraph;
  warnings: Array<{ code: string; message: string; details: Record<string, unknown> }>;
  updated_at: string;
};
export type WorkflowVersion = {
  id: string;
  workflow_id: string;
  version: number;
  graph_schema_version: string;
  graph: WorkflowGraph;
  change_note: string | null;
  created_at: string;
};

export class ApiError extends Error {
  code: string;
  details: Record<string, unknown>;

  constructor(code: string, message: string, details: Record<string, unknown> = {}) {
    super(message);
    this.code = code;
    this.details = details;
  }
}

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? "";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${apiBaseUrl}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (response.status === 204) return undefined as T;
  const body = (await response.json()) as T & { error?: { code: string; message: string; details?: Record<string, unknown> } };
  if (!response.ok) {
    throw new ApiError(body.error?.code ?? "REQUEST_FAILED", body.error?.message ?? "Request failed", body.error?.details);
  }
  return body;
}

export const getHealth = () => request<HealthResponse>("/api/health");

export const getCredentials = () => request<Credential[]>("/api/credentials");
export const createCredential = (payload: CredentialCreate) => request<Credential>("/api/credentials", { method: "POST", body: JSON.stringify(payload) });
export const updateCredential = (id: string, payload: Partial<CredentialCreate>) => request<Credential>(`/api/credentials/${id}`, { method: "PUT", body: JSON.stringify(payload) });
export const deleteCredential = (id: string) => request<void>(`/api/credentials/${id}`, { method: "DELETE" });

export const getAgents = () => request<Agent[]>("/api/agents");
export const createAgent = (payload: AgentPayload) => request<Agent>("/api/agents", { method: "POST", body: JSON.stringify(payload) });
export const updateAgent = (id: string, payload: Partial<AgentPayload>) => request<Agent>(`/api/agents/${id}`, { method: "PUT", body: JSON.stringify(payload) });
export const deleteAgent = (id: string) => request<void>(`/api/agents/${id}`, { method: "DELETE" });
export const testAgent = (id: string) => request<ConnectionTestResult>(`/api/agents/${id}/test`, { method: "POST" });

export const getServices = () => request<Service[]>("/api/services");
export const createService = (payload: ServicePayload) => request<Service>("/api/services", { method: "POST", body: JSON.stringify(payload) });
export const updateService = (id: string, payload: Partial<ServicePayload>) => request<Service>(`/api/services/${id}`, { method: "PUT", body: JSON.stringify(payload) });
export const deleteService = (id: string) => request<void>(`/api/services/${id}`, { method: "DELETE" });
export const testService = (id: string) => request<ConnectionTestResult>(`/api/services/${id}/test`, { method: "POST" });

export const getActions = (serviceId: string) => request<ServiceAction[]>(`/api/services/${serviceId}/actions`);
export const createAction = (serviceId: string, payload: ServiceActionPayload) => request<ServiceAction>(`/api/services/${serviceId}/actions`, { method: "POST", body: JSON.stringify(payload) });
export const updateAction = (serviceId: string, actionId: string, payload: Partial<ServiceActionPayload>) => request<ServiceAction>(`/api/services/${serviceId}/actions/${actionId}`, { method: "PUT", body: JSON.stringify(payload) });
export const deleteAction = (serviceId: string, actionId: string) => request<void>(`/api/services/${serviceId}/actions/${actionId}`, { method: "DELETE" });

export const getWorkflows = (includeArchived = false) => request<Workflow[]>(`/api/workflows?include_archived=${includeArchived}`);
export const createWorkflow = (payload: WorkflowPayload) => request<Workflow>("/api/workflows", { method: "POST", body: JSON.stringify(payload) });
export const getWorkflow = (id: string) => request<Workflow>(`/api/workflows/${id}`);
export const updateWorkflow = (id: string, payload: Partial<WorkflowPayload> & { status?: WorkflowStatus }) => request<Workflow>(`/api/workflows/${id}`, { method: "PUT", body: JSON.stringify(payload) });
export const deleteWorkflow = (id: string) => request<void>(`/api/workflows/${id}`, { method: "DELETE" });
export const getWorkflowGraph = (id: string) => request<WorkflowGraphResponse>(`/api/workflows/${id}/graph`);
export const updateWorkflowGraph = (id: string, graph: WorkflowGraph) => request<WorkflowGraphResponse>(`/api/workflows/${id}/graph`, { method: "PUT", body: JSON.stringify({ graph }) });
export const getWorkflowVersions = (id: string) => request<WorkflowVersion[]>(`/api/workflows/${id}/versions`);
export const createWorkflowVersion = (id: string, changeNote?: string) => request<WorkflowVersion>(`/api/workflows/${id}/versions`, { method: "POST", body: JSON.stringify({ change_note: changeNote }) });
export const getWorkflowVersion = (id: string, version: number) => request<WorkflowVersion>(`/api/workflows/${id}/versions/${version}`);
