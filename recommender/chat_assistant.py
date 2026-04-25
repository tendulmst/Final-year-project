import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


@dataclass(frozen=True)
class ChatResponse:
    text: str
    items: List[Dict]
    intent: str


_LIKE_RE = re.compile(r"\b(?:movies\s+like|like)\s+(?P<title>.+)$", re.IGNORECASE)
_SUGGEST_RE = re.compile(r"\b(?:suggest|recommend)\s+(?P<genre>[a-zA-Z\- ]+?)\s+movies?\b", re.IGNORECASE)


def _normalize_genre(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _extract_intent(message: str) -> Tuple[str, Dict[str, str]]:
    msg = (message or "").strip()
    if not msg:
        return "empty", {}

    m = _LIKE_RE.search(msg)
    if m:
        title = (m.group("title") or "").strip().strip("\"'")
        if title:
            return "similar", {"title": title}

    m = _SUGGEST_RE.search(msg)
    if m:
        genre = _normalize_genre(m.group("genre"))
        if genre:
            return "genre", {"genre": genre}

    return "search", {"query": msg}


def _available_genres_from_metadata(metadata) -> List[str]:
    # metadata['genres'] is list-like per row in this project.
    genres = set()
    if metadata is None or "genres" not in metadata.columns:
        return []
    for g in metadata["genres"].dropna().tolist():
        if isinstance(g, list):
            for x in g:
                if isinstance(x, str) and x.strip():
                    genres.add(x.strip())
        elif isinstance(g, str) and g.strip():
            # sometimes stored as string; best-effort split
            for x in re.split(r"[|,;/]", g):
                x = x.strip()
                if x:
                    genres.add(x)
    return sorted(genres)


def _match_genre(requested: str, available: List[str]) -> Optional[str]:
    req = _normalize_genre(requested)
    if not req:
        return None
    # exact-ish match
    for a in available:
        if _normalize_genre(a) == req:
            return a
    # partial match
    for a in available:
        if req in _normalize_genre(a):
            return a
    return None


def handle_message(recommender, message: str, n: int = 10) -> ChatResponse:
    intent, params = _extract_intent(message)

    if intent == "empty":
        return ChatResponse(
            text="Ask me something like “Suggest thriller movies” or “Movies like Inception”.",
            items=[],
            intent=intent,
        )

    if recommender is None:
        return ChatResponse(
            text="The recommendation model is still loading. Please try again in a moment.",
            items=[],
            intent="loading",
        )

    if intent == "similar":
        title = params["title"]
        result = recommender.get_recommendations(title, n=n)
        if "error" in result:
            sugg = result.get("suggestions") or []
            extra = f" Did you mean: {', '.join(sugg)}?" if sugg else ""
            return ChatResponse(text=result["error"] + extra, items=[], intent=intent)
        items = result.get("recommendations") or []
        return ChatResponse(
            text=f"Here are movies like “{result['query_movie']}”.",
            items=items,
            intent=intent,
        )

    if intent == "genre":
        requested = params["genre"]
        available = _available_genres_from_metadata(recommender.metadata)
        matched = _match_genre(requested, available)
        if not matched:
            sample = ", ".join(available[:12]) + ("…" if len(available) > 12 else "")
            return ChatResponse(
                text=f"I couldn't find genre “{requested}”. Try one of: {sample}",
                items=[],
                intent="genre_unknown",
            )

        # Filter metadata rows where genres contain matched genre
        md = recommender.metadata
        mask = md["genres"].apply(lambda g: isinstance(g, list) and matched in g) if md is not None else None
        subset = md[mask].copy() if mask is not None else md.iloc[0:0].copy()
        if subset.empty:
            return ChatResponse(text=f"I couldn't find any “{matched}” movies in the catalog.", items=[], intent=intent)

        # Rank by vote_average then vote_count (best-effort)
        if "vote_average" in subset.columns:
            subset["vote_average"] = subset["vote_average"].fillna(0)
        if "vote_count" in subset.columns:
            subset["vote_count"] = subset["vote_count"].fillna(0)

        sort_cols = [c for c in ["vote_average", "vote_count"] if c in subset.columns]
        if sort_cols:
            subset = subset.sort_values(sort_cols, ascending=False)

        items: List[Dict] = []
        for _, movie in subset.head(n).iterrows():
            items.append(
                {
                    "title": movie.get("title"),
                    "release_date": movie.get("release_date") if str(movie.get("release_date")) != "nan" else "Unknown",
                    "production": movie.get("primary_company") if str(movie.get("primary_company")) != "nan" else "Unknown",
                    "genres": ", ".join(movie.get("genres")[:3]) if isinstance(movie.get("genres"), list) else "N/A",
                    "rating": f"{float(movie.get('vote_average')):.1f}/10" if movie.get("vote_average") is not None else "N/A",
                    "votes": f"{int(movie.get('vote_count')):,}" if movie.get("vote_count") is not None else "N/A",
                    "google_link": f"https://www.google.com/search?q={'+'.join(str(movie.get('title','')).split())}+movie",
                }
            )

        return ChatResponse(
            text=f"Top {len(items)} “{matched}” picks from the catalog.",
            items=items,
            intent=intent,
        )

    # fallback: treat as title search
    query = params.get("query") or message
    matches = recommender.search_movies(query, n=min(12, max(5, n)))
    if not matches:
        return ChatResponse(text=f"I couldn't find a movie matching “{query}”.", items=[], intent="search_none")
    return ChatResponse(
        text="Try one of these titles, or ask “Movies like <title>”.",
        items=[{"title": m} for m in matches],
        intent="search",
    )

