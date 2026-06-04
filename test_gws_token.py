import os
import json
import base64
from google.oauth2.service_account import Credentials
import google.auth.transport.requests
import subprocess

with open("credentials/service_account.json", "r") as f:
    creds_dict = json.load(f)

SCOPES = [
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/drive",
]

creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
request = google.auth.transport.requests.Request()
creds.refresh(request)
token = creds.token

env = os.environ.copy()
env["GOOGLE_WORKSPACE_CLI_TOKEN"] = token

if os.name == 'nt' and os.path.exists(".\\bin\\gws.exe"):
    bin_path = ".\\bin\\gws.exe"
else:
    bin_path = "gws"

print("Trying gws docs create...")
cmd = [bin_path, "docs", "documents", "create", "--json", '{"title": "Test from Script"}', "--format", "json"]
res = subprocess.run(cmd, env=env, capture_output=True, text=True)
print("Return code:", res.returncode)
print("STDOUT:", res.stdout)
print("STDERR:", res.stderr)
