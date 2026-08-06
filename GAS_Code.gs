/**
 * Google Apps Script for AI News Briefing (비밀번호 인증 및 데이터 조회/관리)
 */

function doGet(e) {
  // POST 리다이렉트 대응 (Python requests의 302 리다이렉트 처리)
  if (e.parameter && e.parameter.action && e.parameter.isRedirect === 'true') {
    e.postData = { contents: JSON.stringify(e.parameter) };
    return doPost(e);
  }

  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const tab = e.parameter.tab || 'News_Data';
  const dateStr = e.parameter.date; // YYYY-MM-DD (단일 날짜)
  const startDateStr = e.parameter.startDate; // YYYY-MM-DD (시작일)
  const endDateStr = e.parameter.endDate; // YYYY-MM-DD (종료일)
  const topic = e.parameter.topic; // 주제 필터
  const action = e.parameter ? e.parameter.action : null;

  // ── 비밀번호 확인 API (GET 대응) ──
  if (action === 'adminLogin') {
    const ADMIN_PW = PropertiesService.getScriptProperties().getProperty('ADMIN_PW');
    if (e.parameter.pw === ADMIN_PW) {
      return createResponse({ success: true });
    } else {
      return createResponse({ success: false, error: '비밀번호가 일치하지 않습니다.' });
    }
  }

  // ── 수동 수집 트리거 (GitHub Actions) ──
  if (action === 'triggerWorkflow') {
    const props = PropertiesService.getScriptProperties();
    const GITHUB_PAT = props.getProperty('GITHUB_PAT') || props.getProperty('GITHUB_TOKEN');
    
    if (!GITHUB_PAT) {
      return createResponse({ error: 'GITHUB_PAT 또는 GITHUB_TOKEN이 스크립트 속성에 설정되지 않았습니다.', ok: false });
    }

    const url = 'https://api.github.com/repos/ktm9898/ai_news_briefing/actions/workflows/collect.yml/dispatches';
    const options = {
      method: 'post',
      headers: {
        'Accept': 'application/vnd.github.v3+json',
        'Authorization': 'Bearer ' + GITHUB_PAT
      },
      payload: JSON.stringify({ ref: 'master' }),
      muteHttpExceptions: true
    };

    try {
      const response = UrlFetchApp.fetch(url, options);
      if (response.getResponseCode() >= 200 && response.getResponseCode() < 300) {
        return createResponse({ ok: true, success: true });
      } else {
        return createResponse({ error: 'GitHub API 오류: ' + response.getContentText(), ok: false });
      }
    } catch (err) {
      return createResponse({ error: '요청 실패: ' + err.toString(), ok: false });
    }
  }

  const sheet = ss.getSheetByName(tab);
  if (!sheet) return createResponse([]);

  const data = sheet.getDataRange().getValues();
  if (data.length <= 1) return createResponse([]);

  const headers = data[0];
  let rows = data.slice(1);

  // 빈 행 제거 (어느 열이든 값이 존재하는 행만 유지)
  rows = rows.filter(row => row.some(cell => String(cell).trim() !== ''));

  let result = rows.map(row => {
    let obj = {};
    headers.forEach((h, i) => {
      let val = row[i];
      if (val instanceof Date || (val && Object.prototype.toString.call(val) === '[object Date]')) {
        val = Utilities.formatDate(val, "GMT+9", "yyyy-MM-dd");
      }
      obj[h] = val;
    });
    return obj;
  });

  // Briefing_Docs 및 Weekly_Briefing_Docs의 경우 최신 10건으로 제한 (타임아웃 방지)
  if (tab === 'Briefing_Docs' || tab === 'Weekly_Briefing_Docs') {
    result = result.slice(-10);
  }

  // News_Data 탭의 경우 날짜 및 주제 필터 적용
  if (tab === 'News_Data') {
    if (startDateStr || endDateStr) {
      result = result.filter(item => {
        let itemDate = item['날짜'];
        if (itemDate instanceof Date || (itemDate && Object.prototype.toString.call(itemDate) === '[object Date]')) {
          itemDate = Utilities.formatDate(itemDate, "GMT+9", "yyyy-MM-dd");
        } else if (itemDate) {
          itemDate = String(itemDate).trim();
          const match = itemDate.match(/(\d{4})[\.\-\/\s]+(\d{1,2})[\.\-\/\s]+(\d{1,2})/);
          if (match) {
            itemDate = match[1] + '-' + ('0' + match[2]).slice(-2) + '-' + ('0' + match[3]).slice(-2);
          } else {
            const dObj = new Date(itemDate);
            if (!isNaN(dObj.getTime())) {
               itemDate = Utilities.formatDate(dObj, "GMT+9", "yyyy-MM-dd");
            }
          }
        }
        if (startDateStr && itemDate < startDateStr) return false;
        if (endDateStr && itemDate > endDateStr) return false;
        return true;
      });
    } else if (dateStr) {
      result = result.filter(item => {
        let itemDate = item['날짜'];
        if (itemDate instanceof Date || (itemDate && Object.prototype.toString.call(itemDate) === '[object Date]')) {
          itemDate = Utilities.formatDate(itemDate, "GMT+9", "yyyy-MM-dd");
        } else if (itemDate) {
          itemDate = String(itemDate).trim();
          // 정규식으로 YYYY-MM-DD 형식 우선 추출
          const match = itemDate.match(/(\d{4})[\.\-\/\s]+(\d{1,2})[\.\-\/\s]+(\d{1,2})/);
          if (match) {
            itemDate = match[1] + '-' + ('0' + match[2]).slice(-2) + '-' + ('0' + match[3]).slice(-2);
          } else {
            // 정규식 실패 시 Date 파싱 시도
            const dObj = new Date(itemDate);
            if (!isNaN(dObj.getTime())) {
               itemDate = Utilities.formatDate(dObj, "GMT+9", "yyyy-MM-dd");
            }
          }
        }
        return itemDate === dateStr;
      });
    }
    if (topic && topic !== '전체') {
      result = result.filter(item => item['주제'] === topic);
    }
    // 너무 많은 데이터 방지를 위해 최신 200건으로 제한 (필터 후)
    if (!dateStr && !startDateStr && !endDateStr && !topic) {
      result = result.slice(-200);
    }
  }

  return createResponse(result);
}

