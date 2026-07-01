import os
import tempfile
import json
import logging
from typing import Dict, Any, List, Optional
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, Form
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from sources.csv_source import parse_csv
from sources.resume_source import parse_resume
from sources.github_source import fetch_github
from pipeline.normalizer import (
    normalize_phone,
    normalize_email,
    normalize_date,
    normalize_country,
    normalize_location,
    canonicalize_skill
)
from pipeline.merger import merge_sources
from pipeline.confidence import score_confidence
from pipeline.projector import apply_config
from schema.canonical import CandidateProfile
from schema.validator import validate_profile

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("pipeline")

app = FastAPI(title="Candidate Data Transformer")

ui_dir = Path(__file__).parent / "ui"
if ui_dir.exists():
    app.mount("/static", StaticFiles(directory=ui_dir), name="static")


@app.get("/")
async def root():
    ui_file = Path(__file__).parent / "ui" / "index.html"
    if ui_file.exists():
        return FileResponse(str(ui_file))
    return {"error": "UI not found"}


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/schema")
async def get_schema():
    return CandidateProfile.model_json_schema()


@app.post("/transform")
async def transform(
    csv_file: UploadFile = File(None),
    resume_file: UploadFile = File(None),
    github_username: str = Form(None),
    config: str = Form(None)
):
    tmp_files = []
    try:
        inputs = {}

        # --- Save uploaded files to temp ---
        if csv_file and csv_file.filename:
            content = await csv_file.read()
            if content:
                tmp = tempfile.NamedTemporaryFile(mode='wb', suffix='.csv', delete=False)
                tmp.write(content)
                tmp.close()
                inputs["csv_path"] = tmp.name
                tmp_files.append(tmp.name)

        if resume_file and resume_file.filename:
            content = await resume_file.read()
            if content:
                suffix = Path(resume_file.filename).suffix or '.txt'
                tmp = tempfile.NamedTemporaryFile(mode='wb', suffix=suffix, delete=False)
                tmp.write(content)
                tmp.close()
                inputs["resume_path"] = tmp.name
                tmp_files.append(tmp.name)

        if github_username and github_username.strip():
            inputs["github_username"] = github_username.strip()

        if not inputs:
            return {"error": "Provide at least one input: CSV file, Resume file, or GitHub username"}

        # --- Parse config ---
        config_dict = None
        if config and config.strip():
            try:
                config_dict = json.loads(config)
            except Exception:
                return {"error": "Invalid config JSON — check for missing commas, brackets, or quotes"}

        # --- Run pipeline ---
        result = run_pipeline(inputs, config_dict)

        # If multiple candidates returned (multi-row CSV), return highest confidence
        if isinstance(result, list) and len(result) > 0:
            result = sorted(result, key=lambda x: x.get("overall_confidence", 0), reverse=True)[0]

        return result

    except Exception as e:
        logger.error(f"Transform endpoint error: {e}", exc_info=True)
        return {"error": str(e)}

    finally:
        # Cleanup temp files AFTER response is built
        for path in tmp_files:
            try:
                os.unlink(path)
            except Exception:
                pass


def _has_useful_data(record: dict) -> bool:
    """
    Check if a source record has at least one meaningful field.
    Prevents empty/failed source records from polluting the merge.
    """
    useful_keys = ["full_name", "name", "emails", "phones", "headline",
                   "skills", "experience", "education", "certifications", "location"]
    for key in useful_keys:
        val = record.get(key)
        if val and val != [] and val != {} and val != "":
            return True
    return False


