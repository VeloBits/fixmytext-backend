# Adding a New Tool (Backend)

> How to implement a new text transformation endpoint in the FixMyText backend.

## Overview

Most tools require changes to 2 files. AI tools use a different service file.

| Tool Type | Files to Change |
|-----------|----------------|
| Regular (non-AI) | `text_service.py` + `text.py` endpoint |
| AI-powered | `ai_service.py` + `text.py` endpoint |
| Custom schema | Above + `schemas/text.py` |

## Architecture

```
HTTP Request
  → Endpoint (app/api/v1/endpoints/text.py)
    → Helper (_local_endpoint or _ai_endpoint)
      → Service function (text_service.py or ai_service.py)
        → Response (TextResponse)
```

The helpers handle access control, history recording, and error handling automatically.

## Regular (Non-AI) Tools

### Step 1: Add Service Function

File: `app/services/text_service.py`

```python
def reverse_words(text: str) -> str:
    """Reverse the order of words on each line.

    Args:
        text: The input string to process.

    Returns:
        String with words reversed on each line.
    """
    lines = text.split('\n')
    return '\n'.join(' '.join(line.split()[::-1]) for line in lines)
```

Rules:
- **Pure function**: no I/O, no database calls, no API calls
- **Signature**: accept `text: str`, return `str`
- **Edge cases**: handle empty string, whitespace-only input
- **Docstring**: Google style with Args and Returns
- **Type hints**: required on all parameters and return

### Step 2: Add Endpoint

File: `app/api/v1/endpoints/text.py`

```python
@router.post("/reverse-words")
async def reverse_words_endpoint(
    request: TextRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user),
):
    """Reverse the order of words on each line."""
    return await _local_endpoint(
        request, db, current_user,
        tool_id="reverse_words",
        transform_fn=text_service.reverse_words
    )
```

The `_local_endpoint()` helper handles:
- Tool access enforcement (trial limits, passes)
- Calling your transform function
- Recording to operation history (for logged-in users)
- Building the TextResponse

**Important:** The `tool_id` must match the `id` field in the frontend's `tools.js`.

### Step 3: Test

```bash
curl -X POST http://localhost:8000/api/v1/text/reverse-words \
  -H "Content-Type: application/json" \
  -d '{"text": "hello world\nfoo bar"}'
```

Expected:
```json
{"original": "hello world\nfoo bar", "result": "world hello\nbar foo", "operation": "reverse_words"}
```

Also check Swagger UI: http://localhost:8000/docs

## AI-Powered Tools

### Step 1: Add Service Class

File: `app/services/ai_service.py`

```python
class SentimentAnalyzerService:
    """Analyze text sentiment using AI."""

    def __init__(self, groq_client):
        self.client = groq_client

    async def process(self, text: str) -> str:
        """Analyze sentiment of the input text.

        Args:
            text: Input text to analyze.

        Returns:
            Sentiment analysis result.
        """
        response = await self.client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{
                "role": "user",
                "content": f"Analyze the sentiment of this text. Provide a brief analysis.\n\n{text}"
            }],
            temperature=0.3,
            max_tokens=2048
        )
        return response.choices[0].message.content.strip()
```

Pattern:
- Class with `__init__(self, groq_client)` and `async def process(self, text: str) -> str`
- Model: `llama-3.3-70b-versatile`
- Keep temperature low (0.3) for consistent results
- Strip whitespace from response

### Step 2: Add Endpoint

```python
@router.post("/sentiment-analysis")
async def sentiment_analysis_endpoint(
    request: TextRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user),
):
    """AI-powered sentiment analysis."""
    return await _ai_endpoint(
        request, db, current_user,
        tool_id="sentiment_analysis",
        service_class=SentimentAnalyzerService
    )
```

The `_ai_endpoint()` helper handles:
- AI rate limiting (`ai_limiter.check()`)
- Groq client injection
- Access control and history recording

## Custom Request Schemas

If your tool needs extra parameters beyond `text`, add a schema to `app/schemas/text.py`:

```python
class ShiftRequest(BaseModel):
    text: str = Field(min_length=1, max_length=50_000)
    shift: int = Field(default=3, ge=1, le=25)
```

Then use it in your endpoint:
```python
@router.post("/your-cipher")
async def your_cipher_endpoint(request: ShiftRequest, ...):
    result = your_cipher(request.text, request.shift)
    ...
```

## Writing Tests

File: `tests/test_text_service.py`

```python
from app.services.text_service import reverse_words

def test_reverse_words():
    assert reverse_words("hello world") == "world hello"

def test_reverse_words_multiline():
    assert reverse_words("foo bar\nbaz qux") == "bar foo\nqux baz"

def test_reverse_words_empty():
    assert reverse_words("") == ""

def test_reverse_words_single_word():
    assert reverse_words("hello") == "hello"
```

```bash
pytest tests/test_text_service.py -v
pytest --cov=app
```

## Checklist

- [ ] Service function has type hints and Google-style docstring
- [ ] Edge cases handled (empty string, whitespace-only)
- [ ] `tool_id` in endpoint matches frontend `tools.js` `id` field
- [ ] Endpoint tested via curl or Swagger UI
- [ ] No hardcoded secrets or API keys
- [ ] Tests written for service function
- [ ] Code formatted and linted with `ruff format . && ruff check .`
