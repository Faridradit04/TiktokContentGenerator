import os
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SCOPES = ['https://www.googleapis.com/auth/drive.file']

def get_gdrive_service():
    """Mengelola otentikasi akun Google."""
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists('credentials.json'):
                raise FileNotFoundError("Berkas 'credentials.json' belum ditaruh di folder proyek.")
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)

        with open('token.json', 'w') as token:
            token.write(creds.to_json())

    return build('drive', 'v3', credentials=creds)

def upload_file_to_drive(file_path: str, folder_id: str = None) -> str:
    """Mengunggah berkas ke Google Drive."""
    service = get_gdrive_service()
    filename = os.path.basename(file_path)

    metadata = {'name': filename}
    if folder_id:
        # Bersihkan jika ada query string yang tertinggal
        clean_folder_id = folder_id.split("?")[0].strip()
        metadata['parents'] = [clean_folder_id]

    media = MediaFileUpload(file_path, resumable=True)
    uploaded = service.files().create(body=metadata, media_body=media, fields='id').execute()
    file_id = uploaded.get('id')
    print(f"☁️ Berkas {filename} berhasil diunggah ke Google Drive (ID: {file_id})")
    return file_id

def save_metadata_file(metadata, output_path: str) -> str:
    """Menyimpan takarir dan tagar ke berkas teks lokal."""
    content = f"JUDUL/TOPIK:\n{metadata.source_topic}\n\n"
    content += f"CAPTION TIKTOK:\n{metadata.tiktok_caption}\n\n"
    content += f"HASHTAGS:\n{' '.join(metadata.hashtags)}\n"

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)
    return output_path