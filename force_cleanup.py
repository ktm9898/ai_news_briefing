import os
import sys
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

try:
    from gws_manager import GWSManager
except ImportError:
    logging.error("먼저 환경 구성을 확인하세요.")
    sys.exit(1)

def force_cleanup():
    gws = GWSManager()
    if not gws.creds:
        logging.error("인증 실패")
        return

    drive = gws._get_drive_service()
    
    # trashed=false 조건 없이 모든 파일 검색
    query = "'me' in owners"
    logging.info(f"조회 쿼리: {query}")
    
    deleted = 0
    page_token = None
    
    while True:
        try:
            results = drive.files().list(
                q=query,
                pageSize=100,
                fields="nextPageToken, files(id, name, trashed)",
                pageToken=page_token
            ).execute()
        except Exception as e:
            logging.error(f"조회 중 에러: {e}")
            break
            
        files = results.get('files', [])
        if not files:
            break
            
        for f in files:
            try:
                drive.files().delete(fileId=f['id']).execute()
                status = "(휴지통 파일)" if f.get('trashed') else ""
                logging.info(f"영구 삭제 완료: {f.get('name')} {status}")
                deleted += 1
            except Exception as e:
                logging.warning(f"삭제 실패 ({f.get('name')}): {e}")
                
        page_token = results.get('nextPageToken')
        if not page_token:
            break

    try:
        # 휴지통 비우기도 명시적으로 실행
        drive.files().emptyTrash().execute()
        logging.info("휴지통 완전 비우기 완료")
    except Exception as e:
        logging.warning(f"휴지통 비우기 실패: {e}")

    logging.info(f"총 {deleted}개의 유령 파일 영구 삭제 완료! 가방이 완전히 비워졌습니다.")

if __name__ == "__main__":
    force_cleanup()
