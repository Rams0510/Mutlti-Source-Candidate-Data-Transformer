from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Any

class Location(BaseModel):
    city: Optional[str] = None
    region: Optional[str] = None
    country: Optional[str] = None

class Links(BaseModel):
    linkedin: Optional[str] = None
    github: Optional[str] = None
    portfolio: Optional[str] = None
    other: List[str] = Field(default_factory=list)

class Skill(BaseModel):
    name: str
    confidence: float
    sources: List[str] = Field(default_factory=list)

class Experience(BaseModel):
    company: Optional[str] = None
    title: Optional[str] = None
    start: Optional[str] = None
    end: Optional[str] = None
    summary: Optional[str] = None

class Education(BaseModel):
    institution: Optional[str] = None
    degree: Optional[str] = None
    field: Optional[str] = None
    end_year: Optional[int] = None

class Provenance(BaseModel):
    field: str
    source: str
    method: str

class CandidateProfile(BaseModel):
    candidate_id: str
    full_name: Optional[str] = None
    emails: List[str] = Field(default_factory=list)
    phones: List[str] = Field(default_factory=list)
    location: Location = Field(default_factory=Location)
    links: Links = Field(default_factory=Links)
    headline: Optional[str] = None
    years_experience: Optional[float] = None
    skills: List[Skill] = Field(default_factory=list)
    experience: List[Experience] = Field(default_factory=list)
    education: List[Education] = Field(default_factory=list)
    certifications: List[str] = Field(default_factory=list)
    provenance: List[Provenance] = Field(default_factory=list)
    overall_confidence: float = 0.0

    model_config = {
        "json_schema_extra": {
            "example": {
                "candidate_id": "a1b2c3d4e5f6",
                "full_name": "Linus Torvalds",
                "emails": ["torvalds@osdl.org"],
                "phones": ["+14155551212"],
                "location": {
                    "city": "Portland",
                    "region": "OR",
                    "country": "US"
                },
                "links": {
                    "linkedin": None,
                    "github": "https://github.com/torvalds",
                    "portfolio": "https://linuxfoundation.org",
                    "other": []
                },
                "headline": "Creator of Linux and Git",
                "years_experience": 35.0,
                "skills": [
                    {
                        "name": "C",
                        "confidence": 0.95,
                        "sources": ["github", "resume"]
                    },
                    {
                        "name": "Git",
                        "confidence": 0.95,
                        "sources": ["github"]
                    }
                ],
                "experience": [
                    {
                        "company": "Linux Foundation",
                        "title": "Fellow",
                        "start": "2003-01",
                        "end": None,
                        "summary": "Actively maintaining the Linux kernel development pipeline."
                    }
                ],
                "education": [
                    {
                        "institution": "University of Helsinki",
                        "degree": "M.S.",
                        "field": "Computer Science",
                        "end_year": 1996
                    }
                ],
                "provenance": [
                    {
                        "field": "full_name",
                        "source": "github",
                        "method": "direct_extraction"
                    }
                ],
                "overall_confidence": 0.9
            }
        }
    }
