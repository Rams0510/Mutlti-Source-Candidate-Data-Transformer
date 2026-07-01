from typing import List, Dict, Any
from pydantic import ValidationError
from schema.canonical import CandidateProfile

def validate_profile(profile_dict: Dict[str, Any]) -> List[str]:
    """
    Validates the profile dictionary against the CandidateProfile Pydantic schema.
    Returns a list of warning/error messages.
    """
    warnings = []
    
    # We strip temporary warning keys before checking schema compliance
    clean_dict = {k: v for k, v in profile_dict.items() if k != "_warnings"}
    
    try:
        CandidateProfile(**clean_dict)
    except ValidationError as e:
        for error in e.errors():
            loc = " -> ".join(str(x) for x in error["loc"])
            msg = error["msg"]
            warnings.append(f"Validation error at '{loc}': {msg}")
            
    # Add semantic / logical warnings if any
    if not clean_dict.get("emails") and not clean_dict.get("phones"):
        warnings.append("Profile has neither email nor phone contact information")
        
    if not clean_dict.get("full_name"):
        warnings.append("Profile full_name is empty")
        
    return warnings
