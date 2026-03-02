# 📰 AI 뉴스 비서 - 통합 관리형 브리핑 시스템

매일 아침 설정된 키워드 기반의 뉴스를 자동 수집·요약하여 **음성 브리핑**과 **통합 뉴스 리포트**를 제공하는 웹 앱입니다.

## ✨ 주요 기능

- **🔍 자동 뉴스 수집**: 네이버 뉴스 API + newspaper4k로 키워드별 최신 뉴스 수집
- **🤖 AI 분석**: Gemini API로 중요도 판단 및 핵심 요약 생성
- **🎙️ 음성 브리핑**: edge-tts로 자연스러운 한국어 아침 브리핑 자동 생성
- **📰 통합 대시보드**: 카테고리·중요도·날짜별 필터링 뉴스 피드
- **⏰ 자동 스케줄링**: 매일 오전 7시 자동 실행 (수동 즉시 실행도 가능)
- **⚙️ 동적 설정**: 앱 내에서 키워드/카테고리 실시간 관리

## 🛠️ 기술 스택

| 구분 | 기술 |
|------|------|
| 뉴스 수집 | 네이버 뉴스 API + newspaper4k |
| AI 분석 | Google Gemini API |
| 음성 합성 | edge-tts (Microsoft Neural TTS) |
| 데이터 저장 | Google Sheets |
| UI/UX | Streamlit |
| 스케줄링 | APScheduler |

## 📁 프로젝트 구조

```
ai_news_briefing/
├── .env.example          # API 키 템플릿
├── requirements.txt      # Python 의존성
├── config.py             # 환경변수 로드 및 전역 설정
├── sheets_manager.py     # Google Sheets CRUD
├── news_collector.py     # 네이버 API + newspaper4k 크롤링
├── ai_analyzer.py        # Gemini API 분석
├── tts_engine.py         # edge-tts 음성 합성
├── scheduler.py          # APScheduler 자동 실행
├── app.py                # Streamlit 메인 대시보드
├── pages/
│   └── settings.py       # 설정 페이지
├── audio/                # 생성된 브리핑 오디오
└── credentials/          # Google 서비스 계정 JSON
```

## 🚀 시작하기

### 1. Python 가상환경 생성

```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
```

### 2. 패키지 설치

```bash
pip install -r requirements.txt
```

### 3. API 키 설정

```bash
cp .env.example .env
# .env 파일을 편집하여 API 키 입력
```

#### 필요한 API 키:
- **네이버 검색 API**: [네이버 개발자 센터](https://developers.naver.com/)에서 발급
- **Gemini API**: [Google AI Studio](https://aistudio.google.com/apikey)에서 발급
- **Google Sheets 서비스 계정**:
  1. [Google Cloud Console](https://console.cloud.google.com/)에서 프로젝트 생성
  2. Google Sheets API, Google Drive API 활성화
  3. 서비스 계정 생성 → JSON 키 다운로드
  4. `credentials/service_account.json`에 배치
  5. Google Sheets에서 서비스 계정 이메일에 편집 권한 부여

### 4. 앱 실행

```bash
streamlit run app.py
```

## 📖 사용 방법

1. **⚙️ 설정 페이지**에서 검색할 키워드와 카테고리를 등록
2. **🔄 지금 새로고침** 버튼으로 뉴스 수집 시작
3. **📰 뉴스 피드**에서 카테고리/중요도별로 뉴스 확인
4. **🎙️ 브리핑 플레이어**에서 AI 음성 브리핑 청취
5. 필요 시 **⏰ 스케줄러**를 활성화하여 매일 자동 실행

---

*AI 뉴스 비서 v1.0 | Powered by 네이버 뉴스 API · Gemini · edge-tts · Streamlit*