function doPost(e) {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const params = JSON.parse(e.postData.contents);
  const action = params.action;
  const ADMIN_PW = PropertiesService.getScriptProperties().getProperty('ADMIN_PW');

  // ── 수동 수집 트리거 (GitHub Actions) ──
  if (action === 'triggerWorkflow') {
    if (params.pw !== ADMIN_PW) {
      return createResponse({ success: false, error: '비밀번호가 일치하지 않습니다.' });
    }

    const props = PropertiesService.getScriptProperties();
    const GITHUB_PAT = props.getProperty('GITHUB_PAT') || props.getProperty('GITHUB_TOKEN');
    
    if (!GITHUB_PAT) {
      return createResponse({ error: 'GITHUB_PAT 또는 GITHUB_TOKEN이 스크립트 속성에 설정되지 않았습니다.', ok: false });
    }

    const url = 'https://api.github.com/repos/ktm9898/ai_news_briefing/actions/workflows/collect.yml/dispatches';
    const options = {
      method: 'post',
      headers: {
        'Accept': 'application/vnd.github.v3+json',
        'Authorization': 'Bearer ' + GITHUB_PAT
      },
      payload: JSON.stringify({ ref: 'master' }),
      muteHttpExceptions: true
    };

    try {
      const response = UrlFetchApp.fetch(url, options);
      if (response.getResponseCode() >= 200 && response.getResponseCode() < 300) {
        return createResponse({ ok: true, success: true });
      } else {
        return createResponse({ error: 'GitHub API 오류: ' + response.getContentText(), ok: false });
      }
    } catch (err) {
      return createResponse({ error: '요청 실패: ' + err.toString(), ok: false });
    }
  }

  // ── 일일 맞춤형 HTML 이메일 발송 ──
  if (action === 'sendDailyReport') {
    const targetEmail = params.email;
    const dateStr = params.date || Utilities.formatDate(new Date(), "GMT+9", "yyyy-MM-dd");
    const briefingScript = params.briefingScript || '';
    const insightReport = params.insightReport || null;
    let newsList = params.newsList || [];
    if (typeof newsList === 'string') {
      try { newsList = JSON.parse(newsList); } catch(e) { newsList = []; }
    }
    if (typeof insightReport === 'string') {
      try { insightReport = JSON.parse(insightReport); } catch(e) {}
    }

    try {
      sendDailyReportEmail(targetEmail, dateStr, briefingScript, insightReport, newsList);
      return createResponse({ success: true });
    } catch (err) {
      return createResponse({ success: false, error: err.toString() });
    }
  }

  // ── 주간 맞춤형 HTML 이메일 발송 ──
  if (action === 'sendWeeklyReport') {
    const targetEmail = params.email;
    const dateRange = params.dateRange || '';
    let insightReport = params.insightReport || null;
    if (typeof insightReport === 'string') {
      try { insightReport = JSON.parse(insightReport); } catch(e) {}
    }

    try {
      sendWeeklyReportEmail(targetEmail, dateRange, insightReport);
      return createResponse({ success: true });
    } catch (err) {
      return createResponse({ success: false, error: err.toString() });
    }
  }

  // ── 테스트 리포트 이메일 수동/테스트 발송 ──
  if (action === 'sendTestReport') {
    const targetEmail = params.email || 'ktm98@seoulshinbo.co.kr';
    const dateStr = params.date || Utilities.formatDate(new Date(), "GMT+9", "yyyy-MM-dd");
    
    try {
      const ss = SpreadsheetApp.getActiveSpreadsheet();
      const sheet = getOrCreateTab(ss, 'Briefing_Docs', ['이메일', '날짜', '제목', '내용']);
      const data = sheet.getDataRange().getValues();
      if (data.length <= 1) {
        return createResponse({ success: false, error: '저장된 인사이트 리포트가 없습니다. (시트가 비어있음)' });
      }
      
      const headers = data[0];
      const emailIdx = headers.indexOf('이메일') !== -1 ? headers.indexOf('이메일') : headers.indexOf('Email');
      const dateIdx = headers.indexOf('날짜') !== -1 ? headers.indexOf('날짜') : headers.indexOf('Date');
      const contentIdx = headers.indexOf('내용') !== -1 ? headers.indexOf('내용') : headers.indexOf('Content');
      
      let latestReport = null;
      let reportDate = dateStr;
      
      // 뒤에서부터 검색하여 해당 이메일의 가장 최근 리포트 추출
      for (let i = data.length - 1; i >= 1; i--) {
        const rowEmail = emailIdx !== -1 ? String(data[i][emailIdx]).trim().toLowerCase() : '';
        if (rowEmail === targetEmail.toLowerCase()) {
          latestReport = contentIdx !== -1 ? data[i][contentIdx] : null;
          let rDate = dateIdx !== -1 ? data[i][dateIdx] : dateStr;
          if (rDate instanceof Date || (rDate && Object.prototype.toString.call(rDate) === '[object Date]')) {
            reportDate = Utilities.formatDate(rDate, "GMT+9", "yyyy-MM-dd");
          } else {
            reportDate = String(rDate);
          }
          break;
        }
      }
      
      if (!latestReport) {
        return createResponse({ success: false, error: '저장된 인사이트 리포트를 찾을 수 없습니다. Email: ' + targetEmail });
      }
      
      let insightReport = null;
      try {
        insightReport = JSON.parse(latestReport);
      } catch(e) {
        return createResponse({ success: false, error: '인사이트 리포트 JSON 파싱 실패: ' + e.toString() });
      }
      
      sendDailyReportEmail(targetEmail, reportDate, '', insightReport, []);
      return createResponse({ success: true, message: '테스트 리포트 메일이 발송되었습니다. 수신처: ' + targetEmail });
    } catch (err) {
      return createResponse({ success: false, error: err.toString() });
    }
  }

  // ── 관리자 인증 API ──
  if (action === 'adminLogin') {
    if (params.pw === ADMIN_PW) {
      return createResponse({ success: true });
    } else {
      return createResponse({ success: false, error: '비밀번호가 일치하지 않습니다.' });
    }
  }

  // 키워드 설정 (Settings 탭)
  if (action === 'addKeyword') {
    const sheet = getOrCreateTab(ss, 'Settings', ['주제', '키워드', '활성화']);
    sheet.appendRow([params.topic, params.keyword, 'TRUE']);
    return createResponse({ success: true });
  }

  if (action === 'deleteKeyword') {
    const sheet = ss.getSheetByName('Settings');
    if (!sheet) return createResponse({ error: 'Settings tab not found' });
    const data = sheet.getDataRange().getValues();
    const headers = data[0];
    const topicIdx = headers.indexOf('주제') !== -1 ? headers.indexOf('주제') : headers.indexOf('카테고리');
    const keyIdx = headers.indexOf('키워드');
    
    for (let i = 1; i < data.length; i++) {
      if (data[i][topicIdx] === params.topic && data[i][keyIdx] === params.keyword) {
        sheet.deleteRow(i + 1);
        return createResponse({ success: true });
      }
    }
    return createResponse({ error: 'Keyword not found' });
  }

  // 주제 및 관련 키워드 전체 삭제 (Settings 및 Topic_Settings 탭)
  if (action === 'deleteTopic') {
    // 1. Topic_Settings 시트에서 해당 주제 삭제
    const topicSheet = ss.getSheetByName('Topic_Settings');
    if (topicSheet) {
      const data = topicSheet.getDataRange().getValues();
      const headers = data[0];
      const topicIdx = headers.indexOf('Topic') !== -1 ? headers.indexOf('Topic') : (headers.indexOf('주제') !== -1 ? headers.indexOf('주제') : 0);
      
      for (let i = data.length - 1; i >= 1; i--) {
        if (data[i][topicIdx] === params.topic) {
          topicSheet.deleteRow(i + 1);
        }
      }
    }

    // 2. Settings 시트에서 해당 주제의 모든 키워드 삭제
    const settingsSheet = ss.getSheetByName('Settings');
    if (settingsSheet) {
      const data = settingsSheet.getDataRange().getValues();
      const headers = data[0];
      const topicIdx = headers.indexOf('주제') !== -1 ? headers.indexOf('주제') : headers.indexOf('카테고리');
      
      for (let i = data.length - 1; i >= 1; i--) {
        if (data[i][topicIdx] === params.topic) {
          settingsSheet.deleteRow(i + 1);
        }
      }
    }

    return createResponse({ success: true });
  }

  // 주요뉴스 활성화 여부 토글 (Settings 탭)
  if (action === 'toggleMainNews') {
    const sheet = getOrCreateTab(ss, 'Settings', ['주제', '키워드', '활성화']);
    const data = sheet.getDataRange().getValues();
    const headers = data[0];
    const topicIdx = headers.indexOf('주제') !== -1 ? headers.indexOf('주제') : headers.indexOf('카테고리');
    const activeIdx = headers.indexOf('활성화');
    
    const isEnabledStr = params.enabled ? 'TRUE' : 'FALSE';

    // 기존 주요뉴스 행이 있으면 업데이트
    for (let i = 1; i < data.length; i++) {
      const rowTopic = topicIdx !== -1 ? String(data[i][topicIdx] || '').trim() : '';
      if (rowTopic === '주요뉴스' || rowTopic === '경제헤드라인') {
        sheet.getRange(i + 1, activeIdx + 1).setValue(isEnabledStr);
        return createResponse({ success: true });
      }
    }
    
    // 없으면 새로 추가
    sheet.appendRow(['주요뉴스', '전체', isEnabledStr]);
    return createResponse({ success: true });
  }

  // 키워드 토글 (Settings 탭)
  if (action === 'toggleKeyword') {
    const sheet = ss.getSheetByName('Settings');
    if (!sheet) return createResponse({ error: 'Settings tab not found' });
    const data = sheet.getDataRange().getValues();
    const headers = data[0];
    const topicIdx = headers.indexOf('주제') !== -1 ? headers.indexOf('주제') : headers.indexOf('카테고리');
    const keyIdx = headers.indexOf('키워드');
    const activeIdx = headers.indexOf('활성화');
    
    for (let i = 1; i < data.length; i++) {
      if (data[i][topicIdx] === params.topic && data[i][keyIdx] === params.keyword) {
        let currentValue = data[i][activeIdx];
        let newValue = (String(currentValue).toUpperCase() === 'TRUE') ? 'FALSE' : 'TRUE';
        sheet.getRange(i + 1, activeIdx + 1).setValue(newValue);
        return createResponse({ success: true });
      }
    }
    return createResponse({ error: 'Keyword not found' });
  }

  // 주제별 AI 기준 및 수집 갯수 설정 (Topic_Settings 탭)
  if (action === 'updateTopicCriteria') {
    const sheet = getOrCreateTab(ss, 'Topic_Settings', ['Topic', 'Criteria', 'MaxCount']);
    const data = sheet.getDataRange().getValues();
    const headers = data[0];
    const topicIdx = headers.indexOf('Topic') !== -1 ? headers.indexOf('Topic') : (headers.indexOf('주제') !== -1 ? headers.indexOf('주제') : 0);
    const criteriaIdx = headers.indexOf('Criteria') !== -1 ? headers.indexOf('Criteria') : (headers.indexOf('기준') !== -1 ? headers.indexOf('기준') : 1);
    let maxCountIdx = headers.indexOf('MaxCount') !== -1 ? headers.indexOf('MaxCount') : (headers.indexOf('수집갯수') !== -1 ? headers.indexOf('수집갯수') : headers.indexOf('개수'));
    
    // MaxCount 헤더가 없으면 새로 추가
    if (maxCountIdx === -1) {
      maxCountIdx = headers.length;
      sheet.getRange(1, maxCountIdx + 1).setValue('MaxCount');
    }
    
    const maxCountVal = params.maxCount !== undefined && params.maxCount !== null ? parseInt(params.maxCount, 10) || 5 : 5;

    let found = false;

    for (let i = 1; i < data.length; i++) {
      const rowTopic = data[i][topicIdx];
      if (rowTopic === params.topic) {
        if (params.criteria !== undefined) {
          sheet.getRange(i + 1, criteriaIdx + 1).setValue(params.criteria);
        }
        sheet.getRange(i + 1, maxCountIdx + 1).setValue(maxCountVal);
        found = true;
        break;
      }
    }
    if (!found) {
      const newRow = [];
      newRow[topicIdx] = params.topic;
      newRow[criteriaIdx] = params.criteria || '';
      newRow[maxCountIdx] = maxCountVal;
      sheet.appendRow(newRow);
    }
    return createResponse({ success: true });
  }

  return createResponse({ error: 'Invalid action' });
}

