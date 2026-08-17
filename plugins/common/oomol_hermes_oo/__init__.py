"""Shared OO CLI behavior for bundled OOMOL Hermes providers."""

from .auth import OOLoginRequired, require_oo_authentication

__all__ = ["OOLoginRequired", "require_oo_authentication"]
