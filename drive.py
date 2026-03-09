import io
import json
import os
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from google.oauth2.service_account import Credentials

SCOPES = ['https://www.googleapis.com/auth/drive']
FOLDER_MAP = {
    'image': '📸 תמונות',
    'video': '🎬 וידאו',
    'audio': '🎵 מוזיקה',
    'document': '📄 מסמכים',
    'other': '📦 שונות',
}

def get_drive_service():
    creds_json = json.loads(os.getenv('GOOGLE_CREDENTIALS_JSON'))
    creds = Credentials.from_service_account_info(creds_json, scopes=SCOPES)
    return build('drive', 'v3', credentials=creds)

def get_or_create_folder(service, name, parent_id):
    query = (f"name='{name}' and mimeType='application/vnd.google-apps.folder' "
             f"and '{parent_id}' in parents and trashed=false")
    results = service.files().list(q=query, fields='files(id)').execute()
    files = results.get('files', [])
    if files:
        return files[0]['id']
    meta = {'name': name, 'mimeType': 'application/vnd.google-apps.folder', 'parents': [parent_id]}
    return service.files().create(body=meta, fields='id').execute()['id']

def upload_stream_to_drive(file_path: str, filename: str, mimetype: str, progress_cb=None) -> dict:
    service = get_drive_service()
    root_folder = os.getenv('DRIVE_FOLDER_ID')
    category = next((k for k in FOLDER_MAP if k in mimetype), 'other')
    folder_id = get_or_create_folder(service, FOLDER_MAP[category], root_folder)
    file_meta = {'name': filename, 'parents': [folder_id]}
    with open(file_path, 'rb') as f:
        media = MediaIoBaseUpload(f, mimetype=mimetype, chunksize=10*1024*1024, resumable=True)
        request = service.files().create(body=file_meta, media_body=media, fields='id,name,size,webViewLink')
        response = None
        while response is None:
            status, response = request.next_chunk()
            if status and progress_cb:
                progress_cb(int(status.progress() * 100))
    service.permissions().create(fileId=response['id'], body={'type': 'anyone', 'role': 'reader'}).execute()
    return response

def check_storage() -> dict:
    service = get_drive_service()
    quota = service.about().get(fields='storageQuota').execute()['storageQuota']
    used, total = int(quota.get('usage', 0)), int(quota.get('limit', 0))
    return {
        'used_gb': round(used/1e9, 2),
        'total_gb': round(total/1e9, 2),
        'free_gb': round((total-used)/1e9, 2),
        'percent': round((used/total)*100, 1) if total else 0
    }
