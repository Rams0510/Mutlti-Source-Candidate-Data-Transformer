import hashlib
import logging
from typing import List, Dict, Any, Tuple, Optional

logger = logging.getLogger("pipeline")

def merge_sources(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Merges multiple normalized candidate profiles into one canonical profile.
    Applies source-priority conflict resolution, deduplicates arrays, tracks
    field provenance, and computes a unique candidate ID.
    """
    merged = {
        "candidate_id": "",
        "full_name": None,
        "emails": [],
        "phones": [],
        "location": {"city": None, "region": None, "country": None},
        "links": {"linkedin": None, "github": None, "portfolio": None, "other": []},
        "headline": None,
        "years_experience": None,
        "skills": [],
        "experience": [],
        "education": [],
        "provenance": [],
        "overall_confidence": 0.0
    }
    
    if not records:
        return merged
        
    # Group records by source type
    resume_recs = [r for r in records if r.get("_source") == "resume"]
    csv_recs = [r for r in records if r.get("_source") == "recruiter_csv"]
    github_recs = [r for r in records if r.get("_source") == "github"]
    
    # Track which sources are used
    sources_used = list(set(r.get("_source") for r in records if r.get("_source")))
    
    provenance_list = []
    
    def select_with_priority(field_name: str, priority_records: List[Dict[str, Any]]) -> Tuple[Any, Optional[str], List[str]]:
        """
        Picks the first non-null value from records in priority order.
        Identifies any lower-priority sources with conflicting values.
        """
        chosen_val = None
        chosen_source = None
        conflicts = []
        
        for r in priority_records:
            val = r.get(field_name)
            if val is not None:
                # Support dictionary/list values check
                if (isinstance(val, list) or isinstance(val, dict)) and not val:
                    continue
                if chosen_val is None:
                    chosen_val = val
                    chosen_source = r.get("_source")
                elif val != chosen_val:
                    conflicts.append(r.get("_source"))
                    
        return chosen_val, chosen_source, conflicts

    # 1. Full name: resume > csv > github
    name_order = resume_recs + csv_recs + github_recs
    full_name, name_src, name_conflicts = select_with_priority("full_name", name_order)
    merged["full_name"] = full_name
    if name_src:
        method = "direct_extraction"
        if name_conflicts:
            method += f"_resolved_conflict_with_{'_and_'.join(name_conflicts)}"
            logger.info(f"Conflict: different full_name found. Picked from {name_src}, ignored {name_conflicts}")
        provenance_list.append({"field": "full_name", "source": name_src, "method": method})

    # 2. Emails: union of all valid emails (deduplicated)
    all_emails = []
    email_sources = {}
    for r in records:
        source = r.get("_source", "unknown")
        # csv record might have a single 'email' field or resume/github has 'emails'
        recs_emails = []
        if "email" in r and r["email"]:
            recs_emails.append(r["email"])
        if "emails" in r and r["emails"]:
            recs_emails.extend(r["emails"])
            
        for email in recs_emails:
            if email not in email_sources:
                email_sources[email] = []
            if source not in email_sources[email]:
                email_sources[email].append(source)
            all_emails.append(email)
            
    merged["emails"] = sorted(list(set(all_emails)))
    # Add provenance for emails
    email_sources_added = set()
    for email in merged["emails"]:
        for src in email_sources[email]:
            if src not in email_sources_added:
                provenance_list.append({"field": "emails", "source": src, "method": "direct_extraction"})
                email_sources_added.add(src)

    # 3. Phones: union of all valid phones (deduplicated)
    all_phones = []
    phone_sources = {}
    for r in records:
        source = r.get("_source", "unknown")
        recs_phones = []
        if "phone" in r and r["phone"]:
            recs_phones.append(r["phone"])
        if "phones" in r and r["phones"]:
            recs_phones.extend(r["phones"])
            
        for phone in recs_phones:
            if phone not in phone_sources:
                phone_sources[phone] = []
            if source not in phone_sources[phone]:
                phone_sources[phone].append(source)
            all_phones.append(phone)
            
    merged["phones"] = sorted(list(set(all_phones)))
    phone_sources_added = set()
    for phone in merged["phones"]:
        for src in phone_sources[phone]:
            if src not in phone_sources_added:
                provenance_list.append({"field": "phones", "source": src, "method": "direct_extraction"})
                phone_sources_added.add(src)

    # 4. Location: github > resume > csv
    loc_order = github_recs + resume_recs + csv_recs
    
    # We parse cities, regions, countries individually or take the location object
    city, city_src, _ = select_with_priority("city", [r.get("location", {}) if isinstance(r.get("location"), dict) else {} for r in loc_order])
    region, region_src, _ = select_with_priority("region", [r.get("location", {}) if isinstance(r.get("location"), dict) else {} for r in loc_order])
    country, country_src, _ = select_with_priority("country", [r.get("location", {}) if isinstance(r.get("location"), dict) else {} for r in loc_order])
    
    merged["location"] = {
        "city": city,
        "region": region,
        "country": country
    }
    
    loc_src = country_src or city_src or region_src
    if loc_src:
        provenance_list.append({"field": "location", "source": loc_src, "method": "direct_extraction"})

    # 5. Headline: resume > github > csv
    headline_order = resume_recs + github_recs + csv_recs
    headline, headline_src, headline_conflicts = select_with_priority("headline", headline_order)
    # If csv has title and company, we can generate a headline candidate as "Title at Company"
    if not headline:
        for r in csv_recs:
            title = r.get("title")
            company = r.get("current_company")
            if title and company:
                headline = f"{title} at {company}"
                headline_src = "recruiter_csv"
                break
            elif title:
                headline = title
                headline_src = "recruiter_csv"
                break
                
    merged["headline"] = headline
    if headline_src:
        method = "direct_extraction"
        if headline_conflicts:
            method += f"_resolved_conflict_with_{'_and_'.join(headline_conflicts)}"
        provenance_list.append({"field": "headline", "source": headline_src, "method": method})

    # 6. Years experience: resume > csv, take higher if both present
    exp_order = resume_recs + csv_recs
    years_exp, yexp_src, _ = select_with_priority("years_experience", exp_order)
    
    # If both resume and csv values exist, take higher
    csv_exp_vals = [r.get("years_experience") for r in csv_recs if r.get("years_experience") is not None]
    resume_exp_vals = [r.get("years_experience") for r in resume_recs if r.get("years_experience") is not None]
    if csv_exp_vals and resume_exp_vals:
        years_exp = max(max(csv_exp_vals), max(resume_exp_vals))
        yexp_src = "resume" if max(resume_exp_vals) >= max(csv_exp_vals) else "recruiter_csv"
        
    merged["years_experience"] = float(years_exp) if years_exp is not None else None
    if yexp_src:
        provenance_list.append({"field": "years_experience", "source": yexp_src, "method": "direct_extraction"})

    # 7. Skills: union across sources; same skill name → merge sources list, average confidence
    # Group skills by canonicalized name (case-insensitive)
    skills_map = {}
    for r in records:
        source = r.get("_source", "unknown")
        r_skills = r.get("skills", [])
        for sk in r_skills:
            if not sk:
                continue
            name = ""
            conf = 0.5
            sources = [source]
            
            if isinstance(sk, dict):
                name = sk.get("name", "")
                conf = sk.get("confidence", 0.5)
                sources = sk.get("sources", [source])
            else:
                name = str(sk)
                conf = 0.6 if source == "github" else (0.8 if source == "resume" else 0.5)
                
            name_lower = name.strip().lower()
            if not name_lower:
                continue
                
            if name_lower not in skills_map:
                skills_map[name_lower] = {
                    "name": name.strip(),  # preserve display case
                    "confidences": [],
                    "sources": set()
                }
            
            skills_map[name_lower]["confidences"].append(conf)
            for s in sources:
                skills_map[name_lower]["sources"].add(s)
                
    merged_skills = []
    for sk_lower, info in skills_map.items():
        avg_conf = sum(info["confidences"]) / len(info["confidences"])
        merged_skills.append({
            "name": info["name"],
            "confidence": round(avg_conf, 2),
            "sources": sorted(list(info["sources"]))
        })
        
    merged["skills"] = sorted(merged_skills, key=lambda x: x["name"])
    if merged["skills"]:
        # Log provenance from any source that contributed skills
        all_skill_sources = set()
        for sk in merged["skills"]:
            for s in sk["sources"]:
                all_skill_sources.add(s)
        for s in sorted(list(all_skill_sources)):
            provenance_list.append({"field": "skills", "source": s, "method": "direct_extraction"})

    # 8. Experience: resume only
    if resume_recs and resume_recs[0].get("experience"):
        merged["experience"] = resume_recs[0]["experience"]
        provenance_list.append({"field": "experience", "source": "resume", "method": "direct_extraction"})

    # 9. Education: resume only
    if resume_recs and resume_recs[0].get("education"):
        merged["education"] = resume_recs[0]["education"]
        provenance_list.append({"field": "education", "source": "resume", "method": "direct_extraction"})

    # 9b. Certifications: resume only
    all_certs = []
    for record in records:
        if record.get("_source") == "resume" and record.get("certifications"):
            all_certs.extend(record["certifications"])
    if all_certs:
        merged["certifications"] = sorted(list(set(all_certs)))
        provenance_list.append({"field": "certifications", "source": "resume", "method": "direct_extraction"})

    # 10. Links.github: github source
    github_link, github_link_src, _ = select_with_priority("github", [r.get("links", {}) if isinstance(r.get("links"), dict) else {} for r in github_recs])
    if not github_link:
        # Fallback to resume
        github_link, github_link_src, _ = select_with_priority("github", [r.get("links", {}) if isinstance(r.get("links"), dict) else {} for r in resume_recs])
        
    # 11. Links.linkedin / portfolio: resume or github (first non-null)
    link_order = resume_recs + github_recs
    linkedin_link, linkedin_src, _ = select_with_priority("linkedin", [r.get("links", {}) if isinstance(r.get("links"), dict) else {} for r in link_order])
    portfolio_link, portfolio_src, _ = select_with_priority("portfolio", [r.get("links", {}) if isinstance(r.get("links"), dict) else {} for r in link_order])
    
    # 12. Links.other: union of others from all sources
    all_other_links = []
    for r in records:
        other_list = r.get("links", {}).get("other", []) if isinstance(r.get("links"), dict) else []
        all_other_links.extend(other_list)
        
    merged["links"] = {
        "linkedin": linkedin_link,
        "github": github_link,
        "portfolio": portfolio_link,
        "other": sorted(list(set(all_other_links)))
    }
    
    links_src = linkedin_src or github_link_src or portfolio_src
    if links_src:
        provenance_list.append({"field": "links", "source": links_src, "method": "direct_extraction"})

    merged["provenance"] = provenance_list

    # 13. Candidate ID: sha256 of first_email or full_name + "_eightfold" (first 12 chars)
    first_email = merged["emails"][0] if merged["emails"] else None
    
    id_base = ""
    if first_email:
        id_base = first_email
    elif merged["full_name"]:
        id_base = merged["full_name"] + "_eightfold"
    else:
        id_base = "empty_candidate_eightfold"
        
    hasher = hashlib.sha256(id_base.encode("utf-8"))
    merged["candidate_id"] = hasher.hexdigest()[:12]

    # Propagate internal scoring flags
    merged["_malformed_emails"] = any(r.get("_malformed_emails") for r in records)
    merged["_malformed_phones"] = any(r.get("_malformed_phones") for r in records)
    merged["_inferred_years_experience"] = any(r.get("_inferred_years_experience") for r in records)

    return merged
