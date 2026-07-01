<!-- # Candidate Data Transformer — Eightfold Engineering Intern Assignment

## What it does
Ingests candidate data from Recruiter CSV, Resume PDF/TXT, and GitHub profile URL.
Normalizes, merges, and deduplicates into one canonical profile per candidate.
Tracks provenance and confidence for every field. Supports runtime output config.

## Pipeline Architecture
Detect → Extract → Normalize → Merge → Confidence → Project → Validate

| Stage | What it does |
|---|---|
| Detect | Checks which input sources are present |
| Extract | Calls the right parser for each source |
| Normalize | Phones→E.164, dates→YYYY-MM, skills→canonical, country→ISO-3166 |
| Merge | Conflict resolution by priority, provenance tracked |
| Confidence | Per-field + overall weighted confidence score |
| Project | Applies runtime config: rename, subset, missing policy |
| Validate | Pydantic schema validation, warns on errors |

## Sources Supported
- Recruiter CSV (structured)
- Resume PDF or TXT (unstructured)
- GitHub profile via REST API (unstructured)

## How to Run

### Setup
```
pip install -r requirements.txt
```

### CLI — default output
```
python cli.py --csv sample_inputs/recruiter.csv --resume sample_inputs/resume.txt --github torvalds
```

### CLI — with custom config
```
python cli.py --csv sample_inputs/recruiter.csv --resume sample_inputs/resume.txt --github torvalds --config config/output_config.json --output sample_outputs/custom_config_output.json --pretty
```

### CLI — validate only
```
python cli.py --csv sample_inputs/recruiter.csv --validate-only
```

### UI (FastAPI)
```
uvicorn main:app --reload
```
Open http://localhost:8000

### Tests
```
python -m pytest tests/ -v
```

## Design Decisions
- **resume > csv > github priority for name**: Resumes are self-authored and most accurate; CSV data is often recruiter-entered and may have typos; GitHub name is public-facing and may be a handle.
- **E.164 for phones**: Unambiguous, internationally parseable, machine-readable — `+14155551212` is unambiguous regardless of region.
- **sha256[:12] for candidate_id**: Deterministic given the same input, collision-resistant at 12 hex chars (48 bits), stores no PII in the ID itself.
- **Weighted confidence**: Email (0.20) and skills (0.20) weighted highest as most signal-rich fields; a missing email is a stronger signal of incompleteness than a missing headline.
- **Provenance on every field**: Auditable, traceable, explainable to downstream systems and hiring reviewers.
- **Strict section heading regex**: Resume sections are matched on whole lines (`^Skills$`) rather than anywhere in text, preventing false matches inside body sentences like "3 years of experience".

## Edge Cases Handled
- **Missing/empty source**: Pipeline continues, other sources fill the profile; overall_confidence degrades proportionally.
- **Malformed phone**: Stored as `None` rather than garbage; confidence scores penalize missing phones vs. valid ones.
- **Conflicting names across sources**: Priority-based resolution (resume > csv > github), conflict logged in provenance method field.
- **Unknown skill name**: Title-cased and stored as-is — values are never invented or hallucinated.
- **GitHub rate limit (403)**: Graceful fallback, warning logged, pipeline continues with remaining sources.
- **All sources missing**: Returns empty profile with `overall_confidence: 0.0`, no crash.
- **CSV row with all null fields**: Row skipped entirely, not added to raw records.
- **on_missing="error"** + required field null: Raises `ValueError` with field name, surfaces cleanly as `{"error": ...}` in CLI and API.

## Descoped
- **LinkedIn URL scraping**: Requires auth or Selenium; out of scope for this assignment.
- **ML-based NER for resume parsing**: Regex heuristics are sufficient for structured resumes and avoid a large model dependency.
- **Cross-file candidate deduplication**: Single candidate per pipeline run assumed; multi-candidate dedup is a separate product concern. -->

# Multi-Source Candidate Data Transformer

> **Eightfold AI – Engineering Intern Assignment**

An end-to-end candidate data transformation pipeline that ingests recruiter CSV files, resumes (PDF/TXT), and GitHub profiles to generate a unified canonical candidate profile with provenance tracking, confidence scoring, configurable output projection, and export support.

---

## Overview

Recruiters often receive candidate information from multiple sources such as ATS exports, resumes, and GitHub profiles. These sources frequently contain incomplete, duplicate, or conflicting information.

This project transforms heterogeneous candidate data into a single standardized profile by:

- Parsing structured recruiter CSV files
- Extracting information from unstructured resumes
- Enriching candidate information using GitHub
- Normalizing and merging all sources
- Tracking provenance for every extracted field
- Computing confidence scores
- Supporting runtime output configuration
- Exporting results as JSON and CSV

---

## Features

- Recruiter CSV ingestion
- Resume parsing (PDF & TXT)
- GitHub profile enrichment
- Canonical candidate profile generation
- Data normalization
- Conflict resolution
- Provenance tracking
- Confidence scoring
- Runtime output configuration
- JSON & CSV export
- FastAPI backend
- React frontend
- Command Line Interface (CLI)
- Automated test suite

---

# Pipeline Architecture

