# app/FastApiClient/services/translation.py
from urllib.parse import urlencode
import httpx

from FastApiClient.core.config import settings


class TranslationError(Exception):
    pass


async def translate_text(
    *,
    text: str,
    source_language: str,
    target_language: str,
) -> str:
    params = {
        "q": text,
        "langpair": f"{source_language}|{target_language}",
    }

    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(
            settings.TRANSLATION_PROVIDER_URL,
            params=params,
        )
        response.raise_for_status()
        data = response.json()

    translated = (
        data.get("responseData", {})
        .get("translatedText", "")
        .strip()
    )

    if not translated:
        raise TranslationError("Translation provider returned empty text")

    return translated