function isUserApproved(ss, email) {
  return true;
}

function getOrCreateTab(ss, name, headers) {
  let sheet = ss.getSheetByName(name);
  if (!sheet) {
    sheet = ss.insertSheet(name);
    sheet.appendRow(headers);
  } else {
    // 기존 탭 헤더 보정: '이메일' 필드 누락 시 추가하여 호환성 유지
    const data = sheet.getDataRange().getValues();
    if (data.length === 0 || data[0].length === 0) {
      sheet.appendRow(headers);
    } else {
      const currentHeaders = data[0];
      if (currentHeaders.indexOf('이메일') === -1 && currentHeaders.indexOf('Email') === -1) {
        sheet.insertColumnBefore(1);
        sheet.getRange(1, 1).setValue('이메일');
        if (sheet.getLastRow() > 1) {
          // 기존 데이터 이메일 열 빈 문자열로 채우기
          sheet.getRange(2, 1, sheet.getLastRow() - 1, 1).setValue('');
        }
      }
    }
  }
  return sheet;
}

function createResponse(data) {
  return ContentService.createTextOutput(JSON.stringify(data))
    .setMimeType(ContentService.MimeType.JSON);
}

function escapeHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function formatParagraphs(text) {
  if (!text) return "";
  text = String(text).trim();
  
  // 만약 개행문자(\n)가 이미 포함되어 있다면 개행문자를 <br>로 치환하여 그대로 반환
  if (text.indexOf('\n') !== -1) {
    return text.replace(/\n/g, '<br>');
  }
  
  // 개행문자가 없는 긴 문장의 경우, 2~3문장 단위로 문단을 분리
  const sentences = text.split(/(?<=\.|\!|\?)\s+/);
  let formatted = "";
  let paragraph = [];
  for (let i = 0; i < sentences.length; i++) {
    paragraph.push(sentences[i]);
    if (paragraph.length === 3 || i === sentences.length - 1) {
      formatted += (formatted ? '<br><br>' : '') + paragraph.join(' ');
      paragraph = [];
    }
  }
  return formatted;
}

