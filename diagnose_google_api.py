import os
import json
import base64
import logging
from googleapiclient.discovery import build
from google.oauth2.service_account import Credentials

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/documents",
]

def get_creds():
    # Attempt to get from env (like GitHub Actions)
    creds_raw = os.getenv("GOOGLE_CREDENTIALS_JSON", "").strip()
    if creds_raw:
        if creds_raw.startswith("{"):
            creds_dict = json.loads(creds_raw)
        else:
            creds_json = base64.b64decode(creds_raw).decode("utf-8")
            creds_dict = json.loads(creds_json)
        return Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    
    # Attempt to get from local file
    path = "credentials/service_account.json"
    if os.path.exists(path):
        return Credentials.from_service_account_file(path, scopes=SCOPES)
    
    return None

def test_apis():
    creds = get_creds()
    if not creds:
        logger.error("Credentials not found!")
        return

    # 1. Test Sheets API
    try:
        sheets_service = build('sheets', 'v4', credentials=creds)
        logger.info("✅ Google Sheets API: Success (Service initialized)")
    except Exception as e:
        logger.error(f"❌ Google Sheets API: Failed - {e}")

    # 2. Test Drive API
    try:
        drive_service = build('drive', 'v3', credentials=creds)
        # Try a simple files().list()
        drive_service.files().list(pageSize=1).execute()
        logger.info("✅ Google Drive API: Success (Can list files)")
    except Exception as e:
        logger.error(f"❌ Google Drive API: Failed - {e}")

    # 3. Test Docs API
    try:
        docs_service = build('docs', 'v1', credentials=creds)
        # Try to create a dummy doc
        doc_body = {'title': 'API Test Document'}
        doc = docs_service.documents().create(body=doc_body).execute()
        doc_id = doc.get('documentId')
        logger.info(f"✅ Google Docs API: Success (Document created: {doc_id})")
        
        # Cleanup
        drive_service = build('drive', 'v3', credentials=creds)
        drive_service.files().delete(fileId=doc_id).execute()
        logger.info(f"🧹 Cleanup: Deleted test document {doc_id}")
        
    except Exception as e:
        logger.error(f"❌ Google Docs API: Failed - {e}")
        if "permission" in str(e).lower():
            logger.warning("Suggestion: Check if 'Google Docs API' is ENABLED in Google Cloud Console.")

if __name__ == "__main__":
    test_apis()
