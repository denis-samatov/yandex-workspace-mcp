import posixpath
import unicodedata
import urllib.parse
from typing import List
from ..models.errors import InvalidPath

def normalize_path(path: str) -> str:
    """
    Normalizes a path to prevent traversal attacks, double encoding, etc.
    """
    # 1. Unquote percent encoding. Do it twice to prevent double-encoding attacks.
    unquoted = urllib.parse.unquote(path)
    unquoted = urllib.parse.unquote(unquoted)
    
    # 2. Normalize unicode to catch visual spoofing or alternate representations of slashes/dots
    normalized_unicode = unicodedata.normalize('NFKC', unquoted)
    
    # 3. Replace backslashes with forward slashes (mixed separators)
    normalized_slashes = normalized_unicode.replace("\\", "/")
    
    # 4. Use posixpath.normpath to resolve '.' and '..' and collapse multiple slashes
    clean_path = posixpath.normpath(normalized_slashes)
    
    # 5. Ensure absolute-like representation for roots
    if not clean_path.startswith("/"):
        clean_path = "/" + clean_path
        
    return clean_path

def is_path_allowed(path: str, allowed_roots: List[str]) -> bool:
    """
    Checks if a normalized path is contained within any of the allowed roots.
    """
    norm_path = normalize_path(path)
    path_parts = norm_path.strip("/").split("/") if norm_path != "/" else []
    
    for root in allowed_roots:
        norm_root = normalize_path(root)
        if norm_root == "/":
            return True # Everything is allowed
            
        root_parts = norm_root.strip("/").split("/")
        
        # Check if root_parts is a prefix of path_parts
        if len(path_parts) >= len(root_parts):
            if path_parts[:len(root_parts)] == root_parts:
                return True
                
    return False

def validate_path(path: str, allowed_roots: List[str]) -> str:
    """
    Validates a path and returns the normalized path. Raises InvalidPath if not allowed.
    """
    norm_path = normalize_path(path)
    if not is_path_allowed(norm_path, allowed_roots):
        raise InvalidPath(f"Path '{path}' is not within allowed roots.")
    return norm_path
