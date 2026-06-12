# app/FastApiClient/graphql/domain/translation/types.py
from typing import Optional
import strawberry

@strawberry.input(name="TranslateTextInput")
class TranslateInput:
    text: str
    target_language: str
    source_language: Optional[str] = None

@strawberry.type
class TranslatePayload:
    original_text: str
    translated_text: str
    source_language: str
    target_language: str
    provider: str
    is_ephemeral: bool