"""Common utility functions for all agents."""

import re
import json

_OFF_TOPIC_PATTERNS = re.compile(
    r"\\b(how|what|why|when|where|can you|could you|please|help|understand|"
    r"manage|tell me|explain|advice|information|suggest|recommend|"
    r"from scratch|everything|general|overview|tips|ways to)\\b",
    re.IGNORECASE,
)

def strip_md_fences(text: str) -> str:
    """Strip markdown code fences that the LLM sometimes wraps JSON in."""
    if not text:
        return ""
    
    # Remove ```json ... ``` or ``` ... ```
    text = re.sub(r"^```(?:json)?\\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"\\s*```$", "", text, flags=re.MULTILINE)
    return text.strip()

def is_off_topic_answer(message: str) -> bool:
    """
    Return True when the user's message looks like an informational request
    rather than a direct answer to a clinical question.
    """
    if "?" in message:
        return True
    return bool(_OFF_TOPIC_PATTERNS.search(message))

def parse_json_safely(text: str):
    """Clean fences and parse JSON safely. Extracts from trailing text if needed."""
    if not text:
        return None
        
    try:
        cleaned = strip_md_fences(text)
        return json.loads(cleaned)
    except Exception:
        pass
    
    # Fallback: extract everything between the first '{' and last '}'
    start_idx = text.find('{')
    end_idx = text.rfind('}')
    
    if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
        json_str = text[start_idx:end_idx+1]
        try:
            return json.loads(json_str)
        except Exception:
            pass
            
    return None
