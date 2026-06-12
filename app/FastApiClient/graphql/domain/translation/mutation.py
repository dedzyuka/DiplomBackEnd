# app/FastApiClient/graphql/domain/translation/mutation.py
import strawberry
from FastApiClient.graphql.context import GraphQLContext
from FastApiClient.core.config import settings
from FastApiClient.graphql.domain.translation.service import translate_text
from .types import TranslateInput, TranslatePayload

@strawberry.type
class TranslationMutations:
    @strawberry.mutation
    async def translate(
        self,
        info: strawberry.Info[GraphQLContext],
        input: TranslateInput,
    ) -> TranslatePayload:
        source = (input.source_language or "").strip().lower()
        target = input.target_language.strip().lower()
        text = input.text.strip()

        if not text:
            raise ValueError("Text must not be empty")
        if len(text) > settings.TRANSLATION_MAX_TEXT_LENGTH:
            raise ValueError("Text too long")
        if not source:
            raise ValueError("sourceLanguage is required")
        if source == target:
            raise ValueError("sourceLanguage and targetLanguage must differ")

        translated_text = await translate_text(
            text=text,
            source_language=source,
            target_language=target,
        )

        return TranslatePayload(
            original_text=text,
            translated_text=translated_text,
            source_language=source,
            target_language=target,
            provider=settings.TRANSLATION_PROVIDER,
            is_ephemeral=True,
        )