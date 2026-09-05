"""Private, fail-closed Responses request accounting.

Forge cannot use the provider's input-token endpoint here: that would itself
be provider transport and require the configured secret. The bounded adapter
therefore measures a deterministic conservative upper bound for the complete
wire request before it resolves the secret.
"""
from __future__ import annotations

import json


class TokenAccountingUnavailable(RuntimeError):
    """The adapter cannot prove a bounded input for the configured model."""


class _CanonicalResponsesRequestTokenCounter:
    """Adapter-owned conservative accounting for the supported Responses model.

    The accounting unit is the UTF-8 byte length of the canonical, complete
    request body. For text-only Responses input, every input token consumes at
    least one UTF-8 byte; serializing the entire body additionally reserves
    for all role/message, metadata, schema, and protocol representation. It is
    therefore a deterministic upper bound, not a character-count proxy.
    Unknown models fail closed rather than guessing a tokenizer or encoding.
    """

    _SUPPORTED_MODELS = frozenset(("gpt-5.6",))

    def count(self, *, model: str, request_body: dict[str, object]) -> int:
        if model not in self._SUPPORTED_MODELS:
            raise TokenAccountingUnavailable("configured model has no proven local request accounting")
        try:
            # Match the transport's JSON escaping. Escaped multibyte text can
            # only make this conservative upper bound larger.
            serialized = json.dumps(request_body, sort_keys=True, separators=(",", ":"))
            return len(serialized.encode("utf-8"))
        except (TypeError, UnicodeError, ValueError) as error:
            raise TokenAccountingUnavailable("request body cannot be accounted deterministically") from error
