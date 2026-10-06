import importlib

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.main import app, get_db, run_job


@pytest.fixture
def client(tmp_path, monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    TestingSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)
    monkeypatch.setattr("app.main.SessionLocal", TestingSession)
    monkeypatch.setattr("app.main.OUTPUT_DIR", tmp_path / "certs")
    def override_get_db():
        yield from _db_session(TestingSession)

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _db_session(factory):
    db = factory()
    try:
        yield db
    finally:
        db.close()


def test_bulk_job_partial_validation_and_certificate_retrieval(client):
    response = client.post("/jobs", json={
        "event_name": "Python Course", "issued_on": "2026-10-07",
        "recipients": [
            {"name": "Ada Lovelace", "email": "ada@example.com"},
            {"name": "", "email": "not-an-email"},
        ],
    })
    assert response.status_code == 202
    created = response.json()
    assert created["status"] == "queued"
    assert created["total"] == 2 and created["failed"] == 1
    run_job(created["id"])
    created = client.get(f"/jobs/{created['id']}").json()
    assert created["status"] == "completed_with_errors"
    assert created["recipients"][1]["status"] == "failed"

    # All-invalid batches are immediately final. Exercise the actual worker with a valid row separately.
    response = client.post("/jobs", json={
        "event_name": "Python Course", "issued_on": "2026-10-07",
        "recipients": [{"name": "Grace Hopper", "email": "grace@example.com"}],
    })
    job = response.json()
    run_job(job["id"])
    job = client.get(f"/jobs/{job['id']}").json()
    assert job["status"] == "completed"
    assert job["succeeded"] == 1
    status = client.get(f"/jobs/{job['id']}").json()
    assert status["recipients"][0]["status"] == "succeeded"
    download = client.get(status["recipients"][0]["certificate_url"])
    assert download.status_code == 200
    assert download.headers["content-type"] == "application/pdf"
    assert download.content.startswith(b"%PDF")


def test_invalid_top_level_input_and_unknown_job(client):
    assert client.post("/jobs", json={"event_name": "", "issued_on": "bad", "recipients": []}).status_code == 422
    assert client.get("/jobs/9999").status_code == 404


def test_one_generation_failure_does_not_stop_other_recipients(client, monkeypatch):
    original = importlib.import_module("app.main").generate_certificate

    def sometimes_fail(name, event, issued, path):
        if name == "Broken Recipient":
            raise RuntimeError("disk write failed")
        return original(name, event, issued, path)

    monkeypatch.setattr("app.main.generate_certificate", sometimes_fail)
    response = client.post("/jobs", json={
        "event_name": "Course", "issued_on": "2026-10-07",
        "recipients": [
            {"name": "Broken Recipient", "email": "broken@example.com"},
            {"name": "Working Recipient", "email": "works@example.com"},
        ],
    })
    job = response.json()
    run_job(job["id"])
    job = client.get(f"/jobs/{job['id']}").json()
    assert job["status"] == "completed_with_errors"
    assert job["failed"] == 1 and job["succeeded"] == 1
    assert [x["status"] for x in job["recipients"]] == ["failed", "succeeded"]
