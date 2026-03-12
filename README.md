# 📰 AI 뉴스 비서

소상공인 종합지원을 위한 AI 뉴스 수집·분석 대시보드

## 아키텍처

```
GitHub Actions (매일 07:00 KST)
  └─ Python: 뉴스 수집 → AI 분석 → Google Sheets 저장

GitHub Pages (index.html)
  └─ Google Apps Script → JSON fetch → 브라우저 렌더링
```

## 주요 기능
- **자동 수집**: 네이버 뉴스 API로 키워드별 최신 뉴스 수집
- **AI 분석**: Google Gemini로 중요도 판단 및 핵심 요약 생성
- **대시보드**: Tailwind CSS 기반 프리미엄 모바일 퍼스트 UI
- **필터링**: 날짜/카테고리/중요도/검색어 필터
- **데이터 저장**: Google Sheets 통합 저장소

## 배포 방법

### 1. GitHub Secrets 설정
Repository Settings > Secrets and variables > Actions에 다음을 추가:
- `NAVER_CLIENT_ID` - 네이버 API 클라이언트 ID
- `NAVER_CLIENT_SECRET` - 네이버 API 시크릿
- `GEMINI_API_KEY` - Google Gemini API 키
- `GOOGLE_SHEET_ID` - 구글 시트 ID
- `GOOGLE_CREDENTIALS_JSON` - 서비스 계정 JSON을 base64 인코딩한 값

### 2. Google Apps Script 설정
구글 시트 > 확장 프로그램 > Apps Script에서 웹 앱 배포 (자세한 코드는 index.html 참조)

### 3. GitHub Pages 활성화
Repository Settings > Pages > Source: Deploy from a branch > main (or master)

## 📱 앱 설치 및 이용 (PWA)

본 대시보드는 PWA(Progressive Web App) 기술이 적용되어 있어, 기본 웹 브라우저가 아닌 별도 앱처럼 설치하여 사용하실 수 있습니다.

### 설치 방법
1.  **안드로이드/데스크톱(Chrome)**: 주소창 옆의 **설치 아이콘(⊕)** 또는 메인 화면의 **[설정(⚙️) > 이 앱을 설치하기]** 버튼 클릭
2.  **iOS(Safari)**: 하단의 **공유 버튼(↑)** 클릭 후 **[홈 화면에 추가]** 선택

### 주요 설정 및 기능
-   **뉴스 수집**: 우측 상단 또는 하단 메뉴의 **[수집]** 버튼으로 최신 기사 즉시 업데이트 (GitHub Actions 연동)
-   **AI 브리핑**: 음성 합성(TTS) 기술을 이용해 오늘의 주요 소식을 라디오처럼 들려줍니다.
-   **PWA 초기화**: 설치가 잘 안 되거나 데이터가 꼬였을 때 **[설정 > PWA 초기화]**를 눌러 깨끗이 정리할 수 있습니다.

## 🛠️ 유지보수 및 인프라
-   **오디오 보존 정책**: 서버(GitHub) 저장 공간 관리를 위해 생성된 지 30일이 지난 오래된 브리핑 오디오 파일은 매일 자동으로 정리됩니다.

## 기술 스택
- **백엔드**: Python, Google Gemini, 네이버 뉴스 API
- **프런트엔드**: HTML, Tailwind CSS, JavaScript
- **데이터**: Google Sheets + Apps Script
- **자동화**: GitHub Actions (cron)
