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
        logger.info(f"AIClient initialized with model: {self.model}")

    def call(self, prompt: str, expect_json: bool = True) -> AIResponse:
        """
        Execute AI call with OpenAI API.

        Automatically detects model type and uses appropriate API:
        - GPT-5 models: Responses API (simpler, newer)
        - GPT-4 models: Chat Completions API (classic)

        Args:
            prompt: Full prompt including system instructions and user query
            expect_json: Whether to use JSON response format

        Returns:
            AIResponse with success status and output
        """
        import time
        start_time = time.time()

        # Detect if using GPT-5 models (use Responses API)
        is_gpt5 = self.model.startswith("gpt-5")

        if is_gpt5:
            return self._call_responses_api(prompt, expect_json, start_time)
        else:
            return self._call_chat_completions_api(prompt, expect_json, start_time)

    def _call_responses_api(self, prompt: str, expect_json: bool, start_time: float) -> AIResponse:
        """
        Call using the new Responses API for GPT-5 models.
        Simpler API: single input parameter, direct output_text access.
        """
        import time

        try:
            # Combine system and user prompts into single input
            system_prompt, user_prompt = self._split_prompt(prompt)

            # For Responses API, combine everything into single input
            if system_prompt:
                full_input = f"{system_prompt}\n\n{user_prompt}"
            else:
                full_input = user_prompt

            prompt_size = len(full_input)
            logger.info(f"Calling Responses API with model={self.model}, input_size={prompt_size} chars")

            # Build request kwargs for Responses API
            kwargs = {
                "model": self.model,
                "input": full_input,
            }

            # CRITICAL: Set reasoning effort to 'minimal' for lowest latency
            # GPT-5 models default to higher reasoning which causes significant delays (10-20s)
            # For personal assistant use case, we need speed over deep reasoning
            # Options: 'minimal' (fastest), 'low', 'medium', 'high' (slowest)
            reasoning_effort = os.getenv("GPT5_REASONING_EFFORT", "minimal")
            kwargs["reasoning"] = {"effort": reasoning_effort}

            # Note: Responses API does NOT support max_completion_tokens or max_tokens
            # Token control is handled through the reasoning effort level
            logger.info(f"Responses API params: reasoning={reasoning_effort}")

            api_start = time.time()
            response = self.openai_client.responses.create(**kwargs)
            api_duration = time.time() - api_start

            # Access output from Responses API
            output = response.output_text
            if output is None:
                logger.error(f"Responses API returned None. Full response: {response}")
                return AIResponse(
                    success=False,
                    error="Responses API returned empty response"
                )

            output = output.strip()

            total_duration = time.time() - start_time
            logger.info(f"Response received in {total_duration:.2f}s (API call: {api_duration:.2f}s, output: {len(output)} chars)")

            if len(output) == 0:
                logger.error(f"Responses API returned empty content")
                return AIResponse(
                    success=False,
                    error="Responses API returned empty content"
                )

            # Extract JSON from markdown if expected
            if expect_json:
                output = self._extract_json_from_markdown(output)
                logger.info(f"Extracted JSON from markdown, final length: {len(output)} chars")

            return AIResponse(
                success=True,
                output=output,
                raw_response=response
            )

        except Exception as e:
            logger.error(f"Responses API error: {e}")
            return AIResponse(
                success=False,
                error=str(e)
            )

    def _call_chat_completions_api(self, prompt: str, expect_json: bool, start_time: float) -> AIResponse:
        """
        Call using the classic Chat Completions API for GPT-4 models.
        Uses messages array and structured response format support.
        """
        import time

        try:
            # Split prompt into system and user parts
            system_prompt, user_prompt = self._split_prompt(prompt)

            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": user_prompt})

            prompt_size = len(system_prompt) + len(user_prompt)
            logger.info(f"Calling Chat Completions API with model={self.model}, prompt_size={prompt_size} chars")

            # Build request kwargs
            kwargs = {
                "model": self.model,
                "messages": messages,
                "max_completion_tokens": 1000,
                "temperature": 0.3  # Low temperature for consistent responses
            }

            # Add JSON mode if expected and supported
            # Only GPT-4o, GPT-4o-mini, and GPT-4-turbo support structured outputs
            supports_json_mode = any([
                self.model.startswith("gpt-4o"),
                self.model.startswith("gpt-4-turbo"),
                "gpt-4-1106" in self.model,  # GPT-4 Turbo preview
            ])

            if expect_json and supports_json_mode:
                kwargs["response_format"] = {"type": "json_object"}

            api_start = time.time()
            response = self.openai_client.chat.completions.create(**kwargs)
            api_duration = time.time() - api_start

            output = response.choices[0].message.content
            if output is None:
                logger.error(f"Chat Completions API returned None content")
                return AIResponse(
                    success=False,
                    error="Chat Completions API returned empty response"
                )

            output = output.strip()

            total_duration = time.time() - start_time
            logger.info(f"Response received in {total_duration:.2f}s (API call: {api_duration:.2f}s, output: {len(output)} chars)")

            if len(output) == 0:
                logger.error(f"Chat Completions API returned empty content")
                return AIResponse(
                    success=False,
                    error="Chat Completions API returned empty content"
                )

            # For models without native JSON mode, extract JSON from markdown
            if expect_json and not supports_json_mode:
                output = self._extract_json_from_markdown(output)
                logger.info(f"Extracted JSON from markdown, final length: {len(output)} chars")

            return AIResponse(
                success=True,
                output=output,
                raw_response=response
            )

        except Exception as e:
            logger.error(f"Chat Completions API error: {e}")
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
        Uses fastest model available for minimal latency.
        """
        # For classification, always use the fastest model (gpt-5-nano or gpt-4o-mini)
        original_model = self.model

        # Override to fastest model for classification
        if os.getenv("CLASSIFICATION_MODEL"):
            self.model = os.getenv("CLASSIFICATION_MODEL")
        elif self.model.startswith("gpt-5"):
            # If using GPT-5, downgrade to nano for classification
            self.model = "gpt-5-nano"
            logger.info(f"Classification: using {self.model} (faster than {original_model})")

        try:
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
        finally:
            # Restore original model
            self.model = original_model
