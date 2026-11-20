# AI Software Requirement Validator (ReqValidator)

A web application for managing and reviewing Software Requirements Specifications (SRS).
All analysis is performed locally — **no cloud AI APIs, no AI-provider keys, no paid inference**.

Architecture: React + Vite → Spring Boot (Java 21, MongoDB) → FastAPI analysis service (Python). Optional SmolLM2-135M-Instruct language model runs inside the user's browser.

## Three separate AI capabilities

| Feature | What it is | Needs a download? |
|---|---|---|
| **SRS analysis engine** (FastAPI) | Deterministic NLP + rules engine; runs automatically on the results page | No |
| **Instant Offline Guide** | Rule-based answers about the report — not an LLM | No |
| **Local AI Chat / Deep Review** | Real `onnx-community/SmolLM2-135M-Instruct-ONNX-MHA` generation in the browser (Transformers.js, ONNX Runtime, WebGPU → WASM fallback) | Yes, once (cached by the browser; quantized ONNX weights are about 182 MB) |

## Analysis engine (`ai-service/srs_engine`)

- **Parsing:** actor, modal/obligation, main action, object, triggers, schedules, measurable constraints (with units and comparators), references, user-story parts.
- **Classification:** functional, non-functional, constraint, business rule, user story; categories for security, performance, availability, reliability, usability, compatibility, maintainability, privacy, data, interface/integration, compliance, scalability.
- **~35 defect checks**, each with evidence, why it matters, a recommendation and a clarification question: vague/ambiguous terms, missing actor/action/outcome, incomplete, not testable, non-atomic, missing pre/postconditions, inputs, outputs, exception handling, validation rules, authorization, security constraints, performance thresholds, measurable targets, unclear references, open-ended scope, terminology, unidentified dependencies, boundaries, triggers, data constraints, incomplete business rules, acceptance criteria, failure/recovery, unrealistic commitments.
- **Explainable scores:** eight dimensions (clarity, completeness, testability, atomicity, consistency, verifiability, feasibility, traceability), each 100 minus documented deductions. Overall = 40% weighted dimension average + 60% per-finding penalty, with documented caps. Every deduction is listed in `score_breakdown`.
- **Generated review:** strengths, improved draft with `[TBD]` placeholders (never invented values), questions, Given/When/Then acceptance criteria, positive/negative/boundary tests, priority with reason.
- **Document level:** duplicates (TF-IDF similarity), possible contradictions (polarity, conflicting thresholds, obligation level, opposing terms, access scope), dependencies (explicit references, data lifecycle, login preconditions), terminology consistency, coverage gaps, likely missing requirements, traceability (generated/duplicate IDs, broken references, matrix), risks, executive summary and prioritised improvement plan.
- **Optional semantic similarity:** `pip install -r requirements-optional.txt && python setup_models.py`, then set `SRS_SEMANTIC_MODEL`. Loaded lazily from local files only; falls back to TF-IDF. Not recommended on 512 MB free tiers.

The engine is deterministic: findings are review signals, not proof, and it does not claim to be a trained neural network.

## Document processing

PDF, DOCX, DOC and TXT. Original requirement IDs (`REQ-001`, `FR-1`, `NFR-2.1`, `3.2.1`) and section headings are preserved; lines wrapped by PDF extraction are joined; exact duplicates are reported; empty, scanned, corrupted or requirement-free documents return clear errors.

## Deployment (Render / Vercel / MongoDB Atlas)

FastAPI service (Root Directory `ai-service`): build `pip install -r requirements.txt`, start `uvicorn main:app --host 0.0.0.0 --port $PORT`, env `SRS_API_KEY`.
Spring Boot: `LLM_API_URL=https://<ai-service>.onrender.com`, `LLM_API_KEY=<same as SRS_API_KEY>`, `MONGODB_URI`, `JWT_SECRET`.
`SRS_API_KEY`/`LLM_API_KEY` is only an **internal service-to-service key**; it is never sent to the browser and is not an AI-provider key. No GPU or model download is needed on the server.

## Local development & tests

```bash
cd ai-service && python -m venv .venv && .venv/Scripts/activate   # or source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
python -m unittest -v test_engine          # engine + API tests
uvicorn main:app --port 8001

cd backend && ./mvnw test                   # needs JWT_SECRET, LLM_API_KEY env vars
cd frontend && npm install && npm run lint && npm run build
```

## Security

Never commit API keys, database credentials, JWT secrets, or `.env` files. The browser talks only to Spring Boot for application data; the local SmolLM2 model downloads public model files on first use and performs inference in the browser. Prompts are not sent to an AI inference API.
