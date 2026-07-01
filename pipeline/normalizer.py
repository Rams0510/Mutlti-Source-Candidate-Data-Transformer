import re
import phonenumbers
from typing import Optional, Dict, Any

def normalize_phone(raw: Any) -> Optional[str]:
    """
    Normalizes phone numbers to E.164 format using phonenumbers library.
    Default region US. Returns None if unparseable/invalid.
    """
    if not raw:
        return None
    raw_str = str(raw).strip()
    
    # Try parsing with US region by default
    try:
        parsed = phonenumbers.parse(raw_str, "US")
        if phonenumbers.is_valid_number(parsed):
            return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
    except Exception:
        pass
        
    # Try parsing with IN region (common in testing)
    try:
        parsed = phonenumbers.parse(raw_str, "IN")
        if phonenumbers.is_valid_number(parsed):
            return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
    except Exception:
        pass
        
    # Try parsing with international code (starts with +)
    if raw_str.startswith("+"):
        try:
            parsed = phonenumbers.parse(raw_str, None)
            if phonenumbers.is_valid_number(parsed):
                return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
        except Exception:
            pass
            
    return None

def normalize_email(raw: Any) -> Optional[str]:
    """
    Normalizes email addresses (lowercase, strip whitespace).
    Returns None if no '@' with a dot after it in domain part.
    """
    if not raw:
        return None
    raw_str = str(raw).strip().lower()
    
    if "@" not in raw_str:
        return None
    parts = raw_str.split("@")
    if len(parts) != 2:
        return None
    domain = parts[1]
    if "." not in domain or domain.startswith(".") or domain.endswith("."):
        return None
        
    return raw_str

def normalize_date(raw: Any) -> Optional[str]:
    """
    Accepts: 'Jan 2022', 'January 2022', '2022-01', '01/2022', '2022'.
    Returns: YYYY-MM or YYYY format. Returns None if unparseable.
    """
    if not raw:
        return None
    raw_str = str(raw).strip()
    
    # Match YYYY-MM
    match_ym = re.match(r"^(\d{4})-(\d{2})$", raw_str)
    if match_ym:
        year, month = match_ym.groups()
        if 1 <= int(month) <= 12:
            return f"{year}-{month}"
            
    # Match MM/YYYY or M/YYYY
    match_my = re.match(r"^(\d{1,2})/(\d{4})$", raw_str)
    if match_my:
        m, y = match_my.groups()
        if 1 <= int(m) <= 12:
            return f"{y}-{int(m):02d}"
            
    # Match Month YYYY or YYYY Month
    month_names = {
        "jan": "01", "january": "01",
        "feb": "02", "february": "02",
        "mar": "03", "march": "03",
        "apr": "04", "april": "04",
        "may": "05",
        "jun": "06", "june": "06",
        "jul": "07", "july": "07",
        "aug": "08", "august": "08",
        "sep": "09", "september": "09",
        "oct": "10", "october": "10",
        "nov": "11", "november": "11",
        "dec": "12", "december": "12"
    }
    
    words = re.findall(r"\b[a-zA-Z]+\b|\b\d{4}\b", raw_str)
    if len(words) == 2:
        year = None
        month = None
        for w in words:
            if w.isdigit() and len(w) == 4:
                year = w
            elif w.lower() in month_names:
                month = month_names[w.lower()]
        if year and month:
            return f"{year}-{month}"
            
    # Match YYYY
    match_y = re.match(r"^(\d{4})$", raw_str)
    if match_y:
        return raw_str
        
    return None

def normalize_country(raw: Any) -> Optional[str]:
    """
    Maps 15+ country names/abbreviations to ISO-3166 alpha-2 country codes.
    """
    if not raw:
        return None
    raw_str = str(raw).strip().lower()
    
    country_map = {
        "india": "IN", "in": "IN",
        "usa": "US", "us": "US", "united states": "US", "united states of america": "US", "u.s.a.": "US", "u.s.": "US",
        "united kingdom": "GB", "uk": "GB", "u.k.": "GB", "great britain": "GB", "gb": "GB",
        "canada": "CA", "ca": "CA",
        "germany": "DE", "de": "DE", "deutschland": "DE",
        "france": "FR", "fr": "FR",
        "japan": "JP", "jp": "JP",
        "china": "CN", "cn": "CN",
        "australia": "AU", "au": "AU",
        "brazil": "BR", "br": "BR",
        "singapore": "SG", "sg": "SG",
        "netherlands": "NL", "nl": "NL",
        "switzerland": "CH", "ch": "CH",
        "sweden": "SE", "se": "SE",
        "ireland": "IE", "ie": "IE"
    }
    
    return country_map.get(raw_str)

def normalize_location(raw: Any) -> Dict[str, Optional[str]]:
    """
    Parses 'City, Region, Country' or 'City, Country' location strings.
    Applies country code normalization.
    """
    result = {
        "city": None,
        "region": None,
        "country": None
    }
    
    if not raw:
        return result
        
    raw_str = str(raw).strip()
    parts = [p.strip() for p in raw_str.split(",")]
    
    if len(parts) == 3:
        result["city"] = parts[0]
        result["region"] = parts[1]
        result["country"] = normalize_country(parts[2]) or parts[2]
    elif len(parts) == 2:
        result["city"] = parts[0]
        result["country"] = normalize_country(parts[1]) or parts[1]
    elif len(parts) == 1:
        # Check if the single part is a country
        country_candidate = normalize_country(parts[0])
        if country_candidate:
            result["country"] = country_candidate
        else:
            result["city"] = parts[0]
            
    return result

def canonicalize_skill(raw: Any) -> str:
    """
    Maps 20+ skill abbreviations and aliases to their canonical name.
    Falls back to title-casing the raw string.
    """
    if not raw:
        return ""
    raw_str = str(raw).strip()
    key = raw_str.lower().replace(" ", "")
    
    skill_map = {
        "js": "JavaScript", "javascript": "JavaScript",
        "py": "Python", "python": "Python",
        "react.js": "React", "reactjs": "React", "react": "React",
        "ml": "Machine Learning", "machinelearning": "Machine Learning",
        "node": "Node.js", "nodejs": "Node.js", "node.js": "Node.js",
        "postgres": "PostgreSQL", "postgresql": "PostgreSQL",
        "ts": "TypeScript", "typescript": "TypeScript",
        "k8s": "Kubernetes", "kubernetes": "Kubernetes",
        "tf": "TensorFlow", "tensorflow": "TensorFlow",
        "aws": "AWS", "amazonwebservices": "AWS",
        "gcp": "GCP", "googlecloud": "GCP", "googlecloudplatform": "GCP",
        "docker": "Docker",
        "git": "Git",
        "html": "HTML", "html5": "HTML",
        "css": "CSS", "css3": "CSS",
        "java": "Java",
        "cpp": "C++", "c++": "C++",
        "rust": "Rust",
        "go": "Go", "golang": "Go",
        "pytorch": "PyTorch",
        "sql": "SQL",
        "nosql": "NoSQL",
        "mongodb": "MongoDB", "mongo": "MongoDB",
        "vue": "Vue.js", "vuejs": "Vue.js", "vue.js": "Vue.js",
        "angular": "Angular", "angularjs": "Angular"
    }
    
    return skill_map.get(key, raw_str.title())
