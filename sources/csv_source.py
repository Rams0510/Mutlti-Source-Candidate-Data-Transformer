import csv
import os
import logging
import re
from pipeline.normalizer import normalize_email, normalize_phone

logger = logging.getLogger("pipeline")

def parse_csv(filepath: str) -> list[dict]:
    """
    Parses a recruiter CSV file.
    Expects columns: name, email, phone, current_company, title (case-insensitive, whitespace-stripped).
    Missing columns default to None. Skips empty rows.
    Normalizes emails and phones into list format, dropping invalid entries.
    Returns a list of dicts, each with '_source': 'recruiter_csv'.
    """
    if not os.path.exists(filepath):
        logger.warning(f"CSV file not found: {filepath}")
        return []
        
    records = []
    try:
        with open(filepath, mode="r", encoding="utf-8-sig", errors="ignore") as f:
            reader = csv.reader(f)
            try:
                headers = next(reader)
            except StopIteration:
                logger.warning(f"CSV file is empty: {filepath}")
                return []
                
            # Clean headers: lowercase and strip whitespace
            clean_headers = [h.strip().lower() for h in headers]
            
            # Map required field names to column indexes
            field_mapping = {
                "name": -1,
                "email": -1,
                "phone": -1,
                "current_company": -1,
                "title": -1
            }
            
            # Match standard variants if present
            for idx, h in enumerate(clean_headers):
                if h in field_mapping:
                    field_mapping[h] = idx
                elif h.replace("_", " ") in field_mapping:
                    field_mapping[h.replace("_", " ")] = idx
                elif h == "company":
                    field_mapping["current_company"] = idx
                    
            for row_idx, row in enumerate(reader, start=2):
                if not row or not any(cell.strip() for cell in row):
                    # Skip empty row
                    continue
                    
                record = {
                    "_source": "recruiter_csv",
                    "emails": [],  # Initialize as lists to match schema and merger logic
                    "phones": []
                }
                
                all_null = True
                for field, col_idx in field_mapping.items():
                    val = None
                    if col_idx != -1 and col_idx < len(row):
                        cell_val = row[col_idx].strip()
                        if cell_val:
                            val = cell_val
                            all_null = False
                    
                    # Split, normalize, and append valid emails
                    if field == "email" and val:
                        for e in re.split(r'[,;]+', val):
                            norm_e = normalize_email(e)
                            if norm_e:
                                record["emails"].append(norm_e)
                                
                    # Split, normalize, and append valid phones
                    elif field == "phone" and val:
                        for p in re.split(r'[,;]+', val):
                            norm_p = normalize_phone(p)
                            if norm_p:
                                record["phones"].append(norm_p)
                                
                    # Assign standard fields like name, current_company, title
                    elif field not in ["email", "phone"]:
                        record[field] = val
                        
                if all_null:
                    # Edge Case: CSV row with all null fields -> skip that row entirely
                    continue
                    
                records.append(record)
    except Exception as e:
        logger.warning(f"Error parsing CSV file {filepath}: {e}")
        return []
        
    return records