import requests
import re
import json
from concurrent.futures import ThreadPoolExecutor

BASE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:149.0) Gecko/20100101 Firefox/149.0",
    "Accept": "*/*",
    "Origin": "https://www.menti.com",
    "Referer": "https://www.menti.com/",
}


def get_identifier() -> tuple[str | None, str | None]: 
    """Holt einen frischen Identifier + JWT vom Server."""
    r = requests.post("https://www.menti.com/core/identifiers", headers=BASE_HEADERS)
    identifier = r.cookies.get("identifier1", "")
    jwt = r.cookies.get("identifierjwt", "")
    return identifier, jwt


def get_questions(slug: str) -> list[dict]:
    """Lädt alle Fragen einer Mentimeter-Präsentation."""
    res = requests.get(f"https://www.menti.com/{slug}", headers=BASE_HEADERS)
    if res.status_code != 200:
        raise ValueError(f"HTTP {res.status_code} beim Laden der Seite.")

    chunks = re.findall(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)', res.text, re.DOTALL)
    if not chunks:
        raise ValueError("Keine Flight-Data gefunden.")

    combined = "".join(json.loads(f'"{c}"') for c in chunks)

    start = combined.find('"slideDeck":')
    if start == -1:
        raise ValueError("slideDeck nicht gefunden.")

    brace_start = combined.index('{', start)
    depth = 0
    deck: dict = {}
    for i, ch in enumerate(combined[brace_start:], brace_start):
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                deck = json.loads(combined[brace_start:i + 1])
                break

    questions = []
    for slide in deck.get("slides", []):
        slide_type = slide.get("staticContent", {}).get("type", "?")
        for ic in slide.get("interactiveContents", []):
            choices = [
                {"id": c["interactiveContentChoiceId"], "label": c["title"]}
                for c in ic.get("choices", [])
            ]
            questions.append({
                "id": ic["interactiveContentId"],
                "title": ic["title"],
                "type": slide_type,
                "choices": choices,
                "open": ic.get("responseMode") == "accepting-responses",
            })
    return questions


def vote_once(slug: str, ic_id: str, payload: dict) -> bool:
    """Sendet eine einzelne Stimme mit frischem Identifier."""
    identifier, jwt = get_identifier()
    if not identifier:
        return False
    url = f"https://www.menti.com/core/audience/{slug}/responses/v2/{ic_id}"
    r = requests.post(
        url,
        json=payload,
        headers={**BASE_HEADERS, "Content-Type": "application/json", "X-Identifier": identifier},
        cookies={"identifier1": identifier, "identifierjwt": jwt},
    )
    return r.status_code in (200, 201)


def vote_choice(slug: str, ic_id: str, choice_id: str, count: int,
                on_result=None, max_workers: int = 10) -> int:
    """Sendet mehrere Multiple-Choice Stimmen parallel."""
    payload = {
        "response": {
            "type": "multiple-choice",
            "choices": [{"interactive_content_choice_id": choice_id}],
        }
    }

    success = 0

    def _vote(_):
        nonlocal success
        ok = vote_once(slug, ic_id, payload)
        if on_result:
            on_result(ok)
        if ok:
            success += 1
        return ok

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        list(ex.map(_vote, range(count)))

    return success


def vote_wordcloud(slug: str, ic_id: str, choice_id: str, word: str, count: int,
                   on_result=None, max_workers: int = 10) -> int:
    """Sendet mehrere Word-Cloud Einträge parallel."""
    payload = {
        "response": {
            "type": "word-cloud",
            "choices": [{"interactive_content_choice_id": choice_id, "value": word}],
        }
    }

    success = 0

    def _vote(_):
        nonlocal success
        ok = vote_once(slug, ic_id, payload)
        if on_result:
            on_result(ok)
        if ok:
            success += 1
        return ok

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        list(ex.map(_vote, range(count)))

    return success