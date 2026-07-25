import os
from importlib import import_module

from dotenv import load_dotenv  # type: ignore

load_dotenv()

VALID_STAGES = {
    "local": "app.settings.local",
    "prod": "app.settings.prod",
}

STAGE = os.getenv("STAGE", "local").lower()

if STAGE not in VALID_STAGES:
    valid_stages = ", ".join(VALID_STAGES.keys())
    raise ValueError(
        f"Invalid STAGE environment: {STAGE}. Supported stages are: {valid_stages}"
    )


settings = import_module(VALID_STAGES[STAGE])
