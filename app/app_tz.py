import os
from zoneinfo import ZoneInfo

# Reads the standard TZ env var; falls back to America/Denver.
# Set TZ=America/Denver in the Docker environment to make this explicit.
APP_TZ = ZoneInfo(os.environ.get("TZ", "America/Denver"))
