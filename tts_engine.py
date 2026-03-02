"""
tts_engine.py - 음성 합성 엔진

edge-tts (1순위): Microsoft Neural TTS, 무료, 한국어 고품질
gTTS (폴백): Google TTS, 무료
"""

import asyncio
import logging
from datetime import datetime
from pathlib import Path

from config import AUDIO_DIR, TTS_VOICE

logger = logging.getLogger(__name__)


class TTSEngine:
    """텍스트 → 음성 변환 엔진"""

    def __init__(self, voice: str = TTS_VOICE):
        self.voice = voice

    def _get_audio_path(self, prefix: str = "briefing") -> Path:
        """날짜 기반 오디오 파일 경로 생성"""
        today = datetime.now().strftime("%Y%m%d")
        return AUDIO_DIR / f"{prefix}_{today}.mp3"

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

    def generate(self, text: str, prefix: str = "briefing") -> Path | None:
        """
        텍스트를 음성 파일(mp3)로 변환.
        edge-tts 시도 후 실패 시 gTTS로 폴백.

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

        # 1차: edge-tts 시도
        loop = asyncio.new_event_loop()
        try:
            success = loop.run_until_complete(
                self._generate_edge_tts(text, output_path)
            )
        finally:
            loop.close()

        if success:
            return output_path

        # 2차: gTTS 폴백
        logger.info("edge-tts 실패, gTTS로 폴백 시도...")
        if self._generate_gtts(text, output_path):
            return output_path

        logger.error("모든 TTS 엔진이 실패했습니다.")
        return None

    def get_latest_audio(self) -> Path | None:
        """가장 최근 생성된 오디오 파일 반환"""
        audio_files = sorted(
            AUDIO_DIR.glob("briefing_*.mp3"),
            reverse=True,
        )
        return audio_files[0] if audio_files else None

    def get_audio_list(self) -> list[Path]:
        """날짜순 정렬된 오디오 파일 목록"""
        return sorted(AUDIO_DIR.glob("briefing_*.mp3"), reverse=True)
