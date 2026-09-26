from unittest import mock
import os
import pytest
from tempo_log.config import load_settings
from tempo_log.keyring_store import (
    delete_credential,
    get_credential,
    is_keyring_available,
    set_credential,
)


def test_keyring_functions_mocked():
    with mock.patch("tempo_log.keyring_store._get_keyring_module") as mock_get_kr:
        fake_kr = mock.MagicMock()
        mock_get_kr.return_value = fake_kr

        set_credential("TEMPO_API_TOKEN", "secret-token")
        fake_kr.set_password.assert_called_once_with("dev-jira-tempo", "TEMPO_API_TOKEN", "secret-token")

        fake_kr.get_password.return_value = "retrieved-token"
        val = get_credential("TEMPO_API_TOKEN")
        assert val == "retrieved-token"
        fake_kr.get_password.assert_called_once_with("dev-jira-tempo", "TEMPO_API_TOKEN")

        delete_credential("TEMPO_API_TOKEN")
        fake_kr.delete_password.assert_called_once_with("dev-jira-tempo", "TEMPO_API_TOKEN")


def test_load_settings_fallback_to_keyring():
    with mock.patch.dict(os.environ, {}, clear=True):
        with mock.patch("tempo_log.config.get_credential") as mock_get_cred:
            mock_get_cred.side_effect = lambda k: "keyring-token" if k == "TEMPO_API_TOKEN" else None
            settings = load_settings()
            assert settings.tempo_api_token == "keyring-token"
            assert settings.jira is None
