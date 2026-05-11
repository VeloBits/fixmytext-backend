# Contributing to FixMyText Backend

## 1. Welcome

Thank you for your interest in contributing to the FixMyText backend! Every contribution -- whether it is a bug fix, a new text tool, improved documentation, or a test -- helps make the project better for everyone.

Please read and follow our [Code of Conduct](CODE_OF_CONDUCT.md) in all interactions.

---

## 2. Prerequisites

Before you begin, make sure you have the following installed and available:

- **Python 3.12+**
- **PostgreSQL 16** (or Docker to run it in a container)
- **Git**
- **Groq API key** -- free at [console.groq.com](https://console.groq.com) (required only for AI-powered tools)
- **Razorpay keys** -- optional, needed only if you are working on billing features

---

## 3. Getting Started

### Docker (recommended)

```bash
cd backend
cp .env.example .env
docker compose --profile dev up --build
```

The API will be available at `http://localhost:8000` and interactive docs at `http://localhost:8000/docs`.

### Manual setup

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
alembic upgrade head
uvicorn main:app --reload --port 8000
```

Edit `.env` with your database connection string, Groq API key, and any other required values before starting the server.

---

## 4. Branch Naming

Use the following prefixes for your branches:

| Prefix       | Purpose                                      | Example                              |
|--------------|----------------------------------------------|--------------------------------------|
| `feat/`      | New feature or tool                          | `feat/morse-decoder-endpoint`        |
| `fix/`       | Bug fix                                      | `fix/caesar-cipher-empty-input`      |
| `docs/`      | Documentation changes                        | `docs/update-env-example`            |
| `refactor/`  | Code restructuring without behavior change   | `refactor/extract-text-helpers`      |
| `test/`      | Adding or updating tests                     | `test/ai-service-unit-tests`         |
| `chore/`     | Dependency updates, CI, tooling              | `chore/upgrade-fastapi-0.111`        |

---

## 5. Commit Messages

Follow the [Conventional Commits](https://www.conventionalcommits.org/) specification:

```
feat: add morse decoder endpoint
fix: handle empty text in caesar cipher
docs: add Groq setup instructions to README
refactor: move validation logic to schemas
test: add coverage for reverse-words service
chore: bump SQLAlchemy to 2.0.30
```

Keep the subject line under 72 characters. Use the body for additional context when needed.

---

## 6. Coding Standards (Python)

### Formatting and linting

- **Ruff** for both formatting and linting with a line length of **120** characters.
- Run before committing:
  ```bash
  ruff format app/ tests/
  ruff check app/ tests/
  ```

### Type hints and docstrings

- Add **type hints** to all function signatures (parameters and return types).
- Use **Google-style docstrings** for all public functions and classes.

### Architecture rules

- Use **async** for all database operations.
- Place business logic in `app/services/`, never directly in endpoint functions.
- Pure (non-AI) text transformation functions go in `app/services/text_service.py`.
- AI-powered tool classes go in `app/services/ai_service.py` and must implement `async def process(self, text: str) -> str`.
- Use the `_local_endpoint()` helper for non-AI tools and `_ai_endpoint()` for AI tools in your endpoint files.
- **Never hardcode secrets.** All keys and credentials must come from environment variables.
- **Handle edge cases:** empty strings, whitespace-only input, and other boundary conditions must be handled gracefully.

---

## 7. How to Add a New Tool (Backend Side)

> **This is the most important section.** Adding a new tool is the most common type of contribution. Follow these steps carefully.

There are two kinds of tools: regular (non-AI) tools and AI-powered tools.

### Regular (non-AI) tool

**Step 1 -- Add the transformation function to `app/services/text_service.py`:**

```python
def reverse_words(text: str) -> str:
    """Reverse word order on each line.

    Args:
        text: Input string.

    Returns:
        String with reversed words.
    """
    lines = text.split('\n')
    return '\n'.join(' '.join(line.split()[::-1]) for line in lines)
```

Rules for service functions:
- Must be a **pure function** (no I/O, no database calls, no side effects).
- Must handle empty string input gracefully.
- Must have type hints and a Google-style docstring.

**Step 2 -- Add the endpoint to `app/api/v1/endpoints/text.py`:**

```python
@router.post("/reverse-words")
async def reverse_words_endpoint(
    request: TextRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user),
):
    return await _local_endpoint(
        request, db, current_user,
        tool_id="reverse_words",
        transform_fn=text_service.reverse_words
    )
