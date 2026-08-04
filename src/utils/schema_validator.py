"""Loads JSON schema files from test_data/schemas for response validation."""
import json
from pathlib import Path

SCHEMA_DIR = Path(__file__).parent.parent.parent / "test_data" / "schemas"


def load_schema(schema_name: str) -> dict:
    path = SCHEMA_DIR / schema_name
    if not path.exists():
        raise FileNotFoundError(f"Schema '{schema_name}' not found at {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
