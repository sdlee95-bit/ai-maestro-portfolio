/**
 * 자체직원(비정규직) 현황 조사 — 취합 웹앱
 * 2026 국립대학 비정규직 채용 현황 실태조사 사전 연습용
 *
 * 하는 일
 *   1) 부서 담당자가 웹에서 입력  → 구글 시트에 1명=1행으로 쌓인다
 *   2) 제출되면 취합 담당자에게 메일이 간다
 *   3) 어느 부서가 냈고 안 냈는지 현황판에서 바로 보인다
 *
 * 엑셀 서식을 돌릴 때와 다른 점
 *   · 연봉액을 사람이 계산하지 않는다 — ((A+B)*12)+C+D+E+F 를 서버가 계산한다
 *   · 담당자 정보(부서·성명·연락처)를 사람마다 반복 입력하지 않는다 — 제출 1회당 1번
 *   · 무기계약직인데 계약종료일을 적는 실수를 입력 단계에서 막는다
 *   · 서식 파일을 모으고 열고 붙여넣는 일이 없다
 *
 * 서식을 바꾸려면 FIELDS 배열만 고치면 된다.
 * 입력 화면·시트 머리글·현황판이 전부 이 배열을 따라간다.
 */

// ─────────────────────────────────────────────────────────────
// 설정 — 여기만 고치면 된다
// ─────────────────────────────────────────────────────────────

var CONFIG = {
  TITLE: '2026년 자체직원(비정규직) 현황 조사',
  BASE_DATE: '2026. 7. 1. 자 기준',

  // 취합 담당자 — 제출 알림을 받을 주소. 쉼표로 여러 명
  ADMIN_EMAIL: 'CHANGE_ME@example.com',

  // 제출 대상 부서. 현황판의 '안 낸 곳'이 이 목록에서 나온다
  DEPTS: [
    '교무과', '학사과', '학생과', '입학과', '총무과', '재무과',
    '시설과', '연구진흥과', '취업전략과', '국제협력실',
    '기획평가과', '정보화기획운영과', '산학협력단'
  ],

  SHEET_DATA: '접수',       // 1명 = 1행
  SHEET_LOG: '제출이력'      // 제출 1회 = 1행
};

// 실태조사 직종분류 26개 — (참고) 직종표 그대로
var JOB_TYPES = [
  '사무(보조)원', '전산(보조)원', '연구(보조)원', '고객관련 업무 종사자',
  '(전화)상담원', '우편업무 종사자', '통계 조사원', '의료업무 종사자',
  '사서 및 기록물정리원', '영양사, 조리사, 조리(보조)원', '경비원', '청원경찰',
  '운전원', '주차관리원', '시설물 관리원', '시설물(건물) 청소원',
  '환경(도로, 공원 등) 미화원', '도로 보수원', '산림보호 업무 종사자',
  '기간제 교원', '운동선수, 체육지도자 업무종사자', '영어회화전문강사',
  '학교강사(초중등)', '(전업)시간강사(대학)', '시간제 경마직', '기타'
];

var FUND_SOURCES = [
  '대학회계(일반재원)', '대학회계(수입대체경비)', '정부재정지원사업',
  '기타 보조금 및 지원금', '발전기금', '기타'
];

/**
 * 직원 1명당 입력 항목.
 * key   : 시트 열 이름이자 내부 이름
 * type  : text | number | date | select
 * calc  : 서버가 계산하는 열(사람이 입력하지 않는다)
 */
var FIELDS = [
  { key: '소속',               type: 'select', options: 'DEPTS', required: true },
  { key: '교직원번호',          type: 'text',   required: true },
  { key: '성명',               type: 'text',   required: true, pii: true },
  { key: '생년월일',            type: 'date',   required: true, pii: true },
  { key: '기관사용 직종명',      type: 'text',   required: true, hint: '기관에서 쓰는 이름 그대로 (예: 사무원, 전임연구원)' },
  { key: '실태조사 직종분류',    type: 'select', options: 'JOB_TYPES', required: true },
  { key: '전일제/단시간',       type: 'select', options: ['전일제', '단시간'], required: true },
  { key: '기간제/무기계약직',    type: 'select', options: ['기간제', '무기계약직'], required: true },
  { key: '계약시작일',          type: 'date',   required: true },
  { key: '계약종료일',          type: 'date',   hint: '무기계약직은 비워 둡니다' },
  { key: '인건비 재원',         type: 'select', options: 'FUND_SOURCES', required: true },
  { key: '사업명 및 지원기관명', type: 'text' },
  { key: '(A) 월급여(세전)',    type: 'number', required: true, unit: '원' },
  { key: '(B) 정액급식비',      type: 'number', unit: '원', hint: '월급여에 포함돼 있으면 0' },
  { key: '(C) 연간 성과상여금',  type: 'number', unit: '원' },
  { key: '(D) 연간 복지포인트',  type: 'number', unit: '원' },
  { key: '(E) 연간 명절상여금',  type: 'number', unit: '원' },
  { key: '(F) 연간 기타수당',    type: 'number', unit: '원', hint: '기말수당·초과근무수당 등' },
  { key: '연봉액',              type: 'number', calc: true, unit: '원',
    hint: '((A+B)×12)+C+D+E+F — 자동 계산' },
  { key: '비고',                type: 'text' }
];

