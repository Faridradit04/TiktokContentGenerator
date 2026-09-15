import os
import time
import gc
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SCOPES = ["https://www.googleapis.com/auth/drive.file"]

def get_drive_service():
    """Menginisialisasi Google Drive API service dengan penanganan token otomatis."""
    creds = None
    token_file = "token.json"

    if os.path.exists(token_file):
        creds = Credentials.from_authorized_user_file(token_file, SCOPES)

    # Jika token belum ada atau sudah kedaluwarsa/tidak valid
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                print("🔄 Token Drive telah kedaluwarsa. Memperbarui via refresh_token...")
                creds.refresh(Request())
                # Perbarui file token.json dengan token yang baru
                with open(token_file, "w", encoding="utf-8") as f:
                    f.write(creds.to_json())
                print("✅ Token Drive berhasil diperbarui dan disimpan.")
            except Exception as e:
                raise RuntimeError(
                    f"Gagal memperbarui token Google Drive secara otomatis: {e}. "
                    "Pastikan refresh_token masih valid atau jalankan autentikasi ulang."
                )
        else:
            raise RuntimeError(
                "File token.json tidak ditemukan atau tidak memiliki refresh_token. "
                "Silakan lakukan autentikasi ulang."
            )

    return build("drive", "v3", credentials=creds)

def create_or_get_drive_folder(folder_name: str, parent_id: str) -> str:
    """Mencari atau membuat subfolder di Google Drive berdasarkan nama topik."""
    service = get_drive_service()
    clean_parent_id = parent_id.split("?")[0].strip()
    
    # Cek apakah folder dengan nama ini sudah ada di parent folder
    query = (
        f"name = '{folder_name}' and "
        f"'{clean_parent_id}' in parents and "
        f"mimeType = 'application/vnd.google-apps.folder' and "
        f"trashed = false"
    )
    results = service.files().list(q=query, spaces="drive", fields="files(id, name)").execute()
    items = results.get("files", [])
    
    if items:
        return items[0]["id"]
    
    # Buat subfolder baru jika belum ada
    file_metadata = {
        "name": folder_name,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [clean_parent_id]
    }
    folder = service.files().create(body=file_metadata, fields="id").execute()
    return folder.get("id")

def upload_file_to_drive(file_path: str, parent_folder_id: str) -> str:
    """Mengunggah file lokal ke Google Drive."""
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
    """Menyimpan berkas teks metadata konten (caption & hashtag) secara lokal."""
    tags = " ".join([f"#{t.replace('#', '')}" for t in metadata.hashtags])
    content = (
        f"JUDUL KONTEN:\n{metadata.source_topic}\n\n"
        f"HEADLINE COVER:\n{metadata.cover_headline}\n\n"
        f"CAPTION:\n{metadata.tiktok_caption}\n\n"
        f"HASHTAGS:\n{tags}\n"
    )
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)
    return output_path

def cleanup_local_files(file_paths: list[str]):
    """Menghapus berkas sementara dengan Garbage Collection dan mekanisme retry untuk Windows."""
    # Memaksa Python melepaskan open file handle di memori
    gc.collect()

    for p in file_paths:
        if not p or not os.path.exists(p):
            continue

        deleted = False
        for attempt in range(3):
            try:
                os.remove(p)
                deleted = True
                break
            except PermissionError:
                time.sleep(0.5)  # Beri jeda sistem operasi Windows melepaskan file lock
            except Exception as e:
                print(f"⚠️ Gagal menghapus file lokal {p}: {e}")
                break

        if not deleted and os.path.exists(p):
            print(f"⚠️ Melewati penghapusan {p} karena masih digunakan proses lain.")