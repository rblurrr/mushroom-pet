"""Platform backends. Import `backend` and use it; never touch os-specific APIs directly."""
from .base import Backend, WindowInfo, get_backend

backend: Backend = get_backend()

__all__ = ["Backend", "WindowInfo", "backend", "get_backend"]
