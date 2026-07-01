import re
import logging
from typing import Dict, Any, Optional
from pipeline.normalizer import normalize_phone, canonicalize_skill

logger = logging.getLogger("pipeline")

def parse_path(path: str, data: Dict[str, Any]) -> Any:
    """
    Parses complex JSON paths from data dict.
    Supports:
    - simple keys: "full_name"
    - dot notation: "links.linkedin"
    - array indexes: "emails[0]"
    - array mapping: "skills[].name"
    """
    if not path or not isinstance(data, dict):
        return None
        
    # Handle array mapping: e.g. "skills[].name"
    match_map = re.match(r"^(\w+)\[\]\.(\w+)$", path)
    if match_map:
        arr_key, prop = match_map.groups()
        arr = data.get(arr_key)
        if not isinstance(arr, list):
            return None
        res = []
        for item in arr:
            if isinstance(item, dict) and prop in item:
                res.append(item[prop])
            elif hasattr(item, prop):
                res.append(getattr(item, prop))
        return res
        
    # Handle array index: e.g. "emails[0]"
    match_idx = re.match(r"^(\w+)\[(\d+)\]$", path)
    if match_idx:
        arr_key, idx_str = match_idx.groups()
        idx = int(idx_str)
        arr = data.get(arr_key)
        if not isinstance(arr, list) or idx >= len(arr):
            return None
        return arr[idx]
        
    # Handle dot notation: e.g. "links.linkedin"
    if "." in path:
        parts = path.split(".")
        current = data
        for part in parts:
            if isinstance(current, dict):
                current = current.get(part)
            else:
                return None
        return current
        
    # Simple key
    return data.get(path)

def apply_config(canonical: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Transforms a canonical candidate profile into a custom-configured structure.
    """
    output = {}
    
    fields = config.get("fields", [])
    on_missing = config.get("on_missing", "null")  # "null", "omit", "error"
    include_confidence = config.get("include_confidence", False)
    
    for f in fields:
        dest_path = f.get("path")
        from_path = f.get("from") or dest_path
        expected_type = f.get("type", "string")
        required = f.get("required", False)
        normalize_option = f.get("normalize")
        
        # 1. Extract value using path helper
        val = parse_path(from_path, canonical)
        
        # 2. Check if missing (None or empty list/dict or empty string)
        is_missing = False
        if val is None:
            is_missing = True
        elif isinstance(val, list) and len(val) == 0:
            is_missing = True
        elif isinstance(val, dict) and len(val) == 0:
            is_missing = True
        elif isinstance(val, str) and not val.strip():
            is_missing = True
            
        if is_missing:
            # Handle missing policy
            if on_missing == "error":
                raise ValueError(f"Required field '{dest_path}' (from '{from_path}') is missing or null.")
            elif on_missing == "omit":
                continue
            else: # "null"
                output[dest_path] = None
                continue
                
        # 3. Apply custom normalization overrides
        if normalize_option == "E164":
            if isinstance(val, list):
                val = [normalize_phone(p) for p in val if normalize_phone(p)]
            else:
                val = normalize_phone(val)
        elif normalize_option == "canonical":
            if isinstance(val, list):
                val = [canonicalize_skill(s) for s in val]
            else:
                val = canonicalize_skill(val)
                
        # 4. Type checking
        type_ok = True
        if expected_type == "string":
            if not isinstance(val, str):
                type_ok = False
        elif expected_type == "string[]":
            if not isinstance(val, list) or not all(isinstance(x, str) for x in val):
                type_ok = False
        elif expected_type == "number":
            if not isinstance(val, (int, float)) or isinstance(val, bool):
                type_ok = False
        elif expected_type == "boolean":
            if not isinstance(val, bool):
                type_ok = False
                
        if not type_ok:
            logger.warning(f"Type mismatch for field '{dest_path}': expected {expected_type}, got {type(val)}")
            output[dest_path] = None
        else:
            output[dest_path] = val
            
    # Include overall confidence if requested
    if include_confidence:
        output["overall_confidence"] = canonical.get("overall_confidence", 0.0)
        
    return output
