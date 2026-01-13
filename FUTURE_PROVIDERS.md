# Future AI Provider Integration Guide

The current `AIClient` is designed for easy extension to support multiple AI providers.

## Current Architecture

```python
class AIClient:
    def __init__(self):
        self.openai_client = OpenAI(...)
        self.model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    def call(self, prompt: str, expect_json: bool = True) -> AIResponse:
        # Calls OpenAI API
        ...
```

## Adding Google Gemini (Future)

### Step 1: Add Environment Variables

```bash
# .env
AI_PROVIDER=openai  # or "gemini" or "anthropic"
GEMINI_API_KEY=your-gemini-key
GEMINI_MODEL=gemini-1.5-flash
```

### Step 2: Extend AIClient.__init__()

```python
def __init__(self):
    self.provider = os.getenv("AI_PROVIDER", "openai")

    if self.provider == "openai":
        self.openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    elif self.provider == "gemini":
        import google.generativeai as genai
        genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
        self.gemini_client = genai.GenerativeModel(os.getenv("GEMINI_MODEL"))

    elif self.provider == "anthropic":
        from anthropic import Anthropic
        self.anthropic_client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        self.model = os.getenv("ANTHROPIC_MODEL", "claude-3-5-haiku-20241022")
```

### Step 3: Route in call() Method

```python
def call(self, prompt: str, expect_json: bool = True) -> AIResponse:
    if self.provider == "openai":
        return self._call_openai(prompt, expect_json)
    elif self.provider == "gemini":
        return self._call_gemini(prompt, expect_json)
    elif self.provider == "anthropic":
        return self._call_anthropic(prompt, expect_json)
    else:
        raise ValueError(f"Unknown provider: {self.provider}")

def _call_openai(self, prompt: str, expect_json: bool) -> AIResponse:
    # Current implementation
    ...

def _call_gemini(self, prompt: str, expect_json: bool) -> AIResponse:
    system_prompt, user_prompt = self._split_prompt(prompt)

    response = self.gemini_client.generate_content(
        user_prompt,
        generation_config={
            "response_mime_type": "application/json" if expect_json else "text/plain"
        }
    )

    return AIResponse(success=True, output=response.text)

def _call_anthropic(self, prompt: str, expect_json: bool) -> AIResponse:
    system_prompt, user_prompt = self._split_prompt(prompt)

    message = self.anthropic_client.messages.create(
        model=self.model,
        max_tokens=1000,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}]
    )

    return AIResponse(success=True, output=message.content[0].text)
```

## Adding Provider-Specific Fallback

```python
def __init__(self):
    self.primary_provider = os.getenv("AI_PRIMARY_PROVIDER", "openai")
    self.fallback_provider = os.getenv("AI_FALLBACK_PROVIDER", None)

    # Initialize both providers
    self._init_provider(self.primary_provider, is_primary=True)
    if self.fallback_provider:
        self._init_provider(self.fallback_provider, is_primary=False)

def call(self, prompt: str, expect_json: bool = True) -> AIResponse:
    # Try primary
    result = self._call_provider(self.primary_provider, prompt, expect_json)

    if result.success:
        return result

    # Try fallback
    if self.fallback_provider:
        logger.warning(f"Primary provider failed, trying fallback: {self.fallback_provider}")
        return self._call_provider(self.fallback_provider, prompt, expect_json)

    return result
```

## Benefits of Current Architecture

- ✅ Single `AIResponse` interface for all providers
- ✅ Consistent error handling
- ✅ Easy to add new providers (just add a new `_call_*` method)
- ✅ No changes needed in `AIHandler` or `IntentRouter`
- ✅ Provider-specific optimizations (JSON mode, temperature, etc.)
- ✅ Fallback support built-in structure
