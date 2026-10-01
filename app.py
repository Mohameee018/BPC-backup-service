import os
import secrets
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from starlette.middleware.sessions import SessionMiddleware
from google_auth_oauthlib.flow import Flow

APP_NAME = "BPC Backup Service"
SCOPES = ["https://www.googleapis.com/auth/drive","https://www.googleapis.com/auth/spreadsheets"]

app = FastAPI(title=APP_NAME)
app.add_middleware(SessionMiddleware, secret_key=os.environ.get("OAUTH_STATE_SECRET","CHANGE_ME"), https_only=True, same_site="lax")

def required(name):
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing environment variable: {name}")
    return value

def client_config():
    return {"web":{
        "client_id":required("GOOGLE_CLIENT_ID"),
        "client_secret":required("GOOGLE_CLIENT_SECRET"),
        "auth_uri":"https://accounts.google.com/o/oauth2/auth",
        "token_uri":"https://oauth2.googleapis.com/token",
    }}

def redirect_uri(request):
    return os.getenv("GOOGLE_REDIRECT_URI") or str(request.base_url).rstrip("/") + "/oauth2/callback"

@app.get("/", response_class=HTMLResponse)
def home():
    return """<!doctype html><html><head><title>BPC Backup Service</title>
    <style>body{font-family:system-ui;max-width:760px;margin:60px auto;padding:0 20px}</style></head>
    <body><h1>BPC Backup Service</h1><p>Backup API is running.</p>
    <ul><li><a href="/health">Health check</a></li><li><a href="/setup">Google setup</a></li></ul></body></html>"""

@app.get("/health")
def health():
    return {"status":"ok","service":APP_NAME}

@app.get("/setup", response_class=HTMLResponse)
def setup_page():
    return """<!doctype html><html><body style="font-family:system-ui;max-width:600px;margin:60px auto">
    <h1>Google backup setup</h1><p>Administrator setup only.</p>
    <form method="post" action="/setup"><input type="password" name="password" placeholder="Setup password" required style="padding:10px;width:100%;box-sizing:border-box">
    <button style="margin-top:12px;padding:10px 16px">Connect Google</button></form></body></html>"""

@app.post("/setup")
def setup(request: Request, password: str = Form(...)):
    expected = required("BACKUP_SETUP_PASSWORD")
    if not secrets.compare_digest(password, expected):
        return HTMLResponse("Invalid setup password", status_code=401)
    state = secrets.token_urlsafe(32)
    request.session["oauth_state"] = state
    flow = Flow.from_client_config(client_config(), scopes=SCOPES, state=state)
    flow.redirect_uri = redirect_uri(request)
    auth_url, _ = flow.authorization_url(access_type="offline", include_granted_scopes="true", prompt="consent")
    return RedirectResponse(auth_url, status_code=303)

@app.get("/oauth2/callback", response_class=HTMLResponse)
def oauth_callback(request: Request):
    state = request.session.pop("oauth_state", None)
    returned_state = request.query_params.get("state")
    if not state or not returned_state or not secrets.compare_digest(state, returned_state):
        return HTMLResponse("OAuth state validation failed.", status_code=400)
    if request.query_params.get("error"):
        return HTMLResponse("Google authorization failed: " + request.query_params.get("error"), status_code=400)

    flow = Flow.from_client_config(client_config(), scopes=SCOPES, state=state)
    flow.redirect_uri = redirect_uri(request)
    flow.fetch_token(authorization_response=str(request.url))
    token = flow.credentials.refresh_token
    if not token:
        return HTMLResponse("<h2>No refresh token returned</h2><p>Re-authorize with offline access.</p>", status_code=400)
    return HTMLResponse("""<!doctype html><html><body style="font-family:system-ui;max-width:900px;margin:50px auto">
    <h1>Google connected</h1><p>Copy this refresh token into the Railway variable GOOGLE_REFRESH_TOKEN.
    Do not post it in chat or commit it to GitHub.</p><textarea readonly style="width:100%;height:110px">""" + token + """</textarea>
    <p>The service does not log or persist this token.</p></body></html>""")

@app.get("/backup/status")
def backup_status():
    return {"status":"ready","worker_schedule":"*/5 * * * *"}
