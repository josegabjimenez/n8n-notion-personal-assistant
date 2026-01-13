import os
import logging
from dataclasses import dataclass
from typing import Any, Optional
from openai import OpenAI

logger = logging.getLogger("AIClient")


@dataclass
class AIResponse:
    """Response from AI client."""
    success: bool
    output: str = ""
    error: str = ""
    raw_response: Any = None


class AIClient:
    """
    Unified AI client with direct API integration.
    Designed for future extensibility (Anthropic fallback).
    """

    def __init__(self):
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            logger.warning("OPENAI_API_KEY not set, AI calls will fail")

        self.openai_client = OpenAI(
            api_key=api_key,
            timeout=float(os.getenv("OPENAI_TIMEOUT", "30"))
        )
        self.model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    def call(self, prompt: str, expect_json: bool = True) -> AIResponse:
        """
        Execute AI call with OpenAI API.

        Args:
            prompt: Full prompt including system instructions and user query
            expect_json: Whether to use JSON response format

        Returns:
            AIResponse with success status and output
        """
        import time
        start_time = time.time()

        try:
            # Split prompt into system and user parts
            system_prompt, user_prompt = self._split_prompt(prompt)

            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": user_prompt})

            prompt_size = len(system_prompt) + len(user_prompt)
            logger.info(f"Calling OpenAI API with model={self.model}, prompt_size={prompt_size} chars")

            # Debug logging for GPT-5 models (to diagnose empty responses)
            if self.model.startswith("gpt-5") and os.getenv("DEBUG_GPT5", "false").lower() == "true":
                logger.debug(f"System prompt preview: {system_prompt[:500]}...")
                logger.debug(f"User prompt preview: {user_prompt[:500]}...")

            # Build request kwargs
            kwargs = {
                "model": self.model,
                "messages": messages,
                "max_completion_tokens": 1000
            }

            # Add temperature for models that support it (GPT-5 models don't)
            if not self.model.startswith("gpt-5"):
                kwargs["temperature"] = 0.3  # Low temperature for consistent responses

            # Add JSON mode if expected (GPT-5-nano doesn't support this)
            # Only GPT-4o, GPT-4o-mini, and GPT-4-turbo support structured outputs
            supports_json_mode = any([
                self.model.startswith("gpt-4o"),
                self.model.startswith("gpt-4-turbo"),
                "gpt-4-1106" in self.model,  # GPT-4 Turbo preview
            ])

            # For GPT-5 models, we'll parse JSON from markdown manually (like old CLI)
            if expect_json and supports_json_mode:
                kwargs["response_format"] = {"type": "json_object"}
            elif expect_json and self.model.startswith("gpt-5"):
                # GPT-5 models: don't force JSON mode, will extract from markdown later
                logger.info(f"Model {self.model} will return natural response, will extract JSON manually")

            api_start = time.time()
            response = self.openai_client.chat.completions.create(**kwargs)
            api_duration = time.time() - api_start

            output = response.choices[0].message.content
            if output is None:
                logger.error(f"OpenAI returned None content. Full response: {response}")
                return AIResponse(
                    success=False,
                    error="OpenAI returned empty response"
                )

            output = output.strip()

            total_duration = time.time() - start_time
            logger.info(f"AI response received in {total_duration:.2f}s (API call: {api_duration:.2f}s, output: {len(output)} chars)")

            if len(output) == 0:
                logger.error(f"OpenAI returned empty content after strip. Raw response: {response.choices[0].message}")
                return AIResponse(
                    success=False,
                    error="OpenAI returned empty content"
                )

            # For models without native JSON mode, extract JSON from markdown
            # (GPT-5 models may wrap JSON in markdown code blocks)
            if expect_json and not supports_json_mode:
                output = self._extract_json_from_markdown(output)
                logger.info(f"Extracted JSON from markdown, final length: {len(output)} chars")

            return AIResponse(
                success=True,
                output=output,
                raw_response=response
            )

        except Exception as e:
            logger.error(f"OpenAI API error: {e}")
            return AIResponse(
                success=False,
                error=str(e)
            )

    def _extract_json_from_markdown(self, output: str) -> str:
        """
        Extract JSON from markdown code blocks.
        Models may wrap JSON in ```json or ``` blocks.
        """
        # Try extracting from ```json blocks first
        if "```json" in output:
            parts = output.split("```json", 1)
            if len(parts) > 1:
                json_part = parts[1].split("```", 1)[0].strip()
                if json_part:
                    return json_part

        # Try extracting from generic ``` blocks
        if "```" in output:
            parts = output.split("```", 1)
            if len(parts) > 1:
                json_part = parts[1].split("```", 1)[0].strip()
                if json_part:
                    return json_part

        # No markdown blocks found, return as-is
        return output

    def _split_prompt(self, prompt: str) -> tuple[str, str]:
        """
        Split combined prompt into system and user parts.
        Looks for 'USER INPUT:' or similar markers.
        """
        markers = ["USER INPUT:", "USER STATUS QUERY:", "USER QUERY:"]

        for marker in markers:
            if marker in prompt:
                parts = prompt.split(marker, 1)
                system_prompt = parts[0].strip()
                user_prompt = marker + parts[1]
                return system_prompt, user_prompt

        # If no marker found, treat entire prompt as user message
        return "", prompt

    def call_for_classification(self, prompt: str) -> str:
        """
        Specialized call for intent router (expects single word response).
        """
        response = self.call(prompt, expect_json=False)

        if not response.success:
            logger.warning(f"Classification failed: {response.error}")
            return "general"  # Default on error

        output = response.output.lower().strip()

        # Extract domain from response
        for domain in ["tasks", "contacts", "status", "general"]:
            if domain in output:
                return domain

        return "general"
