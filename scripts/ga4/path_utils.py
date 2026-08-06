#!/usr/bin/env python3
"""URL path utilities for GA4 queries — sem dependência do SDK Google Analytics."""
from urllib.parse import unquote


def normalize_path(path: str) -> str:
    """Normalize a URL path for consistent comparison against GA4 pagePath.

    Normalizes: percent-decoding, lowercase, leading slash, trailing slash.
    Keeps EXACT match viable while eliminating formatting differences that
    silently drop views (e.g. '/oscs/IDC' vs '/oscs/idc/', '%C3%A7' vs 'ç').

    NOTE: validated locally only — must be verified against a real GA4 property
    with credentials before merging.
    """
    if not path:
        return ""
    path = unquote(path)
    path = path.lower()
    if not path.startswith("/"):
        path = "/" + path
    if not path.endswith("/"):
        path += "/"
    return path
