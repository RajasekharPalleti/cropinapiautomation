"""Central config loader: merges environments/<env>.yaml with .env overrides."""
import os
from functools import lru_cache
from pathlib import Path

import yaml
from dotenv import load_dotenv

load_dotenv()

CONFIG_DIR = Path(__file__).parent / "environments"


class Settings:
    def __init__(self) -> None:
        self.env: str = os.getenv("ENV", "qa")
        self._data: dict = self._load_env_file(self.env)

        self.base_url: str = os.getenv("BASE_URL") or self._data["base_url"]
        self.login_endpoint: str = self._data["login_endpoint"]
        self.timeout_ms: int = int(self._data.get("timeout_ms", 30000))
        self.default_headers: dict = self._data.get("default_headers", {})

        # Credentials are looked up per-environment first (CROPIN_<ENV>_USERNAME, etc.)
        # so one .env file can hold qa/uat/prod creds side by side; falls back to the
        # unprefixed CROPIN_USERNAME/PASSWORD/TENANT_ID for local single-env use.
        env_prefix = self.env.upper()
        self.username: str = os.getenv(f"CROPIN_{env_prefix}_USERNAME") or os.getenv(
            "CROPIN_USERNAME", ""
        )
        self.password: str = os.getenv(f"CROPIN_{env_prefix}_PASSWORD") or os.getenv(
            "CROPIN_PASSWORD", ""
        )
        self.tenant_id: str = os.getenv(f"CROPIN_{env_prefix}_TENANT_ID") or os.getenv(
            "CROPIN_TENANT_ID", ""
        )

        # SSO (Keycloak) token endpoint used by AuthManager.generate_token().
        # tenant_code is deliberately NOT here — it's supplied per-test as test data
        # (see test_data/<env>.json -> "login" section) since it varies by request.
        self.sso_base_url: str = os.getenv("SSO_BASE_URL") or self._data.get(
            "sso_base_url", "https://sso.sg.cropin.in"
        )

        # SMTP config for emailing the HTML report (report_mailer.py) — one
        # mail account for all environments; WHO receives it and WHETHER it
        # sends at all are test data (test_data/<env>.json -> "settings" ->
        # "email_report"), not env vars, so recipients can be edited without
        # touching secrets. Never commit real values — these stay in .env
        # (gitignored) locally, or as Actions secrets in CI.
        self.smtp_host: str = os.getenv("SMTP_HOST", "")
        self.smtp_port: int = int(os.getenv("SMTP_PORT", "587"))
        self.smtp_username: str = os.getenv("SMTP_USERNAME", "")
        self.smtp_password: str = os.getenv("SMTP_PASSWORD", "")
        self.smtp_from_email: str = os.getenv("SMTP_FROM_EMAIL") or self.smtp_username

    @staticmethod
    def _load_env_file(env: str) -> dict:
        config_path = CONFIG_DIR / f"{env}.yaml"
        if not config_path.exists():
            raise FileNotFoundError(
                f"No config found for environment '{env}' at {config_path}"
            )
        with open(config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)


@lru_cache
def get_settings() -> Settings:
    return Settings()