// 제출 1회당 한 번만 받는 것 (엑셀에서는 행마다 반복 입력했다)
var SUBMITTER_FIELDS = [
  { key: '담당자 부서', type: 'text', required: true },
  { key: '담당자 성명', type: 'text', required: true },
  { key: '담당자 연락처', type: 'text', required: true, hint: '예: 051-510-0000' }
];

// ─────────────────────────────────────────────────────────────
// 최초 1회 실행 — 시트를 만든다
// ─────────────────────────────────────────────────────────────

/** 편집기에서 setup 을 한 번 실행하면 스프레드시트가 만들어진다. */
function setup() {
  var props = PropertiesService.getScriptProperties();
  var id = props.getProperty('SS_ID');
  var ss;

  if (id) {
    ss = SpreadsheetApp.openById(id);
  } else {
    ss = SpreadsheetApp.create(CONFIG.TITLE + ' (' + CONFIG.BASE_DATE + ')');
    props.setProperty('SS_ID', ss.getId());
  }

  // 접수 시트 — 1명 = 1행
  var head = ['접수번호', '제출일시']
    .concat(FIELDS.map(function (f) { return f.key; }))
    .concat(SUBMITTER_FIELDS.map(function (f) { return f.key; }));
  var sh = ss.getSheetByName(CONFIG.SHEET_DATA) || ss.insertSheet(CONFIG.SHEET_DATA);
  sh.clear();
  sh.getRange(1, 1, 1, head.length).setValues([head])
    .setFontWeight('bold').setBackground('#1C4FA1').setFontColor('#FFFFFF');
  sh.setFrozenRows(1);
  applyFormats_(sh, 2, 1000);   // 미리 깔아 둔다. 손으로 적어 넣어도 모양이 맞게

  // 제출이력 시트 — 제출 1회 = 1행
  var logHead = ['제출일시', '소속', '담당자 성명', '담당자 연락처', '건수'];
  var lg = ss.getSheetByName(CONFIG.SHEET_LOG) || ss.insertSheet(CONFIG.SHEET_LOG);
  lg.clear();
  lg.getRange(1, 1, 1, logHead.length).setValues([logHead])
    .setFontWeight('bold').setBackground('#2DA7E0').setFontColor('#FFFFFF');
  lg.setFrozenRows(1);

  var d = ss.getSheetByName('시트1');
  if (d) ss.deleteSheet(d);

  Logger.log('스프레드시트 준비 완료: ' + ss.getUrl());
  return ss.getUrl();
}

/**
 * 보이는 모양을 맞춘다.
 *  · 제출일시 : 날짜만 보이면 '누가 언제 냈는지'를 못 가린다. 시각까지 보인다
 *  · 금액     : 천 단위 쉼표. 쉼표가 없으면 0 이 하나 더 붙었는지 눈으로 못 잡는다
 * 값이 아니라 표시 서식만 바꾼다. 계산에는 영향이 없다.
 */
function applyFormats_(sh, row, n) {
  sh.getRange(row, 2, n, 1).setNumberFormat('yyyy-mm-dd hh:mm');
  FIELDS.forEach(function (f, i) {
    if (f.type === 'number') {
      sh.getRange(row, 3 + i, n, 1).setNumberFormat('#,##0');   // 1,2 열은 접수번호·제출일시
    }
  });
}

function getSS_() {
  var id = PropertiesService.getScriptProperties().getProperty('SS_ID');
  if (!id) throw new Error('먼저 setup() 을 한 번 실행해 주십시오.');
  return SpreadsheetApp.openById(id);
}

// ─────────────────────────────────────────────────────────────
// 화면
// ─────────────────────────────────────────────────────────────

function doGet(e) {
  var page = (e && e.parameter && e.parameter.page) || 'form';
  var file = (page === 'status') ? 'Status' : 'Index';
  return HtmlService.createTemplateFromFile(file).evaluate()
    .setTitle(CONFIG.TITLE)
    .addMetaTag('viewport', 'width=device-width, initial-scale=1');
}

function include(name) {
  return HtmlService.createHtmlOutputFromFile(name).getContent();
}

