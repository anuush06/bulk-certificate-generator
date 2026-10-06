# Bulk Certificate Generator

A small FastAPI service that accepts one bulk request, validates each recipient independently, creates a PDF certificate for each valid row, tracks per-recipient outcomes, and serves generated PDFs.

## Setup and run

Requires Python 3.10 or newer.

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

The default database is SQLite at `certificates.db`; generated files are stored under `generated_certificates/`. Set `DATABASE_URL` to a SQLAlchemy URL and `CERTIFICATE_OUTPUT_DIR` to change these locations. Tables are created on startup.

## Submit a generation request

`POST /jobs` accepts an event name, issue date, and up to 1,000 recipient objects. The response includes the job ID, status, and recipient outcomes. Invalid recipient rows are recorded as failures while valid rows continue.

```bash
curl -X POST http://localhost:8000/jobs \
  -H 'Content-Type: application/json' \
  -d '{"event_name":"Data Science Bootcamp","issued_on":"2026-10-07","recipients":[{"name":"Ada Lovelace","email":"ada@example.com"},{"name":"Invalid row","email":"not-an-email"}]}'
```

## Check status and retrieve certificates

Use `GET /jobs/{job_id}` to read overall progress (`queued`, `processing`, `completed`, or `completed_with_errors`) and each recipient's status/error. Successful rows include a `certificate_url`, for example:

```bash
curl -OJ http://localhost:8000/certificates/1
```

The certificate endpoint returns a PDF. Recipient IDs are returned in the job response.

## Tests

```bash
pytest
```

## Design decisions

- FastAPI provides request parsing, OpenAPI docs, and a lightweight HTTP layer; SQLAlchemy persists jobs and recipient results in a relational database.
- Bulk work uses FastAPI's in-process background task facility. This keeps request latency low and each recipient is committed independently, so an individual render error does not cancel other rows. Poll `GET /jobs/{id}` for progress. This is suitable for a single-process assignment/demo; for multi-worker production deployment, move the worker to a durable queue (for example Celery/RQ) and store PDFs in shared object storage.
- Top-level request structure (event name, date, recipient count) is validated as a whole. Recipient shape, non-empty name, and email are checked row by row and captured as failures so a malformed recipient does not reject the rest of the bulk submission.
- One fixed landscape PDF template is rendered with ReportLab. Files use recipient-result IDs as names, avoiding collisions when names repeat.
