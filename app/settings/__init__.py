"""``settings`` is the stage module (``dev``/``test``/``staging``/``prod``) selected by ``STAGE``."""

from importlib import import_module
import os

from dotenv import load_dotenv  # type: ignore

from app.settings.stage import VALID_STAGES, resolve_stage

load_dotenv()

STAGE = resolve_stage(os.environ)

settings = import_module(VALID_STAGES[STAGE])
