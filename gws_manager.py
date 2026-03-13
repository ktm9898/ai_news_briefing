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
        주어진 제목과 내용으로 Google Docs 문서를 생성하고, 
        필요 시 지정된 드라이브 폴더로 이동시킵니다.
        """
        if not self.creds:
            logger.error("[ERROR] 인증 객체가 없어 Google Docs를 생성할 수 없습니다.")
            return False

        logger.info(f"Google Docs 생성 시도: {title}")
        
        try:
            # discovery_cache=False를 권장 (특히 서버리스/Actions 환경)
            docs_service = build('docs', 'v1', credentials=self.creds, static_discovery=False)
            drive_service = build('drive', 'v3', credentials=self.creds, static_discovery=False)
            
            # 1. 빈 문서 생성
            doc_body = {
                'title': title
            }
            doc = docs_service.documents().create(body=doc_body).execute()
            doc_id = doc.get('documentId')
            
            if not doc_id:
                logger.error("[ERROR] 문서 ID를 응답에서 찾을 수 없습니다.")
                return False
                
            logger.info(f"빈 문서 생성 완료 (ID: {doc_id}). 내용 추가 중...")
            
            # 2. 내용 추가
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
                
            # 3. 폴더 이동 (선택 사항)
            from config import GWS_DRIVE_FOLDER_ID
            if GWS_DRIVE_FOLDER_ID:
                try:
                    # Retrieve the existing parents to remove
                    file_metadata = drive_service.files().get(
                        fileId=doc_id, fields='parents').execute()
                    previous_parents = ",".join(file_metadata.get('parents', []))
                    
                    # Move the file to the new folder
                    drive_service.files().update(
                        fileId=doc_id,
                        addParents=GWS_DRIVE_FOLDER_ID,
                        removeParents=previous_parents,
                        fields='id, parents'
                    ).execute()
                    logger.info(f"[SUCCESS] 지정된 폴더({GWS_DRIVE_FOLDER_ID})로 이동 완료.")
                except Exception as e:
                    logger.warning(f"[WARNING] 폴더 이동 실패 (공유 권한 문제일 수 있음): {e}")
            else:
                logger.info("GWS_DRIVE_FOLDER_ID가 설정되지 않아 폴더 이동을 생략합니다. (Warning: 서비스 계정 사용 시 문서를 찾기 어려울 수 있습니다)")

            return True

        except Exception as e:
            logger.error(f"[ERROR] Google Docs 생성 중 예외 발생: {e}")
            return False
