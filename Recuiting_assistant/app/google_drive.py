import json
import os
import re
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials as UserCredentials
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload


SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
FOLDER_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")
PDF_MIME_TYPE = "application/pdf"
FOLDER_MIME_TYPE = "application/vnd.google-apps.folder"


class DriveConfigurationError(RuntimeError):
    pass


class DriveFolderError(RuntimeError):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


def normalize_folder_id(folder_reference: str) -> str:
    reference = folder_reference.strip()
    if not reference:
        raise DriveFolderError("Provide a Google Drive folder ID or folder URL.")

    parsed = urlparse(reference)
    if parsed.scheme or parsed.netloc:
        if parsed.scheme not in {"http", "https"} or parsed.netloc.lower() not in {
            "drive.google.com",
            "www.drive.google.com",
        }:
            raise DriveFolderError("Provide a valid Google Drive folder URL.")

        path_parts = [unquote(part) for part in parsed.path.split("/") if part]
        if "folders" in path_parts:
            folder_index = path_parts.index("folders") + 1
            folder_id = path_parts[folder_index] if folder_index < len(path_parts) else ""
        else:
            folder_id = parse_qs(parsed.query).get("id", [""])[0]
    else:
        folder_id = reference

    if not FOLDER_ID_PATTERN.fullmatch(folder_id):
        raise DriveFolderError("Provide a valid Google Drive folder ID or folder URL.")
    return folder_id


def get_drive_service():
    raw_credentials = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
    service_account_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")

    if raw_credentials:
        credentials = service_account.Credentials.from_service_account_info(
            json.loads(raw_credentials), scopes=SCOPES
        )
    elif service_account_path:
        credentials = service_account.Credentials.from_service_account_file(
            service_account_path, scopes=SCOPES
        )
    else:
        credentials = _load_user_credentials()

    return build("drive", "v3", credentials=credentials, cache_discovery=False)


def _load_user_credentials() -> UserCredentials:
    token_path = Path(os.getenv("GOOGLE_OAUTH_TOKEN_PATH", "/app/secrets/token.json"))
    credentials_path = Path(
        os.getenv("GOOGLE_OAUTH_CREDENTIALS_PATH", "/app/secrets/credentials.json")
    )

    if not credentials_path.is_file():
        raise DriveConfigurationError(
            "Google OAuth credentials are missing. Add secrets/credentials.json or configure "
            "GOOGLE_SERVICE_ACCOUNT_JSON."
        )
    if not token_path.is_file():
        raise DriveConfigurationError(
            "Google Drive authorization is required. Run: "
            "docker compose run --rm -p 8080:8080 api python -m app.google_drive_auth"
        )

    credentials = UserCredentials.from_authorized_user_file(token_path, SCOPES)
    if credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())
        token_path.write_text(credentials.to_json())
        token_path.chmod(0o600)
    if not credentials.valid:
        raise DriveConfigurationError(
            "Google Drive authorization is invalid. Remove secrets/token.json and authorize again."
        )
    return credentials


def download_folder_from_drive(folder_id: str, output_dir: str) -> list[str]:
    service = get_drive_service()
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    normalized_folder_id = normalize_folder_id(folder_id)

    try:
        pdf_items = _find_pdf_items(service, normalized_folder_id)
    except HttpError as exc:
        if exc.resp.status == 404:
            message = (
                "Google Drive folder not found. Check the link and confirm the authenticated "
                "Google account can open the folder."
            )
            raise DriveFolderError(message, status_code=404) from exc
        if exc.resp.status in {401, 403}:
            message = (
                "Google Drive access was denied. Confirm the authenticated Google account can "
                "open the folder, then authorize again if needed."
            )
            raise DriveFolderError(message, status_code=403) from exc
        raise DriveFolderError(
            "Google Drive could not list the folder. Please try again.", status_code=502
        ) from exc

    downloaded_files = []
    for item in pdf_items:
        file_path = destination / Path(item["name"]).name
        request = service.files().get_media(fileId=item["id"])
        try:
            with file_path.open("wb") as file_handle:
                downloader = MediaIoBaseDownload(file_handle, request)
                done = False
                while not done:
                    _, done = downloader.next_chunk()
        except HttpError as exc:
            raise DriveFolderError(
                f"Google Drive could not download {item['name']}. Please try again.",
                status_code=502,
            ) from exc
        downloaded_files.append(str(file_path))

    return downloaded_files


def _find_pdf_items(service, root_folder_id: str) -> list[dict[str, str]]:
    pending_folder_ids = [root_folder_id]
    visited_folder_ids = set()
    pdf_items = []

    while pending_folder_ids:
        folder_id = pending_folder_ids.pop()
        if folder_id in visited_folder_ids:
            continue
        visited_folder_ids.add(folder_id)

        page_token = None
        while True:
            response = (
                service.files()
                .list(
                    q=f"'{folder_id}' in parents and trashed = false",
                    fields="nextPageToken, files(id, name, mimeType)",
                    includeItemsFromAllDrives=True,
                    supportsAllDrives=True,
                    pageToken=page_token,
                )
                .execute()
            )
            for item in response.get("files", []):
                if item["mimeType"] == PDF_MIME_TYPE:
                    pdf_items.append(item)
                elif item["mimeType"] == FOLDER_MIME_TYPE:
                    pending_folder_ids.append(item["id"])

            page_token = response.get("nextPageToken")
            if not page_token:
                break

    return pdf_items