```
Recruiter CSV
        │
Resume PDF/TXT
        │
GitHub Profile
        │
        ▼
 ┌─────────────────────┐
 │ Source Detection    │
 └─────────────────────┘
            │
            ▼
 ┌─────────────────────┐
 │ Data Extraction     │
 └─────────────────────┘
            │
            ▼
 ┌─────────────────────┐
 │ Data Normalization  │
 └─────────────────────┘
            │
            ▼
 ┌─────────────────────┐
 │ Merge & Deduplicate │
 └─────────────────────┘
            │
            ▼
 ┌─────────────────────┐
 │ Confidence Scoring  │
 └─────────────────────┘
            │
            ▼
 ┌─────────────────────┐
 │ Output Projection   │
 └─────────────────────┘
            │
            ▼
 ┌─────────────────────┐
 │ Schema Validation   │
 └─────────────────────┘
            │
            ▼
     Canonical Profile
```

---

# Supported Input Sources

| Source | Type |
|---------|------|
| Recruiter CSV | Structured |
| Resume PDF | Unstructured |
| Resume TXT | Unstructured |
| GitHub Profile | REST API |

---

# Canonical Profile

The generated profile contains:

- Candidate ID
- Full Name
- Email
- Phone Number
- Location
- Headline
- GitHub Profile
- Skills
- Experience
- Education
- Certifications
- Provenance
- Overall Confidence Score

---

# Technology Stack

## Backend

- Python 3.11+
- FastAPI
- Pydantic
- Pandas
- pdfminer.six

## Frontend

- React
- HTML
- CSS
- JavaScript

## Other

- GitHub REST API
- Pytest

---

# Project Structure

```
candidate-transformer/

├── backend/
│   ├── pipeline/
│   ├── sources/
│   ├── models/
│   ├── main.py
│   └── cli.py
│
├── frontend/
│   ├── src/
│   └── public/
│
├── config/
│
├── sample_inputs/
│
├── sample_outputs/
│
├── tests/
│
├── requirements.txt
│
└── README.md
```

---

# How to Run

## 1. Clone Repository

```bash
git clone https://github.com/<your-username>/candidate-transformer.git

cd candidate-transformer
```

---

## 2. Install Dependencies

```bash
pip install -r requirements.txt
```

---

## 3. Run Backend

```bash
uvicorn main:app --reload
```

Backend runs at

```
http://localhost:8000
```

---

## 4. Run Frontend

```bash
npm install

npm start
```

Frontend runs at

```
http://localhost:3000
```

---

## CLI Usage

### Default Output

```bash
python cli.py \
--csv sample_inputs/recruiter.csv \
--resume sample_inputs/resume.pdf \
--github torvalds
```

---

### Custom Output Configuration

```bash
python cli.py \
--csv sample_inputs/recruiter.csv \
--resume sample_inputs/resume.pdf \
--github torvalds \
--config config/output_config.json \
--output sample_outputs/custom_output.json \
--pretty
```

---

### Validate Only

```bash
python cli.py \
--csv sample_inputs/recruiter.csv \
--validate-only
```

---

# Runtime Output Configuration

Users can customize the generated profile by providing a runtime JSON configuration.

Supported features:

- Select fields
- Rename fields
- Change data types
- Missing value policy
- Output projection

Example:

```json
{
  "fields": [
    {
      "path": "full_name"
    },
    {
      "path": "emails[0]",
      "rename": "primary_email"
    }
  ]
}
```

---

# Design Decisions

### Source Priority

```
Resume
    ↓
Recruiter CSV
    ↓
GitHub
```

The resume is considered the primary source because it is self-authored by the candidate.

---

### Candidate ID

Candidate IDs are generated using SHA-256 hashing to produce deterministic, non-PII identifiers.

---

### Phone Normalization

Phone numbers are normalized into E.164 format to ensure consistency across different countries.

---

### Provenance Tracking

Every extracted field records:

- Source
- Extraction Method

This makes the pipeline transparent and auditable.

---

### Confidence Scoring

Each field receives an individual confidence score.

The overall profile confidence is computed using weighted aggregation based on source reliability and field completeness.

---

# Edge Cases Handled

- Missing recruiter CSV
- Missing resume
- Missing GitHub profile
- Empty files
- Duplicate information
- Conflicting values
- Invalid phone numbers
- GitHub API failures
- Missing required fields
- Empty candidate records
- Partial profile generation

---

# Testing

Run the complete test suite:

```bash
pytest tests -v
```

---

# Sample Inputs

The repository includes sample files for testing:

```
sample_inputs/

recruiter.csv

resume.pdf

resume.txt
```

---

# Sample Outputs

Generated outputs include:

```
sample_outputs/

canonical_profile.json

canonical_profile.csv

custom_output.json
```

---

# Future Improvements

- LinkedIn integration
- OCR support for scanned resumes
- AI-based resume parsing using NLP
- Multi-candidate deduplication
- Additional job portal integrations
- Resume ranking and matching

---

# Demo Video

Demo Video:

```
<Insert Demo Video Link Here>
```

---

# Author

**Ramya Thopukonda**

Institute of Aeronautical Engineering

B.Tech – Computer Science & Engineering(Data Sciencec)

GitHub: https://github.com/Rams0510

---

# License

This project was developed as part of the **Eightfold AI Engineering Intern Assignment** and is intended for evaluation purposes.
