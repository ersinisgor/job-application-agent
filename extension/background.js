// Service worker: content script'ten gelen istekleri Python backend'ine iletir.
// fetch'i burada yapmak onu LinkedIn sayfasının kökeninden bağımsız tutar ve host_permissions
// sayesinde CORS'suz erişim sağlar.

const BACKEND_BASE = "http://localhost:8000";

// Mesaj türü -> backend yolu. host_permissions zaten localhost:8000/*'ı kapsıyor,
// yani yeni bir rota eklemek manifest değişikliği gerektirmez.
const ROUTES = {
  SUMMARIZE: "/summarize",
  COVER_LETTER: "/cover-letter",
  ADD_JOB: "/add-job",
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
          /* gövde JSON değil; varsayılan mesajı koru */
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

  // Asenkron cevap için mesaj kanalını açık tut.
  return true;
});
