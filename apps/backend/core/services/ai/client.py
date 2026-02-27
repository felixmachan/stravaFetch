from __future__ import annotations

import json
import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from openai import OpenAI


@dataclass
class AIResult:
    text: str
    parsed: dict[str, Any] | None
    model: str
    source: str
    status: str
    tokens_input: int | None = None
    tokens_output: int | None = None
    error_message: str = ""


class OpenAIResponsesClient:
    def __init__(self) -> None:
        self._key = os.getenv("OPENAI_API_KEY", "").strip()
        self._client = OpenAI(api_key=self._key) if self._key else None
        self._resolved_model_cache: dict[str, str] = {}

    @staticmethod
    def _extract_json_object(text: str) -> dict[str, Any] | None:
        payload = (text or "").strip()
        if not payload:
            return None
        try:
            return json.loads(payload)
        except Exception:
            pass
        start = payload.find("{")
        end = payload.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(payload[start : end + 1])
            except Exception:
                return None
        return None

    @staticmethod
    def _is_bad_request(message: str) -> bool:
        low = (message or "").lower()
        return "400" in low or "invalid_request_error" in low or "bad request" in low

    @staticmethod
    def _wants_no_temperature(message: str) -> bool:
        low = (message or "").lower()
        return "temperature" in low and ("unsupported" in low or "not supported" in low or "unknown parameter" in low)

    @staticmethod
    def _wants_model_fallback(message: str) -> bool:
        low = (message or "").lower()
        return "model" in low and (
            "not found" in low
            or "does not exist" in low
            or "no access" in low
            or "not available" in low
            or "unsupported model" in low
        )

    @staticmethod
    def _fallback_model_for(model: str) -> str:
        env_specific = os.getenv(f"OPENAI_FALLBACK_{model.upper().replace('-', '_')}", "").strip()
        if env_specific:
            return env_specific
        generic = os.getenv("OPENAI_FALLBACK_MODEL", "").strip()
        if generic:
            return generic
        return "gpt-4.1-mini"

    @lru_cache(maxsize=1)
    def _list_model_ids(self) -> tuple[str, ...]:
        if not self._client:
            return tuple()
        try:
            rows = self._client.models.list()
            ids = []
            for row in rows:
                mid = getattr(row, "id", None)
                if isinstance(mid, str) and mid:
                    ids.append(mid)
            return tuple(ids)
        except Exception:
            return tuple()

    def _resolve_model(self, model: str) -> str:
        if model in self._resolved_model_cache:
            return self._resolved_model_cache[model]
        ids = self._list_model_ids()
        if not ids:
            self._resolved_model_cache[model] = model
            return model
        if model in ids:
            self._resolved_model_cache[model] = model
            return model
        prefix_matches = sorted([mid for mid in ids if mid.startswith(f"{model}-")], reverse=True)
        if prefix_matches:
            resolved = prefix_matches[0]
            print(f"[ai:model] resolved alias {model} -> {resolved}")
            self._resolved_model_cache[model] = resolved
            return resolved
        contains_matches = sorted([mid for mid in ids if model in mid], reverse=True)
        if contains_matches:
            resolved = contains_matches[0]
            print(f"[ai:model] resolved alias {model} -> {resolved}")
            self._resolved_model_cache[model] = resolved
            return resolved
        self._resolved_model_cache[model] = model
        return model

    @staticmethod
    def _supports_temperature(model: str) -> bool:
        # gpt-5 family can reject temperature depending on account/model version.
        return not model.startswith("gpt-5")

    def complete_text(self, *, model: str, system_prompt: str, user_prompt: str, temperature: float = 0.2) -> AIResult:
        if not self._client:
            return AIResult(
                text="AI key missing. Set OPENAI_API_KEY to enable live responses.",
                parsed=None,
                model=model,
                source="no_api_key",
                status="fallback",
            )
        try:
            resolved_model = self._resolve_model(model)
            payload = {
                "model": resolved_model,
                "instructions": system_prompt,
                "input": user_prompt,
            }
            if self._supports_temperature(resolved_model):
                payload["temperature"] = temperature
            resp = self._client.responses.create(**payload)
            usage = getattr(resp, "usage", None)
            return AIResult(
                text=(resp.output_text or "").strip(),
                parsed=None,
                model=resolved_model,
                source="openai",
                status="success",
                tokens_input=getattr(usage, "input_tokens", None) if usage else None,
                tokens_output=getattr(usage, "output_tokens", None) if usage else None,
            )
        except Exception as exc:
            message = str(exc)
            # Retry without temperature for models that reject it.
            if self._is_bad_request(message) and self._wants_no_temperature(message):
                try:
                    resolved_model = self._resolve_model(model)
                    resp = self._client.responses.create(
                        model=resolved_model,
                        instructions=system_prompt,
                        input=user_prompt,
                    )
                    usage = getattr(resp, "usage", None)
                    return AIResult(
                        text=(resp.output_text or "").strip(),
                        parsed=None,
                        model=resolved_model,
                        source="openai",
                        status="success",
                        tokens_input=getattr(usage, "input_tokens", None) if usage else None,
                        tokens_output=getattr(usage, "output_tokens", None) if usage else None,
                    )
                except Exception as retry_exc:
                    message = str(retry_exc)

            # Retry with fallback model if current model is unavailable.
            if self._is_bad_request(message) and self._wants_model_fallback(message):
                fallback_model = self._fallback_model_for(model)
                try:
                    resolved_model = self._resolve_model(fallback_model)
                    resp = self._client.responses.create(
                        model=resolved_model,
                        instructions=system_prompt,
                        input=user_prompt,
                    )
                    usage = getattr(resp, "usage", None)
                    return AIResult(
                        text=(resp.output_text or "").strip(),
                        parsed=None,
                        model=resolved_model,
                        source="openai",
                        status="success",
                        tokens_input=getattr(usage, "input_tokens", None) if usage else None,
                        tokens_output=getattr(usage, "output_tokens", None) if usage else None,
                    )
                except Exception as retry_exc:
                    message = str(retry_exc)

            return AIResult(
                text="",
                parsed=None,
                model=model,
                source="provider_error",
                status="failed",
                error_message=message,
            )

    def complete_json(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        schema_name: str,
        schema: dict[str, Any],
        temperature: float = 0.1,
    ) -> AIResult:
        if not self._client:
            return AIResult(
                text="",
                parsed=None,
                model=model,
                source="no_api_key",
                status="fallback",
            )

        attempts = [user_prompt, f"Repair and return valid JSON only. Original request: {user_prompt}"]
        last_error = ""
        for idx, attempt_prompt in enumerate(attempts):
            try:
                resolved_model = self._resolve_model(model)
                payload = {
                    "model": resolved_model,
                    "instructions": system_prompt,
                    "input": attempt_prompt,
                    "text": {
                        "format": {
                            "type": "json_schema",
                            "name": schema_name,
                            "schema": schema,
                            "strict": True,
                        }
                    },
                }
                if self._supports_temperature(resolved_model):
                    payload["temperature"] = temperature
                resp = self._client.responses.create(
                    **payload,
                )
                payload = (resp.output_text or "").strip()
                parsed = json.loads(payload) if payload else None
                usage = getattr(resp, "usage", None)
                return AIResult(
                    text=payload,
                    parsed=parsed,
                    model=resolved_model,
                    source="openai",
                    status="success",
                    tokens_input=getattr(usage, "input_tokens", None) if usage else None,
                    tokens_output=getattr(usage, "output_tokens", None) if usage else None,
                )
            except Exception as exc:
                last_error = str(exc)
                low = last_error.lower()
                schema_related = any(
                    marker in low
                    for marker in ["json_schema", "response_format", "text.format", "schema", "invalid_request_error", "400"]
                )
                if schema_related:
                    # Fallback path for provider/schema incompatibility: ask for raw JSON and parse client-side.
                    fallback = self.complete_text(
                        model=model,
                        system_prompt=system_prompt + " Return JSON only.",
                        user_prompt=(
                            f"{attempt_prompt}\n\nReturn strict JSON object for schema `{schema_name}` only. "
                            "No markdown, no explanation."
                        ),
                        temperature=temperature,
                    )
                    parsed = self._extract_json_object(fallback.text)
                    return AIResult(
                        text=fallback.text,
                        parsed=parsed,
                        model=fallback.model,
                        source=fallback.source,
                        status=fallback.status if parsed is not None else "failed",
                        tokens_input=fallback.tokens_input,
                        tokens_output=fallback.tokens_output,
                        error_message="" if parsed is not None else last_error,
                    )
                if self._is_bad_request(last_error) and self._wants_model_fallback(last_error):
                    fallback_model = self._fallback_model_for(model)
                    try:
                        resolved_model = self._resolve_model(fallback_model)
                        resp = self._client.responses.create(
                            model=resolved_model,
                            instructions=system_prompt,
                            input=attempt_prompt,
                        )
                        payload = (resp.output_text or "").strip()
                        parsed = self._extract_json_object(payload)
                        usage = getattr(resp, "usage", None)
                        return AIResult(
                            text=payload,
                            parsed=parsed,
                            model=resolved_model,
                            source="openai",
                            status="success" if parsed is not None else "failed",
                            tokens_input=getattr(usage, "input_tokens", None) if usage else None,
                            tokens_output=getattr(usage, "output_tokens", None) if usage else None,
                            error_message="" if parsed is not None else last_error,
                        )
                    except Exception as retry_exc:
                        last_error = str(retry_exc)
                if idx == len(attempts) - 1:
                    break
        return AIResult(
            text="",
            parsed=None,
            model=model,
            source="provider_error",
            status="failed",
            error_message=last_error,
        )
