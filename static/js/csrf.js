/**
 * csrf.js — 전역 CSRF 보호
 * 모든 페이지의 <head>에 포함하면 fetch() 호출 시 자동으로 X-CSRF-Token 헤더를 추가합니다.
 *
 * window.csrfReady — CSRF 토큰 준비 완료 시 resolve되는 Promise
 * 다른 스크립트에서 await window.csrfReady 후 POST 요청 사용 권장
 */
(function () {
  let _csrfToken = '';
  let _resolveReady;

  // 외부에서 await 가능한 준비 완료 Promise
  window.csrfReady = new Promise(function (resolve) {
    _resolveReady = resolve;
  });

  // 원본 fetch 보존 (initCsrf 내부에서 사용)
  window._origFetch = window.fetch.bind(window);

  // 페이지 로드 시 서버에서 CSRF 토큰 획득
  async function initCsrf() {
    try {
      const res = await window._origFetch('/api/csrf-token');
      if (res.ok) {
        const data = await res.json();
        _csrfToken = data.csrf_token || '';
      }
    } catch (e) { /* 무시 */ }
    _resolveReady(); // 성공/실패 무관하게 준비 완료 신호
  }

  // fetch 인터셉터: POST/PUT/DELETE/PATCH 요청에 X-CSRF-Token 자동 추가
  window.fetch = function (url, options) {
    options = options || {};
    const method = (options.method || 'GET').toUpperC