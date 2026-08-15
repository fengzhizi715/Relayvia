import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { ApiError, createCredential, deleteCredential, getCredentials, type Credential, type CredentialCreate } from "../../api/client";
import { Modal } from "../../components/Modal";
import { ResourceEmptyState } from "../../components/ResourceEmptyState";

function CredentialForm({ onClose, onSaved }: { onClose: () => void; onSaved: () => void }) {
  const [name, setName] = useState("");
  const [type, setType] = useState<CredentialCreate["type"]>("api_key");
  const [value, setValue] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const mutation = useMutation({ mutationFn: createCredential, onSuccess: onSaved, onError: (value) => setError(value instanceof ApiError ? `${value.message} (${value.code})` : (value as Error).message) });
  function submit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    mutation.mutate(type === "basic_auth" ? { name, type, username, password } : { name, type, value });
  }
  return <Modal title="Add Credential" eyebrow="SECURE REFERENCE" onClose={onClose}><form className="form-stack" onSubmit={submit}><div className="form-section"><p className="form-section-title">Credential identity</p><label className="field"><span>Name</span><input className="input" required value={name} onChange={(event) => setName(event.target.value)} placeholder="Production API token" /></label><label className="field"><span>Type</span><select className="input" value={type} onChange={(event) => setType(event.target.value as CredentialCreate["type"])}><option value="api_key">API Key</option><option value="bearer_token">Bearer Token</option><option value="basic_auth">Basic Auth</option></select></label></div>{type === "basic_auth" ? <div className="form-section"><label className="field"><span>Username</span><input className="input" required value={username} onChange={(event) => setUsername(event.target.value)} /></label><label className="field"><span>Password</span><input className="input" required type="password" value={password} onChange={(event) => setPassword(event.target.value)} /></label></div> : <div className="form-section"><label className="field"><span>{type === "api_key" ? "API key" : "Bearer token"}</span><input className="input" required type="password" value={value} onChange={(event) => setValue(event.target.value)} /></label></div>}<p className="security-note">The secret is encrypted before persistence and is never returned to the browser after save.</p>{error && <div className="inline-error">{error}</div>}<div className="modal-actions"><button className="button" type="button" onClick={onClose}>Cancel</button><button className="button button--primary" disabled={mutation.isPending} type="submit">{mutation.isPending ? "Saving..." : "Save Credential"}</button></div></form></Modal>;
}

export function CredentialsPage() {
  const queryClient = useQueryClient();
  const credentials = useQuery({ queryKey: ["credentials"], queryFn: getCredentials });
  const [showForm, setShowForm] = useState(false);
  const [showDelete, setShowDelete] = useState<Credential | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const refresh = () => { setShowForm(false); void queryClient.invalidateQueries({ queryKey: ["credentials"] }); };
  const remove = useMutation({ mutationFn: deleteCredential, onSuccess: () => { setShowDelete(null); refresh(); }, onError: (value) => setNotice(value instanceof ApiError ? `${value.message} (${value.code})` : "Delete failed") });
  if (credentials.isLoading) return <div className="loading-state">Loading credentials...</div>;
  if (credentials.isError) return <div className="inline-error">Unable to load Credentials. Start the FastAPI backend and retry.</div>;
  const list = credentials.data ?? [];
  return <div className="resource-page"><div className="page-toolbar"><div><p className="eyebrow">SECURITY REFERENCES</p><h3>Credentials</h3><p className="page-description">Store reusable authentication references without exposing secrets to Agents, Services, or the UI.</p></div><button className="button button--primary" type="button" onClick={() => setShowForm(true)}>+ Add Credential</button></div>{notice && <button className="notice" type="button" onClick={() => setNotice(null)}>{notice} · dismiss</button>}{list.length === 0 ? <ResourceEmptyState title="No credentials saved." message="Credentials are optional. Add one when an existing Agent or Service requires authentication." actionLabel="Add Credential" onAction={() => setShowForm(true)} /> : <div className="credential-grid">{list.map((credential) => <article className="credential-card" key={credential.id}><div className="credential-card-icon">⌁</div><div className="credential-card-copy"><strong>{credential.name}</strong><span>{credential.type.replaceAll("_", " ")}</span><small>Secret stored · never readable</small></div><button className="icon-button icon-button--danger" type="button" onClick={() => setShowDelete(credential)} aria-label={`Delete ${credential.name}`}>×</button></article>)}</div>}{showForm && <CredentialForm onClose={() => setShowForm(false)} onSaved={refresh} />}{showDelete && <Modal title="Delete Credential" eyebrow="CONFIRM ACTION" onClose={() => setShowDelete(null)}><div className="confirm-copy"><p>Delete <strong>{showDelete.name}</strong>?</p><p>Agents or Services still using it will block this operation.</p></div><div className="modal-actions"><button className="button" type="button" onClick={() => setShowDelete(null)}>Cancel</button><button className="button button--danger" type="button" disabled={remove.isPending} onClick={() => remove.mutate(showDelete.id)}>Delete Credential</button></div></Modal>}</div>;
}

