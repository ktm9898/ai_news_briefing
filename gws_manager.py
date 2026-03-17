import logging
from googleapiclient.discovery import build
from sheets_manager import _get_credentials

logger = logging.getLogger(__name__)

# 브리핑 문서 보관 기간 (일)
DOCS_RETENTION_DAYS = 7


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

    def _get_drive_service(self):
        return build('drive', 'v3', credentials=self.creds, static_discovery=False)

    def _get_docs_service(self):
        return build('docs', 'v1', credentials=self.creds, static_discovery=False)

    def cleanup_old_briefing_docs(self, drive_service=None, retention_days: int = DOCS_RETENTION_DAYS) -> int:
        """
        서비스 계정이 소유한 오래된 브리핑 문서를 자동 삭제.
        서비스 계정은 자체 Drive 용량(15GB)이 있으므로 주기적 정리가 필수.
        
        Returns:
            삭제된 파일 수
        """
        if not self.creds:
            return 0

        try:
            from datetime import datetime, timedelta, timezone
            drive = drive_service or self._get_drive_service()
            
            # 보관 기한 계산 (UTC 기준)
            cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
            cutoff_str = cutoff.strftime("%Y-%m-%dT%H:%M:%S")
            
            # 서비스 계정 자신이 100% 소유한(me) 브리핑 문서 검색 (이름 패턴 + 생성일 기준)
            query = (
                f"name contains 'AI News Briefing' "
                f"and mimeType='application/vnd.google-apps.document' "
                f"and createdTime < '{cutoff_str}' "
                f"and 'me' in owners "
                f"and trashed=false"
            )
            
            results = drive.files().list(
                q=query,
                pageSize=50,
                fields="files(id, name, createdTime)"
            ).execute()
            
            files = results.get('files', [])
            deleted = 0
            
            for f in files:
                try:
                    drive.files().delete(fileId=f['id']).execute()
                    deleted += 1
                    logger.info(f"오래된 브리핑 문서 삭제: {f['name']} ({f['createdTime']})")
                except Exception as e:
                    logger.warning(f"파일 삭제 실패 ({f['name']}): {e}")
            
            if deleted:
                logger.info(f"서비스 계정 드라이브 정리 완료: {deleted}건 삭제 (기준: {retention_days}일)")
            
            return deleted
            
        except Exception as e:
            logger.warning(f"드라이브 정리 중 오류 (무시): {e}")
            return 0

    def cleanup_all_files(self) -> int:
        """
        서비스 계정이 소유한 모든 파일을 일괄 삭제 (용량 복구용).
        주의: 최초 1회 실행용. 파이프라인에서 자동 호출하지 않음.
        """
        if not self.creds:
            return 0

        try:
            drive = self._get_drive_service()
            deleted = 0
            page_token = None
            
            # '내가 주인인(me)' 파일만 검색 (사용자가 직접 만든 파일이나 남이 공유한 폴더 자체는 건드리지 않음)
            query = "'me' in owners and trashed=false"
            
            while True:
                results = drive.files().list(
                    q=query,
                    pageSize=100,
                    fields="nextPageToken, files(id, name)",
                    pageToken=page_token
                ).execute()
                
                files = results.get('files', [])
                if not files:
                    break
                
                for f in files:
                    try:
                        # 휴지통을 거치지 않고 완전히 영구 삭제하여 즉시 용량 확보
                        drive.files().delete(fileId=f['id']).execute()
                        deleted += 1
                        logger.info(f"용량 확보 완료: {f['name']} 삭제됨 ({f['id']})")
                    except Exception as e:
                        logger.warning(f"삭제 건너뜀: {f['name']} (권한 없음): {e}")
                
                page_token = results.get('nextPageToken')
                if not page_token:
                    break
            
            logger.info(f"서비스 계정 전체 정리 완료: {deleted}건 삭제")
            return deleted
            
        except Exception as e:
            logger.error(f"전체 정리 실패: {e}")
            return 0

    def create_briefing_doc(self, title: str, content: str) -> bool:
        """
        Drive API로 공유 폴더에 Google Docs 문서를 직접 생성한 뒤,
        Docs API로 본문 내용을 채워넣습니다.
        생성 전 오래된 브리핑 문서를 자동 정리하여 용량 초과를 방지합니다.
        """
        if not self.creds:
            logger.error("[ERROR] 인증 객체가 없어 Google Docs를 생성할 수 없습니다.")
            return False

        logger.info(f"Google Docs 생성 시도: {title}")
        
        try:
            from config import GWS_DRIVE_FOLDER_ID
            
            drive_service = self._get_drive_service()
            docs_service = self._get_docs_service()
            
            # 0. 오래된 브리핑 문서 자동 정리 (서비스 계정 용량 확보)
            self.cleanup_old_briefing_docs(drive_service)
            
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

