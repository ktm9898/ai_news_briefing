"""
run_pipeline.py - GitHub Actions 엔트리포인트

GitHub Actions 워크플로우에서 이 스크립트를 직접 실행합니다.
  python run_pipeline.py            # 일반 파이프라인 실행
  python run_pipeline.py --cleanup  # 서비스 계정 Drive 파일 전체 정리 (최초 1회)
"""

import logging
import sys

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

logger = logging.getLogger(__name__)


def run_cleanup():
    """서비스 계정이 소유한 모든 Drive 파일을 일괄 삭제 (용량 복구용)"""
    logger.info("🧹 서비스 계정 Drive 전체 정리 시작...")
    try:
        from gws_manager import GWSManager
        gws = GWSManager()
        deleted = gws.cleanup_all_files()
        logger.info(f"✅ 정리 완료: {deleted}건 삭제")
    except Exception as e:
        logger.error(f"❌ 정리 실패: {e}")
        sys.exit(1)


def main():
    """파이프라인 실행 및 결과 출력"""
    import os
    logger.info("Checking environment variables...")
    required_env = ["NAVER_CLIENT_ID", "NAVER_CLIENT_SECRET", "GEMINI_API_KEY", "GOOGLE_SHEET_ID", "GOOGLE_CREDENTIALS_JSON"]
    missing_env = [env for env in required_env if not os.environ.get(env)]
    
    if missing_env:
        logger.error(f"Missing environment variables: {', '.join(missing_env)}")
        sys.exit(1)

    try:
        from scheduler import run_pipeline
    except ImportError as e:
        logger.error(f"Failed to import scheduler: {e}")
        sys.exit(1)

    logger.info("🚀 뉴스 수집 파이프라인 시작")
    result = run_pipeline()

    status = result.get("status", "알 수 없음")
    collected = result.get("collected", 0)
    analyzed = result.get("analyzed", 0)
    error = result.get("error")

    logger.info(f"📊 결과: 상태={status}, 수집={collected}건, 분석={analyzed}건")

    if error:
        logger.error(f"❌ 오류 발생: {error}")
        sys.exit(1)

    logger.info("✅ 파이프라인 정상 완료")


if __name__ == "__main__":
    if "--cleanup" in sys.argv:
        run_cleanup()
    else:
        main()

