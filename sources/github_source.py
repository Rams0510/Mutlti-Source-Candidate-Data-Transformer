import requests
import logging
from typing import Dict, Any, List

logger = logging.getLogger("pipeline")

def fetch_github(username: str) -> dict:
    """
    Fetches public GitHub profile and repository languages for the given username.
    Returns extracted information or fallback container on error.
    """
    result = {
        "_source": "github",
        "full_name": None,
        "headline": None,
        "location": None,
        "links": {
            "github": f"https://github.com/{username}",
            "portfolio": None,
            "other": []
        },
        "skills": []
    }
    
    if not username:
        return result
        
    headers = {
        "User-Agent": "Candidate-Transformer-Eightfold-Agent",
        "Accept": "application/vnd.github.v3+json"
    }
    
    # 1. Fetch User Profile
    user_url = f"https://api.github.com/users/{username}"
    try:
        response = requests.get(user_url, headers=headers, timeout=5.0)
        if response.status_code == 404:
            logger.warning(f"GitHub user '{username}' not found (404)")
            return result
        elif response.status_code == 403:
            logger.warning(f"GitHub rate limit exceeded or access forbidden (403) for user '{username}'")
            return result
        elif response.status_code != 200:
            logger.warning(f"GitHub user fetch failed with status {response.status_code}")
            return result
            
        user_data = response.json()
        
        result["full_name"] = user_data.get("name")
        result["headline"] = user_data.get("bio")
        result["location"] = user_data.get("location")
        
        blog = user_data.get("blog")
        if blog:
            blog_str = str(blog).strip()
            if blog_str:
                if not blog_str.startswith(("http://", "https://")):
                    blog_str = "https://" + blog_str
                result["links"]["portfolio"] = blog_str
                
        result["links"]["github"] = user_data.get("html_url", f"https://github.com/{username}")
        
    except requests.exceptions.Timeout:
        logger.warning(f"GitHub profile request timed out for user '{username}'")
        return result
    except Exception as e:
        logger.warning(f"Error calling GitHub user API for '{username}': {e}")
        return result
        
    # 2. Fetch User Repos (for languages extraction)
    repos_url = f"https://api.github.com/users/{username}/repos?per_page=30&sort=pushed"
    try:
        response = requests.get(repos_url, headers=headers, timeout=5.0)
        if response.status_code == 200:
            repos = response.json()
            languages = set()
            for r in repos:
                lang = r.get("language")
                if lang:
                    languages.add(lang)
            # Map languages as skills with 0.6 confidence
            result["skills"] = [
                {
                    "name": l,
                    "confidence": 0.6,
                    "sources": ["github"]
                }
                for l in sorted(list(languages))
            ]
        else:
            logger.warning(f"GitHub repos fetch failed with status {response.status_code}")
    except Exception as e:
        logger.warning(f"Error calling GitHub repos API for '{username}': {e}")
        
    return result