function generateInsightReportPdf(date, insightReport) {
  if (!insightReport) return null;

  let html = '<!DOCTYPE html><html><head><meta charset="utf-8">';
  html += '<link href="https://fonts.googleapis.com/css2?family=Nanum+Gothic:wght@400;700&display=swap" rel="stylesheet">';
  html += '<style>';
  html += '@page { size: A4; margin: 20mm; }';
  html += 'body { font-family: "Nanum Gothic", sans-serif; color: #1a1a1a; line-height: 1.7; padding: 0; margin: 0; }';
  html += '.header-table { width: 100%; border-collapse: collapse; margin-bottom: 15px; }';
  html += '.header-title { font-size: 20pt; font-weight: bold; color: #000; }';
  html += '.header-date { text-align: right; color: #666; font-size: 10pt; padding-bottom: 5px; }';
  html += 'hr { border: 0; border-top: 1px solid #000; margin: 0 0 20px 0; }';
  html += '.section-header { font-size: 14pt; font-weight: bold; color: #000; margin-top: 30px; margin-bottom: 12px; }';
  html += '.news-title { font-size: 12pt; font-weight: bold; color: #000; margin-top: 25px; margin-bottom: 10px; }';
  html += 'p { font-size: 10.5pt; color: #333; margin-top: 0; margin-bottom: 10px; line-height: 1.7; text-align: justify; word-break: break-all; }';
  html += '.footer-note { font-size: 9pt; color: #6b7280; text-align: left; margin-top: 40px; border-top: 1px solid #e5e7eb; padding-top: 10px; }';
  html += '</style></head><body>';

  // 1. 헤더 (같은 줄에 배치)
  html += '<table class="header-table"><tr>';
  html += '<td class="header-title">서울신용보증재단 인사이트 리포트</td>';
  html += '<td class="header-date" valign="bottom">' + escapeHtml(date) + '</td>';
  html += '</tr></table>';
  html += '<hr>';

  // 2. 주요 경제 흐름
  html += '<div class="section-header">1. 주요 경제 흐름</div>';
  html += '<p>' + escapeHtml(insightReport.economic_trend || '').replace(/\n/g, '<br>') + '</p>';

  // 3. 업무 인사이트
  html += '<div class="section-header">2. 업무 인사이트</div>';
  if (insightReport.news_insights && Array.isArray(insightReport.news_insights)) {
    insightReport.news_insights.forEach(function(item) {
      var publisherDate = (item.publisher || item.date) ? ' <span style="font-size:10pt; color:#666; font-weight:normal;">(' + escapeHtml(item.publisher || '') + (item.publisher && item.date ? ', ' : '') + escapeHtml(item.date || '') + ')</span>' : '';
      html += '<div class="news-title"><b>' + escapeHtml(item.title) + '</b>' + publisherDate + '</div>';
      html += '<p><b>주요내용:</b> ' + formatParagraphs(item.summary || '') + '</p>';
      
      html += '<p style="margin-bottom: 25px;"><b>인사이트:</b> ' + formatParagraphs(item.implication || '') + '</p>';
    });
  }

  html += '<div class="footer-note">본 리포트는 서울신용보증재단의 정책 결정 및 업무 지원을 위해 AI를 통해 분석된 결과입니다.</div>';
  html += '</body></html>';

  const htmlOutput = HtmlService.createHtmlOutput(html);
  return htmlOutput.getAs('application/pdf').setName('서울신용보증재단_인사이트_리포트_' + date + '.pdf');
}

