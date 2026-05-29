from app.web.llm_settings import resolve_llm_credentials
from app.web_store.store import store


def test_resolve_llm_falls_back_to_env(monkeypatch):
    monkeypatch.setattr(
        "app.web.llm_settings.settings.llm_base_url",
        "https://example.com/v1",
    )
    monkeypatch.setattr(
        "app.web.llm_settings.settings.llm_api_key",
        "env-key",
    )
    monkeypatch.setattr(
        "app.web.llm_settings.settings.llm_model_name",
        "env-model",
    )
    store.save_settings({"llmByUser": {}})
    creds = resolve_llm_credentials("local")
    assert creds.base_url == "https://example.com/v1"
    assert creds.api_key == "env-key"
    assert creds.model == "env-model"


def test_resolve_llm_per_user(monkeypatch):
    monkeypatch.setattr(
        "app.web.llm_settings.settings.llm_api_key",
        "fallback",
    )
    monkeypatch.setattr(
        "app.web.llm_settings.settings.llm_model_name",
        "fallback-model",
    )
    store.save_settings(
        {
            "llmByUser": {
                "Alice": {
                    "connections": [
                        {
                            "id": "default",
                            "baseUrl": "https://gw.example/v1",
                            "apiKey": "alice-key",
                        }
                    ],
                    "activeConnectionId": "default",
                    "activeModelId": "model-a",
                }
            }
        }
    )
    creds = resolve_llm_credentials("Alice")
    assert creds.api_key == "alice-key"
    assert creds.model == "model-a"
