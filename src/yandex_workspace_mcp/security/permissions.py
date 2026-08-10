from functools import wraps
from typing import Callable, Any
from yandex_workspace_mcp.exceptions import PermissionDenied
from yandex_workspace_mcp.config import get_settings
from yandex_workspace_mcp.security.paths import is_path_in_allowed_roots

def check_disk_read(path: str | None = None) -> None:
    settings = get_settings()
    if not settings.disk.enabled:
        raise PermissionDenied("Yandex Disk is disabled")
    if not settings.disk.read:
        raise PermissionDenied("Disk read operations are disabled")
    if path and settings.disk.allowed_roots:
        if not is_path_in_allowed_roots(path, settings.disk.allowed_roots):
            raise PermissionDenied(f"Path '{path}' is outside allowed roots")

def check_disk_write(path: str | None = None) -> None:
    settings = get_settings()
    if not settings.disk.enabled:
        raise PermissionDenied("Yandex Disk is disabled")
    if not settings.disk.write:
        raise PermissionDenied("Disk write operations are disabled")
    if path and settings.disk.allowed_roots:
        if not is_path_in_allowed_roots(path, settings.disk.allowed_roots):
            raise PermissionDenied(f"Path '{path}' is outside allowed roots")

def check_disk_delete(path: str | None = None) -> None:
    settings = get_settings()
    if not settings.disk.enabled:
        raise PermissionDenied("Yandex Disk is disabled")
    if not settings.disk.delete:
        raise PermissionDenied("Disk delete operations are disabled")
    if path and settings.disk.allowed_roots:
        if not is_path_in_allowed_roots(path, settings.disk.allowed_roots):
            raise PermissionDenied(f"Path '{path}' is outside allowed roots")

def check_wiki_read(slug: str | None = None) -> None:
    settings = get_settings()
    if not settings.wiki.enabled:
        raise PermissionDenied("Yandex Wiki is disabled")
    if not settings.wiki.read:
        raise PermissionDenied("Wiki read operations are disabled")
    if slug and settings.wiki.allowed_roots:
        # Wiki paths are usually like project/page or just project.
        # We can reuse the path checker if we prepend /
        if not is_path_in_allowed_roots("/" + slug.lstrip("/"), ["/" + r.lstrip("/") for r in settings.wiki.allowed_roots]):
            raise PermissionDenied(f"Wiki page '{slug}' is outside allowed roots")

def check_wiki_write(slug: str | None = None) -> None:
    settings = get_settings()
    if not settings.wiki.enabled:
        raise PermissionDenied("Yandex Wiki is disabled")
    if not settings.wiki.write:
        raise PermissionDenied("Wiki write operations are disabled")
    if slug and settings.wiki.allowed_roots:
        if not is_path_in_allowed_roots("/" + slug.lstrip("/"), ["/" + r.lstrip("/") for r in settings.wiki.allowed_roots]):
            raise PermissionDenied(f"Wiki page '{slug}' is outside allowed roots")
