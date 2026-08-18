from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

import api.app as app_module


VALID_TOKEN = "test-token-with-at-least-thirty-two-characters"
AUTH_HEADERS = {"Authorization": f"Bearer {VALID_TOKEN}"}


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("ASSET_API_TOKEN", VALID_TOKEN)
    with TestClient(app_module.app) as test_client:
        yield test_client


PROTECTED_REQUESTS = [
    ("GET", "/api/v1/auth/check", None),
    ("POST", "/api/v1/jobs", {"command": "help"}),
    ("POST", "/api/v1/operations/daily", None),
    ("GET", "/api/v1/operations/daily/latest", None),
    ("GET", "/api/v1/operations/daily/history", None),
    ("GET", "/api/v1/approvals?limit=1", None),
    (
        "POST",
        "/api/v1/approvals/example/decision",
        {"decision": "ACKNOWLEDGED"},
    ),
    ("GET", "/api/v1/jobs/example", None),
    ("POST", "/api/v1/jobs/example/retry", None),
    ("GET", "/api/v1/hq/state", None),
]


@pytest.mark.parametrize(("method", "path", "body"), PROTECTED_REQUESTS)
def test_protected_routes_reject_missing_token(
    client: TestClient,
    method: str,
    path: str,
    body: dict[str, str] | None,
) -> None:
    response = client.request(method, path, json=body)

    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize(("method", "path", "body"), PROTECTED_REQUESTS)
def test_protected_routes_reject_wrong_token(
    client: TestClient,
    method: str,
    path: str,
    body: dict[str, str] | None,
) -> None:
    response = client.request(
        method,
        path,
        headers={"Authorization": "Bearer definitely-the-wrong-token-value"},
        json=body,
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}


def test_health_remains_public(client: TestClient) -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json"])
def test_unauthenticated_api_documentation_is_disabled(
    client: TestClient,
    path: str,
) -> None:
    response = client.get(path)

    assert response.status_code == 404


def test_auth_check_accepts_valid_token(client: TestClient) -> None:
    response = client.get("/api/v1/auth/check", headers=AUTH_HEADERS)

    assert response.status_code == 200
    assert response.json() == {"authenticated": True}


def test_protected_routes_accept_valid_token(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        app_module,
        "start_job",
        lambda _: {"job_id": "job-1", "status": "QUEUED"},
    )
    monkeypatch.setattr(
        app_module,
        "start_daily_operations",
        lambda: {"job_id": "daily-1", "status": "QUEUED"},
    )
    monkeypatch.setattr(
        app_module.RUN_STORE,
        "latest_run",
        lambda: {"run_id": "run-1", "status": "COMPLETED"},
    )
    monkeypatch.setattr(app_module.RUN_STORE, "recent_run_summaries", lambda _: [])
    monkeypatch.setattr(app_module.APPROVAL_STORE, "list", lambda **_: [])
    monkeypatch.setattr(
        app_module.APPROVAL_STORE,
        "decide",
        lambda **_: {"approval_id": "approval-1", "status": "ACKNOWLEDGED"},
    )
    monkeypatch.setattr(
        app_module.JOB_STORE,
        "get_job",
        lambda _: {"job_id": "job-1", "status": "COMPLETED"},
    )
    monkeypatch.setattr(
        app_module,
        "retry_job",
        lambda _: {"job_id": "retry-1", "status": "QUEUED"},
    )
    monkeypatch.setattr(
        app_module.JOB_STORE,
        "latest_hq_state",
        lambda: {"latest_job_id": None, "job_status": "IDLE"},
    )

    requests = [
        ("POST", "/api/v1/jobs", {"command": "help"}, 202),
        ("POST", "/api/v1/operations/daily", None, 202),
        ("GET", "/api/v1/operations/daily/latest", None, 200),
        ("GET", "/api/v1/operations/daily/history", None, 200),
        ("GET", "/api/v1/approvals?limit=1", None, 200),
        (
            "POST",
            "/api/v1/approvals/approval-1/decision",
            {"decision": "ACKNOWLEDGED"},
            200,
        ),
        ("GET", "/api/v1/jobs/job-1", None, 200),
        ("POST", "/api/v1/jobs/job-1/retry", None, 202),
        ("GET", "/api/v1/hq/state", None, 200),
    ]

    for method, path, body, expected_status in requests:
        response = client.request(method, path, headers=AUTH_HEADERS, json=body)
        assert response.status_code == expected_status, (method, path, response.text)


@pytest.mark.parametrize("token", [None, "short-token", " x" * 20])
def test_api_startup_fails_closed_for_invalid_token(
    monkeypatch: pytest.MonkeyPatch,
    token: str | None,
) -> None:
    if token is None:
        monkeypatch.delenv("ASSET_API_TOKEN", raising=False)
    else:
        monkeypatch.setenv("ASSET_API_TOKEN", token)

    with pytest.raises(RuntimeError, match="ASSET_API_TOKEN"):
        with TestClient(app_module.app):
            pass
