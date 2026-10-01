import io
import os
from pathlib import Path
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseUpload, MediaIoBaseDownload

SCOPES=["https://www.googleapis.com/auth/drive","https://www.googleapis.com/auth/spreadsheets"]

def credentials():
    refresh=os.environ.get("GOOGLE_REFRESH_TOKEN")
    if not refresh:
        raise RuntimeError("Missing GOOGLE_REFRESH_TOKEN")
    return Credentials(token=None, refresh_token=refresh, token_uri="https://oauth2.googleapis.com/token",
                       client_id=os.environ["GOOGLE_CLIENT_ID"], client_secret=os.environ["GOOGLE_CLIENT_SECRET"], scopes=SCOPES)

def services():
    c=credentials()
    return build("drive","v3",credentials=c,cache_discovery=False), build("sheets","v4",credentials=c,cache_discovery=False)

def find_or_create_folder(drive,name="BPC Backups"):
    safe=name.replace("'","\\'")
    q=f"name = '{safe}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    result=drive.files().list(q=q,spaces="drive",fields="files(id,name)").execute()
    if result.get("files"): return result["files"][0]["id"]
    return drive.files().create(body={"name":name,"mimeType":"application/vnd.google-apps.folder"},fields="id").execute()["id"]

def find_file(drive,name,folder_id=None):
    safe=name.replace("'","\\'")
    parts=[f"name = '{safe}'","trashed = false"]
    if folder_id: parts.append(f"'{folder_id}' in parents")
    result=drive.files().list(q=" and ".join(parts),spaces="drive",fields="files(id,name,modifiedTime,createdTime)").execute()
    return result.get("files",[None])[0]

def upload_file(drive,path,folder_id):
    media=MediaFileUpload(path,mimetype="application/gzip",resumable=True)
    return drive.files().create(body={"name":Path(path).name,"parents":[folder_id]},media_body=media,fields="id,name,size,createdTime").execute()

def download_text(drive,file_id):
    request=drive.files().get_media(fileId=file_id)
    buffer=io.BytesIO(); downloader=MediaIoBaseDownload(buffer,request); done=False
    while not done: _,done=downloader.next_chunk()
    return buffer.getvalue().decode("utf-8")

def upload_text(drive,name,text,folder_id):
    existing=find_file(drive,name,folder_id)
    media=MediaIoBaseUpload(io.BytesIO(text.encode()),mimetype="application/json",resumable=True)
    if existing:
        return drive.files().update(fileId=existing["id"],media_body=media,fields="id,name,modifiedTime").execute()
    return drive.files().create(body={"name":name,"parents":[folder_id]},media_body=media,fields="id,name,modifiedTime").execute()

def get_or_create_sheet(sheets,drive):
    name=os.getenv("GOOGLE_SHEET_NAME","BPC Backup Monitor")
    existing=find_file(drive,name)
    if existing: return existing["id"]
    sheet=sheets.spreadsheets().create(body={"properties":{"title":name}}).execute()
    sid=sheet["spreadsheetId"]
    sheets.spreadsheets().values().update(spreadsheetId=sid,range="Sheet1!A1:H1",valueInputOption="RAW",
        body={"values":[["timestamp_utc","backup_status","backup_file","backup_size_bytes","db_name","changed","clients","message"]]}).execute()
    return sid

def append_sheet_row(sheets,sid,row):
    sheets.spreadsheets().values().append(spreadsheetId=sid,range="Sheet1!A:H",valueInputOption="USER_ENTERED",
        insertDataOption="INSERT_ROWS",body={"values":[row]}).execute()

def cleanup_old_backups(drive,folder_id,retention_days):
    from datetime import datetime,timezone,timedelta
    cutoff=datetime.now(timezone.utc)-timedelta(days=retention_days)
    result=drive.files().list(q=f"'{folder_id}' in parents and trashed = false",spaces="drive",
                              fields="files(id,name,createdTime)",pageSize=1000).execute()
    removed=0
    for f in result.get("files",[]):
        if not f["name"].endswith(".sql.gz"): continue
        created=datetime.fromisoformat(f["createdTime"].replace("Z","+00:00"))
        if created<cutoff:
            drive.files().delete(fileId=f["id"]).execute(); removed+=1
    return removed
