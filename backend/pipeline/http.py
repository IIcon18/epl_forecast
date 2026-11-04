import logging
import time

import requests

from pipeline import settings

log = logging.getLogger(__name__)


class SourceUnavailable(Exception):
    pass


def get(url: str, *, headers: dict | None = None, params: dict | None = None,
        retries: int = 4) -> requests.Response:
    delay = 2
    reason = "неизвестная ошибка"
    for attempt in range(1, retries + 1):
        wait = delay
        try:
            resp = requests.get(url, headers=headers, params=params, timeout=settings.HTTP_TIMEOUT)
        except (requests.Timeout, requests.ConnectionError) as exc:
            reason = f"сеть: {type(exc).__name__}"
        else:
            if resp.status_code == 429:
                reason = "превышен лимит запросов (429)"
                wait = min(int(resp.headers.get("Retry-After") or
                               resp.headers.get("X-RequestCounter-Reset") or 60) + 1, 70)
            elif resp.status_code >= 500:
                reason = f"ошибка сервера {resp.status_code}"
            elif resp.status_code >= 400:
                raise SourceUnavailable(f"{url}: HTTP {resp.status_code}")
            else:
                return resp
        log.warning("%s (попытка %d/%d)", reason, attempt, retries)
        if attempt < retries:
            time.sleep(wait)
        delay *= 2
    raise SourceUnavailable(f"{url}: {reason}, попытки исчерпаны")
