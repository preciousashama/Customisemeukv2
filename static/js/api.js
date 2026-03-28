
window.API_BASE_URL = window.API_BASE_URL || '';

/** Read a cookie by name (used to get csrftoken). */
function getCookie(name) {
  const value = `; ${document.cookie}`;
  const parts = value.split(`; ${name}=`);
  if (parts.length === 2) return parts.pop().split(';').shift();
  return null;
}


async function apiPost(endpoint, body = {}) {
  const resp = await fetch(`${window.API_BASE_URL}${endpoint}`, {
    method:  'POST',
    headers: {
      'Content-Type':     'application/json',
      'X-CSRFToken':      getCookie('csrftoken') || '',
      'X-Requested-With': 'XMLHttpRequest',
    },
    credentials: 'same-origin',   // send session cookie
    body: JSON.stringify(body),
  });
  return resp.json();
}

/**
 * GET a Django auth endpoint.
 * @param {string} endpoint
 * @returns {Promise<object>}
 */
async function apiGet(endpoint) {
  const resp = await fetch(`${window.API_BASE_URL}${endpoint}`, {
    method:  'GET',
    headers: { 'X-Requested-With': 'XMLHttpRequest' },
    credentials: 'same-origin',
  });
  return resp.json();
}

/** Navigate to a URL (used after successful auth actions). */
function goTo(url) {
  window.location.href = url;
}

window.API = { post: apiPost, get: apiGet, goTo };