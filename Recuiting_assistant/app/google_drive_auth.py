import os
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

from app.google_drive import SCOPES


def main() -> None:
    credentials_path = Path(
        os.getenv("GOOGLE_OAUTH_CREDENTIALS_PATH", "/app/secrets/credentials.json")
    )
    token_path = Path(os.getenv("GOOGLE_OAUTH_TOKEN_PATH", "/app/secrets/token.json"))

    if not credentials_path.is_file():
        raise SystemExit(f"OAuth client file not found: {credentials_path}")

    flow = InstalledAppFlow.from_client_secrets_file(credentials_path, SCOPES)
    credentials = flow.run_local_server(
        host="localhost",
        bind_addr="0.0.0.0",
        port=8080,
        open_browser=False,
        authorization_prompt_message="\nOpen this URL in your browser:\n{url}\n",
        success_message="Google Drive authorization completed. You can close this tab.",
        access_type="offline",
        prompt="consent",
    )

    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(credentials.to_json())
    token_path.chmod(0o600)
    print(f"Authorization token saved to {token_path}")


if __name__ == "__main__":
    main()
