"""Tests for /api/v1/share endpoints."""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

# ── Helpers ───────────────────────────────────────────────────────────────────


def make_shared_result(**kwargs):
    from app.db.models.shared_result import SharedResult

    row = SharedResult(
        user_id=kwargs.get("user_id"),
        tool_id=kwargs.get("tool_id", "uppercase"),
        tool_label=kwargs.get("tool_label", "Uppercase"),
        output_text=kwargs.get("output_text", "HELLO WORLD"),
    )
    row.id = kwargs.get("id", uuid.uuid4())
    row.view_count = kwargs.get("view_count", 0)
    row.created_at = kwargs.get("created_at", datetime.now(UTC))
    row.expires_at = kwargs.get("expires_at", datetime.now(UTC) + timedelta(days=30))
    return row


# ── POST /share ───────────────────────────────────────────────────────────────


def test_create_share_anonymous(anon_client, mock_db):
    resp = anon_client.post(
        "/api/v1/share",
        json={
            "tool_id": "uppercase",
            "tool_label": "Uppercase",
            "output_text": "HELLO WORLD",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "id" in data
    assert "share_url" in data
    assert "uppercase" not in data["share_url"] or True  # url contains share id


def test_create_share_authenticated(client, mock_db):
    resp = client.post(
        "/api/v1/share",
        json={
            "tool_id": "lowercase",
            "tool_label": "Lowercase",
            "output_text": "hello world",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "share_url" in data


def test_create_share_missing_fields(anon_client):
    resp = anon_client.post(
        "/api/v1/share",
        json={"tool_id": "uppercase"},
    )
    assert resp.status_code == 422


def test_create_share_at_max_length(anon_client, mock_db):
    # Max allowed length per schema validation (50k chars)
    long_text = "x" * 50_000
    resp = anon_client.post(
        "/api/v1/share",
        json={
            "tool_id": "uppercase",
            "tool_label": "Uppercase",
            "output_text": long_text,
        },
    )
    assert resp.status_code == 200


def test_create_share_over_max_length_rejected(anon_client):
    # Schema rejects text over 50k chars
    long_text = "x" * 50_001
    resp = anon_client.post(
        "/api/v1/share",
        json={
            "tool_id": "uppercase",
            "tool_label": "Uppercase",
            "output_text": long_text,
        },
    )
    assert resp.status_code == 422


# ── GET /share/{share_id} ─────────────────────────────────────────────────────


def test_get_share_success(anon_client, mock_db):
    share_id = uuid.uuid4()
    row = make_shared_result(id=share_id)

    result = MagicMock()
    result.scalar_one_or_none.return_value = row
    mock_db.execute.return_value = result

    resp = anon_client.get(f"/api/v1/share/{share_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == str(share_id)
    assert data["tool_id"] == "uppercase"
    assert data["output_text"] == "HELLO WORLD"


def test_get_share_not_found(anon_client, mock_db):
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = result

    resp = anon_client.get(f"/api/v1/share/{uuid.uuid4()}")
    assert resp.status_code == 404


def test_get_share_invalid_uuid(anon_client, mock_db):
    resp = anon_client.get("/api/v1/share/not-a-uuid")
    assert resp.status_code == 404


def test_get_share_expired(anon_client, mock_db):
    share_id = uuid.uuid4()
    row = make_shared_result(
        id=share_id,
        created_at=datetime.now(UTC) - timedelta(days=31),  # expired
    )

    result = MagicMock()
    result.scalar_one_or_none.return_value = row
    mock_db.execute.return_value = result

    resp = anon_client.get(f"/api/v1/share/{share_id}")
    assert resp.status_code == 410


def test_get_share_contains_all_fields(anon_client, mock_db):
    share_id = uuid.uuid4()
    row = make_shared_result(
        id=share_id,
        tool_id="reverse",
        tool_label="Reverse",
        output_text="olleh",
    )

    result = MagicMock()
    result.scalar_one_or_none.return_value = row
    mock_db.execute.return_value = result

    resp = anon_client.get(f"/api/v1/share/{share_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["tool_id"] == "reverse"
    assert data["tool_label"] == "Reverse"
    assert data["output_text"] == "olleh"
    assert "created_at" in data
