import re
from dataclasses import dataclass
from typing import List, Dict, Any


PROMO_WORDS = {
    "buy",
    "discount",
    "offer",
    "free",
    "subscribe",
    "promo",
    "promotion",
    "click",
    "link",
    "whatsapp",
    "telegram",
    "dm",
    "inbox",
    "guaranteed",
}

GENERIC_PHRASES = {
    "best movie ever",
    "must watch",
    "highly recommended",
    "worth watching",
    "amazing",
    "awesome",
    "excellent",
    "superb",
    "mind blowing",
}


@dataclass(frozen=True)
class FakeReviewResult:
    score: float  # 0..1 (higher = more likely fake)
    label: str  # "fake" | "real"
    reasons: List[str]
    features: Dict[str, Any]


def _clamp01(x: float) -> float:
    return 0.0 if x < 0.0 else 1.0 if x > 1.0 else x


def analyze_review_text(text: str) -> FakeReviewResult:
    """
    Lightweight heuristic fake-review detection.
    No external dependencies; works offline.
    """
    raw = (text or "").strip()
    t = raw.lower()

    # Basic stats
    length = len(raw)
    word_count = len(re.findall(r"\b[\w']+\b", t))
    exclam = raw.count("!")
    qmarks = raw.count("?")
    urls = len(re.findall(r"https?://|www\.", t))
    emojis = len(re.findall(r"[\U0001F300-\U0001FAFF]", raw))
    repeated_chars = len(re.findall(r"(.)\1{3,}", raw))
    repeated_words = len(re.findall(r"\b(\w+)\b(?:\s+\1\b){2,}", t))
    all_caps_ratio = 0.0
    letters = re.findall(r"[A-Za-z]", raw)
    if letters:
        caps = sum(1 for c in letters if c.isupper())
        all_caps_ratio = caps / max(1, len(letters))

    promo_hits = sum(1 for w in PROMO_WORDS if re.search(rf"\b{re.escape(w)}\b", t))
    generic_hits = sum(1 for p in GENERIC_PHRASES if p in t)

    # Scoring: each feature adds suspicion; keep it interpretable.
    score = 0.0
    reasons: List[str] = []

    if word_count <= 3:
        score += 0.35
        reasons.append("Very short review")
    elif word_count <= 8:
        score += 0.18
        reasons.append("Short / low-detail review")

    if exclam >= 4:
        score += 0.18
        reasons.append("Excessive exclamation marks")
    elif exclam >= 2:
        score += 0.08

    if urls > 0:
        score += 0.30
        reasons.append("Contains a link")

    if promo_hits > 0:
        score += 0.30
        reasons.append("Promotional / spammy wording")

    if generic_hits > 0:
        score += min(0.22, 0.11 * generic_hits)
        reasons.append("Generic praise (low specificity)")

    if all_caps_ratio >= 0.6 and length >= 12:
        score += 0.18
        reasons.append("Mostly ALL CAPS")

    if repeated_chars > 0:
        score += 0.12
        reasons.append("Repeated characters (e.g., 'soooo')")

    if repeated_words > 0:
        score += 0.12
        reasons.append("Repeated words / unnatural repetition")

    if emojis >= 4:
        score += 0.10
        reasons.append("Excessive emojis")

    if qmarks >= 4:
        score += 0.06

    score = _clamp01(score)
    label = "fake" if score >= 0.65 else "real"

    if not raw:
        return FakeReviewResult(
            score=0.0,
            label="real",
            reasons=["Empty review"],
            features={
                "length": 0,
                "word_count": 0,
            },
        )

    return FakeReviewResult(
        score=score,
        label=label,
        reasons=reasons[:6],
        features={
            "length": length,
            "word_count": word_count,
            "exclamations": exclam,
            "question_marks": qmarks,
            "links": urls,
            "promo_hits": promo_hits,
            "generic_hits": generic_hits,
            "all_caps_ratio": round(all_caps_ratio, 3),
            "repeated_chars": repeated_chars,
            "repeated_words": repeated_words,
            "emoji_count": emojis,
        },
    )

