import pytest
import os
from pipeline.normalizer import (
    normalize_phone,
    normalize_email,
    normalize_date,
    canonicalize_skill
)
from sources.csv_source import parse_csv
from pipeline.merger import merge_sources
from pipeline.confidence import score_confidence
from pipeline.projector import apply_config
from main import run_pipeline

# 1. test_normalize_phone
def test_normalize_phone():
    assert normalize_phone("+1 415 555 2671") == "+14155552671"
    assert normalize_phone("+91 98765 43210") == "+919876543210"
    assert normalize_phone("not-a-phone-number") is None

# 2. test_normalize_email
def test_normalize_email():
    assert normalize_email("torvalds@osdl.org") == "torvalds@osdl.org"
    assert normalize_email("torvalds_at_osdl.org") is None
    assert normalize_email("  torvalds@osdl.org   ") == "torvalds@osdl.org"

# 3. test_normalize_date
def test_normalize_date():
    assert normalize_date("Jan 2022") == "2022-01"
    assert normalize_date("2022-01") == "2022-01"
    assert normalize_date("garbage_date") is None

# 4. test_canonicalize_skill
def test_canonicalize_skill():
    assert canonicalize_skill("js") == "JavaScript"
    assert canonicalize_skill("py") == "Python"
    assert canonicalize_skill("unknown_tool") == "Unknown_Tool"

# 5. test_csv_parser
def test_csv_parser():
    # Make sure we use a local path relative or exact
    csv_path = "sample_inputs/recruiter.csv"
    assert os.path.exists(csv_path), "Please create recruiter.csv sample file first"
    rows = parse_csv(csv_path)
    assert len(rows) == 3
    assert rows[0]["name"] == "Alice Smith"
    assert rows[1]["phones"] == []

# 6. test_merge_sources
def test_merge_sources():
    fake_csv = {
        "_source": "recruiter_csv",
        "name": "Alice T. Smith",
        "email": "alice@example.com",
        "phone": "+14155552671",
        "current_company": "Google",
        "title": "Software Engineer"
    }
    fake_resume = {
        "_source": "resume",
        "full_name": "Alice Smith",
        "emails": ["alice.smith@example.com", "alice@example.com"],
        "phones": ["+14155552671"],
        "headline": "Senior Software Engineer",
        "skills": [{"name": "Python", "confidence": 0.8, "sources": ["resume"]}],
        "experience": [],
        "education": []
    }
    
    merged = merge_sources([fake_csv, fake_resume])
    # emails unioned
    assert "alice@example.com" in merged["emails"]
    assert "alice.smith@example.com" in merged["emails"]
    assert len(merged["emails"]) == 2
    
    # name priority: resume > csv
    assert merged["full_name"] == "Alice Smith"
    
    # provenance lists both sources
    prov_sources = [p["source"] for p in merged["provenance"]]
    assert "resume" in prov_sources
    assert "recruiter_csv" in prov_sources

# 7. test_confidence_scorer
def test_confidence_scorer():
    merged_record = {
        "full_name": "Linus Torvalds",
        "emails": ["torvalds@osdl.org"],
        "phones": ["+14155551212"],
        "location": {
            "city": "Portland",
            "region": "OR",
            "country": "US"
        },
        "skills": [
            {"name": "C", "confidence": 0.9, "sources": ["github", "resume"]},
            {"name": "Git", "confidence": 0.8, "sources": ["github"]}
        ],
        "experience": [
            {"company": "Linux Foundation", "title": "Fellow", "start": "2003-01", "end": None, "summary": "Kernel."}
        ],
        "education": [
            {"institution": "University of Helsinki", "degree": "M.S.", "field": "CS", "end_year": 1996}
        ],
        "provenance": [
            {"field": "full_name", "source": "resume", "method": "direct_extraction"},
            {"field": "location", "source": "github", "method": "direct_extraction"},
            {"field": "emails", "source": "resume", "method": "direct_extraction"},
            {"field": "phones", "source": "resume", "method": "direct_extraction"}
        ],
        "overall_confidence": 0.0
    }
    
    scored = score_confidence(merged_record, ["resume", "github"])
    # should be well filled, overall_confidence >= 0.7
    assert scored["overall_confidence"] >= 0.7

# 8. test_projector_omit
def test_projector_omit():
    canonical = {
        "full_name": "Alice Smith",
        "emails": [],  # empty/missing
        "phones": ["+14155552671"],
        "overall_confidence": 0.85
    }
    config = {
        "fields": [
            {"path": "name", "from": "full_name", "type": "string"},
            {"path": "email", "from": "emails[0]", "type": "string"},
            {"path": "phone", "from": "phones[0]", "type": "string"}
        ],
        "include_confidence": True,
        "on_missing": "omit"
    }
    
    projected = apply_config(canonical, config)
    # emails[0] is missing, so 'email' should be omitted from output
    assert "name" in projected
    assert "phone" in projected
    assert "email" not in projected

# 9. test_projector_error
def test_projector_error():
    canonical = {
        "full_name": "Alice Smith",
        "emails": [],  # missing
        "phones": ["+14155552671"],
        "overall_confidence": 0.85
    }
    config = {
        "fields": [
            {"path": "name", "from": "full_name", "type": "string"},
            {"path": "email", "from": "emails[0]", "type": "string", "required": True},
            {"path": "phone", "from": "phones[0]", "type": "string"}
        ],
        "include_confidence": True,
        "on_missing": "error"
    }
    
    with pytest.raises(ValueError):
        apply_config(canonical, config)

# 10. test_full_pipeline_csv_only
def test_full_pipeline_csv_only():
    csv_path = "sample_inputs/recruiter.csv"
    inputs = {"csv_path": csv_path}
    
    result = run_pipeline(inputs)
    
    # If run_pipeline returns a list (grouped candidates), grab the first one
    if isinstance(result, list) and len(result) > 0:
        result = result[0]
        
    assert "candidate_id" in result
    assert isinstance(result["emails"], list)
    assert isinstance(result["overall_confidence"], float)
