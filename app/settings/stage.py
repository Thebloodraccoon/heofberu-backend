"""Stage resolution from the process environment (kept import-light so it is unit-testable)."""

from collections.abc import Mapping

VALID_STAGES = {
    "dev": "app.settings.dev",
    "test": "app.settings.test",
    "staging": "app.settings.staging",
    "prod": "app.settings.prod",
}

_TRUTHY = {"1", "true", "yes", "on"}


def resolve_stage(environ: Mapping[str, str]) -> str:
    """
    Return the validated stage name from ``environ``.

    ``STAGE`` defaults to ``dev`` for local work, but production images set
    ``REQUIRE_EXPLICIT_STAGE=true``: a missing ``STAGE`` must never silently
    turn a deployed container into a dev instance (open CORS, SQL echo, docs).
    """

    if "STAGE" not in environ and environ.get("REQUIRE_EXPLICIT_STAGE", "").strip().lower() in _TRUTHY:
        raise RuntimeError("STAGE is not set. Set STAGE explicitly (dev | test | staging | prod) in this environment.")

    stage = environ.get("STAGE", "dev").lower()
    if stage not in VALID_STAGES:
        valid_stages = ", ".join(VALID_STAGES)
        raise ValueError(f"Invalid STAGE environment: {stage!r}. Supported stages are: {valid_stages}")

    return stage
