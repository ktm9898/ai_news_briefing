/**
 * Google Apps Script for AI News Briefing (v3 - 주제별 설정 지원)
 * 
 * Features:
 * - doGet: 주제(Topic) 필터 및 날짜(Date) 필터 지원 데이터 조회
 * - doPost: 주제별 키워드 및 AI 판단 기준(Criteria) CRUD
 */

function doGet(e) {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const tab = e.parameter.tab || 'News_Data';
  const dateStr = e.parameter.date; // YYYY-MM-DD
  const topic = e.parameter.topic; // 주제 필터
  const action = e.parameter.action;

  // ── 수동 수집 트리거 (GitHub Actions) ──
  if (action === 'triggerWorkflow') {
    // PropertiesService에서 GitHub PAT 가져오기
    const GITHUB_PAT = PropertiesService.getScriptProperties().getProperty('GITHUB_PAT');
    if (!GITHUB_PAT) {
      return createResponse({ error: 'GITHUB_PAT가 스크립트 속성에 설정되지 않았습니다.', ok: false });
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
  if (!sheet) return createResponse({ error: 'Tab not found' });

  const data = sheet.getDataRange().getValues();
  if (data.length <= 1) return createResponse([]);

  const headers = data[0];
  let rows = data.slice(1);

  // 빈 행 제거
  rows = rows.filter(row => row[0]);

  let result = rows.map(row => {
    let obj = {};
    headers.forEach((h, i) => {
      let val = row[i];
      if (val instanceof Date) {
        val = Utilities.formatDate(val, "GMT+9", "yyyy-MM-dd");
      }
      obj[h] = val;
    });
    return obj;
  });

  // News_Data 탭의 경우 날짜 및 주제 필터 적용
  if (tab === 'News_Data') {
    if (dateStr) {
      result = result.filter(item => item['날짜'] === dateStr);
    }
    if (topic && topic !== '전체') {
      result = result.filter(item => item['주제'] === topic);
    }
    // 너무 많은 데이터 방지를 위해 최신 100건으로 제한 (필터 후)
    if (!dateStr && !topic) {
      result = result.slice(-100);
    }
  }

  return createResponse(result);
}

function doPost(e) {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const params = JSON.parse(e.postData.contents);
  const action = params.action;

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

  // 주제별 AI 기준 설정 (Topic_Settings 탭)
  if (action === 'updateTopicCriteria') {
    const sheet = getOrCreateTab(ss, 'Topic_Settings', ['Topic', 'Criteria']);
    const data = sheet.getDataRange().getValues();
    let found = false;
    for (let i = 1; i < data.length; i++) {
      const dbTopic = data[i][0] || data[i][headers.indexOf('주제')];
      if (dbTopic === params.topic) {
        sheet.getRange(i + 1, 2).setValue(params.criteria);
        found = true;
        break;
      }
    }
    if (!found) {
      sheet.appendRow([params.topic, params.criteria]);
    }
    return createResponse({ success: true });
  }

  // 레거시 action (수동 수집) fallback (GET 통신 방식 실패 시)
  if (action === 'triggerWorkflow') {
    const GITHUB_PAT = PropertiesService.getScriptProperties().getProperty('GITHUB_PAT');
    if (!GITHUB_PAT) return createResponse({ error: 'GITHUB_PAT 미설정', ok: false });
    const url = 'https://api.github.com/repos/ktm9898/ai_news_briefing/actions/workflows/collect.yml/dispatches';
    try {
      UrlFetchApp.fetch(url, {
        method: 'post',
        headers: { 'Accept': 'application/vnd.github.v3+json', 'Authorization': 'Bearer ' + GITHUB_PAT },
        payload: JSON.stringify({ ref: 'master' })
      });
      return createResponse({ ok: true, success: true });
    } catch (err) {
        return createResponse({ error: err.toString(), ok: false });
    }
  }

  return createResponse({ error: 'Invalid action' });
}


function getOrCreateTab(ss, name, headers) {
  let sheet = ss.getSheetByName(name);
  if (!sheet) {
    sheet = ss.insertSheet(name);
    sheet.appendRow(headers);
  }
  return sheet;
}

function createResponse(data) {
  return ContentService.createTextOutput(JSON.stringify(data))
    .setMimeType(ContentService.MimeType.JSON);
}