function sendDailyReportEmail(email, date, briefingScript, insightReport, newsList) {
  if (!email) return;

  // 인사이트 리포트가 없는 경우 로그 기록 및 조기 리턴
  if (!insightReport) {
    Logger.log("인사이트 리포트 데이터가 없어서 이메일을 발송하지 않습니다. Email: " + email);
    return;
  }

  // 1. PDF 첨부파일 생성
  const pdfBlob = generateInsightReportPdf(date, insightReport);
  if (!pdfBlob) {
    Logger.log("PDF 생성 실패. Email: " + email);
    return;
  }

  // 2. 이메일 본문 HTML 작성 (인쇄 화면 레이아웃과 동일하게 디자인)
  let newsInsightsHtml = "";
  if (insightReport.news_insights && Array.isArray(insightReport.news_insights)) {
    insightReport.news_insights.forEach(function(item) {
      var publisherDate = (item.publisher || item.date) ? ' <span style="font-size:10pt; color:#666; font-weight:normal;">(' + escapeHtml(item.publisher || '') + (item.publisher && item.date ? ', ' : '') + escapeHtml(item.date || '') + ')</span>' : '';
      newsInsightsHtml += '<div style="font-size: 12pt; font-weight: bold; color: #000; margin-top: 25px; margin-bottom: 10px;"><b>' + escapeHtml(item.title) + '</b>' + publisherDate + '</div>';
      newsInsightsHtml += '<p style="font-size: 10.5pt; color: #333; margin-top: 0; margin-bottom: 10px; line-height: 1.7; text-align: justify; word-break: break-all;"><b>주요내용:</b> ' + formatParagraphs(item.summary || '') + '</p>';
      
      // references 배열 존재 여부에 따라 하단 마진 조절
      var hasRefs = (item.references && item.references.length > 0) || (item.reference && String(item.reference).trim() !== '');
      newsInsightsHtml += '<p style="font-size: 10.5pt; color: #333; margin-top: 0; margin-bottom: ' + (hasRefs ? '15px' : '25px') + '; line-height: 1.7; text-align: justify; word-break: break-all;"><b>인사이트:</b> ' + formatParagraphs(item.implication || '') + '</p>';
      
      // 신규 배열 형식 (references)
      if (item.references && Array.isArray(item.references) && item.references.length > 0) {
        item.references.forEach(function(ref, idx) {
          var isLast = (idx === item.references.length - 1);
          var mb = isLast ? '25px' : '5px';
          var refName = typeof ref === 'string' ? ref : (ref.name || '');
          var refUrl = typeof ref === 'string' ? '' : (ref.url || '');
          // URL 유효성 검증: http(s)로 시작하는 경우만 실제 링크로 사용
          var isValidUrl = refUrl && /^https?:\/\//i.test(String(refUrl).trim());
          if (isValidUrl) {
            var safeUrl = String(refUrl).trim().replace(/&/g, '&amp;').replace(/"/g, '&quot;');
            newsInsightsHtml += '<p style="font-size: 10.5pt; margin-top: 0; margin-bottom: ' + mb + '; line-height: 1.7;"><a href="' + safeUrl + '" target="_blank" style="text-decoration: underline; color: #2563eb;">[참고 출처: ' + escapeHtml(refName) + ']</a></p>';
          } else {
            var q = encodeURIComponent(String(refName).replace(/"/g, ''));
            newsInsightsHtml += '<p style="font-size: 10.5pt; margin-top: 0; margin-bottom: ' + mb + '; line-height: 1.7;"><a href="https://www.google.com/search?q=' + q + '" target="_blank" style="text-decoration: underline; color: #2563eb;">[참고 출처: ' + escapeHtml(refName) + ']</a></p>';
          }
        });
      }
      // 기존 단일 문자열 형식 (하위 호환)
      else if (item.reference && String(item.reference).trim() !== '') {
        var legacyUrl = item.reference_url || '';
        var isValidLegacyUrl = legacyUrl && /^https?:\/\//i.test(String(legacyUrl).trim());
        if (isValidLegacyUrl) {
          var safeRefUrl = String(legacyUrl).trim().replace(/&/g, '&amp;').replace(/"/g, '&quot;');
          newsInsightsHtml += '<p style="font-size: 10.5pt; margin-top: 0; margin-bottom: 25px; line-height: 1.7;"><a href="' + safeRefUrl + '" target="_blank" style="text-decoration: underline; color: #2563eb;">[참고 출처: ' + escapeHtml(item.reference) + ']</a></p>';
        } else {
          var q = encodeURIComponent(String(item.reference).replace(/"/g, ''));
          newsInsightsHtml += '<p style="font-size: 10.5pt; margin-top: 0; margin-bottom: 25px; line-height: 1.7;"><a href="https://www.google.com/search?q=' + q + '" target="_blank" style="text-decoration: underline; color: #2563eb;">[참고 출처: ' + escapeHtml(item.reference) + ']</a></p>';
        }
      }
    });
  }

  let htmlBody = '<div style="font-family: \'Nanum Gothic\', \'Malgun Gothic\', \'Apple SD Gothic Neo\', sans-serif; background-color: #f8fafc; padding: 40px 20px; color: #1a1a1a;">';
  htmlBody += '<div style="max-width: 700px; margin: 0 auto; background-color: #ffffff; border: 1px solid #e2e8f0; padding: 40px; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1); border-radius: 8px;">';
  
  // 헤더
  htmlBody += '<table width="100%" style="border-collapse: collapse; margin-bottom: 15px;"><tr>';
  htmlBody += '<td align="left" style="font-size: 20pt; font-weight: bold; color: #000;">서울신용보증재단 인사이트 리포트</td>';
  htmlBody += '<td align="right" valign="bottom" style="color: #666; font-size: 10pt; padding-bottom: 5px;">' + escapeHtml(date) + '</td>';
  htmlBody += '</tr></table>';
  htmlBody += '<hr style="border: 0; border-top: 1px solid #000; margin: 0 0 20px 0;">';

  // 1. 주요 경제 흐름
  htmlBody += '<div style="font-size: 14pt; font-weight: bold; color: #000; margin-top: 30px; margin-bottom: 12px;">1. 주요 경제 흐름</div>';
  htmlBody += '<p style="font-size: 10.5pt; color: #333; margin-top: 0; margin-bottom: 10px; line-height: 1.7; text-align: justify; word-break: break-all;">' + escapeHtml(insightReport.economic_trend || '').replace(/\n/g, '<br>') + '</p>';

  // 2. 업무 인사이트
  htmlBody += '<div style="font-size: 14pt; font-weight: bold; color: #000; margin-top: 30px; margin-bottom: 12px;">2. 업무 인사이트</div>';
  htmlBody += newsInsightsHtml;

  // 푸터 안내선 및 비고
  htmlBody += '<div style="font-size: 9pt; color: #6b7280; text-align: left; margin-top: 40px; border-top: 1px solid #e5e7eb; padding-top: 10px;">';
  htmlBody += '본 리포트는 서울신용보증재단의 정책 결정 및 업무 지원을 위해 AI를 통해 분석된 결과입니다.';
  htmlBody += '</div>';
  
  htmlBody += '</div>'; // card end
  
  // 이메일 외곽 하단부
  htmlBody += '<div style="max-width: 700px; margin: 20px auto 0 auto; text-align: center; font-size: 11px; color: #94a3b8; line-height: 1.5;">';
  htmlBody += '<p style="margin: 0;">* 본 메일에는 <strong>PDF 파일</strong>이 첨부되어 있습니다. 인쇄 또는 보관을 원하시면 첨부파일을 다운로드해 주세요.</p>';
  htmlBody += '<p style="margin: 4px 0 0 0;">수신 이메일: <strong>' + escapeHtml(email) + '</strong> | 발송처: 서울신용보증재단 AI 뉴스 센터</p>';
  htmlBody += '</div>';
  
  htmlBody += '</div>'; // wrapper end

  // 3. 메일 발송
  MailApp.sendEmail({
    to: email,
    subject: `📰 [AI News Briefing] ${date} 데일리 인사이트 보고서`,
    htmlBody: htmlBody,
    attachments: [pdfBlob]
  });
}

function generateWeeklyInsightReportPdf(dateRange, insightReport) {
  if (!insightReport) return null;

  const displayDateRange = dateRange.replace(/-/g, '.');

  let html = '<!DOCTYPE html><html><head><meta charset="utf-8">';
  html += '<link href="https://fonts.googleapis.com/css2?family=Nanum+Gothic:wght@400;700&display=swap" rel="stylesheet">';
  html += '<style>';
  html += '@page { size: A4; margin: 20mm; }';
  html += 'body { font-family: "Nanum Gothic", sans-serif; color: #1a1a1a; line-height: 1.7; padding: 0; margin: 0; }';
  html += '.header-table { width: 100%; border-collapse: collapse; margin-bottom: 15px; }';
  html += '.header-title { font-size: 20pt; font-weight: bold; color: #000; }';
  html += '.header-date { text-align: right; color: #666; font-size: 10pt; padding-bottom: 5px; }';
  html += 'hr { border: 0; border-top: 1px solid #000; margin: 0 0 20px 0; }';
  html += '.section-header { font-size: 14pt; font-weight: bold; color: #000; margin-top: 30px; margin-bottom: 12px; }';
  html += '.news-title { font-size: 12pt; font-weight: bold; color: #000; margin-top: 25px; margin-bottom: 10px; }';
  html += 'p { font-size: 10.5pt; color: #333; margin-top: 0; margin-bottom: 10px; line-height: 1.7; text-align: justify; word-break: break-all; }';
  html += '.footer-note { font-size: 9pt; color: #6b7280; text-align: left; margin-top: 40px; border-top: 1px solid #e5e7eb; padding-top: 10px; }';
  html += '</style></head><body>';

  // 1. 헤더 (같은 줄에 배치)
  html += '<table class="header-table"><tr>';
  html += '<td class="header-title">소기업·소상공인 주간 인사이트 리포트</td>';
  html += '<td class="header-date" valign="bottom">' + escapeHtml(displayDateRange) + '</td>';
  html += '</tr></table>';
  html += '<hr>';

  // 2. 주요 경제 흐름
  html += '<div class="section-header">1. 주요 경제 흐름</div>';
  html += '<p>' + escapeHtml(insightReport.economic_trend || '').replace(/\\n/g, '<br>') + '</p>';

  // 3. 인사이트
  html += '<div class="section-header">2. 인사이트</div>';
  if (insightReport.news_insights && Array.isArray(insightReport.news_insights)) {
    insightReport.news_insights.forEach(function(item) {
      var publisherDate = (item.publisher || item.date) ? ' <span style="font-size:10pt; color:#666; font-weight:normal;">(' + escapeHtml(item.publisher || '') + (item.publisher && item.date ? ', ' : '') + escapeHtml(item.date || '') + ')</span>' : '';
      html += '<div class="news-title"><b>' + escapeHtml(item.title) + '</b>' + publisherDate + '</div>';
      html += '<p><b>주요내용:</b> ' + formatParagraphs(item.summary || '') + '</p>';
      
      html += '<p style="margin-bottom: 25px;"><b>인사이트:</b> ' + formatParagraphs(item.implication || '') + '</p>';
    });
  }

  html += '<div class="footer-note">본 리포트는 서울시 소기업 및 소상공인의 사업운영을 지원하기 위해 AI를 통해 분석된 주간 경제 보고서입니다.</div>';
  html += '</body></html>';

  const htmlOutput = HtmlService.createHtmlOutput(html);
  return htmlOutput.getAs('application/pdf').setName('소상공인_주간_인사이트_리포트_' + dateRange.replace(/\\s/g, '') + '.pdf');
}

function sendWeeklyReportEmail(email, dateRange, insightReport) {
  if (!email) return;

  if (!insightReport) {
    Logger.log("주간 인사이트 리포트 데이터가 없어서 이메일을 발송하지 않습니다. Email: " + email);
    return;
  }

  const pdfBlob = generateWeeklyInsightReportPdf(dateRange, insightReport);
  if (!pdfBlob) {
    Logger.log("주간 PDF 생성 실패. Email: " + email);
    return;
  }

  const displayDateRange = dateRange.replace(/-/g, '.');

  let newsInsightsHtml = "";
  if (insightReport.news_insights && Array.isArray(insightReport.news_insights)) {
    insightReport.news_insights.forEach(function(item) {
      var publisherDate = (item.publisher || item.date) ? ' <span style="font-size:10pt; color:#666; font-weight:normal;">(' + escapeHtml(item.publisher || '') + (item.publisher && item.date ? ', ' : '') + escapeHtml(item.date || '') + ')</span>' : '';
      newsInsightsHtml += '<div style="font-size: 12pt; font-weight: bold; color: #000; margin-top: 25px; margin-bottom: 10px;"><b>' + escapeHtml(item.title) + '</b>' + publisherDate + '</div>';
      newsInsightsHtml += '<p style="font-size: 10.5pt; color: #333; margin-top: 0; margin-bottom: 10px; line-height: 1.7; text-align: justify; word-break: break-all;"><b>주요내용:</b> ' + formatParagraphs(item.summary || '') + '</p>';
      
      // references 배열 존재 여부에 따라 하단 마진 조절
      var hasRefs = (item.references && item.references.length > 0) || (item.reference && String(item.reference).trim() !== '');
      newsInsightsHtml += '<p style="font-size: 10.5pt; color: #333; margin-top: 0; margin-bottom: ' + (hasRefs ? '15px' : '25px') + '; line-height: 1.7; text-align: justify; word-break: break-all;"><b>인사이트:</b> ' + formatParagraphs(item.implication || '') + '</p>';
      
      // 신규 배열 형식 (references)
      // 신규 배열 형식 (references)
      if (item.references && Array.isArray(item.references) && item.references.length > 0) {
        item.references.forEach(function(ref, idx) {
          var isLast = (idx === item.references.length - 1);
          var mb = isLast ? '25px' : '5px';
          var refName = typeof ref === 'string' ? ref : (ref.name || '');
          var refUrl = typeof ref === 'string' ? '' : (ref.url || '');
          // URL 유효성 검증: http(s)로 시작하는 경우만 실제 링크로 사용
          var isValidUrl = refUrl && /^https?:\/\//i.test(String(refUrl).trim());
          if (isValidUrl) {
            var safeUrl = String(refUrl).trim().replace(/&/g, '&amp;').replace(/"/g, '&quot;');
            newsInsightsHtml += '<p style="font-size: 10.5pt; margin-top: 0; margin-bottom: ' + mb + '; line-height: 1.7;"><a href="' + safeUrl + '" target="_blank" style="text-decoration: underline; color: #2563eb;">[참고 출처: ' + escapeHtml(refName) + ']</a></p>';
          } else {
            var q = encodeURIComponent(String(refName).replace(/"/g, ''));
            newsInsightsHtml += '<p style="font-size: 10.5pt; margin-top: 0; margin-bottom: ' + mb + '; line-height: 1.7;"><a href="https://www.google.com/search?q=' + q + '" target="_blank" style="text-decoration: underline; color: #2563eb;">[참고 출처: ' + escapeHtml(refName) + ']</a></p>';
          }
        });
      }
      // 기존 단일 문자열 형식 (하위 호환)
      else if (item.reference && String(item.reference).trim() !== '') {
        var legacyUrl = item.reference_url || '';
        var isValidLegacyUrl = legacyUrl && /^https?:\/\//i.test(String(legacyUrl).trim());
        if (isValidLegacyUrl) {
          var safeRefUrl = String(legacyUrl).trim().replace(/&/g, '&amp;').replace(/"/g, '&quot;');
          newsInsightsHtml += '<p style="font-size: 10.5pt; margin-top: 0; margin-bottom: 25px; line-height: 1.7;"><a href="' + safeRefUrl + '" target="_blank" style="text-decoration: underline; color: #2563eb;">[참고 출처: ' + escapeHtml(item.reference) + ']</a></p>';
        } else {
          var q = encodeURIComponent(String(item.reference).replace(/"/g, ''));
          newsInsightsHtml += '<p style="font-size: 10.5pt; margin-top: 0; margin-bottom: 25px; line-height: 1.7;"><a href="https://www.google.com/search?q=' + q + '" target="_blank" style="text-decoration: underline; color: #2563eb;">[참고 출처: ' + escapeHtml(item.reference) + ']</a></p>';
        }
      }
    });
  }

  let htmlBody = '<div style="font-family: \\\'Nanum Gothic\\\', \\\'Malgun Gothic\\\', \\\'Apple SD Gothic Neo\\\', sans-serif; background-color: #f8fafc; padding: 40px 20px; color: #1a1a1a;">';
  htmlBody += '<div style="max-width: 700px; margin: 0 auto; background-color: #ffffff; border: 1px solid #e2e8f0; padding: 40px; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1); border-radius: 8px;">';
  
  // 헤더
  htmlBody += '<table width="100%" style="border-collapse: collapse; margin-bottom: 15px;"><tr>';
  htmlBody += '<td align="left" style="font-size: 20pt; font-weight: bold; color: #000;">소기업·소상공인 주간 인사이트 리포트</td>';
  htmlBody += '<td align="right" valign="bottom" style="color: #666; font-size: 10pt; padding-bottom: 5px;">' + escapeHtml(displayDateRange) + '</td>';
  htmlBody += '</tr></table>';
  htmlBody += '<hr style="border: 0; border-top: 1px solid #000; margin: 0 0 20px 0;">';

  // 1. 주요 경제 흐름
  htmlBody += '<div style="font-size: 14pt; font-weight: bold; color: #000; margin-top: 30px; margin-bottom: 12px;">1. 주요 경제 흐름</div>';
  htmlBody += '<p style="font-size: 10.5pt; color: #333; margin-top: 0; margin-bottom: 10px; line-height: 1.7; text-align: justify; word-break: break-all;">' + escapeHtml(insightReport.economic_trend || '').replace(/\\n/g, '<br>') + '</p>';

  // 2. 인사이트
  htmlBody += '<div style="font-size: 14pt; font-weight: bold; color: #000; margin-top: 30px; margin-bottom: 12px;">2. 인사이트</div>';
  htmlBody += newsInsightsHtml;

  // 푸터 안내선 및 비고
  htmlBody += '<div style="font-size: 9pt; color: #6b7280; text-align: left; margin-top: 40px; border-top: 1px solid #e5e7eb; padding-top: 10px;">';
  htmlBody += '본 리포트는 서울시 소기업 및 소상공인의 사업운영을 지원하기 위해 AI를 통해 분석된 주간 경제 보고서입니다.';
  htmlBody += '</div>';
  
  htmlBody += '</div>'; // card end
  
  // 이메일 외곽 하단부
  htmlBody += '<div style="max-width: 700px; margin: 20px auto 0 auto; text-align: center; font-size: 11px; color: #94a3b8; line-height: 1.5;">';
  htmlBody += '<p style="margin: 0;">* 본 메일에는 <strong>PDF 파일</strong>이 첨부되어 있습니다. 인쇄 또는 보관을 원하시면 첨부파일을 다운로드해 주세요.</p>';
  htmlBody += '<p style="margin: 4px 0 0 0;">수신 이메일: <strong>' + escapeHtml(email) + '</strong> | 발송처: 서울신용보증재단 AI 뉴스 센터</p>';
  htmlBody += '</div>';
  
  htmlBody += '</div>'; // wrapper end

  MailApp.sendEmail({
    to: email,
    subject: `📰 [AI News Briefing] 주간 소기업·소상공인 인사이트 보고서 (${displayDateRange})`,
    htmlBody: htmlBody,
    attachments: [pdfBlob]
  });
}
