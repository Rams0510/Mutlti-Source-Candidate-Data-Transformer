import os
import re
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger("pipeline")

SKILLS_PATTERN = r'(?:technical\s+)?skills|competencies|expertise|technologies'
EXPERIENCE_PATTERN = r'(?:professional\s+|work\s+|internship\s+|relevant\s+)?experience(?:s)?'
EDUCATION_PATTERN = r'education|academic\s+background|academic\s+qualifications'
CERTIFICATIONS_PATTERN = r'certificat(?:e|es|ion|ions)|licenses?\s*(?:&|and)?\s*certifications?'
PROJECTS_PATTERN = r'projects?|personal\s+projects?|academic\s+projects?'

def parse_resume(filepath: str) -> dict:
    """
    Parses a PDF or TXT resume.
    Uses pdfminer.six for PDF files.
    Extracts name, emails, phones, headline, skills, years of experience, experience blocks, and education.
    Always returns a dictionary and never crashes, degrading gracefully.
    """
    result = {
        "_source": "resume",
        "full_name": None,
        "emails": [],
        "phones": [],
        "headline": None,
        "skills": [],
        "years_experience": None,
        "experience": [],
        "education": [],
        "certifications": [],
        "links": {
            "linkedin": None,
            "github": None,
            "portfolio": None,
            "other": []
        }
    }
    
    if not filepath or not os.path.exists(filepath):
        logger.warning(f"Resume file not found: {filepath}")
        return result
        
    try:
        _, ext = os.path.splitext(filepath.lower())
        text = ""
        
        if ext == ".pdf":
            try:
                from pdfminer.high_level import extract_text
                from pdfminer.layout import LAParams
                
                # Use LAParams to better preserve reading order for multi-column layouts
                laparams = LAParams(
                    line_margin=0.5,
                    word_margin=0.1,
                    char_margin=2.0,
                    boxes_flow=0.5  # helps with column detection
                )
                text = extract_text(filepath, laparams=laparams)
            except Exception as e:
                logger.warning(f"PDF extraction error: {e}")
                return result
        else:
            try:
                with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                    text = f.read()
            except Exception as e:
                logger.warning(f"TXT read error: {e}")
                return result
                
        if not text or not text.strip():
            logger.warning(f"Resume text is empty: {filepath}")
            return result
            
        # Standardize lines
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        
        # 1. Full name: first non-empty line (2-4 words, no special chars, only letters/spaces)
        for line in lines[:5]:
            words = line.split()
            if 2 <= len(words) <= 4 and re.match(r"^[a-zA-Z\s]+$", line):
                result["full_name"] = line
                break
                
        # 2. Emails: all email-pattern strings
        email_pattern = r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+"
        emails = re.findall(email_pattern, text)
        result["emails"] = sorted(list(set(emails)))
        
        # 3. Phones: all phone-pattern strings
        phone_pattern = r"\+?\d[\d\s\(\)\.\-]{8,}\d"
        phones = re.findall(phone_pattern, text)
        cleaned_phones = []
        for p in phones:
            digits = re.sub(r"\D", "", p)
            if 7 <= len(digits) <= 15:
                cleaned_phones.append(p.strip())
        result["phones"] = sorted(list(set(cleaned_phones)))
        
        # ========== EXTRACT HEADLINE ==========
        result["headline"] = None

        # Strategy: Look at the PROFILE/SUMMARY section first (most reliable)
        profile_pattern = r'profile|summary|objective|about\s+me'
        profile_idx = None
        for i, line in enumerate(lines):
            if re.search(profile_pattern, line, re.IGNORECASE) and len(line) < 30:
                profile_idx = i
                break

        if profile_idx is not None and profile_idx + 1 < len(lines):
            # Take first sentence of profile/summary section as headline
            next_line = lines[profile_idx + 1]
            if next_line and len(next_line) < 200:
                # Take first sentence only (up to first period)
                first_sentence = next_line.split('.')[0].strip()
                if len(first_sentence) > 10:
                    result["headline"] = first_sentence + "."

        # Fallback: if no profile section, look for job title near name 
        # (only if it's a SHORT, CLEAN line with no contact symbols)
        if not result["headline"] and result["full_name"]:
            name_idx = None
            for i, line in enumerate(lines[:5]):
                if result["full_name"] in line:
                    name_idx = i
                    break
            
            if name_idx is not None and name_idx + 1 < len(lines):
                candidate_line = lines[name_idx + 1]
                # Must be short, no @ or digit-heavy contact info, no URLs
                has_contact_chars = any(c in candidate_line for c in ['@', 'http', 'linkedin', 'github'])
                has_many_digits = sum(c.isdigit() for c in candidate_line) > 3
                
                if not has_contact_chars and not has_many_digits and 10 < len(candidate_line) < 100:
                    result["headline"] = candidate_line
                
        # 5. Links
        urls = re.findall(r"https?://[^\s]+", text)
        for url in urls:
            url_clean = url.rstrip(",.)(]")
            if "linkedin.com" in url_clean:
                result["links"]["linkedin"] = url_clean
            elif "github.com" in url_clean:
                result["links"]["github"] = url_clean
            elif "portfolio" in url_clean or "blog" in url_clean:
                result["links"]["portfolio"] = url_clean
            else:
                if url_clean not in result["links"]["other"]:
                    result["links"]["other"].append(url_clean)

        lower_text = text.lower()
        
        # 6. Skills: items under "Skills" heading
        skills_header_match = re.search(r"^\s*(?:" + SKILLS_PATTERN + r")\s*$", text, re.MULTILINE | re.IGNORECASE)
        if skills_header_match:
            start_pos = skills_header_match.end()
            skills_sub = text[start_pos:]
            end_match = re.search(r"^\s*(?:" + EXPERIENCE_PATTERN + r"|" + EDUCATION_PATTERN + r"|work history|academic)\s*$", skills_sub, re.MULTILINE | re.IGNORECASE)
            if end_match:
                skills_sub = skills_sub[:end_match.start()]
                
            skills_raw = []
            for item in re.split(r"[,\n•|]|\s{3,}", skills_sub):
                item_clean = item.strip()
                if item_clean and len(item_clean) < 35 and not re.search(r"\d", item_clean):
                    skills_raw.append(item_clean)
            result["skills"] = sorted(list(set(skills_raw)))
            
        # 7. Years of experience (explicitly stated)
        y_exp_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:\+|plus)?\s*years?\s+of\s+(?:work\s+)?experience", lower_text)
        if y_exp_match:
            result["years_experience"] = float(y_exp_match.group(1))

        # ========== EXTRACT EXPERIENCE (alternative bullet-based format) ==========
        exp_idx = None
        for i, line in enumerate(lines):
            if re.search(r'^\s*(?:' + EXPERIENCE_PATTERN + r')\s*$', line, re.IGNORECASE) and len(line) < 40:
                exp_idx = i
                break

        if exp_idx is not None:
            exp_lines = lines[exp_idx + 1:]
            current_job = None
            
            for line in exp_lines:
                # Stop at next major section
                if re.search(r'^\s*(?:' + EDUCATION_PATTERN + r'|' + SKILLS_PATTERN + r'|' + PROJECTS_PATTERN + r'|' + CERTIFICATIONS_PATTERN + r')\s*$', line, re.IGNORECASE) and len(line) < 30:
                    break
                
                # Date pattern like "10/2025 - 12/2025" or "Jan 2024 - Present"
                date_regex = r"((?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{4}|\d{4}-\d{2}|\d{1,2}/\d{4}|\d{4})"
                date_range_match = re.search(date_regex + r"\s*[-–—]\s*(Present|" + date_regex + r")", line, re.IGNORECASE)
                
                # Job title line: "Title -Company" or "Title - Company" pattern
                title_company_match = re.match(r'^([A-Za-z][A-Za-z\s]+?)\s*[-–—]\s*([A-Za-z][A-Za-z\s]+)$', line)
                
                if title_company_match and not line.startswith(('•', '-', '*')):
                    if current_job:
                        result["experience"].append(current_job)
                    current_job = {
                        "company": title_company_match.group(2).strip(),
                        "title": title_company_match.group(1).strip(),
                        "start": None,
                        "end": None,
                        "summary": ""
                    }
                elif date_range_match and current_job:
                    current_job["start"] = date_range_match.group(1)
                    current_job["end"] = date_range_match.group(2) if date_range_match.group(2).lower() != "present" else None
                elif current_job and line.strip():
                    clean_line = re.sub(r'^[•\-\*\u2022]\s*', '', line).strip()
                    if clean_line and not date_range_match:
                        current_job["summary"] += (" " if current_job["summary"] else "") + clean_line
            
            if current_job:
                result["experience"].append(current_job)

        # Fallback to old experience logic if empty
        if not result["experience"]:
            exp_header_match = re.search(r"^\s*(?:" + EXPERIENCE_PATTERN + r"|work history|employment)\s*$", text, re.MULTILINE | re.IGNORECASE)
            if exp_header_match:
                start_pos = exp_header_match.end()
                exp_sub = text[start_pos:]
                end_match = re.search(r"^\s*(?:" + EDUCATION_PATTERN + r"|" + SKILLS_PATTERN + r"|academic)\s*$", exp_sub, re.MULTILINE | re.IGNORECASE)
                if end_match:
                    exp_sub = exp_sub[:end_match.start()]
                    
                exp_lines = [l.strip() for l in exp_sub.splitlines() if l.strip()]
                
                date_regex = r"((?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{4}|\d{4}-\d{2}|\d{2}/\d{4}|\d{4})"
                range_regex = date_regex + r"\s*(?:-|to)\s*(Present|" + date_regex + r")"
                
                i = 0
                while i < len(exp_lines):
                    line = exp_lines[i]
                    match = re.search(range_regex, line, re.IGNORECASE)
                    if match:
                        start_raw = match.group(1)
                        end_raw = match.group(2)
                        
                        line_no_dates = re.sub(range_regex, "", line, flags=re.IGNORECASE).strip("() ,|•-")
                        title = None
                        company = None
                        
                        parts = [p.strip() for p in re.split(r"[,|•-]", line_no_dates) if p.strip()]
                        if len(parts) >= 2:
                            company = parts[0]
                            title = parts[1]
                        elif len(parts) == 1:
                            company = parts[0]
                            if i > 0:
                                title = exp_lines[i-1]
                        else:
                            if i > 0:
                                prev_line = exp_lines[i-1]
                                prev_parts = [p.strip() for p in re.split(r"[,|•-]", prev_line) if p.strip()]
                                if len(prev_parts) >= 2:
                                    company = prev_parts[0]
                                    title = prev_parts[1]
                                else:
                                    company = prev_line
                                    
                        summary_sentences = []
                        j = i + 1
                        while j < len(exp_lines) and not re.search(range_regex, exp_lines[j], re.IGNORECASE) and len(summary_sentences) < 2:
                            if re.search(r"\b(?:education|skills)\b", exp_lines[j].lower()):
                                break
                            if j + 1 < len(exp_lines) and re.search(range_regex, exp_lines[j+1], re.IGNORECASE):
                                break
                            summary_sentences.append(exp_lines[j])
                            j += 1
                            
                        summary = " ".join(summary_sentences)
                        result["experience"].append({
                            "company": company,
                            "title": title,
                            "start": start_raw,
                            "end": end_raw if end_raw.lower() != "present" else None,
                            "summary": summary
                        })
                        i = j - 1
                    i += 1
                    
        # 9. Education: blocks under Education heading
        edu_header_match = re.search(r"^\s*(?:" + EDUCATION_PATTERN + r"|studies|degrees)\s*$", text, re.MULTILINE | re.IGNORECASE)
        if edu_header_match:
            start_pos = edu_header_match.end()
            edu_sub = text[start_pos:]
            end_match = re.search(r"^\s*(?:" + EXPERIENCE_PATTERN + r"|" + SKILLS_PATTERN + r"|projects)\s*$", edu_sub, re.MULTILINE | re.IGNORECASE)
            if end_match:
                edu_sub = edu_sub[:end_match.start()]
                
            edu_lines = [l.strip() for l in edu_sub.splitlines() if l.strip()]
            for line in edu_lines:
                year_match = re.search(r"\b(19\d{2}|20\d{2})\b", line)
                end_year = int(year_match.group(1)) if year_match else None
                line_no_year = re.sub(r"\b(19\d{2}|20\d{2})\b", "", line).strip("() ,|•-")
                
                parts = [p.strip() for p in re.split(r"[,|•-]", line_no_year) if p.strip()]
                institution = None
                degree = None
                field = None
                
                degree_keywords = ["bs", "b.s.", "bachelor", "ms", "m.s.", "master", "phd", "ph.d.", "btech", "b.tech", "mtech", "m.tech", "ba", "b.a."]
                for p in parts:
                    p_lower = p.lower()
                    if any(dk in p_lower for dk in degree_keywords):
                        degree = p
                        field_match = re.search(r"(?:in|of)\s+([a-zA-Z\s]+)", p, re.IGNORECASE)
                        if field_match:
                            field = field_match.group(1).strip()
                    elif any(k in p_lower for k in ["university", "college", "institute", "school"]):
                        institution = p
                        
                if not institution and len(parts) > 0:
                    for p in parts:
                        if p != degree:
                            institution = p
                            break
                if not field and len(parts) > 0:
                    for p in parts:
                        if p != degree and p != institution:
                            field = p
                            break
                            
                if institution or degree or field or end_year:
                    result["education"].append({
                        "institution": institution,
                        "degree": degree,
                        "field": field,
                        "end_year": end_year
                    })

        # ========== EXTRACT CERTIFICATIONS ==========
        result["certifications"] = []

        cert_match = None
        for i, line in enumerate(lines):
            if re.search(r'^\s*(?:' + CERTIFICATIONS_PATTERN + r')\s*$', line, re.IGNORECASE) and len(line) < 40:
                cert_match = i
                break

        if cert_match is not None:
            cert_lines = lines[cert_match + 1:]
            
            for line in cert_lines[:15]:  # Check next 15 lines
                # Stop at next section header
                if re.search(r'^\s*(?:' + EDUCATION_PATTERN + r'|' + EXPERIENCE_PATTERN + r'|' + SKILLS_PATTERN + r'|' + PROJECTS_PATTERN + r')\s*$', line, re.IGNORECASE) and len(line) < 30:
                    break
                
                # Skip empty or very long lines (likely not a cert entry)
                if line and len(line) < 150:
                    # Clean bullet points
                    clean_line = re.sub(r'^[•\-\*\u2022]\s*', '', line).strip()
                    if clean_line:
                        result["certifications"].append(clean_line)

        # Inferred Years of Experience
        if result["years_experience"] is None and result["experience"]:
            from pipeline.normalizer import normalize_date
            total_months = 0
            for exp in result["experience"]:
                start = exp.get("start")
                end = exp.get("end")
                s_norm = normalize_date(start)
                e_norm = normalize_date(end) if end else "2026-06"
                if s_norm:
                    try:
                        s_yr = int(s_norm[:4])
                        s_mo = int(s_norm[5:7]) if len(s_norm) > 4 else 1
                        e_yr = int(e_norm[:4])
                        e_mo = int(e_norm[5:7]) if len(e_norm) > 4 else 6
                        months = (e_yr - s_yr) * 12 + (e_mo - s_mo)
                        if months > 0:
                            total_months += months
                    except Exception:
                        pass
            if total_months > 0:
                result["years_experience"] = round(total_months / 12, 1)
                
    except Exception as e:
        logger.warning(f"Error parsing resume {filepath}: {e}")
        # Never raise, return empty container
        pass
        
    return result
