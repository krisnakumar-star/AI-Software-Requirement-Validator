# AI Software Requirement Validator

An AI-powered web application designed to help users validate software requirements, identify inconsistencies and duplicates, and analyze Software Requirements Specification (SRS) documents.

## Overview

The AI Software Requirement Validator provides a centralized platform for managing software projects and reviewing their requirements. It combines a React frontend, a Spring Boot backend, and a Python-based AI service.

## Features

- **User Authentication:** Register and log in securely.
- **Project Management:** Create, view, and manage software requirement projects.
- **SRS Upload:** Upload Software Requirements Specification documents.
- **Requirement Management:** Add and manage individual software requirements.
- **Requirement Validation:** Check requirements for potential issues.
- **Duplicate Detection:** Identify potentially duplicate requirements.
- **Consistency Detection:** Help identify inconsistencies between requirements.
- **AI-Powered Analysis:** Analyze requirements using the configured language-model service.
- **Validation Results:** Review validation results and analysis for your project.

## Technology Stack

| Component | Technologies |
|---|---|
| Frontend | React, Vite, JavaScript, CSS |
| Backend | Java, Spring Boot, Maven |
| AI Service | Python |
| Database | MongoDB |
| Authentication | JWT |
| Version Control | Git and GitHub |

## Project Structure

```text
AI-Software-Requirement-Validator/
├── ai-service/
│   └── main.py
├── backend/
│   ├── pom.xml
│   └── src/
│       └── main/
│           ├── java/
│           └── resources/
├── frontend/
│   ├── package.json
│   └── src/
├── .gitignore
└── README.md
```

## Application Screenshots

### Home Page

![Home Page](screenshots/home.png)

### Dashboard

![Dashboard](screenshots/dashboard.png)

### Validation Results

![Validation Results](screenshots/validation-result.png)
## Prerequisites

Install the following before running the application:

- Node.js and npm
- Java and Maven (or use the included Maven wrapper)
- Python 3
- MongoDB
- Access to the configured language-model API, if required for AI analysis

## Getting Started

### 1. Clone the repository

```bash
git clone https://github.com/krisnakumar-star/AI-Software-Requirement-Validator.git
cd AI-Software-Requirement-Validator
```

### 2. Start MongoDB

Ensure your MongoDB server is running and the database connection is configured correctly.

The backend's default database URI is:

```text
mongodb://localhost:27017/requirement_validator
```

### 3. Configure and run the AI service

The FastAPI service includes an offline, deterministic SRS analysis engine. It does not call an external LLM provider and does not require Groq, JarvisClaw, a provider API key, or paid AI credits.

Set `SRS_API_KEY` on the AI service. This private internal key must match the backend's `LLM_API_KEY` value.

The local analyzer evaluates requirement wording, actors, obligation language, measurable criteria, ambiguity indicators, completeness signals, testability, and likely requirement classification. It returns a structured quality assessment, issues, missing information, and a suggested rewrite. Its results are heuristic rather than generative-LLM output and should be reviewed by a requirements engineer.

Create `ai-service/.env` from `.env.example`, set `SRS_API_KEY`, then run:

```powershell
cd ai-service
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
if (!(Test-Path .env)) { Copy-Item .env.example .env }
uvicorn main:app --host 0.0.0.0 --port 8001
```

On Render, set `SRS_API_KEY` on the AI service and set the same value as `LLM_API_KEY` on the Spring Boot backend. No external provider key is needed.

### 4. Run Spring Boot

In a separate PowerShell terminal, set `LLM_API_KEY` to the same private value as `SRS_API_KEY`. Set `JWT_SECRET` to the existing application's stable secret. Configure `MONGODB_URI` if MongoDB is not using the local default. Never rotate the JWT secret casually because existing sessions depend on it.

```powershell
$env:LLM_API_URL = "http://localhost:8001"
$env:LLM_API_KEY = "same-value-as-SRS_API_KEY"
$env:LLM_API_CONNECT_TIMEOUT = "10000"
$env:LLM_API_READ_TIMEOUT = "120000"
cd backend
.\mvnw.cmd spring-boot:run
```

Spring Boot listens on port `8080` by default. The authenticated project analysis endpoint calls FastAPI and stores returned analyses on the existing requirement records.

### 5. Run React

```powershell
cd frontend
npm install
npm run dev
```

Open the local URL displayed by Vite. React only sends authenticated requests to Spring Boot; it never receives either AI service key.

### 6. Start MongoDB

If MongoDB is installed as a Windows service, run PowerShell as an account permitted to start it:

```powershell
Start-Service MongoDB
```

The backend uses `mongodb://localhost:27017/requirement_validator` by default. Set `MONGODB_URI` for a different local or hosted database.

## Security Notes

- Never commit API keys, passwords, or production secrets.
- Use environment variables for sensitive configuration.
- Use a unique, strong JWT secret.
- Configure CORS and database access appropriately before deployment.
- Do not expose private documents or uploaded user data in a public repository.

## Future Improvements

- More advanced requirement quality checks.
- Improved reporting and validation summaries.
- Enhanced requirement traceability.
- Deployment and integration testing.

## Author

**Krishna Kumar V**

GitHub: [Rakshali-p09](https://github.com/krisnakumar-star)

## License

No license has been specified yet. All rights are reserved by default unless a license is added to this repository.
