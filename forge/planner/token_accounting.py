"""Fail-closed token accounting for bounded planning-provider requests.

The Responses API reports usage after submission, which is too late to enforce
Forge's G011 admission limits.  This boundary counts the *exact text input
items* constructed for one request before a secret is resolved or transport is
attempted.  A concrete counter must be explicitly bound to the configured
model; an unavailable or unknown tokenizer is never approximated with bytes or
characters.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class TokenCountingUnavailable(RuntimeError):
    """The configured model has no trusted deterministic local tokenizer."""


class ModelTokenCounter(Protocol):
    """Counts the exact submitted text items for one explicitly named model."""

    def count(self, *, model: str, input_texts: tuple[str, ...]) -> int: ...


@dataclass(frozen=True)
class TiktokenModelTokenCounter:
    """Explicit model-to-encoding binding backed by the deterministic tiktoken codec.

    The binding is deliberately supplied by the owning runtime integration.
    Guessing an encoding from a model-family prefix would turn an unknown
    tokenizer into an apparently valid count and is therefore forbidden.
    """

    model_encodings: dict[str, str]

    def count(self, *, model: str, input_texts: tuple[str, ...]) -> int:
        encoding_name = self.model_encodings.get(model)
        if not encoding_name:
            raise TokenCountingUnavailable("configured model has no trusted tokenizer binding")
        try:
            import tiktoken  # type: ignore[import-not-found]
            encoding = tiktoken.get_encoding(encoding_name)
        except Exception as error:
            raise TokenCountingUnavailable("configured tokenizer is unavailable") from error
        try:
            # Each string is exactly one Responses input_text item.  Keeping
            # item boundaries avoids treating JSON/UTF-8 byte length as token
            # accounting and lets a counter model any provider item overhead.
            return sum(len(encoding.encode(text, disallowed_special=())) for text in input_texts)
        except Exception as error:
            raise TokenCountingUnavailable("configured tokenizer could not count request input") from error
