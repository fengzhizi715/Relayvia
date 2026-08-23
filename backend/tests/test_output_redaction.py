from app.runtime.executor.trace import sanitize_output


def test_output_redacts_sensitive_keys_inline_values_and_known_credential_echoes():
    output = sanitize_output(
        {
            "token": "header-secret",
            "message": "Authorization: header-secret; echoed=credential-value",
            "nested": {"note": "credential-value"},
        },
        sensitive_values={"credential-value"},
    )
    assert output["token"] == "***REDACTED***"
    assert output["message"] == "Authorization:***REDACTED***; echoed=***REDACTED***"
    assert output["nested"]["note"] == "***REDACTED***"
