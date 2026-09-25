"""Load only station settings from the project's .env; never execute shell code."""
import os
from pathlib import Path
from dotenv import dotenv_values


def load_environment(path=None):
    target = Path(path) if path is not None else Path(__file__).resolve().parents[1] / ".env"
    values = dotenv_values(target, encoding="utf-8-sig", interpolate=False)
    for key in ("QC_API_KEY", "QC_TWIN_URL"):
        value = values.get(key)
        if value is not None:
            os.environ.setdefault(key, value)
