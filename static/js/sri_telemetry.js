/**
 * Sri AI — Omni-Heal Pillar A: Frontend JavaScript Watcher
 * =========================================================
 * Loaded before all other custom scripts via upload.html <head>.
 *
 * What it catches:
 *   1. Uncaught JS runtime exceptions    (window.onerror)
 *   2. Unhandled Promise rejections      (unhandledrejection)
 *   3. Failed fetch() calls              (fetch wrapper)
 *   4. Manual events from UI code        (dispatchEvent / sri:report)
 */

(function SriTelemetry() {
  "use strict";

  // ── Config ────────────────────────────────────────────────
  const ENDPOINT    = "/api/sri-heal/frontend/";
  const MAX_RETRIES = 2;
  const DEBOUNCE_MS = 3000;
  const seen        = new Set();

  // ── Core reporter ─────────────────────────────────────────
  function report(errorType, message, stack, severity) {
    stack    = stack    || "";
    severity = severity || "MEDIUM";

    const key = errorType + ":" + String(message).slice(0, 80);
    if (seen.has(key)) return;
    seen.add(key);
    setTimeout(function () { seen.delete(key); }, DEBOUNCE_MS);

    var payload = {
      error_type : errorType,
      message    : String(message).slice(0, 500),
      stack      : String(stack).slice(0, 2000),
      url        : window.location.href,
      severity   : severity,
      source     : "browser",
      timestamp  : new Date().toISOString(),
    };

    _sendWithRetry(payload, MAX_RETRIES);
  }

  function _sendWithRetry(payload, retriesLeft) {
    fetch(ENDPOINT, {
      method   : "POST",
      headers  : { "Content-Type": "application/json" },
      body     : JSON.stringify(payload),
      keepalive: true,  // survives page unloads
    }).catch(function () {
      if (retriesLeft > 0) {
        setTimeout(function () { _sendWithRetry(payload, retriesLeft - 1); }, 1500);
      }
    });
  }

  // ── 1. Uncaught JS exceptions ─────────────────────────────
  window.onerror = function (message, source, lineno, colno, error) {
    report(
      "JS_RUNTIME",
      message + " (" + source + ":" + lineno + ":" + colno + ")",
      error ? error.stack : "",
      "HIGH"
    );
    return false;
  };

  // ── 2. Unhandled Promise rejections ───────────────────────
  window.addEventListener("unhandledrejection", function (event) {
    var reason = event.reason;
    report(
      "PROMISE_REJECTION",
      reason && reason.message ? reason.message : String(reason),
      reason && reason.stack  ? reason.stack  : "",
      "HIGH"
    );
  });

  // ── 3. Fetch wrapper — intercepts network failures ────────
  var _originalFetch = window.fetch;
  window.fetch = function () {
    var args = Array.prototype.slice.call(arguments);
    return _originalFetch.apply(this, args).then(function (response) {
      if (!response.ok && response.status !== 401) {
        report(
          "FETCH_FAIL",
          "HTTP " + response.status + " " + response.statusText + " \u2192 " + args[0],
          "",
          response.status >= 500 ? "CRITICAL" : "MEDIUM"
        );
      }
      return response;
    }).catch(function (err) {
      report("FETCH_NETWORK_ERROR", err.message, err.stack || "", "HIGH");
      throw err;
    });
  };

  // ── 4. Custom manual event hook ───────────────────────────
  // Usage:
  //   window.dispatchEvent(new CustomEvent("sri:report", {
  //     detail: { type: "UI_BUG", message: "...", severity: "HIGH" }
  //   }));
  window.addEventListener("sri:report", function (event) {
    var detail   = event.detail || {};
    var type     = detail.type     || "UI_BUG";
    var message  = detail.message  || "Manual report";
    var stack    = detail.stack    || "";
    var severity = detail.severity || "MEDIUM";
    report(type, message, stack, severity);
  });

  console.log("[SriTelemetry] \uD83D\uDEE1\uFE0F  Watcher active.");
})();
