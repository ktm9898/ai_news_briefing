/**
 * Google Apps Script for AI News Briefing (v4 - 이메일 기반 다중 사용자 구분 및 일일 리포트 자동 발송)
 * 
 * Features:
 * - doGet: 이메일(email) 필터링이 추가된 데이터 조회
 * - doPost: 이메일별 키워드 및 AI 기준 CRUD 및 HTML 이메일 자동 발송 액션 추가
 */

function doGet(e) {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const tab = e.parameter.tab || 'News_Data';
  const dateStr = e.parameter.date; // YYYY-MM-DD
  const topic = e.parameter.topic; // 주제 필터
  const action = e.parameter.action;
  const email = e.parameter.email; // 사용자 식별 이메일

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
      if (val instanceof Date || (val && Object.prototype.toString.call(val) === '[object Date]')) {
        val = Utilities.formatDate(val, "GMT+9", "yyyy-MM-dd");
      }
      obj[h] = val;
    });
    return obj;
  });

  // ── 이메일 필터링 적용 (headers에 이메일이 존재하는 탭의 경우) ──
  const emailIdx = headers.indexOf('이메일') !== -1 ? headers.indexOf('이메일') : headers.indexOf('Email');
  if (email && emailIdx !== -1) {
    const targetEmail = String(email).trim().toLowerCase();
    result = result.filter(item => {
      const itemEmail = String(item['이메일'] || item['Email'] || '').trim().toLowerCase();
      // 레거시 데이터 호환: 이메일이 지정되지 않은 데이터는 모두 접근 가능하도록 허용
      return itemEmail === '' || itemEmail === targetEmail;
    });
  }

  // News_Data 탭의 경우 날짜 및 주제 필터 적용
  if (tab === 'News_Data') {
    if (dateStr) {
      result = result.filter(item => {
        let itemDate = item['날짜'];
        if (itemDate instanceof Date || (itemDate && Object.prototype.toString.call(itemDate) === '[object Date]')) {
          itemDate = Utilities.formatDate(itemDate, "GMT+9", "yyyy-MM-dd");
        } else if (itemDate) {
          itemDate = String(itemDate).trim();
          const dObj = new Date(itemDate);
          if (!isNaN(dObj.getTime())) {
             itemDate = Utilities.formatDate(dObj, "GMT+9", "yyyy-MM-dd");
          } else {
            const match = String(itemDate).match(/(\d{4})[\.\-\/\s]+(\d{1,2})[\.\-\/\s]+(\d{1,2})/);
            if (match) {
              itemDate = match[1] + '-' + ('0' + match[2]).slice(-2) + '-' + ('0' + match[3]).slice(-2);
            }
          }
        }
        return itemDate === dateStr;
      });
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
  const email = params.email || '';

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

  // ── 일일 맞춤형 HTML 이메일 발송 ──
  if (action === 'sendDailyReport') {
    const targetEmail = params.email;
    const dateStr = params.date || Utilities.formatDate(new Date(), "GMT+9", "yyyy-MM-dd");
    const briefingScript = params.briefingScript || '';
    const insightReport = params.insightReport || null;
    const newsList = params.newsList || [];

    try {
      sendDailyReportEmail(targetEmail, dateStr, briefingScript, insightReport, newsList);
      return createResponse({ success: true });
    } catch (err) {
      return createResponse({ success: false, error: err.toString() });
    }
  }

  // 키워드 설정 (Settings 탭)
  if (action === 'addKeyword') {
    const sheet = getOrCreateTab(ss, 'Settings', ['이메일', '주제', '키워드', '활성화']);
    sheet.appendRow([email, params.topic, params.keyword, 'TRUE']);
    return createResponse({ success: true });
  }

  if (action === 'deleteKeyword') {
    const sheet = ss.getSheetByName('Settings');
    if (!sheet) return createResponse({ error: 'Settings tab not found' });
    const data = sheet.getDataRange().getValues();
    const headers = data[0];
    const emailIdx = headers.indexOf('이메일') !== -1 ? headers.indexOf('이메일') : headers.indexOf('Email');
    const topicIdx = headers.indexOf('주제') !== -1 ? headers.indexOf('주제') : headers.indexOf('카테고리');
    const keyIdx = headers.indexOf('키워드');
    
    const targetEmail = String(email).trim().toLowerCase();

    for (let i = 1; i < data.length; i++) {
      const rowEmail = emailIdx !== -1 ? String(data[i][emailIdx] || '').trim().toLowerCase() : '';
      const matchEmail = (emailIdx === -1) || (rowEmail === targetEmail) || (rowEmail === '');
      
      if (matchEmail && data[i][topicIdx] === params.topic && data[i][keyIdx] === params.keyword) {
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
    const emailIdx = headers.indexOf('이메일') !== -1 ? headers.indexOf('이메일') : headers.indexOf('Email');
    const topicIdx = headers.indexOf('주제') !== -1 ? headers.indexOf('주제') : headers.indexOf('카테고리');
    const keyIdx = headers.indexOf('키워드');
    const activeIdx = headers.indexOf('활성화');
    
    const targetEmail = String(email).trim().toLowerCase();

    for (let i = 1; i < data.length; i++) {
      const rowEmail = emailIdx !== -1 ? String(data[i][emailIdx] || '').trim().toLowerCase() : '';
      const matchEmail = (emailIdx === -1) || (rowEmail === targetEmail) || (rowEmail === '');

      if (matchEmail && data[i][topicIdx] === params.topic && data[i][keyIdx] === params.keyword) {
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
    const sheet = getOrCreateTab(ss, 'Topic_Settings', ['이메일', 'Topic', 'Criteria']);
    const data = sheet.getDataRange().getValues();
    const headers = data[0];
    const emailIdx = headers.indexOf('이메일') !== -1 ? headers.indexOf('이메일') : headers.indexOf('Email');
    const topicIdx = headers.indexOf('Topic') !== -1 ? headers.indexOf('Topic') : (headers.indexOf('주제') !== -1 ? headers.indexOf('주제') : 0);
    const criteriaIdx = headers.indexOf('Criteria') !== -1 ? headers.indexOf('Criteria') : (headers.indexOf('기준') !== -1 ? headers.indexOf('기준') : 1);
    
    const targetEmail = String(email).trim().toLowerCase();
    let found = false;

    for (let i = 1; i < data.length; i++) {
      const rowEmail = emailIdx !== -1 ? String(data[i][emailIdx] || '').trim().toLowerCase() : '';
      const matchEmail = (emailIdx === -1) || (rowEmail === targetEmail) || (rowEmail === '');
      const rowTopic = data[i][topicIdx];

      if (matchEmail && rowTopic === params.topic) {
        sheet.getRange(i + 1, criteriaIdx + 1).setValue(params.criteria);
        found = true;
        break;
      }
    }
    if (!found) {
      sheet.appendRow([email, params.topic, params.criteria]);
    }
    return createResponse({ success: true });
  }

  return createResponse({ error: 'Invalid action' });
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

function sendDailyReportEmail(email, date, briefingScript, insightReport, newsList) {
  if (!email) return;

  let insightReportHtml = "";
  if (insightReport) {
    insightReportHtml += '<div style="background-color: #ffffff; border-radius: 16px; padding: 24px; border: 1px solid #e2e8f0; box-shadow: 0 2px 4px rgba(0, 0, 0, 0.02); margin-bottom: 24px;">';
    insightReportHtml += '<h2 style="margin-top: 0; margin-bottom: 16px; font-size: 18px; font-weight: 700; color: #1e3a8a; border-bottom: 2px solid #eff6ff; padding-bottom: 8px;">📊 오늘의 경제 흐름 및 인사이트</h2>';
    
    if (insightReport.economic_trend) {
      insightReportHtml += '<div style="margin-bottom: 20px;">';
      insightReportHtml += '<h3 style="margin-top: 0; margin-bottom: 8px; font-size: 15px; font-weight: 700; color: #0f172a;">📈 거시 경제 동향 요약</h3>';
      insightReportHtml += '<p style="margin: 0; font-size: 14px; color: #334155; line-height: 1.6; background-color: #faf5ff; border: 1px solid #f3e8ff; border-radius: 8px; padding: 12px;">' + escapeHtml(insightReport.economic_trend) + '</p>';
      insightReportHtml += '</div>';
    }
    
    if (insightReport.news_insights && insightReport.news_insights.length > 0) {
      insightReportHtml += '<div>';
      insightReportHtml += '<h3 style="margin-top: 0; margin-bottom: 12px; font-size: 15px; font-weight: 700; color: #0f172a;">💡 서울신용보증재단 정책 연계 인사이트</h3>';
      insightReportHtml += '<div style="space-y: 12px;">';
      for (let i = 0; i < insightReport.news_insights.length; i++) {
        const ins = insightReport.news_insights[i];
        insightReportHtml += '<div style="border: 1px solid #f1f5f9; border-radius: 12px; padding: 16px; background-color: #f8fafc; margin-bottom: 12px;">';
        insightReportHtml += '<h4 style="margin-top: 0; margin-bottom: 8px; font-size: 14px; font-weight: 700; color: #1e40af;">' + escapeHtml(ins.title) + '</h4>';
        insightReportHtml += '<p style="margin: 0 0 8px 0; font-size: 13px; color: #475569;"><strong>주요내용:</strong> ' + escapeHtml(ins.summary) + '</p>';
        insightReportHtml += '<p style="margin: 0; font-size: 13px; color: #334155; line-height: 1.6; border-top: 1px dashed #e2e8f0; padding-top: 8px;"><strong>시사점 및 통찰:</strong> ' + escapeHtml(ins.implication) + '</p>';
        insightReportHtml += '</div>';
      }
      insightReportHtml += '</div>';
      insightReportHtml += '</div>';
    }
    insightReportHtml += '</div>';
  }

  let newsListHtml = "";
  if (newsList && newsList.length > 0) {
    newsListHtml += '<div style="space-y: 16px;">';
    for (let i = 0; i < newsList.length; i++) {
      const news = newsList[i];
      const badgeBg = news.중요도 === '상' ? '#ffe4e6' : (news.중요도 === '하' ? '#e0f2fe' : '#fef3c7');
      const badgeTextColor = news.중요도 === '상' ? '#991b1b' : (news.중요도 === '하' ? '#075985' : '#78350f');
      
      newsListHtml += '<div style="padding: 16px 0; border-bottom: 1px solid #f1f5f9;';
      if (i === newsList.length - 1) {
        newsListHtml += ' border-bottom: none;';
      }
      newsListHtml += '">';
      newsListHtml += '<div style="display: flex; gap: 8px; margin-bottom: 8px; align-items: center; flex-wrap: wrap;">';
      newsListHtml += '<span style="display: inline-block; font-size: 10px; font-weight: 700; padding: 2px 8px; border-radius: 4px; background-color: ' + badgeBg + '; color: ' + badgeTextColor + ';">중요도 ' + escapeHtml(news.중요도) + '</span>';
      newsListHtml += '<span style="display: inline-block; font-size: 10px; font-weight: 500; padding: 2px 8px; border-radius: 4px; background-color: #f1f5f9; color: #475569;">' + escapeHtml(news.주제) + '</span>';
      newsListHtml += '<span style="font-size: 11px; color: #94a3b8; margin-left: 8px;">' + escapeHtml(news.언론사) + '</span>';
      newsListHtml += '</div>';
      newsListHtml += '<h3 style="margin-top: 0; margin-bottom: 8px; font-size: 15px; font-weight: 700; color: #0f172a; line-height: 1.4;">';
      if (news.링크) {
        newsListHtml += '<a href="' + news.링크 + '" target="_blank" style="color: #3b82f6; text-decoration: none;">' + escapeHtml(news.제목) + '</a>';
      } else {
        newsListHtml += escapeHtml(news.제목);
      }
      newsListHtml += '</h3>';
      newsListHtml += '<p style="margin: 0; font-size: 13px; color: #475569; line-height: 1.6;">' + escapeHtml(news.AI요약 || news.AI_요약 || news.summary || "") + '</p>';
      newsListHtml += '</div>';
    }
    newsListHtml += '</div>';
  } else {
    newsListHtml = '<p style="margin: 0; font-size: 14px; color: #94a3b8; text-align: center;">오늘 수집된 분석 기사가 없습니다.</p>';
  }

  const htmlBody = `
<div style="font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; background-color: #f8fafc; color: #1e293b; line-height: 1.6;">
  <!-- Header -->
  <div style="background: linear-gradient(135deg, #1e3a8a 0%, #3b82f6 100%); padding: 30px 24px; border-radius: 16px; color: #ffffff; text-align: center; box-shadow: 0 4px 10px rgba(59, 130, 246, 0.15); margin-bottom: 24px;">
    <h1 style="margin: 0; font-size: 24px; font-weight: 800; letter-spacing: -0.5px;">📰 데일리 AI 뉴스 브리핑</h1>
    <p style="margin: 8px 0 0 0; font-size: 14px; opacity: 0.9; font-weight: 500;">${escapeHtml(date)}</p>
  </div>
  
  <!-- Briefing Script Card -->
  <div style="background-color: #ffffff; border-radius: 16px; padding: 24px; border: 1px solid #e2e8f0; box-shadow: 0 2px 4px rgba(0, 0, 0, 0.02); margin-bottom: 24px;">
    <h2 style="margin-top: 0; margin-bottom: 16px; font-size: 18px; font-weight: 700; color: #1e3a8a; border-bottom: 2px solid #eff6ff; padding-bottom: 8px;">🎙️ 오늘의 라디오 브리핑 대본</h2>
    <div style="background-color: #f8fafc; border-left: 4px solid #3b82f6; padding: 16px; border-radius: 8px; font-style: italic; color: #475569; font-size: 14px; white-space: pre-wrap; line-height: 1.7;">${escapeHtml(briefingScript)}</div>
  </div>

  <!-- Economic Trend & Insights -->
  ${insightReportHtml}

  <!-- Key News Cards -->
  <div style="background-color: #ffffff; border-radius: 16px; padding: 24px; border: 1px solid #e2e8f0; box-shadow: 0 2px 4px rgba(0, 0, 0, 0.02); margin-bottom: 24px;">
    <h2 style="margin-top: 0; margin-bottom: 16px; font-size: 18px; font-weight: 700; color: #1e3a8a; border-bottom: 2px solid #eff6ff; padding-bottom: 8px;">📌 선별된 주요 뉴스 요약</h2>
    ${newsListHtml}
  </div>

  <!-- Footer -->
  <div style="text-align: center; padding-top: 16px; border-top: 1px solid #e2e8f0; margin-top: 32px; font-size: 12px; color: #94a3b8;">
    <p style="margin: 0;">본 메일은 AI News Briefing 시스템에서 자동으로 발송한 맞춤형 보고서입니다.</p>
    <p style="margin: 4px 0 0 0;">수신 이메일: <strong>${escapeHtml(email)}</strong> | 발송처: 서울신용보증재단 AI 뉴스 센터</p>
  </div>
</div>
  `;

  MailApp.sendEmail({
    to: email,
    subject: `📰 [AI News Briefing] ${date} 데일리 맞춤 보고서`,
    htmlBody: htmlBody
  });
}
