// Service worker: forwards requests from the content script to the Python backend.
// Doing the fetch here keeps it independent of the LinkedIn page origin and allows
// CORS-free access via host_permissions.

const BACKEND_BASE = "http://localhost:8000";

// Message type -> backend path. host_permissions already covers localhost:8000/*,
// so adding a route needs no manifest change.
const ROUTES = {
  SUMMARIZE: "/summarize",
  COVER_LETTER: "/cover-letter",
};

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  const path = ROUTES[message?.type];
  if (!path) return false;

  fetch(BACKEND_BASE + path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(message.payload),
  })
    .then(async (res) => {
      if (!res.ok) {
        let detail = `Server error (${res.status})`;
        try {
          const body = await res.json();
          if (body?.detail) detail = body.detail;
        } catch (_) {
          /* body is not JSON; keep the default message */
        }
        sendResponse({ ok: false, error: detail });
        return;
      }
      const data = await res.json();
      sendResponse({ ok: true, data });
    })
    .catch(() => {
      sendResponse({
        ok: false,
        error:
          "Backend unreachable. Make sure the Python server (localhost:8000) is running.",
      });
    });

  // Keep the message channel open for the async response.
  return true;
});
