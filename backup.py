import gzip
import hashlib
import json
import os
import subprocess
import tempfile
from datetime import datetime,timezone
import psycopg
from google_drive import services,find_or_create_folder,find_file,download_text,upload_file,upload_text,get_or_create_sheet,append_sheet_row,cleanup_old_backups

STATE_NAME="bpc-backup-state.json"

def now(): return datetime.now(timezone.utc)
def db_url():
    value=os.getenv("DATABASE_URL") or os.getenv("SUPABASE_DB_URL")
    if not value: raise RuntimeError("Missing DATABASE_URL")
    return value

def db_snapshot():
    sql="""SELECT COALESCE(SUM(n_tup_ins),0),COALESCE(SUM(n_tup_upd),0),COALESCE(SUM(n_tup_del),0),
                    COALESCE(SUM(n_live_tup),0) FROM pg_stat_user_tables"""
    with psycopg.connect(db_url(),connect_timeout=15) as conn:
        row=conn.execute(sql).fetchone()
        clients=conn.execute("SELECT count(*) FROM public.brands").fetchone()[0]
        db_name=conn.execute("SELECT current_database()").fetchone()[0]
    data={"db_name":db_name,"inserts":int(row[0]),"updates":int(row[1]),"deletes":int(row[2]),"live_rows":int(row[3]),"clients":int(clients)}
    data["fingerprint"]=hashlib.sha256(json.dumps(data,sort_keys=True).encode()).hexdigest()
    return data

def pg_dump(out_path):
    env=os.environ.copy(); env["PGCONNECT_TIMEOUT"]="30"
    command=["pg_dump",db_url(),"--format=plain","--no-owner","--no-privileges","--no-comments"]
    with open(out_path,"wb") as raw:
        proc=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env)
        with gzip.GzipFile(fileobj=raw,mode="wb",compresslevel=6) as gz:
            while True:
                chunk=proc.stdout.read(1024*1024)
                if not chunk: break
                gz.write(chunk)
        err=proc.stderr.read().decode("utf-8",errors="replace"); code=proc.wait()
    if code: raise RuntimeError(f"pg_dump failed ({code}): {err[-4000:]}")

def run():
    started=now(); drive,sheets=services(); folder=find_or_create_folder(drive)
    snapshot=db_snapshot(); previous=None
    state=find_file(drive,STATE_NAME,folder)
    if state: previous=json.loads(download_text(drive,state["id"]))
    changed=previous is None or previous.get("fingerprint")!=snapshot["fingerprint"]
    daily=previous is None or (started-datetime.fromisoformat(previous["last_full_backup"].replace("Z","+00:00"))).total_seconds()>=86400
    sid=get_or_create_sheet(sheets,drive)
    if not changed and not daily:
        append_sheet_row(sheets,sid,[started.isoformat(),"SKIPPED_NO_CHANGES","",0,snapshot["db_name"],False,snapshot["clients"],"No DB changes detected"])
        print(json.dumps({"status":"skipped","changed":False})); return
    with tempfile.TemporaryDirectory() as tmp:
        path=os.path.join(tmp,f"bpc-backup-{started.strftime('%Y%m%dT%H%M%SZ')}.sql.gz")
        pg_dump(path); uploaded=upload_file(drive,path,folder); size=os.path.getsize(path)
    state_data={"last_full_backup":started.isoformat().replace("+00:00","Z"),"fingerprint":snapshot["fingerprint"],
                "db_name":snapshot["db_name"],"clients":snapshot["clients"],"live_rows_estimate":snapshot["live_rows"]}
    upload_text(drive,STATE_NAME,json.dumps(state_data,indent=2),folder)
    append_sheet_row(sheets,sid,[started.isoformat(),"SUCCESS",uploaded["name"],size,snapshot["db_name"],changed,snapshot["clients"],"Full PostgreSQL dump uploaded to Google Drive"])
    cleanup_old_backups(drive,folder,int(os.getenv("BACKUP_RETENTION_DAYS","30")))
    print(json.dumps({"status":"success","file":uploaded["name"],"size_bytes":size,"clients":snapshot["clients"]}))

if __name__=="__main__": run()
