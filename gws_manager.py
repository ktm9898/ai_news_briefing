import logging
from googleapiclient.discovery import build
from sheets_manager import _get_credentials

logger = logging.getLogger(__name__)

class GWSManager:
    """Google Workspace API 연동을 위한 매니저 클래스 (Python Client 기반)"""

    def __init__(self):
        try:
            self.creds = _get_credentials()
            if self.creds:
                logger.info(f"Google API 인증 객체 로드 성공 (계정: {self.creds.service_account_email})")
            else:
                logger.error("Google API 인증 객체 로드 실패: credentials가 없습니다.")
        except Exception as e:
            logger.error(f"Google API 인증 실패 (gws_manager): {e}")
            self.creds = None
        
    def create_briefing_doc(self, title: str, content: str) -> bool:
        """
        Drive API로 공유 폴더에 Google Docs 문서를 직접 생성한 뒤,
        Docs API로 본문 내용을 채워넣습니다.
        """
        if not self.creds:
            logger.error("[ERROR] 인증 객체가 없어 Google Docs를 생성할 수 없습니다.")
            return False

        logger.info(f"Google Docs 생성 시도: {title}")
        
        try:
            from config import GWS_DRIVE_FOLDER_ID
            
            drive_service = build('drive', 'v3', credentials=self.creds, static_discovery=False)
            docs_service = build('docs', 'v1', credentials=self.creds, static_discovery=False)
            
            # 1. Drive API로 공유 폴더에 빈 Google Docs 문서 직접 생성
            file_metadata = {
                'name': title,
                'mimeType': 'application/vnd.google-apps.document',
            }
            if GWS_DRIVE_FOLDER_ID:
                file_metadata['parents'] = [GWS_DRIVE_FOLDER_ID]
            
            created_file = drive_service.files().create(
                body=file_metadata,
                fields='id'
            ).execute()
            doc_id = created_file.get('id')
            
            if not doc_id:
                logger.error("[ERROR] 문서 ID를 응답에서 찾을 수 없습니다.")
                return False
                
            logger.info(f"빈 문서 생성 완료 (ID: {doc_id}, 폴더: {GWS_DRIVE_FOLDER_ID or '루트'}). 내용 추가 중...")
            
            # 2. Docs API로 본문 내용 추가
            requests = [
                {
                    'insertText': {
                        'location': {
                            'index': 1,
                        },
                        'text': content
                    }
                }
            ]
            docs_service.documents().batchUpdate(
                documentId=doc_id, body={'requests': requests}).execute()
                
            logger.info(f"[SUCCESS] Google Docs 문서 작성 완료! (ID: {doc_id})")
            return True

        except Exception as e:
            logger.error(f"[ERROR] Google Docs 생성 중 예외 발생: {e}")
            return False
