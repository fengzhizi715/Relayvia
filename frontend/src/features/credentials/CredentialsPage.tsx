import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { ApiError, createCredential, deleteCredential, getCredentials, type Credential, type CredentialCreate } from "../../api/client";
import { Modal } from "../../components/Modal";
import { ResourceEmptyState } from "../../components/ResourceEmptyState";
import { useTranslation } from "../../i18n";
import { credentialTypeLabel } from "./credentialType";

function CredentialForm({ onClose, onSaved }: { onClose: () => void; onSaved: () => void }) {
  const { t } = useTranslation();
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
  return <Modal title={t("credentials.formTitle")} eyebrow={t("credentials.eyebrow")} onClose={onClose}><form className="form-stack" onSubmit={submit}><div className="form-section"><p className="form-section-title">{t("credentials.identity")}</p><label className="field"><span>{t("credentials.name")}</span><input className="input" required value={name} onChange={(event) => setName(event.target.value)} placeholder={t("credentials.namePlaceholder")} /></label><label className="field"><span>{t("credentials.type")}</span><select className="input" value={type} onChange={(event) => setType(event.target.value as CredentialCreate["type"])}><option value="api_key">{t("credentials.apiKey")}</option><option value="bearer_token">{t("credentials.bearerToken")}</option><option value="basic_auth">{t("credentials.basicAuth")}</option></select></label></div>{type === "basic_auth" ? <div className="form-section"><label className="field"><span>{t("credentials.username")}</span><input className="input" required value={username} onChange={(event) => setUsername(event.target.value)} /></label><label className="field"><span>{t("credentials.password")}</span><input className="input" required type="password" value={password} onChange={(event) => setPassword(event.target.value)} /></label></div> : <div className="form-section"><label className="field"><span>{type === "api_key" ? t("credentials.secretApiKey") : t("credentials.secretBearer")}</span><input className="input" required type="password" value={value} onChange={(event) => setValue(event.target.value)} /></label></div>}<p className="security-note">{t("credentials.securityNote")}</p>{error && <div className="inline-error">{error}</div>}<div className="modal-actions"><button className="button" type="button" onClick={onClose}>{t("common.cancel")}</button><button className="button button--primary" disabled={mutation.isPending} type="submit">{mutation.isPending ? t("common.saving") : t("credentials.save")}</button></div></form></Modal>;
}

export function CredentialsPage() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const credentials = useQuery({ queryKey: ["credentials"], queryFn: getCredentials });
  const [showForm, setShowForm] = useState(false);
  const [showDelete, setShowDelete] = useState<Credential | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const refresh = () => { setShowForm(false); void queryClient.invalidateQueries({ queryKey: ["credentials"] }); };
  const remove = useMutation({ mutationFn: deleteCredential, onSuccess: () => { setShowDelete(null); refresh(); }, onError: (value) => setNotice(value instanceof ApiError ? `${value.message} (${value.code})` : t("common.deleteFailed")) });
  if (credentials.isLoading) return <div className="loading-state">{t("credentials.loading")}</div>;
  if (credentials.isError) return <div className="inline-error">{t("credentials.loadError")}</div>;
  const list = credentials.data ?? [];
  return <div className="resource-page"><div className="page-toolbar"><div><p className="eyebrow">{t("credentials.eyebrowPage")}</p><h3>{t("credentials.title")}</h3><p className="page-description">{t("credentials.description")}</p></div><button className="button button--primary" type="button" onClick={() => setShowForm(true)}>{t("credentials.add")}</button></div>{notice && <button className="notice" type="button" onClick={() => setNotice(null)}>{notice} · {t("common.dismiss")}</button>}{list.length === 0 ? <ResourceEmptyState title={t("credentials.emptyTitle")} message={t("credentials.emptyMessage")} actionLabel={t("credentials.add")} onAction={() => setShowForm(true)} /> : <div className="credential-grid">{list.map((credential) => <article className="credential-card" key={credential.id}><div className="credential-card-icon">⌁</div><div className="credential-card-copy"><strong>{credential.name}</strong><span>{credentialTypeLabel(credential.type, t)}</span><small>{t("credentials.secretStored")}</small></div><button className="icon-button icon-button--danger" type="button" onClick={() => setShowDelete(credential)} aria-label={t("credentials.deleteAria", { name: credential.name })}>×</button></article>)}</div>}{showForm && <CredentialForm onClose={() => setShowForm(false)} onSaved={refresh} />}{showDelete && <Modal title={t("credentials.deleteTitle")} eyebrow={t("common.confirmAction")} onClose={() => setShowDelete(null)}><div className="confirm-copy"><p>{t("credentials.deleteConfirm", { name: showDelete.name })}</p><p>{t("credentials.deleteNote")}</p></div><div className="modal-actions"><button className="button" type="button" onClick={() => setShowDelete(null)}>{t("common.cancel")}</button><button className="button button--danger" type="button" disabled={remove.isPending} onClick={() => remove.mutate(showDelete.id)}>{t("credentials.deleteAction")}</button></div></Modal>}</div>;
}
