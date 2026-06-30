import re
from typing import List, Tuple, Dict

# ---- Layer 1: Patterns (soft signals) ----
INJECTION_PATTERNS = [
    (r"ignore (previous|all) instructions", "high"),
    (r"you are now", "medium"),
    (r"pretend (you are|to be)", "medium"),
    (r"jailbreak", "high"),
    (r"DAN mode", "high"),
    (r"forget your (system|instructions)", "high"),
]

PII_PATTERNS = {
    "credit_card": r"\b(?:\d[ -]*?){13,16}\b",
    "ssn": r"\b\d{3}-\d{2}-\d{4}\b",
    "passport": r"\b[A-Z]{1,2}\d{6,9}\b",
    "email": r"\b[\w\.-]+@[\w\.-]+\.\w+\b",
    "phone": r"\b\d{10}\b",
}

HTML_PATTERN = r"<\s*(script|iframe|object)[^>]*>"
PROMPT_LIKE_PATTERN = r"(you are|act as|system prompt)"


# ---- Normalize ----
def normalize_text(text: str) -> str:
    text = text.lower()
    text = re.sub(r"\s+", " ", text)
    return text.strip()


# ---- Chunking (DocRAG essential) ----
def chunk_text(text: str, chunk_size: int = 500) -> List[str]:
    return [text[i:i + chunk_size] for i in range(0, len(text), chunk_size)]


# ---- Injection Detection ----
def detect_injection(text: str) -> Tuple[List[str], int]:
    flags = []
    score = 0

    for pattern, severity in INJECTION_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            flags.append(pattern)
            score += 3 if severity == "high" else 1

    if re.search(HTML_PATTERN, text, re.IGNORECASE):
        flags.append("html_injection")
        score += 2

    # Detect prompt-like embedded instructions
    if len(re.findall(PROMPT_LIKE_PATTERN, text)) > 2:
        flags.append("prompt_injection_like")
        score += 2

    return flags, score


# ---- Smart PII Masking ----
def mask_pii(text: str) -> Tuple[str, Dict]:
    metadata = {}
    masked = text

    for pii_type, pattern in PII_PATTERNS.items():
        matches = re.findall(pattern, masked)

        if matches:
            metadata[pii_type] = len(matches)

            # Only mask high-risk PII
            if pii_type in ["credit_card", "ssn"]:
                masked = re.sub(pattern, f"[REDACTED_{pii_type.upper()}]", masked)

    return masked, metadata


# ---- MAIN SANITIZER ----
def sanitize_input(text: str) -> dict:
    normalized = normalize_text(text)
    chunks = chunk_text(text)

    total_flags = []
    total_score = 0

    for chunk in chunks:
        flags, score = detect_injection(chunk)
        total_flags.extend(flags)
        total_score += score

    masked_text, pii_meta = mask_pii(text)

    return {
        "clean_text": masked_text,
        "normalized_text": normalized,
        "chunks": len(chunks),
        "injection_flags": list(set(total_flags)),
        "pii_detected": pii_meta,
        "risk_score": total_score,
    }

class OutputValidationError(Exception):
    pass


def safe_json_parse(raw_output: str):
    import json, re

    # Extract largest JSON block
    matches = re.findall(r'\{.*?\}', raw_output, re.DOTALL)

    if not matches:
        raise ValueError("No JSON object found")

    json_str = max(matches, key=len)

    # Fix common issues
    json_str = re.sub(r',\s*}', '}', json_str)  # trailing commas
    json_str = re.sub(r'\\\n', '', json_str)
    json_str = json_str.replace('\n', '\\n')

    try:
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        raise OutputValidationError(f"Invalid JSON: {e}")
    

def validate_llm_output(raw_output: str) -> str:
    if not isinstance(raw_output, str):
        raise OutputValidationError("Output must be a string")

    reply = raw_output.strip()

    # ---- Length ----
    word_count = len(reply.split())
    if word_count < 15:
        raise OutputValidationError(f"Reply too short: {word_count} words")

    # ---- Repetition check (LLM glitch) ----
    if len(set(reply.split())) < word_count * 0.3:
        raise OutputValidationError("Too repetitive (possible LLM failure)")

    # ---- Hallucination signals ----
    hallucination_flags = []

    HALLUCINATION_PATTERNS = [
        r"\$\d{4,}",
        r"guaranteed price",
        r"confirmed booking",
        r"100% success",
        r"no risk",
        r"as of \d{4}",
    ]

    for pattern in HALLUCINATION_PATTERNS:
        if re.search(pattern, reply, re.IGNORECASE):
            hallucination_flags.append(pattern)

    # ---- Unsafe claims detection ----
    if "definitely" in reply.lower() or "always" in reply.lower():
        hallucination_flags.append("overconfidence")

    if hallucination_flags:
        print(f"⚠️ Hallucination risk detected: {hallucination_flags}")

    return reply