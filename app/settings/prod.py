import os

from app.settings.local import *  # noqa: F403

ALLOWED_HOSTS = os.getenv("ALLOWED_HOSTS", "").split(",")
