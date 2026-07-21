"""Built-in web dashboard.

Zero-dependency (stdlib http.server) so the edge agent stays lightweight.
Serves the main presence dashboard at "/", the integration-points page at
"/integrations", and a small read-only JSON API under /api/*.
"""
from .server import start_web  # noqa: F401
