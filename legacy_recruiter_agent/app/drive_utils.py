import os
import io
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

SCOPES = ['https://www.googleapis.com/auth/drive.readonly']

def get_drive_service(token_path='token.json', credentials_path='credentials.json'):
    """Authenticates and returns the Google Drive API service client."""
    creds = None
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(credentials_path):
                raise FileNotFoundError(
                    f"Missing {credentials_path}. Please download your OAuth client secrets from Google Cloud Console."
                )
            flow = InstalledAppFlow.from_client_secrets_file(credentials_path, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_path, 'token.json') as token:
            token.write(creds.to_json())
    return build('drive', 'v3', credentials=creds)

def download_folder_from_drive(folder_id: str, output_dir: str):
    """Downloads all PDF/docx resumes from a specified Google Drive folder ID."""
    service = get_drive_service()
    os.makedirs(output_dir, exist_ok=True)
    
    query = f"'{folder_id}' in parents and trashed = false"
    results = service.files().list(q=query, fields="files(id, name, mimeType)").execute()
    items = results.get('files', [])

    downloaded_files = []
    for item in items:
        file_id = item['id']
        file_name = item['name']
        
        request = service.files().get_media(fileId=file_id)
        file_path = os.path.join(output_dir, file_name)
        
        fh = io.FileIO(file_path, 'wb')
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            status, done = downloader.next_chunk()
            
        downloaded_files.append(file_path)
    return downloaded_files