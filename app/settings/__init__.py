import os
from importlib import import_module

from dotenv import load_dotenv  # type: ignore

load_dotenv()

VALID_STAGES = {
    "dev": "app.settings.dev",
    "test": "app.settings.test",
    "prod": "app.settings.prod",
}

STAGE = os.getenv("STAGE", "dev").lower()

if STAGE not in VALID_STAGES:
    valid_stages = ", ".join(VALID_STAGES.keys())
    raise ValueError(
        f"Invalid STAGE environment: {STAGE!r}. Supported stages are: {valid_stages}"
    )


settings = import_module(VALID_STAGES[STAGE])
