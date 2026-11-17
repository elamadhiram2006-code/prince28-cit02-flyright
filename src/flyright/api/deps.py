from fastapi import Request

from flyright.config import Settings, get_settings


def get_app_settings() -> Settings:
    """Return application settings."""
    return get_settings()


def get_store(request: Request):
    """Return the document store from application state."""
    return request.app.state.store
