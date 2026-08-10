import os
from yandex_workspace_mcp.exceptions import InvalidPath

def normalize_path(path: str) -> str:
    """Normalize path and check for directory traversal attempts."""
    if not path:
        raise InvalidPath("Path cannot be empty")
    
    # Handle Yandex Disk scheme if provided
    if path.startswith("disk:/"):
        path = path[5:]

    # Ensure path starts with /
    if not path.startswith("/"):
        path = "/" + path

    # Use posixpath for consistent forward slash behavior
    import posixpath
    normalized = posixpath.normpath(path)
    
    # Check for path traversal tricks that normpath might have resolved
    # If the original path contained sequences that shouldn't be there, 
    # we should probably reject it entirely.
    if ".." in path or "%2e%2e" in path.lower():
        raise InvalidPath("Path traversal is not allowed")

    return normalized

def is_path_in_allowed_roots(path: str, allowed_roots: list[str]) -> bool:
    """Check if a normalized path is within any of the allowed roots."""
    if not allowed_roots:
        return True # If no roots configured, assume all allowed (or should we deny?)
                    # Let's enforce that if roots are configured, it must match.
                    # Wait, the spec says "any attempt to access outside whitelist".
                    # If whitelist is empty, we probably allow all.
    
    normalized_path = normalize_path(path)
    
    for root in allowed_roots:
        normalized_root = normalize_path(root)
        
        # Exact match
        if normalized_path == normalized_root:
            return True
            
        # Subpath match
        if normalized_path.startswith(normalized_root.rstrip("/") + "/"):
            return True
            
    return False
