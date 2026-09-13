import os
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SCOPES = ["https://www.googleapis.com/auth/drive.file"]

def get_drive_service():
    creds = None
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    if not creds or not creds.valid:
        raise RuntimeError("File token.json tidak ditemukan atau sudah kedaluwarsa. Lakukan autentikasi ulang.")
    return build("drive", "v3", credentials=creds)

def create_or_get_drive_folder(folder_name: str, parent_id: str) -> str:
    """Mencari atau membuat subfolder di dalam Google Drive berdasarkan nama judul."""
    service = get_drive_service()
    clean_parent_id = parent_id.split("?")[0].strip()
    
    # Cek apakah folder dengan nama ini sudah ada di dalam parent folder
    query = f"name = '{folder_name}' and '{clean_parent_id}' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    results = service.files().list(q=query, spaces="drive", fields="files(id, name)").execute()
    items = results.get("files", [])
    
    if items:
        return items[0]["id"]
    
    # Buat subfolder baru
    file_metadata = {
        "name": folder_name,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [clean_parent_id]
    }
    folder = service.files().create(body=file_metadata, fields="id").execute()
    return folder.get("id")

def upload_file_to_drive(file_path: str, parent_folder_id: str) -> str:
    """Mengunggah file ke Google Drive."""
    service = get_drive_service()
    clean_parent_id = parent_folder_id.split("?")[0].strip()
    file_name = os.path.basename(file_path)

    file_metadata = {
        "name": file_name,
        "parents": [clean_parent_id]
    }
    media = MediaFileUpload(file_path, resumable=True)
    uploaded_file = service.files().create(
        body=file_metadata,
        media_body=media,
        fields="id"
    ).execute()
    return uploaded_file.get("id")

def save_metadata_file(metadata, output_path: str) -> str:
    """Menyimpan file metadata lokal sementara sebelum diunggah."""
    tags = " ".join([f"#{t.replace('#', '')}" for t in metadata.hashtags])
    content = f"JUDUL KONTEN:\n{metadata.source_topic}\n\n" \
              f"HEADLINE COVER:\n{metadata.cover_headline}\n\n" \
              f"CAPTION:\n{metadata.tiktok_caption}\n\n" \
              f"HASHTAGS:\n{tags}\n"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)
    return output_path

def cleanup_local_files(file_paths: list[str]):
    """Menghapus file sementara agar media penyimpanan server/VPS tidak penuh."""
    for p in file_paths:
        try:
            if p and os.path.exists(p):
                os.remove(p)
        except Exception as e:
            print(f"⚠️ Gagal menghapus file lokal {p}: {e}")