def run_pipeline(inputs: Dict[str, Any], config: Optional[Dict[str, Any]] = None) -> Any:
    """
    Multi-Source Candidate Data Transformer Pipeline.
    Steps: DETECT → EXTRACT → NORMALIZE → GROUP → MERGE → CONFIDENCE → SCHEMA → VALIDATE → PROJECT
    """
    raw_records = []
    sources_used = []

    empty_profile = {
        "candidate_id": "empty_000000",
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
        "certifications": [],
        "provenance": [],
        "overall_confidence": 0.0
    }

    try:
        csv_path = inputs.get("csv_path")
        resume_path = inputs.get("resume_path")
        github_username = inputs.get("github_username")

        logger.info(f"DETECT: csv={csv_path} resume={resume_path} github={github_username}")

        # ============================================================
        # 2. EXTRACT
        # BUG FIX: check _has_useful_data() instead of len(dict) > 1
        # ============================================================
        if csv_path:
            try:
                csv_rows = parse_csv(csv_path)
                for row in (csv_rows or []):
                    if _has_useful_data(row):
                        raw_records.append(row)
                if csv_rows:
                    sources_used.append("recruiter_csv")
                    logger.info(f"EXTRACT: {len(csv_rows)} CSV rows loaded")
            except Exception as e:
                logger.warning(f"EXTRACT CSV failed: {e}")

        if resume_path:
            try:
                resume_data = parse_resume(resume_path)
                if resume_data and _has_useful_data(resume_data):
                    raw_records.append(resume_data)
                    sources_used.append("resume")
                    logger.info("EXTRACT: Resume loaded")
                else:
                    logger.warning("EXTRACT: Resume parsed but had no useful data")
            except Exception as e:
                logger.warning(f"EXTRACT Resume failed: {e}")

        if github_username:
            try:
                github_data = fetch_github(github_username)
                if github_data and _has_useful_data(github_data):
                    raw_records.append(github_data)
                    sources_used.append("github")
                    logger.info(f"EXTRACT: GitHub data loaded for '{github_username}'")
                else:
                    logger.warning(f"EXTRACT: GitHub returned no useful data for '{github_username}'")
            except Exception as e:
                logger.warning(f"EXTRACT GitHub failed: {e}")

        if not raw_records:
            logger.info("No valid source data — returning empty profile")
            return apply_config(empty_profile, config) if config else empty_profile

        # ============================================================
        # 3. NORMALIZE
        # BUG FIX: skills confidence uses per-source base, NOT hardcoded 0.8
        # resume=0.75, csv=0.65, github=0.6 — BEFORE multi-source bonus
        # ============================================================
        normalized_records = []
        for rec in raw_records:
            norm = dict(rec)
            source = rec.get("_source", "unknown")

            # Emails
            raw_emails = list(rec.get("emails") or [])
            if rec.get("email"):
                raw_emails.append(rec["email"])
            norm_emails = []
            for e in raw_emails:
                ne = normalize_email(str(e))
                if ne:
                    norm_emails.append(ne)
                else:
                    norm["_malformed_emails"] = True
            norm["emails"] = list(set(norm_emails))

            # Phones
            raw_phones = list(rec.get("phones") or [])
            if rec.get("phone"):
                raw_phones.append(rec["phone"])
            norm_phones = []
            for p in raw_phones:
                np_val = normalize_phone(str(p))
                if np_val:
                    norm_phones.append(np_val)
                else:
                    norm["_malformed_phones"] = True
            norm["phones"] = list(set(norm_phones))

            # Location
            loc = rec.get("location")
            if isinstance(loc, str) and loc.strip():
                norm["location"] = normalize_location(loc)
            elif isinstance(loc, dict):
                country = normalize_country(loc.get("country")) if loc.get("country") else None
                norm["location"] = {
                    "city": loc.get("city"),
                    "region": loc.get("region"),
                    "country": country
                }

            # Experience dates
            if isinstance(rec.get("experience"), list):
                norm_exp = []
                for exp in rec["experience"]:
                    norm_exp.append({
                        "company": exp.get("company"),
                        "title": exp.get("title"),
                        "start": normalize_date(exp.get("start")),
                        "end": normalize_date(exp.get("end")) if exp.get("end") else None,
                        "summary": exp.get("summary")
                    })
                norm["experience"] = norm_exp

            # Skills — base confidence by source, NOT hardcoded
            # BUG FIX: was `0.8 if source == "resume"` → hardcoded everything to 80%
            SOURCE_BASE_CONF = {
                "resume": 0.75,
                "recruiter_csv": 0.65,
                "github": 0.60,
            }
            base_conf = SOURCE_BASE_CONF.get(source, 0.60)

            if isinstance(rec.get("skills"), list):
                norm_skills = []
                for sk in rec["skills"]:
                    if isinstance(sk, dict):
                        name = canonicalize_skill(sk.get("name", ""))
                        conf = sk.get("confidence", base_conf)
                        srcs = sk.get("sources", [source])
                    else:
                        name = canonicalize_skill(str(sk))
                        conf = base_conf
                        srcs = [source]
                    if name:
                        norm_skills.append({"name": name, "confidence": conf, "sources": srcs})
                norm["skills"] = norm_skills

            # Pass certifications through unchanged
            if "certifications" not in norm:
                norm["certifications"] = rec.get("certifications", [])

            # Pass links through
            if "links" not in norm or not isinstance(norm.get("links"), dict):
                norm["links"] = rec.get("links", {
                    "linkedin": None, "github": None, "portfolio": None, "other": []
                })

            normalized_records.append(norm)

        # ============================================================
        # 3.5 GROUP RECORDS (record linkage — same candidate from multiple sources)
        # ============================================================
        groups = []
        for rec in normalized_records:
            rec_emails = set(rec.get("emails", []))
            rec_name = (rec.get("full_name") or rec.get("name") or "").lower().strip()

            matched_idx = -1
            for i, grp in enumerate(groups):
                grp_emails = set()
                grp_names = set()
                for g in grp:
                    grp_emails.update(g.get("emails", []))
                    n = (g.get("full_name") or g.get("name") or "").lower().strip()
                    if n:
                        grp_names.add(n)

                if (rec_emails and rec_emails & grp_emails) or (rec_name and rec_name in grp_names):
                    matched_idx = i
                    break

            if matched_idx != -1:
                groups[matched_idx].append(rec)
            else:
                groups.append([rec])

        # ============================================================
        # 4–8. MERGE → CONFIDENCE → SCHEMA → VALIDATE → PROJECT
        # ============================================================
        final_profiles = []

        for group_records in groups:
            # 4. MERGE
            merged = merge_sources(group_records)

            # Pass certifications through merge (merger may not handle it)
            if not merged.get("certifications"):
                all_certs = []
                for r in group_records:
                    all_certs.extend(r.get("certifications") or [])
                merged["certifications"] = list(dict.fromkeys(all_certs))  # dedup, preserve order
                if merged["certifications"]:
                    merged.setdefault("provenance", []).append({
                        "field": "certifications",
                        "source": "resume",
                        "method": "direct_extraction"
                    })

            # 5. CONFIDENCE
            group_sources = list(set(r.get("_source") for r in group_records if r.get("_source")))
            merged = score_confidence(merged, group_sources)

            # Ensure links dict is complete
            links = merged.get("links") or {}
            if not isinstance(links, dict):
                links = {}
            merged["links"] = {
                "linkedin": links.get("linkedin"),
                "github": links.get("github"),
                "portfolio": links.get("portfolio"),
                "other": links.get("other") or []
            }

            # 6. MAP TO SCHEMA
            # BUG FIX: pop certifications before Pydantic (it may not be in schema)
            # then re-attach after model_dump()
            certifications = merged.pop("certifications", [])

            try:
                profile = CandidateProfile(**merged)
                canonical_dict = profile.model_dump()
            except Exception as e:
                logger.warning(f"Schema mapping error: {e} — using merged dict directly")
                canonical_dict = {k: v for k, v in merged.items() if not k.startswith("_")}

            # Re-attach certifications to output
            canonical_dict["certifications"] = certifications or []

            # 7. VALIDATE
            warnings = validate_profile(canonical_dict)
            if warnings:
                canonical_dict["_warnings"] = warnings
                logger.warning(f"VALIDATE warnings: {warnings}")

            # 8. PROJECT
            if config:
                try:
                    projected = apply_config(canonical_dict, config)
                    if warnings:
                        projected["_warnings"] = warnings
                    # Preserve certifications in projected output if not explicitly excluded
                    if "certifications" not in projected and certifications:
                        projected["certifications"] = certifications
                    final_profiles.append(projected)
                except Exception as e:
                    logger.warning(f"Projection error: {e} — returning canonical")
                    final_profiles.append(canonical_dict)
            else:
                final_profiles.append(canonical_dict)

        if not final_profiles:
            return empty_profile

        return final_profiles if len(final_profiles) > 1 else final_profiles[0]

    except Exception as e:
        logger.error(f"PIPELINE FAILURE: {e}", exc_info=True)
        return {"error": str(e), "partial": {}}