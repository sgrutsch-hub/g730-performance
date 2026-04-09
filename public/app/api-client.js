/**
 * Swing Doctor API Client
 *
 * Standalone browser client for the Swing Doctor backend API.
 * No build tools, no imports — just drop a <script> tag and go.
 *
 * Usage:
 *   <script src="api-client.js"></script>
 *   await SwingDoctorAPI.login('user@example.com', 'password');
 *   const profiles = await SwingDoctorAPI.getProfiles();
 */

(function () {
  'use strict';

  // ── Configuration ──────────────────────────────────────────────

  const isLocalhost =
    location.hostname === 'localhost' ||
    location.hostname === '127.0.0.1' ||
    location.hostname === '[::1]';

  const API_BASE = isLocalhost
    ? 'http://localhost:8000/api/v1'
    : 'https://swing-doctor-api.fly.dev/api/v1';

  const TOKEN_KEY = 'sd_access_token';
  const REFRESH_KEY = 'sd_refresh_token';
  const EXPIRES_KEY = 'sd_token_expires_at';

  // ── Error class ────────────────────────────────────────────────

  class SwingDoctorAPIError extends Error {
    constructor(status, message, detail) {
      super(message);
      this.name = 'SwingDoctorAPIError';
      this.status = status;
      this.detail = detail || null;
    }
  }

  // ── Token helpers ──────────────────────────────────────────────

  function getAccessToken() {
    return localStorage.getItem(TOKEN_KEY);
  }

  function getRefreshToken() {
    return localStorage.getItem(REFRESH_KEY);
  }

  function storeTokens(data) {
    localStorage.setItem(TOKEN_KEY, data.access_token);
    localStorage.setItem(REFRESH_KEY, data.refresh_token);
    if (data.expires_in) {
      const expiresAt = Date.now() + data.expires_in * 1000;
      localStorage.setItem(EXPIRES_KEY, String(expiresAt));
    }
  }

  function clearTokens() {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(REFRESH_KEY);
    localStorage.removeItem(EXPIRES_KEY);
  }

  function isTokenExpired() {
    const expiresAt = localStorage.getItem(EXPIRES_KEY);
    if (!expiresAt) return true;
    // Consider expired 60s before actual expiry to avoid race conditions
    return Date.now() > Number(expiresAt) - 60000;
  }

  // ── Core fetch wrapper ─────────────────────────────────────────

  let _refreshPromise = null;

  async function refreshToken() {
    // Deduplicate concurrent refresh attempts
    if (_refreshPromise) return _refreshPromise;

    const rt = getRefreshToken();
    if (!rt) {
      clearTokens();
      throw new SwingDoctorAPIError(401, 'No refresh token available');
    }

    _refreshPromise = (async () => {
      try {
        const res = await fetch(API_BASE + '/auth/refresh', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ refresh_token: rt }),
        });
        if (!res.ok) {
          clearTokens();
          throw new SwingDoctorAPIError(res.status, 'Token refresh failed');
        }
        const data = await res.json();
        storeTokens(data);
        return data.access_token;
      } finally {
        _refreshPromise = null;
      }
    })();

    return _refreshPromise;
  }

  /**
   * Internal fetch wrapper with auth, retry-on-401, rate-limit, and
   * offline handling.
   *
   * @param {string} path    — URL path relative to API_BASE (e.g. '/profiles')
   * @param {object} options — fetch options (method, headers, body, etc.)
   * @param {boolean} _retried — internal flag to prevent infinite retry loops
   * @returns {Promise<any>}
   */
  async function apiFetch(path, options, _retried) {
    if (!navigator.onLine) {
      throw new SwingDoctorAPIError(0, 'You appear to be offline', 'network_offline');
    }

    const url = API_BASE + path;
    const headers = Object.assign({}, options.headers || {});

    // Attach auth header unless explicitly skipped
    if (!options._skipAuth) {
      const token = getAccessToken();
      if (token) {
        // Proactively refresh if we know the token is expired
        if (isTokenExpired() && !_retried) {
          try {
            const newToken = await refreshToken();
            headers['Authorization'] = 'Bearer ' + newToken;
          } catch (_) {
            // If proactive refresh fails, try the request anyway —
            // the 401 retry path will handle it.
            headers['Authorization'] = 'Bearer ' + token;
          }
        } else {
          headers['Authorization'] = 'Bearer ' + token;
        }
      }
    }

    let res;
    try {
      const fetchConfig = { method: options.method || 'GET', headers: headers };
      if (options.body) fetchConfig.body = options.body;
      if (fetchConfig.method === 'GET') fetchConfig.cache = 'no-store';
      res = await fetch(url, fetchConfig);
    } catch (err) {
      throw new SwingDoctorAPIError(0, 'Network request failed: ' + err.message, 'network_error');
    }

    // ── 401: try token refresh once ──
    if (res.status === 401 && !_retried && !options._skipAuth) {
      try {
        await refreshToken();
        return apiFetch(path, options, true);
      } catch (_) {
        clearTokens();
        throw new SwingDoctorAPIError(401, 'Authentication expired — please log in again');
      }
    }

    // ── 429: rate-limited ──
    if (res.status === 429) {
      const retryAfter = res.headers.get('Retry-After');
      const waitMs = retryAfter ? Number(retryAfter) * 1000 : 5000;
      if (!_retried) {
        await new Promise(function (r) { setTimeout(r, Math.min(waitMs, 30000)); });
        return apiFetch(path, options, true);
      }
      throw new SwingDoctorAPIError(429, 'Rate limited — try again later', 'rate_limited');
    }

    // ── 204: no content ──
    if (res.status === 204) return null;

    // ── Parse body ──
    let body;
    const ct = res.headers.get('Content-Type') || '';
    if (ct.includes('application/json')) {
      body = await res.json();
    } else {
      body = await res.text();
    }

    if (!res.ok) {
      const msg =
        (body && body.detail) ||
        (body && body.message) ||
        (typeof body === 'string' ? body : 'Request failed');
      throw new SwingDoctorAPIError(res.status, msg, body && body.detail);
    }

    return body;
  }

  // ── Query-string builder ───────────────────────────────────────

  function qs(params) {
    if (!params) return '';
    const parts = [];
    Object.keys(params).forEach(function (key) {
      const v = params[key];
      if (v !== undefined && v !== null && v !== '') {
        parts.push(encodeURIComponent(key) + '=' + encodeURIComponent(v));
      }
    });
    return parts.length ? '?' + parts.join('&') : '';
  }

  // ── Public API ─────────────────────────────────────────────────

  const api = {};

  // -- Config --

  /** Base URL the client is using. */
  api.API_BASE = API_BASE;

  /** True when running against localhost. */
  api.isDev = isLocalhost;

  /** The error class, exposed for instanceof checks. */
  api.APIError = SwingDoctorAPIError;

  // -- Auth --

  /**
   * Register a new account.
   * @param {string} email
   * @param {string} password
   * @param {string} displayName
   * @returns {Promise<object>} Token response
   */
  api.register = async function (email, password, displayName) {
    const data = await apiFetch('/auth/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        email: email,
        password: password,
        display_name: displayName,
      }),
      _skipAuth: true,
    });
    storeTokens(data);
    return data;
  };

  /**
   * Log in with email and password.
   * @param {string} email
   * @param {string} password
   * @returns {Promise<object>} Token response
   */
  api.login = async function (email, password) {
    const data = await apiFetch('/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: email, password: password }),
      _skipAuth: true,
    });
    storeTokens(data);
    return data;
  };

  /**
   * Manually refresh the access token.
   * Normally you don't need to call this — 401 responses trigger it
   * automatically.
   * @returns {Promise<string>} New access token
   */
  api.refreshToken = refreshToken;

  /**
   * Log out — clears stored tokens.
   */
  api.logout = function () {
    clearTokens();
  };

  /**
   * Check whether the user has a stored (non-expired) token.
   * Does NOT validate the token server-side.
   * @returns {boolean}
   */
  api.isAuthenticated = function () {
    return !!getAccessToken() && !isTokenExpired();
  };

  /**
   * Verify an email address with a token from the verification email.
   * @param {string} token
   * @returns {Promise<object>}
   */
  api.verifyEmail = async function (token) {
    return apiFetch('/auth/verify-email', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token: token }),
      _skipAuth: true,
    });
  };

  /**
   * Request a password reset email.
   * @param {string} email
   * @returns {Promise<object>}
   */
  api.forgotPassword = async function (email) {
    return apiFetch('/auth/forgot-password', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: email }),
      _skipAuth: true,
    });
  };

  /**
   * Reset password using the token from the reset email.
   * @param {string} token
   * @param {string} newPassword
   * @returns {Promise<object>}
   */
  api.resetPassword = async function (token, newPassword) {
    return apiFetch('/auth/reset-password', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token: token, new_password: newPassword }),
      _skipAuth: true,
    });
  };

  // -- Profiles --

  /**
   * List all profiles for the current user.
   * @returns {Promise<Array>}
   */
  api.getProfiles = async function () {
    return apiFetch('/profiles', { method: 'GET' });
  };

  /**
   * Create a new golfer profile.
   * @param {object} data — { name, launch_monitor?, ... }
   * @returns {Promise<object>}
   */
  api.createProfile = async function (data) {
    return apiFetch('/profiles', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
  };

  /**
   * Update an existing profile.
   * @param {string} id — Profile UUID
   * @param {object} data — Fields to update
   * @returns {Promise<object>}
   */
  api.updateProfile = async function (id, data) {
    return apiFetch('/profiles/' + id, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
  };

  // -- Sessions --

  /**
   * Upload a CSV file for processing.
   * @param {string} profileId — Target profile UUID
   * @param {File} file — CSV File object
   * @param {object} [options] — { ballType }
   * @returns {Promise<Array>} Created session(s)
   */
  api.uploadCSV = async function (profileId, file, options) {
    const formData = new FormData();
    formData.append('file', file);
    const queryParams = { profile_id: profileId };
    if (options && options.ballType) {
      queryParams.ball_type = options.ballType;
    }
    if (options && options.overrideDate) {
      queryParams.override_date = options.overrideDate;
    }
    // Don't set Content-Type — browser sets it with boundary for multipart
    return apiFetch('/sessions/upload' + qs(queryParams), {
      method: 'POST',
      body: formData,
    });
  };

  /**
   * Export all shot data as a clean CSV download.
   * @param {string} profileId
   */
  api.exportCSV = async function (profileId) {
    // Build auth header the same way apiFetch does
    const token = getAccessToken();
    if (!token) throw new SwingDoctorAPIError(401, 'Not logged in', 'auth_required');
    const headers = { 'Authorization': 'Bearer ' + token };

    const resp = await fetch(API_BASE + '/sessions/export' + qs({ profile_id: profileId }), { headers });
    if (!resp.ok) {
      const text = await resp.text().catch(() => '');
      throw new SwingDoctorAPIError(resp.status, text || 'Export failed', 'export_error');
    }
    const blob = await resp.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = resp.headers.get('Content-Disposition')?.split('filename=')[1]?.replace(/"/g, '') || 'swing-doctor-export.csv';
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  };

  /**
   * List sessions for a profile.
   * @param {string} profileId
   * @param {object} [filters] — { dateFrom, dateTo, ballType, page, pageSize }
   * @returns {Promise<object>} { items, total, page, page_size, has_more }
   */
  api.getSessions = async function (profileId, filters) {
    const params ={ profile_id: profileId };
    if (filters) {
      if (filters.dateFrom) params.date_from = filters.dateFrom;
      if (filters.dateTo) params.date_to = filters.dateTo;
      if (filters.ballType) params.ball_type = filters.ballType;
      if (filters.page) params.page = filters.page;
      if (filters.pageSize) params.page_size = filters.pageSize;
    }
    return apiFetch('/sessions' + qs(params), { method: 'GET' });
  };

  /**
   * Get a single session with all its shots.
   * @param {string} sessionId
   * @returns {Promise<object>}
   */
  api.getSession = async function (sessionId) {
    return apiFetch('/sessions/' + sessionId, { method: 'GET' });
  };

  /**
   * Update session metadata.
   * @param {string} sessionId
   * @param {object} data — { ball_type?, notes?, location? }
   * @returns {Promise<object>}
   */
  api.updateSession = async function (sessionId, data) {
    return apiFetch('/sessions/' + sessionId, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
  };

  /**
   * Delete a session and all its shots.
   * @param {string} sessionId
   * @returns {Promise<null>}
   */
  api.deleteSession = async function (sessionId) {
    return apiFetch('/sessions/' + sessionId, { method: 'DELETE' });
  };

  // -- Analytics --

  /** Map common filter keys (camelCase) to API query params (snake_case). */
  function analyticsParams(filters) {
    const params ={};
    if (filters) {
      if (filters.club) params.club = filters.club;
      if (filters.dateFrom) params.date_from = filters.dateFrom;
      if (filters.dateTo) params.date_to = filters.dateTo;
      if (filters.ballType) params.ball_type = filters.ballType;
    }
    return params;
  }

  /**
   * Get the full analytics bundle for a profile.
   * @param {string} profileId
   * @param {object} [filters] — { club, dateFrom, dateTo, ballType }
   * @returns {Promise<object>}
   */
  api.getFullAnalytics = async function (profileId, filters) {
    return apiFetch('/analytics/profiles/' + profileId + '/summary' + qs(analyticsParams(filters)), { method: 'GET' });
  };

  /**
   * Get per-club aggregate statistics.
   * @param {string} profileId
   * @param {object} [filters] — { club, dateFrom, dateTo, ballType }
   * @returns {Promise<Array>}
   */
  api.getClubSummaries = async function (profileId, filters) {
    return apiFetch('/analytics/profiles/' + profileId + '/clubs' + qs(analyticsParams(filters)), { method: 'GET' });
  };

  /**
   * Get session-over-session trend data for charting.
   * @param {string} profileId
   * @param {object} [filters] — { club, dateFrom, dateTo, ballType }
   * @returns {Promise<Array>}
   */
  api.getTrends = async function (profileId, filters) {
    return apiFetch('/analytics/profiles/' + profileId + '/trends' + qs(analyticsParams(filters)), { method: 'GET' });
  };

  /**
   * Get improvement comparison (recent vs earlier performance).
   * @param {string} profileId
   * @param {object} [options] — { club, days }
   * @returns {Promise<Array>}
   */
  api.getImprovement = async function (profileId, options) {
    const params ={};
    if (options) {
      if (options.club) params.club = options.club;
      if (options.days) params.days = options.days;
    }
    return apiFetch('/analytics/profiles/' + profileId + '/improvement' + qs(params), {
      method: 'GET',
    });
  };

  /**
   * Get estimated handicap potential.
   * @param {string} profileId
   * @returns {Promise<object>}
   */
  api.getHandicap = async function (profileId) {
    return apiFetch('/analytics/profiles/' + profileId + '/handicap', {
      method: 'GET',
    });
  };

  // -- AI Coach --

  /**
   * Request AI-powered swing analysis (requires Pro subscription).
   * @param {string} profileId
   * @param {object} [options] — { club, dateFrom, dateTo, ballType, additionalContext }
   * @returns {Promise<object>}
   */
  api.getAIAnalysis = async function (profileId, options) {
    const params ={};
    let bodyObj = null;
    if (options) {
      if (options.club) params.club = options.club;
      if (options.dateFrom) params.date_from = options.dateFrom;
      if (options.dateTo) params.date_to = options.dateTo;
      if (options.ballType) params.ball_type = options.ballType;
      if (options.additionalContext) {
        bodyObj = { additional_context: options.additionalContext };
      }
    }
    const fetchOpts = { method: 'POST' };
    if (bodyObj) {
      fetchOpts.headers = { 'Content-Type': 'application/json' };
      fetchOpts.body = JSON.stringify(bodyObj);
    }
    return apiFetch('/ai/profiles/' + profileId + '/analyze' + qs(params), fetchOpts);
  };

  // -- Event hooks ────────────────────────────────────────────────

  /**
   * Register a callback for auth state changes.
   * Called with true on login/register, false on logout/token expiry.
   * Returns an unsubscribe function.
   *
   * @param {function(boolean): void} callback
   * @returns {function(): void} unsubscribe
   */
  api.onAuthChange = function (callback) {
    _authListeners.push(callback);
    return function () {
      _authListeners = _authListeners.filter(function (cb) { return cb !== callback; });
    };
  };

  let _authListeners = [];

  function _notifyAuth(isLoggedIn) {
    _authListeners.forEach(function (cb) {
      try { cb(isLoggedIn); } catch (_) { /* swallow listener errors */ }
    });
  }

  // Wrap login/register/logout to fire auth events
  const _origLogin = api.login;
  api.login = async function () {
    const result = await _origLogin.apply(null, arguments);
    _notifyAuth(true);
    return result;
  };

  const _origRegister = api.register;
  api.register = async function () {
    const result = await _origRegister.apply(null, arguments);
    _notifyAuth(true);
    return result;
  };

  const _origLogout = api.logout;
  api.logout = function () {
    _origLogout();
    _notifyAuth(false);
  };

  // Listen for token changes from other tabs
  window.addEventListener('storage', function (e) {
    if (e.key === TOKEN_KEY) {
      _notifyAuth(!!e.newValue);
    }
  });

  // ── Expose globally ────────────────────────────────────────────

  window.SwingDoctorAPI = api;
})();
