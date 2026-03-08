import logging
import subprocess
import os

logger = logging.getLogger(__name__)

class GWSManager:
    """Google Workspace CLI (gws) 연동을 위한 매니저 클래스"""

    def __init__(self, bin_path=".\\bin\\gws.exe"):
        self.bin_path = bin_path
        
    def create_briefing_doc(self, title: str, content: str) -> bool:
        """
        주어진 제목과 내용으로 Google Docs 문서를 생성합니다.
        
        Args:
            title (str): 생성할 문서의 제목
            content (str): 문서의 본문 내용 (마크다운 포맷)
            
        Returns:
            bool: 생성 성공 여부
        """
        logger.info(f"Google Docs 생성 시도: {title}")
        
        try:
            import json
            
            # 1. 빈 문서 생성
            create_cmd = [
                self.bin_path,
                "docs",
                "documents",
                "create",
                "--json", json.dumps({"title": title}),
                "--format", "json"
            ]
            
            startupinfo = None
            if os.name == 'nt':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                
            create_res = subprocess.run(
                create_cmd,
                capture_output=True,
                text=True,
                startupinfo=startupinfo,
                encoding='utf-8' # 한글 깨짐 방지
            )
            
            if create_res.returncode != 0:
                logger.error(f"[ERROR] 빈 문서 생성 실패: {create_res.stderr.strip()}")
                return False
                
            try:
                doc_info = json.loads(create_res.stdout)
                doc_id = doc_info.get("documentId")
            except Exception as e:
                logger.error(f"[ERROR] JSON 파싱 실패: {e}")
                return False
                
            if not doc_id:
                logger.error("[ERROR] 문서 ID를 응답에서 찾을 수 없습니다.")
                return False
                
            logger.info(f"빈 문서 생성 완료 (ID: {doc_id}). 내용 추가 중...")
            
            # 2. 내용 추가
            write_cmd = [
                self.bin_path,
                "docs",
                "+write",
                "--document", doc_id,
                "--text", content
            ]
            
            write_res = subprocess.run(
                write_cmd,
                capture_output=True,
                text=True,
                startupinfo=startupinfo,
                encoding='utf-8'
            )

            if write_res.returncode == 0:
                logger.info(f"[SUCCESS] Google Docs 문서 작성 완료! (ID: {doc_id})")
                return True
            else:
                logger.error(f"[ERROR] Google Docs 내용 작성 실패 (종료 코드: {write_res.returncode})")
                logger.error(f"에러 출력: {write_res.stderr.strip()}")
                return False

        except FileNotFoundError:

            logger.error(f"[ERROR] {self.bin_path} 파일을 찾을 수 없습니다. gws가 정상적으로 설치되었는지 확인하세요.")
            return False
        except Exception as e:
            logger.error(f"[ERROR] Google Docs 생성 중 예외 발생: {e}")
            return False
