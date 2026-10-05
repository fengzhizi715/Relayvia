import type { CredentialType } from "../../api/client";
import type { Translator } from "../../i18n";

export function credentialTypeLabel(type: CredentialType | string, t: Translator): string {
  switch (type) {
    case "api_key":
      return t("credentials.apiKey");
    case "bearer_token":
      return t("credentials.bearerToken");
    case "basic_auth":
      return t("credentials.basicAuth");
    default:
      return type;
  }
}
