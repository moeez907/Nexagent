import asyncio
import json
import logging
import os
import re
from typing import Any, Dict, Optional, Type

from openai import (
    AsyncOpenAI,
    OpenAI,
    APIConnectionError,
    APIError,
    APITimeoutError,
    RateLimitError,
)
from pydantic import BaseModel

from app.core.config import settings
from app.llm.base import LLMProvider

logger = logging.getLogger("web_agent.llm.nebius")


class NebiusProvider(LLMProvider):
    MAX_ATTEMPTS = 3
    RETRY_DELAY_SECONDS = 360

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
    ):
        resolved_api_key = api_key or settings.NEBIUS_API_KEY or os.environ.get("NEBIUS_API_KEY")
        if not resolved_api_key or str(resolved_api_key).strip() in ("", "your_actual_nebius_api_key_here"):
            raise ValueError(
                "NEBIUS_API_KEY is not configured. "
                "Please add your Nebius API Key in the .env file (NEBIUS_API_KEY=your_key)."
            )
        self.api_key = resolved_api_key
        self.base_url = (base_url or settings.NEBIUS_BASE_URL or "https://api.tokenfactory.us-north1.nebius.com/v1/").rstrip("/")
        self.model = model or settings.NEBIUS_MODEL or "nvidia/Nemotron-3.5-Super-VL"
        self.timeout = timeout_seconds or settings.NEBIUS_TIMEOUT_SECONDS

        self.client = AsyncOpenAI(
            base_url=self.base_url,
            api_key=self.api_key,
            timeout=self.timeout,
        )
        self.sync_client = OpenAI(
            base_url=self.base_url,
            api_key=self.api_key,
            timeout=self.timeout,
        )

        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_tokens = 0

    @staticmethod
    def _clean_json_response(text: str) -> str:
        cleaned = text.strip()
        cleaned = re.sub(r"<think>.*?(?:</think>|$)", "", cleaned, flags=re.IGNORECASE | re.DOTALL).strip()
        match = re.search(r"```(?:json)?\s*(\{.*\}|\[.*\])\s*```", cleaned, re.DOTALL)
        if match:
            return match.group(1)
        if cleaned.startswith(("{", "[")):
            return cleaned
        for start, character in enumerate(cleaned):
            if character not in "{[":
                continue
            try:
                _, end = json.JSONDecoder().raw_decode(cleaned[start:])
                return cleaned[start : start + end]
            except json.JSONDecodeError:
                continue
        return cleaned

    def _record_usage(self, usage: Any) -> None:
        if usage is None:
            message = "Nebius token usage unavailable for this response."
            logger.warning(message)
            print(message, flush=True)
            return

        input_tokens = getattr(usage, "prompt_tokens", None)
        output_tokens = getattr(usage, "completion_tokens", None)
        total_tokens = getattr(usage, "total_tokens", None)

        if input_tokens is None and isinstance(usage, dict):
            input_tokens = usage.get("prompt_tokens")
            output_tokens = usage.get("completion_tokens")
            total_tokens = usage.get("total_tokens")

        if not all(isinstance(value, int) and value >= 0 for value in (input_tokens, output_tokens, total_tokens)):
            message = "Nebius token usage unavailable or malformed for this response."
            logger.warning(message)
            print(message, flush=True)
            return

        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens
        self.total_tokens += total_tokens
        message = (
            f"Nebius tokens: input={input_tokens}, output={output_tokens}, total={total_tokens}; "
            f"cumulative input={self.total_input_tokens}, output={self.total_output_tokens}, "
            f"total={self.total_tokens}."
        )
        logger.info(message)
        print(message, flush=True)

    async def _complete(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
    ) -> str:
        messages = [
            {
                "role": "system",
                "content": system_prompt,
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": user_prompt,
                    }
                ],
            },
        ]

        for attempt in range(1, self.MAX_ATTEMPTS + 1):
            try:
                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=temperature,
                    stream=False,
                )
                self._record_usage(response.usage)
                first_choice = response.choices[0] if response.choices else None
                content = (first_choice.message.content or "") if first_choice and first_choice.message else ""
                return str(content).strip()

            except RateLimitError as exc:
                if attempt == self.MAX_ATTEMPTS:
                    raise RuntimeError(
                        f"Nebius rate limit reached after {self.MAX_ATTEMPTS} attempts: {exc}"
                    ) from exc
                message = (
                    f"Nebius limit/error reached (HTTP 429). "
                    f"Retrying in {self.RETRY_DELAY_SECONDS} seconds "
                    f"(attempt {attempt + 1}/{self.MAX_ATTEMPTS})."
                )
                logger.warning(message)
                print(message, flush=True)
                await asyncio.sleep(self.RETRY_DELAY_SECONDS)

            except (APIConnectionError, APITimeoutError) as exc:
                if attempt == self.MAX_ATTEMPTS:
                    raise RuntimeError(
                        f"Nebius API request failed: {type(exc).__name__}: {exc}"
                    ) from exc
                wait_sec = 2 * attempt
                logger.warning(
                    "Nebius network/read error (%s: %s); retrying in %s seconds (attempt %s/%s).",
                    type(exc).__name__,
                    exc,
                    wait_sec,
                    attempt,
                    self.MAX_ATTEMPTS,
                )
                await asyncio.sleep(wait_sec)

            except APIError as exc:
                status_code = getattr(exc, "status_code", "Unknown")
                error_body = getattr(exc, "body", str(exc))
                raise RuntimeError(
                    f"Nebius API request failed with HTTP {status_code}: {error_body}"
                ) from exc

            except (KeyError, IndexError, TypeError, ValueError) as exc:
                raise ValueError(f"Nebius API returned an unexpected response: {exc}") from exc

            except Exception as exc:
                if attempt == self.MAX_ATTEMPTS:
                    raise RuntimeError(
                        f"Nebius API request failed: {type(exc).__name__}: {exc}"
                    ) from exc
                wait_sec = 2 * attempt
                logger.warning(
                    "Nebius unexpected error (%s: %s); retrying in %s seconds (attempt %s/%s).",
                    type(exc).__name__,
                    exc,
                    wait_sec,
                    attempt,
                    self.MAX_ATTEMPTS,
                )
                await asyncio.sleep(wait_sec)

    async def generate_structured(
        self,
        system_prompt: str,
        user_prompt: str,
        response_model: Optional[Type[BaseModel]] = None,
        temperature: float = 0.0,
    ) -> Dict[str, Any]:
        schema_instruction = ""
        if response_model:
            try:
                schema = json.dumps(response_model.model_json_schema(), separators=(",", ":"))
                schema_instruction = (
                    "\nReturn exactly one JSON object that conforms to this JSON schema. "
                    f"Do not include markdown or any text outside the JSON object.\nJSON schema: {schema}"
                )
            except Exception as exc:
                logger.warning("Could not build JSON schema for Nebius request: %s", exc)

        structured_prompt = (
            system_prompt
            + "\n/no_think\nIMPORTANT: Respond ONLY with one complete top-level JSON object matching the required schema. "
            + "Never return a JSON array, markdown, explanation, or <think> text. Keep thought concise."
            + schema_instruction
        )
        last_error = None
        retry_prompt = user_prompt
        for attempt in range(1, 4):
            content = await self._complete(
                structured_prompt,
                retry_prompt,
                temperature=0.0,
            )
            try:
                parsed = json.loads(self._clean_json_response(content))
                if not isinstance(parsed, dict):
                    raise ValueError(
                        f"Expected a top-level JSON object, got {type(parsed).__name__}"
                    )
                if response_model:
                    return response_model.model_validate(parsed).model_dump()
                return parsed
            except (json.JSONDecodeError, TypeError, ValueError) as exc:
                last_error = exc
                logger.warning(
                    "Nebius structured output attempt %s/%s was invalid: %s; output=%r",
                    attempt,
                    3,
                    exc,
                    content[:300],
                )
                if attempt < 3:
                    retry_prompt = (
                        f"{user_prompt}\n\nYour previous response was empty or invalid. "
                        "Return ONLY one complete top-level JSON OBJECT now, never a JSON array. "
                        "The object must contain every required field from the schema, including "
                        "action, intent, target, thought, ordered_steps, and current_requirement. "
                        "Do not explain, use markdown, or omit any required field."
                    )
        raise ValueError(f"Nebius output was not valid JSON after retry: {last_error}") from last_error

    async def generate_text(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.1,
    ) -> str:
        return await self._complete(system_prompt, user_prompt, temperature)