```

The `_local_endpoint()` helper handles rate limit enforcement, calling your transform function, building the response, and recording operation history for authenticated users.

**Step 3 -- Test your endpoint:**

Test via curl:

```bash
curl -X POST http://localhost:8000/api/v1/text/reverse-words \
  -H "Content-Type: application/json" \
  -d '{"text": "hello world"}'
```

Also verify it appears and works correctly in the Swagger UI at `http://localhost:8000/docs`.

---

### AI tool

AI tools are dispatched through the `_AI_HANDLERS` registry in `app/services/ai_service.py`. Adding a new AI tool is a single dict entry — no new class required.

**Step 1 -- Add an entry to `_AI_HANDLERS` in `app/services/ai_service.py`:**

```python
_AI_HANDLERS: dict[
    str,
    tuple[str | None, Callable[..., str], tuple[Any, ...], dict[str, Any]],
] = {
    # tool_id: (prompt_key, fallback_fn, extra_fallback_args, ai_kwargs)
    ...
    "your-tool-slug": (
        "your_prompt_key",      # key in PROMPTS dict (app/services/ai_prompts.py)
        _passthrough_fallback,  # called when Groq is unavailable
        (),                     # extra positional args for the fallback (usually empty)
        {"temperature": 0.7, "max_tokens": 500},  # overrides for _ai_transform
    ),
}
```

Then add the matching prompt string to `PROMPTS` in `app/services/ai_prompts.py`:

```python
PROMPTS = {
    ...
    "your_prompt_key": "You are a ... Return ONLY the result, nothing else.",
}
```

For tools that need no meaningful offline fallback, use `_ai_unavailable_fallback` instead of `_passthrough_fallback`. That raises HTTP 503 when Groq is not configured.

**Step 2 -- Add the endpoint using the `_ai_endpoint()` helper:**

Wire it up in `app/api/v1/endpoints/text.py` the same way as a regular tool, but use `_ai_endpoint()` instead of `_local_endpoint()`. The `_ai_endpoint()` helper handles AI rate limiting, `run_ai_tool()` dispatch, access control, and history recording.

```python
@router.post("/your-tool-slug")
async def your_tool_endpoint(
    request: TextRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user),
):
    """Your tool description."""
    return await _ai_endpoint(
        request, db, current_user,
        tool_id="your-tool-slug",
    )
```

The `tool_id` passed to `_ai_endpoint()` must exactly match the key in `_AI_HANDLERS`.

> **Note:** A new tool also requires a matching definition in the frontend repository. The `tool_id` must be identical in both repos. See the frontend CONTRIBUTING.md for details.

---

## 8. Testing

Run the full test suite:

```bash
pytest
```

Run tests with coverage:

```bash
pytest --cov=app
```

Run tests for a specific file:

```bash
pytest tests/test_text_service.py -v
```

Write tests for every new tool or endpoint you add. Place test files in the `tests/` directory.

---

## 9. Database Migrations

Apply all pending migrations:

```bash
alembic upgrade head
```

Generate a new migration after changing models:

```bash
alembic revision --autogenerate -m "add usage_count column to tools"
```

Roll back the most recent migration:

```bash
alembic downgrade -1
```

Always review auto-generated migration files before committing -- Alembic does not catch every edge case.

---

## 10. PR Guidelines

Before opening a pull request, confirm the following:

- [ ] The new endpoint works correctly (tested via curl or Swagger UI).
- [ ] Code is formatted with **Ruff** (`ruff format .`).
- [ ] All tests pass (`pytest`).
- [ ] No secrets, API keys, or credentials are committed.
- [ ] The `tool_id` in the backend matches the corresponding definition in the frontend repo.
- [ ] Migration files (if any) are included and apply cleanly.

---

## 11. Review Process

- A maintainer will review your PR within **3 business days**.
- At least **one approval** is required before merging.
- PRs are merged using **squash merge** to keep the commit history clean.

Feel free to ping the maintainers if you have not received a review after 3 business days.

---

## 12. Reporting Issues

- **Bugs and feature requests:** Open a GitHub Issue with a clear description and steps to reproduce.
- **Security vulnerabilities:** Do **not** open a public issue. Email [security@velobits.org](mailto:security@velobits.org) directly with details.
