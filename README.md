# AI Software Requirement Validator

A web application for managing and reviewing Software Requirements Specifications (SRS), with a lightweight Python analysis service.

## Analysis service

The FastAPI service provides:
- Requirement classification: Functional, Non-Functional and Constraint.
- Textual clarity, completeness and testability assessment.
- Detection of vague language, missing actors/actions, weak acceptance criteria and broad compound statements.
- Requirement-specific findings, explanation and a suggested rewrite.
- Single and batch analysis using the existing API contract.

**Implementation note:** the current analyzer is a deterministic, model-free NLP/heuristic engine. It does not download model weights, call an external AI provider, require paid API credits, or claim to be a generative LLM. Its score is a textual quality indicator and should be reviewed by a requirements engineer.

## Render deployment

Create a Python Web Service with Root Directory `ai-service`.

- Build command: `pip install -r requirements.txt`
- Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
- Runtime: Python 3.11 or newer.
- Environment variable: `SRS_API_KEY` (private random value).
- Set the exact same value in Spring Boot as `LLM_API_KEY`.
- No model download, persistent model disk, GPU, JarvisClaw account, or paid AI provider is required.

Keep the existing Spring Boot configuration:
- `LLM_API_URL=https://<your-ai-service>.onrender.com`
- `LLM_API_KEY=<same value as SRS_API_KEY>`

## Local development

```bash
cd ai-service
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# macOS/Linux: source .venv/bin/activate
python -m pip install -r requirements.txt
```

Set `SRS_API_KEY`, then run:

```bash
uvicorn main:app --host 0.0.0.0 --port 8001
```

The API endpoints are `GET /`, `GET /health`, `POST /analyze`, and `POST /analyze-batch`. The single and batch response structures retain the fields used by the existing backend.

## Security

Never commit API keys, database credentials, JWT secrets, or production environment files. Keep the AI service private behind its internal API key. The browser must communicate through Spring Boot and must never receive service credentials.
