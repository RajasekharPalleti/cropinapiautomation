"""Loads environment-scoped test data from test_data/<env>.json.

Each environment file is a flat map of module -> named data sets, e.g.:
    {
      "login": {"valid": {...}, "invalid_credentials": {...}},
      "farmer": {"create_valid": {...}},
      "asset": {},
      "plantype": {},
      "crop_variety": {},
      "project": {}
    }

Add a new named case under the relevant module section (in qa.json/uat.json/prod.json)
as you get real API data for it, then load it in tests via
load_test_data("<module>", "<name>") — the active environment (--env / ENV) is
resolved automatically, so the same test code runs unchanged against qa/uat/prod.
"""
import json
from functools import lru_cache
from pathlib import Path

from src.config.settings import get_settings

TEST_DATA_DIR = Path(__file__).parent.parent.parent / "test_data"


@lru_cache
def _env_data(env: str) -> dict:
    path = TEST_DATA_DIR / f"{env}.json"
    if not path.exists():
        raise FileNotFoundError(f"No test data file for environment '{env}' at {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_test_data(module: str, name: str, env: str | None = None) -> dict:
    """Loads the named data set for a module from the active environment's JSON file.

    module: e.g. "login", "farmer", "asset", "plantype", "crop_variety", "project".
    name: the logical case within that module, e.g. "valid", "create_missing_name".
    env: overrides the active environment (defaults to the current Settings().env).
    """
    env = env or get_settings().env
    data = _env_data(env)
    try:
        return data[module][name]
    except KeyError as exc:
        raise KeyError(
            f"No test data for '{module}.{name}' in test_data/{env}.json"
        ) from exc