/** 입력 화면이 쓸 설정값 */
function getFormConfig() {
  var opt = { DEPTS: CONFIG.DEPTS, JOB_TYPES: JOB_TYPES, FUND_SOURCES: FUND_SOURCES };
  var fields = FIELDS.map(function (f) {
    var c = JSON.parse(JSON.stringify(f));
    if (typeof c.options === 'string') c.options = opt[c.options];
    return c;
  });
  return {
    title: CONFIG.TITLE,
    baseDate: CONFIG.BASE_DATE,
    fields: fields,
    submitter: SUBMITTER_FIELDS,
    depts: CONFIG.DEPTS
  };
}

// ─────────────────────────────────────────────────────────────
// 제출
// ─────────────────────────────────────────────────────────────

/** 연봉액 = ((A+B)×12)+C+D+E+F */
function calcAnnual_(r) {
  var n = function (k) { return Number(r[k] || 0); };
  return (n('(A) 월급여(세전)') + n('(B) 정액급식비')) * 12
    + n('(C) 연간 성과상여금') + n('(D) 연간 복지포인트')
    + n('(E) 연간 명절상여금') + n('(F) 연간 기타수당');
}

/** 서버 쪽 검증 — 화면을 우회해 들어와도 막는다 */
function validate_(rows, submitter) {
  var errs = [];

  SUBMITTER_FIELDS.forEach(function (f) {
    if (f.required && !String(submitter[f.key] || '').trim())
      errs.push('담당자 정보: ' + f.key + ' 을(를) 입력해 주십시오.');
  });

  if (!rows.length) errs.push('직원이 한 명도 입력되지 않았습니다.');

  rows.forEach(function (r, i) {
    var at = (i + 1) + '번째 직원';

    FIELDS.forEach(function (f) {
      if (f.calc) return;
      if (f.required && !String(r[f.key] || '').trim())
        errs.push(at + ': ' + f.key + ' 은(는) 필수입니다.');
      if (f.type === 'number' && r[f.key] !== '' && isNaN(Number(r[f.key])))
        errs.push(at + ': ' + f.key + ' 은(는) 숫자여야 합니다.');
    });

    // 서식의 규칙 — 무기계약직은 계약종료일이 없다
    if (r['기간제/무기계약직'] === '무기계약직' && String(r['계약종료일'] || '').trim())
      errs.push(at + ': 무기계약직은 계약종료일을 비워 두어야 합니다.');
    if (r['기간제/무기계약직'] === '기간제' && !String(r['계약종료일'] || '').trim())
      errs.push(at + ': 기간제는 계약종료일이 필요합니다.');

    var s = r['계약시작일'], e = r['계약종료일'];
    if (s && e && new Date(s) > new Date(e))
      errs.push(at + ': 계약종료일이 시작일보다 빠릅니다.');
  });

  return errs;
}

/**
 * 입력 화면에서 부른다.
 * @param {Object} payload {submitter:{}, rows:[{}]}
 */
function submitRecords(payload) {
  var lock = LockService.getScriptLock();
  lock.waitLock(30000);                       // 두 부서가 동시에 내도 행이 안 섞이게
  try {
    var submitter = payload.submitter || {};
    var rows = payload.rows || [];

    var errs = validate_(rows, submitter);
    if (errs.length) return { ok: false, errors: errs };

    var ss = getSS_();
    var sh = ss.getSheetByName(CONFIG.SHEET_DATA);
    var now = new Date();
    var start = sh.getLastRow();              // 머리글 포함

    var values = rows.map(function (r, i) {
      r['연봉액'] = calcAnnual_(r);
      return [start + i, now]
        .concat(FIELDS.map(function (f) {
          var v = r[f.key];
          // 금액은 빈칸으로 두지 않는다.
          // 서식이 「월급여액에 포함된 경우에는 0으로 작성」이라고 요구하고,
          // 빈칸과 0 은 제출 서식에 붙일 때 다른 뜻으로 읽힌다.
          if (f.type === 'number') return Number(v || 0);
          return (v === undefined || v === null) ? '' : v;
        }))
        .concat(SUBMITTER_FIELDS.map(function (f) { return submitter[f.key] || ''; }));
    });

    var at = sh.getLastRow() + 1;
    sh.getRange(at, 1, values.length, values[0].length).setValues(values);
    applyFormats_(sh, at, values.length);   // 미리 깔아 둔 1000행을 넘겨도 모양이 유지되게

    ss.getSheetByName(CONFIG.SHEET_LOG).appendRow([
      now,
      rows[0]['소속'] || submitter['담당자 부서'] || '',
      submitter['담당자 성명'] || '',
      submitter['담당자 연락처'] || '',
      rows.length
    ]);

    notify_(submitter, rows, ss.getUrl());
    return { ok: true, count: rows.length, total: sh.getLastRow() - 1 };
  } finally {
    lock.releaseLock();
  }
}

