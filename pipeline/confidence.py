import logging
from typing import Dict, Any, List

logger = logging.getLogger("pipeline")

def score_confidence(merged: Dict[str, Any], sources_used: List[str]) -> Dict[str, Any]:
    """
    Computes per-field confidence scores and the overall weighted confidence score
    for a merged candidate profile.
    
    Overall confidence = (full_name * 0.15) + (email * 0.20) + (phone * 0.10) +
                         (location * 0.10) + (skills * 0.20) + (experience * 0.15) +
                         (education * 0.10)
    """
    
    # 1. Full name confidence
    # 0.9 resume / 0.8 csv / 0.7 github; 0.5 if single source only
    full_name_score = 0.0
    if merged.get("full_name"):
        if len(sources_used) == 1:
            full_name_score = 0.5
        else:
            # Check source of the name value from provenance
            name_prov = next((p for p in merged.get("provenance", []) if p["field"] == "full_name"), None)
            if name_prov:
                src = name_prov["source"]
                if src == "resume":
                    full_name_score = 0.9
                elif src == "recruiter_csv":
                    full_name_score = 0.8
                elif src == "github":
                    full_name_score = 0.7
                else:
                    full_name_score = 0.6
            else:
                full_name_score = 0.6
                
    # 2. Emails confidence
    # 0.95 valid format / 0.5 malformed / 0.0 if missing
    email_score = 0.0
    if merged.get("emails"):
        email_score = 0.95
    elif merged.get("_malformed_emails"):
        email_score = 0.5
    else:
        email_score = 0.0
        
    # 3. Phones confidence
    # 0.9 if E.164 parseable / 0.4 raw string / 0.0 if missing
    phone_score = 0.0
    if merged.get("phones"):
        phone_score = 0.9
    elif merged.get("_malformed_phones"):
        phone_score = 0.4
    else:
        phone_score = 0.0

    # 4. Location confidence
    # 0.8 ISO-3166 resolved / 0.5 raw string / 0.0 null
    loc_score = 0.0
    loc = merged.get("location", {})
    if loc and (loc.get("city") or loc.get("region") or loc.get("country")):
        country = loc.get("country")
        if country and len(country) == 2 and country.isupper():
            loc_score = 0.8
        else:
            loc_score = 0.5
            
    # 5. Skills confidence
    # Apply +0.1 bonus for overlap (appears in 2+ sources) capped at 1.0
    skills = merged.get("skills", [])
    skills_score = 0.0
    
    for sk in skills:
        sources = sk.get("sources", [])
        # Apply bonus
        if len(sources) >= 2:
            sk["confidence"] = min(sk.get("confidence", 0.5) + 0.1, 1.0)
            
        sk["confidence"] = round(sk["confidence"], 2)
        
    if skills:
        skills_score = sum(sk["confidence"] for sk in skills) / len(skills)
        
    # 6. Experience & Education confidence
    # 0.85 if from resume / 0.0 if missing
    exp_score = 0.85 if merged.get("experience") else 0.0
    edu_score = 0.85 if merged.get("education") else 0.0
    
    # Years of experience score (tracked but does not enter overall_confidence formula directly)
    # 0.8 explicit / 0.6 inferred / 0.0 if missing
    years_exp_score = 0.0
    if merged.get("years_experience") is not None:
        if merged.get("_inferred_years_experience"):
            years_exp_score = 0.6
        else:
            years_exp_score = 0.8

    # Calculate overall confidence
    overall = (
        (full_name_score * 0.15) +
        (email_score * 0.20) +
        (phone_score * 0.10) +
        (loc_score * 0.10) +
        (skills_score * 0.20) +
        (exp_score * 0.15) +
        (edu_score * 0.10)
    )
    
    merged["overall_confidence"] = round(overall, 2)
    
    # Remove internal tracking variables
    merged.pop("_malformed_emails", None)
    merged.pop("_malformed_phones", None)
    merged.pop("_inferred_years_experience", None)
    
    return merged
