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

## 기술 스택
- **백엔드**: Python, Google Gemini, 네이버 뉴스 API
- **프런트엔드**: HTML, Tailwind CSS, JavaScript
- **데이터**: Google Sheets + Apps Script
- **자동화**: GitHub Actions (cron)
