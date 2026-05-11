/**
 * csrf.js — 전역 CSRF 보호
 * 모든 페이지의 <head>에 포함하면 fetch() 호출 시 자동으로 X-CSRF-Token 헤더를 추가합니다.
 */
(function () {
  let _csrfToken = '';

  // 페이지 로드 시 서버에서 CSRF 토큰 획득
  async function initCsrf() {
    try {
      const res = await window._origFetch('/api/csrf-token');
      if (res.ok) {
        const data = await res.json();
        _csrfToken = data.csrf_token || '';
      }
    } catch (e) { /* 무시 */ }
  }

  // 원본 fetch 보존
  window._origFetch = window.fetch.bind(window);

  // fetch 인터셉터: POST/PUT/DELETE/PATCH 요청에 X-CSRF-Token 자동 추가
  window.fetch = function (url, options) {
    options = options || {};
    const method = (options.method || 'GET').toUpperCase();

    if (['POST', 'PUT', 'DELETE', 'PATCH'].includes(method) && _csrfToken) {
      options.headers = Object.assign({}, options.headers || {}, {
        'X-CSRF-Token': _csrfToken
      });
    }
    return window._origFetch(url, options);
  };

  // DOM 준비 후 토큰 초기화
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initCsrf);
  } else {
    initCsrf();
  }
})();