function notify_(submitter, rows, url) {
  if (!CONFIG.ADMIN_EMAIL || CONFIG.ADMIN_EMAIL.indexOf('CHANGE_ME') === 0) return;
  var dept = rows[0]['소속'] || submitter['담당자 부서'] || '(부서 미상)';
  var st = getStatus();
  var body =
    CONFIG.TITLE + ' — 제출이 접수되었습니다.\n\n' +
    '부서      : ' + dept + '\n' +
    '담당자    : ' + (submitter['담당자 성명'] || '') +
    ' (' + (submitter['담당자 연락처'] || '') + ')\n' +
    '제출 인원 : ' + rows.length + '명\n' +
    '제출 일시 : ' + Utilities.formatDate(new Date(), 'Asia/Seoul', 'yyyy-MM-dd HH:mm') + '\n\n' +
    '진행      : ' + st.submitted.length + ' / ' + st.depts.length + ' 부서\n' +
    '미제출    : ' + (st.pending.join(', ') || '없음') + '\n\n' +
    '시트: ' + url;
  MailApp.sendEmail({
    to: CONFIG.ADMIN_EMAIL,
    subject: '[' + CONFIG.TITLE + '] ' + dept + ' 제출 (' + rows.length + '명)',
    body: body
  });
}

// ─────────────────────────────────────────────────────────────
// 현황판 — 취합에서 가장 오래 걸리는 일은 '안 낸 곳 찾기'다
// ─────────────────────────────────────────────────────────────

function getStatus() {
  var ss = getSS_();
  var sh = ss.getSheetByName(CONFIG.SHEET_DATA);
  var last = sh.getLastRow();

  var byDept = {}, total = 0;
  if (last > 1) {
    var idx = FIELDS.map(function (f) { return f.key; }).indexOf('소속') + 3; // 접수번호,제출일시 다음
    var col = sh.getRange(2, idx, last - 1, 1).getValues();
    col.forEach(function (r) {
      var d = String(r[0] || '').trim();
      if (!d) return;
      byDept[d] = (byDept[d] || 0) + 1;
      total++;
    });
  }

  var submitted = CONFIG.DEPTS.filter(function (d) { return byDept[d]; });
  var pending = CONFIG.DEPTS.filter(function (d) { return !byDept[d]; });
  var etc = Object.keys(byDept).filter(function (d) {
    return CONFIG.DEPTS.indexOf(d) < 0;       // 목록에 없는 부서가 낸 경우
  });

  // 화면(iframe) 의 location 은 googleusercontent 주소라 쓸 수 없다.
  // 독촉 문구에 넣을 입력 화면 주소는 서버에서 가져와야 한다.
  var appUrl = '';
  try { appUrl = ScriptApp.getService().getUrl() || ''; } catch (e) {}

  return {
    title: CONFIG.TITLE, baseDate: CONFIG.BASE_DATE,
    depts: CONFIG.DEPTS, byDept: byDept,
    submitted: submitted, pending: pending, etc: etc,
    total: total, sheetUrl: ss.getUrl(), appUrl: appUrl,
    updated: Utilities.formatDate(new Date(), 'Asia/Seoul', 'yyyy-MM-dd HH:mm')
  };
}

/**
 * 이미 쌓인 행에 서식을 입히고 금액 빈칸을 0 으로 채운다.
 * setup 은 시트를 비우므로, 데이터가 있을 때는 이쪽을 쓴다.
 * 한 번만 돌리면 된다. 여러 번 돌려도 결과는 같다.
 */
function formatExisting() {
  var sh = getSS_().getSheetByName(CONFIG.SHEET_DATA);
  var last = sh.getLastRow();
  if (last < 2) { Logger.log('채울 데이터가 없습니다.'); return; }

  var n = last - 1;
  applyFormats_(sh, 2, Math.max(n, 1000));

  var filled = 0;
  FIELDS.forEach(function (f, i) {
    if (f.type !== 'number') return;
    var rg = sh.getRange(2, 3 + i, n, 1);
    var v = rg.getValues();
    var touched = false;
    for (var r = 0; r < v.length; r++) {
      if (v[r][0] === '' || v[r][0] === null) { v[r][0] = 0; touched = true; filled++; }
    }
    if (touched) rg.setValues(v);
  });

  Logger.log('서식 적용 완료 · 빈 금액칸 ' + filled + '개를 0 으로 채웠습니다.');
}

/** 미제출 부서 목록을 문자열로 — 독촉 메일에 붙여 쓴다 */
function getPendingText() {
  var st = getStatus();
  return st.pending.length
    ? '미제출 ' + st.pending.length + '개 부서: ' + st.pending.join(', ')
    : '전 부서 제출 완료';
}
