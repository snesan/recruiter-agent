# Recuiting_assistant

A two-container recruiting assistant with a FastAPI API and Streamlit UI. The project accepts browser-based PDF uploads, evaluates resumes against a job description, and can shortlist PDFs from a shared Google Drive folder.

## Project layout

```text
Recuiting_assistant/
├── app/
│   ├── api.py
│   ├── google_drive.py
│   ├── google_drive_auth.py
│   ├── recruiter.py
│   └── ui.py
├── deployment/aws/       # ECS task and IAM templates
├── requirements/         # Separate API and UI dependencies
├── scripts/              # ECR push and AWS template rendering
├── compose.yaml
├── Dockerfile.api
└── Dockerfile.ui
```

## Run locally

1. Create the local environment file:

   ```bash
   cp .env.example .env
   ```

2. Add a current `OPENAI_API_KEY` to `.env`.

3. Build and start both services:

   ```bash
   docker compose up --build
   ```

4. Open [http://localhost:8501](http://localhost:8501). API documentation is available at [http://localhost:8000/docs](http://localhost:8000/docs).

## Google Drive setup

### Local Docker OAuth

The local setup supports a Google Desktop OAuth client:

1. Enable the Google Drive API and configure the OAuth consent screen in the credential's Google Cloud project.
2. Save the downloaded Desktop OAuth client as `secrets/credentials.json`.
3. Run the one-time authorization flow:

   ```bash
   docker compose run --rm -p 8080:8080 api python -m app.google_drive_auth
   ```

4. Open the printed Google URL, grant read-only Drive access, and return to the application. The refresh token is saved as `secrets/token.json` and is excluded from Docker images and source control.

### AWS service account

For ECS, create a Google service account with Drive API access, share the resume folder with its service-account email, and inject the complete service-account JSON through AWS Secrets Manager as `GOOGLE_SERVICE_ACCOUNT_JSON`. Do not deploy the local Desktop OAuth files from `secrets/`.

## AWS deployment

Follow [`deployment/aws/README.md`](deployment/aws/README.md) for the ECS Fargate deployment and cost-control steps.

## Security notes

- Secrets are excluded by `.gitignore` and `.dockerignore`.
- Uploaded resumes are processed from temporary files and are not retained by the API.
- The containers run as a non-root user.
- Expose only the Streamlit port publicly; the API remains reachable from the UI over the task's loopback interface.
