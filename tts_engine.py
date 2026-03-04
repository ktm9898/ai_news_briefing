"""
tts_engine.py - 음성 합성 엔진

우선순위:
  1. Google Cloud TTS (Neural2/Journey, 최고 품질)
  2. edge-tts (Microsoft Neural TTS, 무료)
  3. gTTS (Google TTS, 무료, 폴백)
"""

import asyncio
import logging
import shutil
from datetime import datetime, timedelta
from pathlib import Path

from config import (
    AUDIO_DIR,
    TTS_VOICE,
    GOOGLE_TTS_VOICE,
    GOOGLE_CREDENTIALS_PATH,
    AUDIO_RETENTION_DAYS,
)

logger = logging.getLogger(__name__)


class TTSEngine:
    """텍스트 → 음성 변환 엔진"""

    def __init__(self, voice: str = TTS_VOICE, google_voice: str = GOOGLE_TTS_VOICE):
        self.voice = voice
        self.google_voice = google_voice

    def _get_audio_path(self, prefix: str = "briefing") -> Path:
        """날짜 기반 오디오 파일 경로 생성"""
        today = datetime.now().strftime("%Y%m%d")
        return AUDIO_DIR / f"{prefix}_{today}.mp3"

    def _get_latest_path(self) -> Path:
        """최신 오디오 파일 고정 경로"""
        return AUDIO_DIR / "briefing_latest.mp3"

    # ── 1순위: Google Cloud TTS ──

    def _generate_google_tts(self, text: str, output_path: Path) -> bool:
        """Google Cloud TTS로 고품질 음성 생성"""
        try:
            from google.cloud import texttospeech
            from google.oauth2.service_account import Credentials

            # 서비스 계정 JSON으로 인증
            import os
            creds_json = os.getenv("GOOGLE_CREDENTIALS_JSON", "").strip()

            if creds_json:
                # GitHub Actions 환경: 환경변수에서 인증
                import json
                import tempfile
                import base64

                if creds_json.startswith("{"):
                    creds_dict = json.loads(creds_json)
                else:
                    creds_dict = json.loads(base64.b64decode(creds_json).decode("utf-8"))

                creds = Credentials.from_service_account_info(creds_dict)
                client = texttospeech.TextToSpeechClient(credentials=creds)
            elif Path(GOOGLE_CREDENTIALS_PATH).exists():
                # 로컬 환경: JSON 파일 인증
                creds = Credentials.from_service_account_file(GOOGLE_CREDENTIALS_PATH)
                client = texttospeech.TextToSpeechClient(credentials=creds)
            else:
                logger.warning("Google Cloud 인증 정보를 찾을 수 없습니다.")
                return False

            # TTS 요청 구성
            synthesis_input = texttospeech.SynthesisInput(text=text)

            voice_params = texttospeech.VoiceSelectionParams(
                language_code="ko-KR",
                name=self.google_voice,
            )

            audio_config = texttospeech.AudioConfig(
                audio_encoding=texttospeech.AudioEncoding.MP3,
                speaking_rate=1.05,  # 자연스러운 속도
                pitch=0.0,
            )

            response = client.synthesize_speech(
                input=synthesis_input,
                voice=voice_params,
                audio_config=audio_config,
            )

            # 파일 저장
            with open(output_path, "wb") as f:
                f.write(response.audio_content)

            size_kb = output_path.stat().st_size / 1024
            logger.info(f"Google Cloud TTS 생성 완료: {output_path} ({size_kb:.1f}KB)")
            return True

        except ImportError:
            logger.warning("google-cloud-texttospeech 패키지가 설치되지 않았습니다.")
            return False
        except Exception as e:
            logger.error(f"Google Cloud TTS 실패: {e}")
            return False

    # ── 2순위: edge-tts ──

    async def _generate_edge_tts(self, text: str, output_path: Path) -> bool:
        """edge-tts로 음성 생성 (비동기)"""
        try:
            import edge_tts

            communicate = edge_tts.Communicate(text, self.voice)
            await communicate.save(str(output_path))
            logger.info(f"edge-tts 음성 생성 완료: {output_path}")
            return True
        except Exception as e:
            logger.error(f"edge-tts 실패: {e}")
            return False

    # ── 3순위: gTTS ──

    def _generate_gtts(self, text: str, output_path: Path) -> bool:
        """gTTS로 음성 생성 (폴백)"""
        try:
            from gtts import gTTS

            tts = gTTS(text=text, lang="ko")
            tts.save(str(output_path))
            logger.info(f"gTTS 음성 생성 완료: {output_path}")
            return True
        except Exception as e:
            logger.error(f"gTTS 폴백도 실패: {e}")
            return False

    # ── 메인 생성 메서드 ──

    def generate(self, text: str, prefix: str = "briefing") -> Path | None:
        """
        텍스트를 음성 파일(mp3)로 변환.
        Google Cloud TTS → edge-tts → gTTS 순서로 시도.
        생성 후 briefing_latest.mp3로 복사 + 오래된 파일 정리.

        Args:
            text: 변환할 텍스트 (브리핑 대본)
            prefix: 파일명 접두사

        Returns:
            생성된 오디오 파일 경로 또는 None
        """
        if not text or not text.strip():
            logger.warning("TTS 입력 텍스트가 비어있습니다.")
            return None

        output_path = self._get_audio_path(prefix)

        # 1차: Google Cloud TTS
        if self._generate_google_tts(text, output_path):
            self._copy_to_latest(output_path)
            self._cleanup_old_files(prefix)
            return output_path

        # 2차: edge-tts
        logger.info("Google Cloud TTS 실패, edge-tts로 폴백 시도...")
        loop = asyncio.new_event_loop()
        try:
            success = loop.run_until_complete(
                self._generate_edge_tts(text, output_path)
            )
        finally:
            loop.close()

        if success:
            self._copy_to_latest(output_path)
            self._cleanup_old_files(prefix)
            return output_path

        # 3차: gTTS
        logger.info("edge-tts 실패, gTTS로 폴백 시도...")
        if self._generate_gtts(text, output_path):
            self._copy_to_latest(output_path)
            self._cleanup_old_files(prefix)
            return output_path

        logger.error("모든 TTS 엔진이 실패했습니다.")
        return None

    # ── 유틸리티 ──

    def _copy_to_latest(self, source_path: Path):
        """최신 파일을 briefing_latest.mp3로 복사"""
        latest = self._get_latest_path()
        try:
            shutil.copy2(source_path, latest)
            logger.info(f"최신 파일 복사: {source_path.name} → {latest.name}")
        except Exception as e:
            logger.error(f"최신 파일 복사 실패: {e}")

    def _cleanup_old_files(self, prefix: str = "briefing"):
        """AUDIO_RETENTION_DAYS보다 오래된 오디오 파일 자동 삭제"""
        cutoff = datetime.now() - timedelta(days=AUDIO_RETENTION_DAYS)
        deleted = 0

        for f in AUDIO_DIR.glob(f"{prefix}_*.mp3"):
            # briefing_latest.mp3는 건드리지 않음
            if f.name == "briefing_latest.mp3":
                continue

            # 파일명에서 날짜 추출 (briefing_YYYYMMDD.mp3)
            try:
                date_str = f.stem.split("_")[-1]
                file_date = datetime.strptime(date_str, "%Y%m%d")
                if file_date < cutoff:
                    f.unlink()
                    deleted += 1
            except (ValueError, IndexError):
                continue

        if deleted:
            logger.info(f"오래된 오디오 파일 {deleted}개 삭제 (기준: {AUDIO_RETENTION_DAYS}일)")

    def get_latest_audio(self) -> Path | None:
        """가장 최근 생성된 오디오 파일 반환"""
        latest = self._get_latest_path()
        if latest.exists():
            return latest
        # 폴백: 날짜순 정렬
        audio_files = sorted(
            AUDIO_DIR.glob("briefing_*.mp3"),
            reverse=True,
        )
        return audio_files[0] if audio_files else None

    def get_audio_list(self) -> list[Path]:
        """날짜순 정렬된 오디오 파일 목록"""
        return sorted(AUDIO_DIR.glob("briefing_*.mp3"), reverse=True)
