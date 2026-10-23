// LinkedIn iş sayfasında seçili ilanı okur, Python backend'inden Türkçe bir özet alır ve
// yan panelde gösterir. İlan değiştikçe panel güncellenir.
//
// GÜVENLİK NOTU: bu script LinkedIn'e HİÇBİR ek ağ isteği yapmaz. Yalnızca sayfada zaten
// görünen ilan metnini okur ve özetlenmesi için SADECE kendi localhost backend'ine gönderir.
// (Eski bir sürümde LinkedIn'in iç API'sini çağıran bir hover/prefetch vardı; otomasyon olarak
// algılandı ve oturum kapanmalarına yol açtı, bu yüzden kaldırıldı.)

(() => {
  "use strict";

  const LOG = "[JobSum]";
  // LinkedIn'in hash'li sınıflı arayüzüne karşı seçicileri düzeltmek için kullanılan DIAG
  // çıktısını (seçici yedeği uyarıları + DOM dökümü) yazdırmak için true yap. Normal kullanımda
  // konsol sessiz kalsın diye varsayılan kapalı.
  const DEBUG = false;
  // Bir ilanın açıklamasının DOM'da belirmesi için ne kadar bekleneceği; sonra okuyamadığımız
  // bir yerleşimde sonsuza kadar dönmek yerine vazgeçip yeniden deneme ipucu gösterilir.
  const DESC_LOAD_TIMEOUT_MS = 12000;
  // Yeni arayüz detay panelini parça parça yükler; erken bir okuma yalnızca başlığı/rol özetini
  // yakalar (bir "Çalışma: hybrid" parçası). Özetlemeden önce çıkarılan metin bu kadar süre
  // değişmeden kalana kadar bekle, böylece biraz sonra gelen stack/deneyim/uyum bölümleri de girer.
  const DESC_STABLE_MS = 1400;
  // Gerçek bir ilan açıklamasını okuyamadığımızda gösterilir (hiç yüklenmedi ya da okuduğumuz
  // metin ilan çıkmadı ve backend özeti boş döndü).
  const DESC_HINT = 'İş açıklaması okunamadı. Sayfayı biraz aşağı kaydırıp "Yenile"ye bas.';
  console.log(LOG, "content script loaded:", location.href);

  // --- LinkedIn DOM seçicileri (kırılgan; sırayla denenir, ilk eşleşen kazanır) ---
  // Açıklamanın kendisi artık seçicilerle okunmuyor — hash'li yeni arayüz onları yanlış bölgeye
  // eşleştirdi (bkz. heuristicDescription); başlık/şirket/konum ise panel başlığı ve backend
  // yükü için hâlâ best-effort ipuçları.
  const SELECTORS = {
    title: [
      ".job-details-jobs-unified-top-card__job-title",
      ".jobs-unified-top-card__job-title",
      ".job-details-jobs-unified-top-card__job-title h1",
    ],
    company: [
      ".job-details-jobs-unified-top-card__company-name",
      ".jobs-unified-top-card__company-name",
    ],
    location: [
      ".job-details-jobs-unified-top-card__primary-description-container",
      ".jobs-unified-top-card__primary-description",
      ".job-details-jobs-unified-top-card__tertiary-description-container",
    ],
  };

  // Panel alan sırası ve etiketleri. Bilerek asgari: ilanın uyup uymadığına karar vermek için
  // tek bakış yetmeli. "work" istemci tarafında work_type + work_type_note'tan oluşturulur
  // (tek satır, ör. "on-site — İstanbul tercihli").
  const FIELDS = [
    { key: "role_summary", label: "Özet" },
    { key: "work", label: "Çalışma" },
    { key: "stack", label: "Stack" },
    { key: "min_experience", label: "Deneyim" },
    { key: "visa_sponsorship", label: "Vize / Sponsorluk" }, // yalnızca varsa gösterilir
  ];

  let lastJobId = null; // en son gösterilen ilan no'su
  let seenOnlyShownFor = null; // "kapatıldı, hiç özetlenmedi" gövdesi açık olan ilan
  let pendingJobId = null; // açıklamasının yüklenmesini bekleyen ilan
  let pendingSince = 0; // bekleyen ilanın beklemeye başladığı an (yükleme zaman aşımı için)
  let pendingDesc = ""; // bekleyen ilan için son okunan açıklama (kararlılık kontrolü)
  let pendingDescSince = 0; // pendingDesc'in son DEĞİŞTİĞİ an (oturma zamanlayıcısı)
  let lastShownDescription = ""; // gösterilen ilanın açıklaması (bayatlık koruması)
  let requestSeq = 0; // yarış durumlarını önlemek için istek sırası
  let lastBodyHtml = `<div class="jobsum-status">Ready — click a job on the left.</div>`;
  let lastHeader = { title: "Job Summary", company: "" }; // panel başlık durumu
  let userClosed = false; // kullanıcı paneli kapattıysa yeniden açma
  let showingList = false; // panel özet yerine bir işaret listesi gösteriyor
  let listKind = "reviewed"; // hangi liste gösteriliyor: "reviewed" ya da "maybe"
  let showingCover = false; // panel bu ilanın mektubunu gösteriyor
  let coverJobId = null; // gösterilen mektubun ait olduğu ilan (bayatlık koruması)
  let coverLang = "en"; // getirilecek mektubun dili

  // Gövde özetten başka bir şeye aitken true. Her çizici bunu kontrol eder: LinkedIn
  // değişiklikleri maybeUpdate()'i her 700 ms'de tetikler; yoksa liste/mektup bir özetle ya da
  // dönen simgeyle ezilirdi.
  function bodyLocked() {
    return showingList || showingCover;
  }

  // İlan başına özet önbelleği: bir ilana dönünce özet anında görünür.
  const CACHE = new Map(); // jobId -> { summary, description }
  const CACHE_LIMIT = 60;

  function cacheSet(jobId, summary, description) {
    CACHE.set(jobId, { summary, description });
    if (CACHE.size > CACHE_LIMIT) {
      CACHE.delete(CACHE.keys().next().value); // en eskiyi at
    }
  }

  // --- Kalıcı "incelendi" hafızası -----------------------------------------
  // LinkedIn'in kapatma (X) durumu aramaya özel; aynı ilan başka iş alarmı listelerinde
  // kapatılmamış olarak yeniden çıkar. Kanonik ilan no'suna (aramalar arasında sabit) göre
  // anahtarlı kendi hafızamızı chrome.storage.local'da tutar ve incelenmiş bir ilan yeniden
  // çıkınca uyarırız.

  // Bir işaret deposu, bir dizi ilan no'sunu (hafif üst veriyle) chrome.storage.local'da tek bir
  // anahtar altında saklar; zaman damgasına göre bir üst sınıra budanır. İki tane tutarız:
  // "reviewed" (zaten bakılmış her ilan) ve "maybe" (sonra dönülecek, stack'i uyan ilanların
  // kısa listesi). BİRBİRİNDEN BAĞIMSIZDIRLAR — bir ilan ikisinden birinde, ikisinde ya da
  // hiçbirinde olabilir.
  const MARKER_LIMIT = 3000; // depo başına üst sınır; yazarken en eskileri zaman damgasına göre buda

  function makeMarkerStore(storeKey, name) {
    let map = {}; // jobId -> { t, title, company, fit, seenOnly }

    function load() {
      try {
        chrome.storage.local.get(storeKey, (res) => {
          if (chrome.runtime.lastError) return;
          map = (res && res[storeKey]) || {};
          scheduleUpdate(); // yüklenen durumu listeye/panele yansıt
        });
      } catch (_) {
        /* depolama kullanılamıyor; özellik sadece etkisiz kalır */
      }
    }

    // Başka bir sekme depoyu değiştirirse senkron kal.
    try {
      chrome.storage.onChanged.addListener((changes, area) => {
        if (area === "local" && changes[storeKey]) {
          map = changes[storeKey].newValue || {};
          scheduleUpdate();
        }
      });
    } catch (_) {
      /* yok say */
    }

    function persist() {
      const ids = Object.keys(map);
      if (ids.length > MARKER_LIMIT) {
        ids
          .sort((a, b) => (map[a].t || 0) - (map[b].t || 0))
          .slice(0, ids.length - MARKER_LIMIT)
          .forEach((id) => delete map[id]);
      }
      try {
        chrome.storage.local.set({ [storeKey]: map });
      } catch (_) {
        /* yok say */
      }
    }

    function mark(jobId, meta) {
      if (!jobId) return;
      const existing = map[jobId];
      map[jobId] = {
        t: existing && existing.t ? existing.t : Date.now(), // ilk görülme zamanını koru
        title: (meta && meta.title) || (existing && existing.title) || "",
        company: (meta && meta.company) || (existing && existing.company) || "",
        fit: meta && meta.fit != null ? meta.fit : existing ? existing.fit : null,
        // Bir kez temizlenince kalıcı: sonradan özetlenen bir ilan asla yalnızca-uyarıya geri
        // düşmemeli, yani açık bir `false` saklı bir `true`'ya her zaman üstün gelir.
        seenOnly:
          meta && meta.seenOnly != null
            ? !!meta.seenOnly
            : !!(existing && existing.seenOnly),
      };
      persist();
      console.log(LOG, "marked " + name + ":", jobId);
      scheduleUpdate();
    }

    function unmark(jobId) {
      if (!jobId || !map[jobId]) return;
      delete map[jobId];
      persist();
      console.log(LOG, "unmarked " + name + ":", jobId);
      scheduleUpdate();
    }

    return {
      load,
      mark,
      unmark,
      has: (jobId) => !!(jobId && map[jobId]),
      get: (jobId) => map[jobId],
      entries: () => Object.entries(map),
    };
  }

  const reviewed = makeMarkerStore("jobsum_reviewed", "reviewed");
  const maybe = makeMarkerStore("jobsum_maybe", "maybe");
  // "Ekle" ile sheet'e zaten eklenmiş ilanlar. Sunucu tarafındaki bir gerçeğin yerel aynası;
  // böylece bir ilana dönünce buton sheet indirilmeden "eklendi" olarak çizilir. Depo bir gün
  // kaybolursa yeniden tıklamak sadece "exists" döner ve yeniden işaretler.
  const added = makeMarkerStore("jobsum_added", "added");
  const isAdded = added.has;

  // İnce takma adlar (çok sayıdaki) reviewed çağrı yerlerini okunur tutar.
  const isReviewed = reviewed.has;
  const markReviewed = reviewed.mark;
  const unmarkReviewed = reviewed.unmark;
  const isMaybe = maybe.has;
  const isSeenOnly = (jobId) => !!(reviewed.get(jobId) || {}).seenOnly;

  // "bunu N önce gördün" için Türkçe göreli zaman.
  function relativeTime(t) {
    const mins = Math.max(0, Math.floor((Date.now() - t) / 60000));
    if (mins < 1) return "az önce";
    if (mins < 60) return `${mins} dk önce`;
    const hours = Math.floor(mins / 60);
    if (hours < 24) return `${hours} saat önce`;
    const days = Math.floor(hours / 24);
    if (days < 7) return `${days} gün önce`;
    const weeks = Math.floor(days / 7);
    return `${weeks} hafta önce`;
  }

  // --- Yardımcılar ---

  // LinkedIn'in yeni iş arayüzü ilan panelini açık shadow root'ların ve aynı kökenli
  // iframe'lerin içinde çizer; düz document.querySelector / TreeWalker oraya ulaşamaz.
  // collectRoots() ana belgeyi artı iç içe her açık shadow root'u ve okunabilir (aynı kökenli)
  // iframe belgesini döndürür; böylece aşağıdaki bütün metin çıkarma bu sınırları delebilir.
  // Farklı kökenli iframe'ler erişimde hata fırlatır ve sessizce atlanır.
  function collectRoots() {
    const roots = [document];
    for (let i = 0; i < roots.length; i++) {
      const root = roots[i];
      let all;
      try {
        all = root.querySelectorAll("*");
      } catch (_) {
        continue;
      }
      all.forEach((el) => {
        if (el.shadowRoot) roots.push(el.shadowRoot);
        if (el.tagName === "IFRAME") {
          let doc = null;
          try {
            doc = el.contentDocument;
          } catch (_) {
            /* farklı köken; okunamaz */
          }
          if (doc) roots.push(doc);
        }
      });
    }
    return roots;
  }

  function deepQuery(selector, roots) {
    for (const root of roots || collectRoots()) {
      let el = null;
      try {
        el = root.querySelector(selector);
      } catch (_) {
        /* bu kök türü için geçersiz seçici; atla */
      }
      if (el) return el;
    }
    return null;
  }

  // deepQuery gibi, ama bütün köklerdeki HER eşleşmeyi döndürür. Kart süslemesinin ilki değil,
  // hepsi lazım.
  function deepQueryAll(selector, roots) {
    const out = [];
    for (const root of roots || collectRoots()) {
      try {
        root.querySelectorAll(selector).forEach((el) => out.push(el));
      } catch (_) {
        /* bu kök türü için geçersiz seçici; atla */
      }
    }
    return out;
  }

  function firstMatchText(selectorList) {
    const roots = collectRoots();
    for (const sel of selectorList) {
      const el = deepQuery(sel, roots);
      if (el) {
        const text = el.innerText.trim();
        if (text) return text;
      }
    }
    return "";
  }

  // Açıklama, sayfadaki en uzun GÖRÜNÜR metin düğümü bulunarak okunur (neredeyse her zaman bir
  // ilan açıklaması paragrafı), sonra hâlâ bir içerik paneline benzeyen en büyük kapsayıcıya
  // tırmanılır (bütün sayfa değil, sonuç listesi değil). LinkedIn JSON yığınlarını <code>
  // etiketlerinde saklar; bu yüzden gizli düğümler atlanmalı.
  function findLongestVisibleTextEl() {
    let best = null;
    let bestLen = 0;
    for (const root of collectRoots()) {
      const scope = root.body || root; // Document -> body; ShadowRoot -> kendisi
      if (!scope) continue;
      const doc = root.ownerDocument || root; // createTreeWalker için sahip Document
      let walker;
      try {
        walker = doc.createTreeWalker(scope, NodeFilter.SHOW_TEXT);
      } catch (_) {
        continue;
      }
      let node;
      while ((node = walker.nextNode())) {
        const parent = node.parentElement;
        if (!parent) continue;
        const len = node.textContent.trim().length;
        if (len <= bestLen) continue;
        if (parent.closest("#jobsum-panel,code,script,style,noscript,template")) continue;
        // Bir LİSTE kartı asla açıklama değildir — atla; yoksa bir arama sonuçları sayfasındaki en
        // uzun metin başka bir ilanın kart başlığı olur ve sezgisel yöntem yanlış ilana tırmanır.
        if (parent.closest(LIST_CARD_SELECTOR)) continue;
        if (parent.checkVisibility && !parent.checkVisibility()) continue;
        best = parent;
        bestLen = len;
      }
    }
    return { el: best, len: bestLen };
  }

  // Yeni /jobs/search-results arayüzünde yeni tıklanan bir ilan açıklamasını sağ panelde
  // tıklamadan biraz SONRA çizer. O aralıkta sayfayı okursan açıklama seçicileri ıskalar ve en
  // uzun metin yöntemi bunun yerine LinkedIn'in genel menüsüne + filtre çubuğuna tırmanır
  // ("Skip to main content / Home / My Network / …").
  // Bu kabuk bir ilan değildir: backend onun için boş bir özet döndürür. "Skip to main content"
  // gerçek bir açıklamada asla geçmez; bu yüzden menü imzasını taşıyan her metni "henüz
  // yüklenmedi" say ve gerçek açıklamayı beklemeye devam et.
  function looksLikePageChrome(text) {
    if (!text) return false;
    const head = text.slice(0, 600).toLowerCase();
    // LinkedIn'in bir iş ilanında asla geçmeyen kendi arayüz metinleri. Eski sınıf seçicileri,
    // hash'li yeni arayüzde bazen üst menü çubuğunu BAZEN sol filtre/sonuç çubuğunu yakalıyor —
    // ikisi de reddedilsin diye ikisi de tanınmalı.
    return (
      head.includes("skip to main content") || // üst menü çubuğu
      head.includes("ai-powered search is in beta") || // sonuç başlığı
      head.includes("how promoted jobs are ranked") || // sonuç başlığı
      (head.includes("experience level") && head.includes("employment type")) || // filtre çubuğu
      (head.includes("my network") && head.includes("notifications")) // üst menü çubuğu
    );
  }

  // Bir katmanın sonucu sayfa kabuğuysa onu boşalt; böylece çıkarma zinciri menü çubuğunu kabul
  // etmek yerine bir sonraki katmana düşer.
  const nonChrome = (text) => (looksLikePageChrome(text) ? "" : text || "");

  function heuristicDescription() {
    const { el: start, len } = findLongestVisibleTextEl();
    // Düşük tohum eşiği: yeni arayüz açıklamayı birçok kısa satıra böler, yani en uzun tek düğümü
    // bir cümleden kısa olabilir. Çöp yakalamaya karşı asıl koruma, aşağıda birleştirilmiş
    // kapsayıcıdaki 300 karakterlik tabandır.
    if (!start || len < 50) return "";
    let el = start;
    while (el.parentElement && el.parentElement !== document.body) {
      const parent = el.parentElement;
      const parentText = (parent.innerText || "").trim();
      if (parentText.length > 12000) break; // bütün sayfayı yutma
      // Genel menüyü / filtre çubuğunu da içine alan bir ebeveynden önce dur: yeni arayüzde temiz
      // açıklama kapsayıcısının atası sol kabuğu da tutar ve ona tırmanmak bütün sonucu sayfa
      // kabuğu gibi okutur (sonra reddedilir ve ilan zaman aşımına uğrar). Onun yerine temiz
      // çocuğu tut.
      if (looksLikePageChrome(parentText)) break;
      // Sol SONUÇ LİSTESİNİ de içeren bir ebeveynden önce dur. Detay paneli ve ilan kartı listesi bir
      // atayı paylaşır; ona tırmanmak sonucun kart yığınıyla başlamasına yol açtı ("Senior Backend
      // Developer … GönderAL … Viewed …") — model ilanı değil listeyi özetledi. Detay panelinde liste
      // kartı yoktur; yani kart içeren bir ebeveyn, dışarı tırmandığımız anlamına gelir: çocuğu tut.
      if (parent.querySelector(LIST_CARD_SELECTOR)) break;
      el = parent;
    }
    const text = (el.innerText || "").trim();
    return text.length >= 300 ? text.slice(0, 15000) : "";
  }

  // Başarısız seçiciler yapıştırılmış bir konsol dökümünden düzeltilebilsin diye en uzun görünür
  // metnin etrafındaki DOM'u logla. Olağan ilan başına yolda DEBUG'a bağlı; açıklama zaman aşımı
  // yolu ise koşulsuz çağırır (takılmış bir panel, isteğe bağlı gürültü değil, bir tanıyı hak eden
  // gerçek bir hatadır).
  function logDomDiagnosis() {
    const { el: best, len } = findLongestVisibleTextEl();
    if (!best) {
      console.warn(LOG, "DIAG: no visible text node found at all");
    } else {
      console.warn(
        LOG,
        `DIAG longest visible text: ${len} chars:`,
        best.textContent.trim().slice(0, 100)
      );
      let el = best;
      const chain = [];
      while (el && el !== document.body && chain.length < 10) {
        const cls = String(
          el.className && el.className.baseVal !== undefined
            ? el.className.baseVal
            : el.className || ""
        ).slice(0, 100);
        const textLen = (el.innerText || "").trim().length;
        chain.push(
          `<${el.tagName.toLowerCase()}> id=${el.id || "-"} class=${cls || "-"} len=${textLen}`
        );
        el = el.parentElement;
      }
      console.warn(LOG, "DIAG ancestor chain:\n" + chain.join("\n"));
    }
    const roots = collectRoots();
    const readableIframes = roots.filter(
      (r) => r.nodeType === 9 && r !== document
    ).length;
    const shadows = roots.filter((r) => r.nodeType === 11).length;
    const totalIframes = document.querySelectorAll("iframe").length;
    console.warn(
      LOG,
      `DIAG iframes=${totalIframes} (readable=${readableIframes}) ` +
        `shadowRoots=${shadows} rootsSearched=${roots.length}`
    );
    // Aynı DOM'un kart tarafı: açıklamayı saklayan bir yerleşim genellikle kartları da saklar ve
    // buradaki sıfır, eksik bir "görüldü" rozetini açıklar.
    const deepCards = deepQueryAll(CARD_SELECTOR, roots).length;
    const docCards = document.querySelectorAll(CARD_SELECTOR).length;
    console.warn(LOG, `DIAG cards deep=${deepCards} (document-only=${docCards})`);
  }

  // Eklenti yeniden yüklendiğinde/güncellendiğinde açık sekmelere zaten enjekte edilmiş content
  // script yetim kalır: çalışma zamanı ölüdür ama zamanlayıcısı/gözlemcisi çalışmaya devam eder
  // ve her tikte "chrome-extension://invalid/" hatalarıyla konsolu doldurur. Bunu algıla ve
  // kendini imha et (bkz. en alttaki teardown()).
  function extensionAlive() {
    try {
      return typeof chrome !== "undefined" && !!chrome.runtime && !!chrome.runtime.id;
    } catch (_) {
      return false; // bağlam gidince chrome.runtime'a erişmek hata fırlatır
    }
  }

  // Content script her LinkedIn sayfasına enjekte edilir (böylece herhangi bir sekmede iş görünümüne
  // SPA gezinmesinden sağ çıkar), ama panel ve işi yalnızca iş sayfalarına aittir.
  function isJobsPage() {
    return location.pathname.startsWith("/jobs/");
  }

  function getCurrentJobId() {
    const params = new URLSearchParams(window.location.search);
    const fromUrl = params.get("currentJobId");
    if (fromUrl) return fromUrl;

    // Tek başına ilan sayfası (/jobs/view/<id>/…): no yolun içindedir ve okunacak bir liste
    // kartı yoktur.
    const fromPath = location.pathname.match(/\/jobs\/view\/(\d+)/);
    if (fromPath) return fromPath[1];

    const selected = document.querySelector(
      ".jobs-search-results-list__list-item--active [data-job-id], li.jobs-search-results__list-item.active [data-occludable-job-id], .job-card-container--active [data-job-id]"
    );
    if (selected) {
      return (
        selected.getAttribute("data-job-id") ||
        selected.getAttribute("data-occludable-job-id")
      );
    }
    return null;
  }

  // Bir ilan kartının hangi ilan olduğunu nasıl bildirdiği. Eski arayüz onu data-job-id ile
  // etiketler; yeni /jobs/search-results arayüzünde hash'li sınıflar var, data-job-id yok ve
  // kartın içinde ilan linki yok — ama componentkey="job-card-component-ref-<id>" taşıyor.
  const CARD_SELECTOR =
    '[data-job-id], [data-occludable-job-id], [componentkey^="job-card-component-ref-"]';
  // HER ZAMAN sol liste kartı olan alt küme. data-job-id'yi bilerek dışarıda bırakır: sağdaki
  // detay paneli de onu taşıyabilir ve açıklama sezgisi o paneli atlanacak bir liste kartı
  // saymamalı.
  const LIST_CARD_SELECTOR =
    '[data-occludable-job-id], [componentkey^="job-card-component-ref-"]';
  const JOB_LINK = 'a[href*="/jobs/view/"]';

  // Tıklanan bir kontrolün sahibi olan ilan kartı. Element.closest()'un geçemediği shadow root
  // sınırlarını aşan composed path'i dolaşır.
  function cardFrom(node, path) {
    const tagged = node.closest && node.closest(CARD_SELECTOR);
    if (tagged) return tagged;
    // Tanımadığımız bir kart biçimi için son çare: TAM OLARAK BİR ilan linki tutan en geniş ata.
    // Birden fazla, karttan sonuç listesine tırmandığımız anlamına gelir; orada ilk link başka bir
    // ilana aittir.
    let widest = null;
    for (const el of path && path.length ? path : ancestorsOf(node)) {
      if (!el || el.nodeType !== 1 || !el.querySelectorAll) continue;
      if (el === document.body || el === document.documentElement) break;
      if (el.matches && el.matches(CARD_SELECTOR)) return el;
      const links = el.querySelectorAll(JOB_LINK).length;
      if (links > 1) break;
      if (links === 1) widest = el;
    }
    return widest;
  }

  function ancestorsOf(node) {
    const chain = [];
    for (let el = node; el; el = el.parentElement) chain.push(el);
    return chain;
  }

  function cardJobId(card) {
    if (!card) return null;
    const attr =
      card.getAttribute("data-job-id") ||
      card.getAttribute("data-occludable-job-id");
    if (attr) return attr;
    const key = card.getAttribute("componentkey") || "";
    const fromKey = key.match(/job-card-component-ref-(\d+)/);
    if (fromKey) return fromKey[1];
    const link = card.querySelector(JOB_LINK);
    const match = link && link.getAttribute("href").match(/\/jobs\/view\/(\d+)/);
    return match ? match[1] : null;
  }

  // Bir ilan kartından best-effort başlık/şirket. Yeni arayüz başlığı iki kez yazar — bir kez
  // ekran okuyucular için durum önekiyle ("Selected, <title> (Verified job)"), bir kez görsel
  // olarak — ve bunların tek bir innerText satırına mı iki satıra mı düştüğü CSS'e bağlı. Bu
  // yüzden başlığı varsa görünür span'dan oku ve şirket olarak başlığın tekrarı olmayan ilk
  // satırı al.
  function cardMeta(card) {
    if (!card) return {};
    const lines = (card.innerText || "")
      .split("\n")
      .map((l) => l.trim())
      .filter(Boolean);
    const titleEl = card.querySelector('p span[aria-hidden="true"]');
    const title = (titleEl && titleEl.textContent.trim()) || lines[0] || "";
    const company = title
      ? lines.find((l) => !l.includes(title) && !title.includes(l)) || ""
      : lines[1] || "";
    return { title, company };
  }

  // LinkedIn'in kendi kapatma (X) / geri al (↩️) butonlarına tıklamaları algıla. aria-label
  // LinkedIn'in en kararlı işaretidir (CSS sınıfları hash'li). Bu desenler bir dili kaçırırsa
  // panel düğmesi güvenilir yedektir.
  const DISMISS_RE = /dismiss|yoksay|gizle|kapat|not interested|ilgilenmiyorum/i;
  const UNDO_RE = /undo|geri al|geri getir/i;
  const warnedLabels = new Set(); // farklı eşleşmeyen aria-label'lar, üst sınırlı

  function onDocClick(event) {
    // composedPath() shadow root'ların içini görür; event.target shadow HOST'a yeniden hedeflenir,
    // yani .closest("button") yeni arayüzün kapatma butonunu kaçırırdı.
    const path =
      typeof event.composedPath === "function" ? event.composedPath() : [];
    const btn =
      path.find((n) => n && n.nodeType === 1 && n.tagName === "BUTTON") ||
      (event.target.closest && event.target.closest("button"));
    if (!btn) return;
    const card = cardFrom(btn, path);
    const jobId = cardJobId(card);
    const label = (btn.getAttribute("aria-label") || btn.title || "").trim();
    if (!jobId) {
      // Bir ilan kartının içinde buton değil — meğer ki sadece çözemediysek.
      if (DEBUG && (UNDO_RE.test(label) || DISMISS_RE.test(label)))
        console.warn(LOG, "dismiss/undo click but no job id resolved:", label);
      return;
    }
    if (UNDO_RE.test(label)) {
      unmarkReviewed(jobId);
    } else if (DISMISS_RE.test(label)) {
      // Herhangi bir özet olmadan doğrudan listeden kapatıldı: bunu hatırla; böylece ilanla yeniden
      // karşılaşınca yalnızca uyarı gösterilir ve asla bir model çağrısına mal olmaz.
      markReviewed(jobId, {
        ...cardMeta(card),
        fit: cachedFit(jobId),
        seenOnly: !CACHE.get(jobId),
      });
    } else if (label && warnedLabels.size < 8 && !warnedLabels.has(label)) {
      // Doğrulama sırasında DISMISS_RE/UNDO_RE'yi kullanıcının diline göre ayarlamaya yardım et.
      warnedLabels.add(label);
      console.warn(LOG, "card button click, unmatched aria-label:", label);
    }
  }

  function cachedFit(jobId) {
    const c = CACHE.get(jobId);
    return c && c.summary ? c.summary.fit_score : null;
  }

  // Ekrandaki ilanın başlığı/şirketi/uyumu: özet esastır, panel başlığı yedektir — eksi onun statik
  // "Job Summary" yer tutucusu; o asla sheet'in L sütununa gitmemeli.
  function jobMeta(jobId) {
    const c = CACHE.get(jobId);
    const headTitle = lastHeader.title === "Job Summary" ? "" : lastHeader.title;
    return {
      title: (c && c.summary && c.summary.job_title) || headTitle || "",
      company: (c && c.summary && c.summary.company) || lastHeader.company || "",
      fit: cachedFit(jobId),
    };
  }

  // --- Panel: <html> altına eklenir, silinirse yeniden oluşturulur ---

  function buildPanel() {
    const panel = document.createElement("div");
    panel.id = "jobsum-panel";
    panel.innerHTML = `
      <div id="jobsum-header">
        <div id="jobsum-actions">
          <button id="jobsum-add" type="button" title="İlanı tabloya ekle (CV için sheet'te B sütununu Üretilecek yap)" aria-label="İlanı tabloya ekle">Ekle</button>
          <button id="jobsum-refresh" type="button" title="Özeti yeniden oluştur" aria-label="Özeti yeniden oluştur">Yenile</button>
          <button id="jobsum-cover" type="button" title="Bu ilan için cover letter" aria-label="Bu ilan için cover letter">Mektup</button>
          <button id="jobsum-list" type="button" title="İncelenen ilanlar" aria-label="İncelenen ilanlar">Liste</button>
          <button id="jobsum-maybe-list" type="button" title="Olabilir listesi" aria-label="Olabilir listesi">Olabilir</button>
          <button id="jobsum-close" title="Close" aria-label="Close">×</button>
        </div>
        <div id="jobsum-heading">
          <span id="jobsum-title">${escapeHtml(lastHeader.title)}</span>
          <span id="jobsum-company">${escapeHtml(lastHeader.company)}</span>
        </div>
      </div>
      <div id="jobsum-review"></div>
      <div id="jobsum-body">${lastBodyHtml}</div>
    `;
    panel.querySelector("#jobsum-close").addEventListener("click", () => {
      userClosed = true;
      panel.remove();
    });
    panel.querySelector("#jobsum-add").addEventListener("click", addCurrentJob);
    panel.querySelector("#jobsum-refresh").addEventListener("click", refreshSummary);
    panel.querySelector("#jobsum-cover").addEventListener("click", () => toggleCover());
    panel
      .querySelector("#jobsum-list")
      .addEventListener("click", () => showList("reviewed"));
    panel
      .querySelector("#jobsum-maybe-list")
      .addEventListener("click", () => showList("maybe"));
    updateHeaderButtons(panel);
    return panel;
  }

  // --- İşaret listesi görünümleri ----------------------------------------------------
  // İki başlık butonu, işaretlenmiş ilanların (başlık/şirket/uyum/ne zaman) listesini LinkedIn'in
  // kanonik ilan URL'sine linkle aç/kapa yapar — işaretli bir ilan aramayla artık bulunamadığında
  // işe yarar. "Liste" incelenen ilanları, "Olabilir" sonra dönülecek stack'i uyan kısa listeyi
  // gösterir.

  function markerJobUrl(jobId) {
    return `https://www.linkedin.com/jobs/view/${encodeURIComponent(jobId)}/`;
  }

  function renderMarkerList(kind) {
    const store = kind === "maybe" ? maybe : reviewed;
    const headLabel = kind === "maybe" ? "Olabilir" : "İncelenen ilanlar";
    const emptyLabel =
      kind === "maybe"
        ? 'Henüz "Olabilir" ilan yok.'
        : "Henüz incelenen ilan yok.";
    const entries = store.entries().sort((a, b) => (b[1].t || 0) - (a[1].t || 0));
    if (!entries.length) {
      return `<div class="jobsum-status">${emptyLabel}</div>`;
    }
    const items = entries
      .map(([id, v]) => {
        const title = escapeHtml(v.title || `İlan ${id}`);
        const company = escapeHtml(v.company || "");
        const fit = v.fit != null ? `%${v.fit}` : "";
        const when = v.t ? escapeHtml(relativeTime(v.t)) : "";
        const sub = [company, fit, when].filter(Boolean).join(" · ");
        return `
        <div class="jobsum-listitem">
          <a href="${markerJobUrl(id)}" target="_blank" rel="noopener">
            <span class="jobsum-listitem-title">${title}</span>
            <span class="jobsum-listitem-sub">${sub}</span>
          </a>
          <button class="jobsum-listitem-remove" type="button" data-jid="${escapeHtml(
            id
          )}" title="Kaldır" aria-label="Kaldır">×</button>
        </div>`;
      })
      .join("");
    return `<div class="jobsum-listhead">${headLabel} (${entries.length})</div>${items}`;
  }

  function attachListHandlers() {
    const panel = document.getElementById("jobsum-panel");
    if (!panel) return;
    const store = listKind === "maybe" ? maybe : reviewed;
    panel.querySelectorAll(".jobsum-listitem-remove").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        store.unmark(btn.getAttribute("data-jid"));
        if (showingList) {
          setBody(renderMarkerList(listKind)); // listeyi yerinde yenile
          attachListHandlers();
        }
      });
    });
  }

  // Hangi görünümün etkin olduğunu başlık butonlarına yansıt. `jobIdArg` çağıranın çizdiği ilandır;
  // elinde olduğunda her zaman geçir (aşağıdaki "Ekle" notuna bak).
  function updateHeaderButtons(panelArg, jobIdArg) {
    const panel = panelArg || document.getElementById("jobsum-panel");
    if (!panel) return;
    const lb = panel.querySelector("#jobsum-list");
    const mb = panel.querySelector("#jobsum-maybe-list");
    const cb = panel.querySelector("#jobsum-cover");
    if (lb) lb.classList.toggle("is-active", showingList && listKind === "reviewed");
    if (mb) mb.classList.toggle("is-active", showingList && listKind === "maybe");
    if (cb) cb.classList.toggle("is-active", showingCover);

    // "Ekle" bir görünüm düğmesi değil — ilan başına durumu yansıtır. buildPanel() başlığı statik bir
    // HTML metninden geri yükler; yani bu olmadan etiket her yeniden kurulumda "Ekle"ye döner.
    // Geçici etiket 700 ms'lik yoklamadan sağ çıksın diye yanıp sönme sırasında atlanır.
    const ab = panel.querySelector("#jobsum-add");
    if (ab && !addBusy) {
      // No, varsa çağırandan GELMELİ. renderReviewStatus maybeUpdate'in en başında, lastJobId aşağıda
      // yeniden atanmadan ÖNCE çalışır; yani burada lastJobId'yi okumak butonu az önce ayrıldığımız
      // ilana göre etiketler — ve o çağrı reviewRenderKey ile hafızaya alındığından bir daha çalışmaz,
      // yanlış etiket takılı kalır. Çağıran yoksa (kullanıcı eylemleri) canlı sayfa son özetlenen
      // ilandan üstündür.
      const jobId = jobIdArg !== undefined ? jobIdArg : getCurrentJobId() || lastJobId;
      const done = isAdded(jobId);
      ab.textContent = done ? "Eklendi ✓" : "Ekle";
      ab.classList.toggle("is-active", done);
      ab.disabled = false;
    }
  }

  // Bir listeden ya da mektuptan özet görünümüne geri dön.
  function backToSummary() {
    showingList = false;
    showingCover = false;
    coverJobId = null;
    updateHeaderButtons();
    reviewRenderKey = null;
    lastJobId = null;
    scheduleUpdate();
  }

  function showList(kind) {
    // Zaten açık listeye tıklamak onu kapatır ve özete döner.
    if (showingList && listKind === kind) {
      backToSummary();
      return;
    }
    showingCover = false; // bir liste ve bir mektup gövdeye aynı anda sahip olamaz
    coverJobId = null;
    showingList = true;
    listKind = kind;
    updateHeaderButtons();
    setBody(renderMarkerList(kind));
    attachListHandlers();
  }

  // İnceleme durumu bloğu (başlığın altında): uyarı bandı + mevcut ilan için işaretle/kaldır
  // düğmesi. Yalnızca (ilan, incelendi) durumu değişince yeniden çizilir.
  let reviewRenderKey = null;
  function renderReviewStatus(jobId) {
    const panel = ensurePanel();
    if (!panel) return;
    const slot = panel.querySelector("#jobsum-review");
    if (!slot) return;

    const key = `${jobId || ""}:${isReviewed(jobId)}:${isMaybe(jobId)}:${isAdded(jobId)}`;
    if (key === reviewRenderKey) return; // hiçbir şey değişmedi
    reviewRenderKey = key;
    updateHeaderButtons(panel, jobId); // "Ekle" etiketi de ilan başına durumdur

    if (!jobId) {
      slot.className = "jobsum-review";
      slot.innerHTML = "";
      return;
    }

    const reviewedNow = isReviewed(jobId);
    const maybeNow = isMaybe(jobId);
    slot.className = reviewedNow ? "jobsum-review jobsum-review--seen" : "jobsum-review";

    // Sol taraf: incelendi durumu (uyarı + geri al, ya da "incelendi olarak işaretle" butonu).
    const reviewedHtml = reviewedNow
      ? `<span class="jobsum-review-text"><span class="jobsum-warn-icon">⚠</span> Bu ilanı ${escapeHtml(
          relativeTime(reviewed.get(jobId).t || Date.now())
        )} gördün</span>
         <button class="jobsum-review-btn jobsum-review-btn--undo" data-act="unreview" type="button">Geri al</button>`
      : `<button class="jobsum-review-btn" data-act="review" type="button">İncelendi</button>`;

    // Sağ taraf: bağımsız "Olabilir" kısa liste düğmesi.
    const maybeHtml = `<button class="jobsum-review-btn jobsum-review-btn--maybe${
      maybeNow ? " is-active" : ""
    }" data-act="maybe" type="button">${maybeNow ? "Olabilir ✓" : "Olabilir"}</button>`;

    slot.innerHTML = reviewedHtml + maybeHtml;

    // İşaretli girdi listesinde düzgün görünsün diye başlık/şirket/uyumun anlık görüntüsünü al.
    const meta = () => jobMeta(jobId);

    slot.querySelectorAll("button").forEach((btn) => {
      const act = btn.getAttribute("data-act");
      btn.addEventListener("click", () => {
        if (act === "review") markReviewed(jobId, meta());
        else if (act === "unreview") unmarkReviewed(jobId);
        else if (act === "maybe")
          isMaybe(jobId) ? maybe.unmark(jobId) : maybe.mark(jobId, meta());
      });
    });
  }

  // Başlık: pozisyon başlığı üstte, şirket altında (LinkedIn'in üst kartı gibi). Bir ilan
  // özetlenene kadar statik "Job Summary" etiketine düşer.
  function setHeader(title, company) {
    lastHeader = {
      title: (title || "").trim() || "Job Summary",
      company: (company || "").trim(),
    };
    const panel = ensurePanel();
    if (!panel) return;
    panel.querySelector("#jobsum-title").textContent = lastHeader.title;
    panel.querySelector("#jobsum-company").textContent = lastHeader.company;
  }

  function ensurePanel() {
    if (!isJobsPage()) return null;
    if (userClosed) return null;
    let panel = document.getElementById("jobsum-panel");
    if (!panel) {
      panel = buildPanel();
      document.documentElement.appendChild(panel);
      console.log(LOG, "panel added");
      // Gövdeye hangi görünüm sahipse onu yeniden bağla. buildPanel onu kaydedilmiş HTML metninden
      // geri yükler; yani bu olmadan butonları canlı görünen ölü işaretleme olarak geri gelir —
      // mektubun Kopyala'sı sessizce hiçbir şey yapmazdı.
      if (showingList) attachListHandlers();
      else if (showingCover) attachCoverHandlers();
    }
    return panel;
  }

  function setBody(html) {
    lastBodyHtml = html;
    const panel = ensurePanel();
    if (!panel) return;
    panel.querySelector("#jobsum-body").innerHTML = html;
  }

  function showLoading() {
    if (bodyLocked()) return; // liste / mektup görünümünü ezme
    setBody(
      `<div class="jobsum-loading">
         <span class="jobsum-spinner" aria-hidden="true"></span>
         <span>Özet hazırlanıyor…</span>
       </div>`
    );
  }

  function showError(message) {
    if (bodyLocked()) return;
    setBody(`<div class="jobsum-status jobsum-error">${escapeHtml(message)}</div>`);
  }

  // Hiç özetlenmeden listeden kapatılmış bir ilan. "Zaten incelendi" bandı bunun üstünde durur;
  // gövde yalnızca neden gösterilecek bir şey olmadığını açıklar.
  function showSeenOnly() {
    if (bodyLocked()) return;
    setBody(
      `<div class="jobsum-status">Bu ilanı listeden elemiştin; özet oluşturulmadı.</div>`
    );
  }

  function renderSummary(data) {
    if (bodyLocked()) return;
    // Claude'un ilandan çıkardığını tercih et; DOM seçicilerine düş (yalnızca LinkedIn'in eski
    // arayüzüyle eşleşirler).
    setHeader(
      data.job_title || firstMatchText(SELECTORS.title),
      data.company || firstMatchText(SELECTORS.company)
    );
    // Tek satırlık çalışma alanını oluştur: "on-site — İstanbul tercihli".
    const workType =
      data.work_type && data.work_type !== "unspecified" ? data.work_type : "";
    data = { ...data, work: [workType, data.work_type_note].filter(Boolean).join(" — ") };
    const rows = FIELDS.map((field) => {
      const rendered =
        field.key === "stack"
          ? renderStack(data.stack, data.stack_known)
          : renderValue(data[field.key]);
      if (rendered === null) return "";
      return `
        <div class="jobsum-row">
          <div class="jobsum-label">${escapeHtml(field.label)}</div>
          <div class="jobsum-value">${rendered}</div>
        </div>`;
    }).join("");
    setBody(
      renderFit(data.fit_score, data.fit_reason) +
        (rows || `<div class="jobsum-status">No information to summarize.</div>`)
    );
  }

  // Üstte uyum rozeti: renkli %NN + tek satırlık gerekçe. Puan yoksa gizli.
  function renderFit(score, reason) {
    const n = Math.round(Number(score) || 0);
    if (n <= 0) return "";
    const band = n >= 70 ? "high" : n >= 40 ? "mid" : "low";
    const reasonHtml = reason
      ? `<span class="jobsum-fit-reason">${escapeHtml(String(reason))}</span>`
      : "";
    return `
      <div class="jobsum-fit jobsum-fit--${band}">
        <div class="jobsum-label">Uygunluk</div>
        <div class="jobsum-fit-body">
          <span class="jobsum-fit-score">%${n}</span>
          ${reasonHtml}
        </div>
      </div>`;
  }

  // Stack: teknoloji başına bir çip — aday biliyorsa yeşil, bilmiyorsa kırmızı (`stack_known`,
  // backend'in CV + geçmiş projelere göre hesapladığı).
  //
  // Birkaç seçenekli bir grup, ilanın kendisinin sunduğu bir seçimdir ("React, Next.js veya
  // benzeri"); kendi satırını alır ve "veya" diye etiketlenir. Geri kalan her şey düz bir
  // gereksinimdir ve hepsi panel genişliğinde kayan tek bir satırı paylaşır — her birine bir satır
  // panelin çoğunu boşa harcardı.
  function renderStack(groups, known) {
    if (!Array.isArray(groups) || groups.length === 0) return null;

    const chip = (option, flag) => {
      // Hiç bayrak yok (backend'de aday profili yok): her gereksinimi kırmızıya boyamak yerine
      // nötr kal.
      const state = typeof flag === "boolean" ? (flag ? "known" : "missing") : "";
      const cls = state ? ` jobsum-chip--${state}` : "";
      return `<span class="jobsum-chip${cls}">${escapeHtml(String(option))}</span>`;
    };

    const altRows = [];
    const required = [];
    groups.forEach((group, gi) => {
      const options = (Array.isArray(group) ? group : [group]).filter(Boolean);
      if (options.length === 0) return;
      const flags = (Array.isArray(known) && known[gi]) || [];
      if (options.length === 1) {
        required.push(chip(options[0], flags[0]));
        return;
      }
      const chips = options.map((option, oi) => chip(option, flags[oi])).join("");
      altRows.push(
        `<div class="jobsum-stack-row jobsum-stack-row--alt">` +
          `<span class="jobsum-stack-alt">veya</span>` +
          `<div class="jobsum-stack-chips">${chips}</div></div>`
      );
    });

    if (required.length) {
      altRows.push(
        `<div class="jobsum-stack-row"><div class="jobsum-stack-chips">${required.join(
          ""
        )}</div></div>`
      );
    }
    return altRows.join("") || null;
  }

  function renderValue(value) {
    if (value === null || value === undefined) return null;
    if (Array.isArray(value)) {
      if (value.length === 0) return null;
      return value
        .map((v) => `<span class="jobsum-chip">${escapeHtml(String(v))}</span>`)
        .join(" ");
    }
    const str = String(value).trim();
    if (!str || str.toLowerCase() === "unspecified") return null;
    return escapeHtml(str);
  }

  function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
  }

  // Bir backend özeti gösterilmeye değer hiçbir şey taşımıyorsa true — başlık yok, uyum yok, stack
  // yok, alan yok. Okuduğumuz metin aslında bir ilan değilse olur (model o zaman her alanı boş
  // doldurur); bazı yerleşimlerde çıkarmamızın yanlış kapsayıcıyı yakaladığının TEK işareti budur.
  // Bir okuma hatası gibi ele alınır.
  function summaryIsBlank(data) {
    if (!data) return true;
    if (data.job_title || data.company) return false;
    if (Math.round(Number(data.fit_score) || 0) > 0) return false;
    const stackHasContent =
      Array.isArray(data.stack) &&
      data.stack.some((g) => (Array.isArray(g) ? g.length > 0 : !!g));
    if (stackHasContent) return false;
    return !FIELDS.some(
      (f) => f.key !== "stack" && renderValue(data[f.key]) !== null
    );
  }

  // --- Ana akış ---

  // Backend'i çağır (yalnızca kendi localhost servisimiz). `type` rotayı seçer —
  // bkz. background.js'teki ROUTES.
  function callBackend(type, payload) {
    return new Promise((resolve, reject) => {
      if (!extensionAlive()) {
        reject(new Error("Extension reloaded. Refresh the page."));
        return;
      }
      let sending;
      try {
        sending = chrome.runtime.sendMessage(
          { type, payload },
          (response) => {
            if (chrome.runtime.lastError) {
              reject(new Error("Extension messaging error. Reload the page."));
              return;
            }
            handle(response);
          }
        );
      } catch (_) {
        reject(new Error("Extension reloaded. Refresh the page."));
        return;
      }
      // Bazı Chrome sürümleri callback kullanmak yerine bir Promise döndürür.
      if (sending && typeof sending.then === "function") {
        sending.then(handle, () =>
          reject(new Error("Extension messaging error. Reload the page."))
        );
      }

      function handle(response) {
        if (!response) {
          reject(new Error("No response from backend."));
          return;
        }
        if (!response.ok) {
          reject(new Error(response.error || "Unknown error."));
          return;
        }
        resolve(response.data);
      }
    });
  }

  // maybeUpdate'in zincirini yansıtan 3 katmanlı açıklama çıkarma. "Yenile" butonu, yeniden
  // hesaplamadan önce mevcut sayfanın metnini yeniden okumak için kullanır.
  function getDescription() {
    // Yalnızca sezgisel, kabuk reddedilmiş (seçicilerin neden dışarıda olduğu için bkz. maybeUpdate).
    return nonChrome(heuristicDescription());
  }

  // "Yenile": mevcut ilanın özetini şu an ekrandaki metinden yeniden hesaplar (ör. ilk
  // önbelleğe alındığı arama sayfasından daha temiz bir /jobs/view sayfası); iki önbelleği de
  // atlar ve taze sonuçla üzerlerine yazar.
  function refreshSummary() {
    if (bodyLocked()) return; // yalnızca özet görünümünde anlamlı
    const jobId = lastJobId || getCurrentJobId();
    if (!jobId) return;
    const description = getDescription();
    if (!description || description.length < 40) {
      showError("Açıklama bulunamadı; özet yenilenemedi.");
      return;
    }
    CACHE.delete(jobId); // bayat istemci tarafı kopyayı at
    // Açık bir "Yenile" listeden kapatmayı geçersiz kılar: bundan sonra özetle.
    if (isReviewed(jobId)) markReviewed(jobId, { seenOnly: false });
    lastShownDescription = description;
    showLoading();
    requestSummary(jobId, description, { force: true });
  }

  // --- "Ekle": bu ilanı sheet'e ekle ------------------------------
  // Backend link (K) + başlık (L) + şirket (J) yazar ve CV No'yu (N) boş bırakır. Kullanıcı
  // başvururken B'yi "Üretilecek" yapınca CV agent'ı satırı alır. İlan metni de birlikte gider
  // ve sunucu tarafında KAYDEDİLİR: CV agent'ı sayfayı yine kendisi okur (birincil kaynak); bu
  // metin yalnızca ilan kalkmışsa ve kullanıcı --allow-staged isterse kullanılır.

  let addBusy = false;
  const ADD_TITLE = "İlanı tabloya ekle (CV için sheet'te B sütununu Üretilecek yap)";

  function addCurrentJob() {
    if (addBusy) return; // bir çift tıklama iki kez eklememeli
    const btn = document.getElementById("jobsum-add");
    const jobId = lastJobId || getCurrentJobId();
    if (!jobId) {
      flashAdd(btn, "İlan yok");
      return;
    }
    // lastShownDescription panelin BU ilan için gerçekten özetlediği metindir; onu tercih et.
    // DOM'u yalnızca özet henüz gelmediyse (ya da başka bir ilana aitse) yeniden oku. Hiçbir şey
    // göndermemek de sorun değil — birincil kaynak scrape.
    const fresh = jobId === lastJobId ? lastShownDescription : "";
    const description = fresh || getDescription() || "";
    const meta = jobMeta(jobId);

    addBusy = true;
    if (btn) {
      btn.disabled = true;
      btn.textContent = "Ekleniyor…";
    }
    callBackend("ADD_JOB", {
      job_id: jobId,
      url: markerJobUrl(jobId), // kanonik /jobs/view/<id>/ — bkz. _canonical_link
      title: meta.title,
      company: meta.company,
      description,
    })
      .then((data) => {
        added.mark(jobId, meta);
        console.log(LOG, "add-job:", data.status, "row", data.row);
        let label;
        if (data.status === "exists") {
          label = data.cv_no ? `Zaten var · CV ${data.cv_no}` : "Zaten var";
        } else {
          label = data.staged ? "Eklendi ✓" : "Eklendi (metin yok)";
        }
        flashAdd(btn, label);
      })
      .catch((err) => {
        console.warn(LOG, "add-job error:", err.message);
        flashAdd(btn, "Hata", err.message);
      });
  }

  // Butonda geçici etiket (mektubun "Kopyala"sıyla aynı desen), sonra kalıcı durum ne diyorsa ona
  // dön. Gövdeye asla dokunmaz: bir kayıt işlemi kullanıcının okuduğu özeti ezmemeli.
  function flashAdd(btn, label, tooltip) {
    if (!btn) {
      addBusy = false;
      return;
    }
    btn.textContent = label;
    if (tooltip) btn.title = tooltip;
    setTimeout(() => {
      addBusy = false;
      btn.title = ADD_TITLE;
      updateHeaderButtons();
    }, 2200);
  }

  // --- Cover letter ---------------------------------------------------------
  // Backend mektubu diske zaten kaydedilmiş CV ve ilan metninden kurar (sheet'teki CV No'ya göre);
  // yani burada hiçbir şey okunmaz — istek sadece ilan no'sudur. Mektup yoksa backend mektup
  // agent'ını çalıştırır (~30-60 sn). (İlan, dil) başına bir kez üretilir; yeniden istemek sadece
  // dosyayı yeniden okur.

  function toggleCover() {
    if (showingCover) {
      backToSummary(); // Mektup'a yeniden tıklamak mektubu kapatır
      return;
    }
    const jobId = lastJobId || getCurrentJobId();
    if (!jobId) return;
    showingList = false;
    showingCover = true;
    coverJobId = jobId;
    updateHeaderButtons();
    fetchCover({ force: false });
  }

  // Kullanıcı başka bir ilana geçince mektubu bırak. Bir mektup tam olarak bir ilana aittir ve
  // maybeUpdate() ilan değişince başlığı boşaltır — yani açık kalan bir mektup yanlış ilanın
  // başlığı altında durur ve yanlışlıkla kopyalanırdı.
  function exitCoverView() {
    showingCover = false;
    coverJobId = null;
    updateHeaderButtons();
  }

  function fetchCover(opts) {
    const jobId = coverJobId;
    const force = !!(opts && opts.force);
    setCoverBody(
      `<div class="jobsum-loading">
         <span class="jobsum-spinner" aria-hidden="true"></span>
         <span>${force ? "Mektup yeniden yazılıyor…" : "Mektup hazırlanıyor…"}</span>
       </div>`
    );
    callBackend("COVER_LETTER", { job_id: jobId, lang: coverLang, force })
      .then((data) => {
        if (!showingCover || coverJobId !== jobId) return; // kullanıcı başka ilana geçti
        renderCover(data);
      })
      .catch((err) => {
        if (!showingCover || coverJobId !== jobId) return;
        setCoverBody(
          `<div class="jobsum-status jobsum-error">${escapeHtml(err.message)}</div>`
        );
      });
  }

  // Gövdeye, özet çizicilerinin kullandığı bodyLocked() koruması OLMADAN yaz — o korumalar
  // özetin bu görünümü ezmesini engellemek için var, tersini değil.
  function setCoverBody(html) {
    lastBodyHtml = html;
    const panel = ensurePanel();
    if (!panel) return;
    panel.querySelector("#jobsum-body").innerHTML = html;
  }

  function renderCover(data) {
    const langRow = ["en", "tr"]
      .map(
        (l) =>
          `<button class="jobsum-review-btn${
            l === coverLang ? " is-active" : ""
          }" data-cover="lang" data-lang="${l}" type="button">${l.toUpperCase()}</button>`
      )
      .join("");
    setCoverBody(
      `<div class="jobsum-cover-actions">
         ${langRow}
         <button class="jobsum-review-btn" data-cover="copy" type="button">Kopyala</button>
         <button class="jobsum-review-btn" data-cover="force" type="button">Yeniden üret</button>
       </div>
       <div class="jobsum-cover-meta">CV ${data.cv_no} · ${
        data.created ? "yeni üretildi" : "kayıtlı mektup"
      }</div>
       <div class="jobsum-cover-text">${escapeHtml(coverBody(data.text))}</div>`
    );
    attachCoverHandlers();
  }

  // Backend'in dosyaya yazdığı `<!-- cv_no: ... -->` kayıt başlığını at.
  function coverBody(text) {
    return text.replace(/^\s*<!--[^>]*-->\s*/, "").trim();
  }

  function attachCoverHandlers() {
    const panel = document.getElementById("jobsum-panel");
    if (!panel) return;
    panel.querySelectorAll("[data-cover]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const act = btn.getAttribute("data-cover");
        if (act === "copy") {
          // Tıklamanın içinde senkron çalışmalı: beklenen bir fetch'ten sonra kopyalamak kullanıcı
          // etkileşimini harcar ve yazma reddedilir.
          const text = panel.querySelector(".jobsum-cover-text");
          copyText(text ? text.textContent : "").then((ok) => {
            btn.textContent = ok ? "Kopyalandı ✓" : "Kopyalanamadı";
            setTimeout(() => (btn.textContent = "Kopyala"), 1500);
          });
        } else if (act === "force") {
          fetchCover({ force: true });
        } else if (act === "lang") {
          const lang = btn.getAttribute("data-lang");
          if (lang === coverLang) return;
          coverLang = lang;
          fetchCover({ force: false });
        }
      });
    });
  }

  async function copyText(text) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch (_) {
      // Pano API'si engellenmiş olabilir (izin politikası, etkileşim yok) — yedeğe düş.
      const ta = document.createElement("textarea");
      ta.value = text;
      ta.style.cssText = "position:fixed;left:-9999px;top:0;";
      document.documentElement.appendChild(ta);
      ta.select();
      let ok = false;
      try {
        ok = document.execCommand("copy");
      } catch (_) {
        ok = false;
      }
      ta.remove();
      return ok;
    }
  }

  function requestSummary(jobId, description, opts) {
    const payload = {
      text: description,
      title: firstMatchText(SELECTORS.title) || null,
      company: firstMatchText(SELECTORS.company) || null,
      location: firstMatchText(SELECTORS.location) || null,
      job_id: jobId || null, // sunucu buna göre önbelleğe alır, böylece bir ilan bir kez özetlenir
      refresh: !!(opts && opts.force), // "Yenile": önbelleği atla + üzerine yaz
    };

    const seq = ++requestSeq;
    console.log(LOG, "requesting summary:", payload.title || "(no title)");

    callBackend("SUMMARIZE", payload)
      .then((data) => {
        // Boş bir özet, okuduğumuz metnin gerçek bir ilan olmadığı anlamına gelir. Önbelleğe alma (ki
        // açıklama yüklenince sonraki bir Yenile / yeniden açma yine başarılı olabilsin), bir tanı dök
        // ve yükleme zaman aşımıyla aynı yeniden deneme ipucunu göster.
        if (summaryIsBlank(data)) {
          if (seq !== requestSeq || jobId !== lastJobId) return;
          console.warn(
            LOG,
            `backend summary was blank; sent ${description.length} chars:`,
            JSON.stringify(description.slice(0, 200))
          );
          logDomDiagnosis();
          showError(DESC_HINT);
          return;
        }
        cacheSet(jobId, data, description);
        if (seq !== requestSeq || jobId !== lastJobId) return; // bu arada ilan değişti
        console.log(LOG, "summary received");
        renderSummary(data);
      })
      .catch((err) => {
        if (seq !== requestSeq || jobId !== lastJobId) return;
        console.warn(LOG, "error:", err.message);
        showError(err.message);
      });
  }

  // --- İncelenmiş kart süslemesi ---------------------------------------------
  // LinkedIn'in kendi kapatması bir gün içinde unutulur: aynı ilan dokunulmamış görünerek geri
  // gelir. Bizim hafızamız kalıcıdır; bu yüzden onu karta boya — soluk, sol kenar boyunca mavi bir
  // şerit ve X butonunun yanında bir "görüldü" rozeti.
  //
  // Stil panel.css üzerinden değil, SATIR İÇİ uygulanır; iki nedenle: manifest'te bildirilen
  // stil sayfası yeni arayüzün kartları çizdiği shadow root'lara geçmez ve tek bir sınıf
  // LinkedIn'in kendi kurallarına yenilir. Aşağıdaki sınıflar yalnızca durum/arama işaretleri
  // olarak kalır.
  const SEEN_PROPS = ["opacity", "box-shadow", "position"];
  const BADGE_TEXT = "görüldü";

  function seenColors() {
    const dark =
      window.matchMedia &&
      window.matchMedia("(prefers-color-scheme: dark)").matches;
    return dark
      ? { bg: "#29343d", fg: "#a9b0b8", stripe: "#70b5f9" }
      : { bg: "#eef3f8", fg: "#57606a", stripe: "#0a66c2" };
  }

  function styleSeenCard(card, colors) {
    const s = card.style;
    s.setProperty("opacity", "0.5", "important");
    // içe doğru, böylece şerit yerleşime mal olmaz (border-left içeriği kaydırırdı).
    s.setProperty("box-shadow", `inset 4px 0 0 ${colors.stripe}`, "important");
    // Rozet absolute ve bir kapsayıcı blok gerektirir. Kartın doğal konumunu BİR KEZ oku ve öğenin
    // üzerinde önbelleğe al: sonraki bir tikte yeniden okumak az önce ayarladığımız "relative"i
    // görür ve kararı sonsuza kadar ileri geri çevirirdi.
    if (card.__jobsumPos === undefined)
      card.__jobsumPos = getComputedStyle(card).position;
    if (card.__jobsumPos === "static")
      s.setProperty("position", "relative", "important");
  }

  function makeSeenBadge(colors) {
    const badge = document.createElement("span");
    badge.className = "jobsum-seen-badge";
    badge.textContent = BADGE_TEXT;
    const s = badge.style;
    s.setProperty("position", "absolute", "important");
    s.setProperty("top", "4px", "important");
    s.setProperty("right", "4px", "important");
    s.setProperty("z-index", "5", "important");
    s.setProperty("background", colors.bg, "important");
    s.setProperty("color", colors.fg, "important");
    s.setProperty("border-radius", "10px", "important");
    s.setProperty("padding", "1px 7px", "important");
    s.setProperty("font-size", "10px", "important");
    s.setProperty("font-weight", "600", "important");
    s.setProperty("line-height", "16px", "important");
    // Rozet LinkedIn'in X butonunun üstünde durur — tıklamalar ona geçmeli.
    s.setProperty("pointer-events", "none", "important");
    return badge;
  }

  // Bizim sınıfımız ve rozetimiz birbirinden bağımsız iki kalıntı — LinkedIn'in kendi çizimi
  // ikisinden birini düşürebilir — bu yüzden "bu kart süslü mü?" ikisini de sormalı; yoksa geri
  // alınmış bir ilan sonsuza kadar soluk (ya da rozetli) kalabilir.
  function hasSeenDecoration(card) {
    return (
      card.classList.contains("jobsum-seen") ||
      !!card.querySelector(":scope > .jobsum-seen-badge")
    );
  }

  function clearSeenCard(card) {
    card.classList.remove("jobsum-seen");
    SEEN_PROPS.forEach((p) => card.style.removeProperty(p));
    const b = card.querySelector(":scope > .jobsum-seen-badge");
    if (b) b.remove();
  }

  let seenCounts = ""; // son loglanan sayım, böylece DEBUG yalnızca bir değişiklikte konuşur

  // Her tikte yeniden uygulanır: LinkedIn listeyi sanallaştırır (kartlar takılıp çıkarılır) ve bir
  // kartın çocuklarını yerinde yeniden çizer; bu da rozetimizi sessizce düşürür. Aynı satır içi
  // stilleri yeniden yazmak bedavadır ve — rozeti eklemenin aksine — hiçbir mutasyon tetiklemez,
  // yani bizi çağıran gözlemciyi besleyemez.
  function markSeenCards() {
    // collectRoots() her kökün her düğümünü dolaşır; bu her 700 ms'lik tikte harcanmak için fazla.
    // Sonuç listesi TEK bir uygulamayla çizilir; ana belge liste kartları tutuyorsa hepsi oradadır,
    // yalnızca hiç tutmuyorsa derin (shadow root + aynı kökenli iframe) taramanın bedelini öderiz.
    const cards = document.querySelector(LIST_CARD_SELECTOR)
      ? Array.from(document.querySelectorAll(CARD_SELECTOR))
      : deepQueryAll(CARD_SELECTOR);
    const colors = seenColors();
    let resolved = 0;
    let marked = 0;
    cards.forEach((card) => {
      if (card.closest("#jobsum-panel")) return; // kendi panelimize asla dokunma
      // Yeni arayüz componentkey'i iç içe bir div'de tekrarlar; yalnızca en dıştakine rozet koy.
      if (card.parentElement && card.parentElement.closest(CARD_SELECTOR)) return;
      // Bir LIST_CARD_SELECTOR eşleşmesi her zaman bir sol liste kartıdır. Düz [data-job-id] biçimi
      // öyle değil: büyük sağ detay paneli de onu taşıyabilir; orada yine metin uzunluğu karar verir.
      if (!card.matches(LIST_CARD_SELECTOR) && (card.innerText || "").length > 800)
        return;
      const id = cardJobId(card);
      if (!id) return;
      resolved++;
      if (isReviewed(id)) {
        marked++;
        card.classList.add("jobsum-seen");
        styleSeenCard(card, colors);
        if (!card.querySelector(":scope > .jobsum-seen-badge"))
          card.appendChild(makeSeenBadge(colors));
      } else if (hasSeenDecoration(card)) {
        clearSeenCard(card);
      }
    });
    if (DEBUG) {
      const tally = `${cards.length}/${resolved}/${marked}`;
      if (tally !== seenCounts) {
        seenCounts = tally;
        console.log(LOG, "DIAG cards scanned/with-id/seen:", tally);
      }
    }
  }

  function maybeUpdate() {
    // Eklenti yeniden yüklendikten sonra yetim kaldı: her şeyi durdur ve sessizleş.
    if (!extensionAlive()) {
      teardown();
      return;
    }
    // İş sayfalarının dışında (akış, mesajlar, bir profil, …) script etkisizdir: sekme içi önceki bir
    // gezinmeden kalan paneli kaldır ve çık.
    if (!isJobsPage()) {
      const stale = document.getElementById("jobsum-panel");
      if (stale) stale.remove();
      return;
    }
    ensurePanel(); // kaldırıldıysa paneli yeniden ekle
    markSeenCards(); // incelendi durumunu listeye yansıt

    const jobId = getCurrentJobId();
    renderReviewStatus(jobId); // bu ilan için panel bandını/düğmesini güncelle
    if (!jobId) return;

    // Bir mektup tam olarak bir ilana aittir. Kullanıcı başka ilana geçer geçmez görünümü bırak —
    // aşağıdaki dallar başlığı boşaltmadan önce; yoksa eski mektup yeni ilanın başlığı altında,
    // yanlışlıkla kopyalanmaya hazır dururdu. coverJobId'ye (mektubun kendi ilanı) göre anahtarlı;
    // böylece erken dönen aşağıdaki yalnızca-görüldü yolunu da kapsar.
    if (showingCover && coverJobId && jobId !== coverJobId) exitCoverView();

    // Hiç açılmadan listeden kapatıldı: yukarıdaki incelendi bandı hikâyenin tamamı; başka bir şey
    // gösterme ve buna asla bir model çağrısı harcama. Kullanıcı fikrini değiştirirse "Yenile" yine
    // gerçek bir özeti zorlar.
    if (isSeenOnly(jobId) && !CACHE.get(jobId)) {
      // `lastJobId` yerine ilana göre anahtarlı; böylece bir kapatma, zaten üzerinde olduğumuz ilandan
      // kalan bir "Özet hazırlanıyor…" ya da hata mesajının da yerini alır.
      if (seenOnlyShownFor !== jobId && !bodyLocked()) {
        seenOnlyShownFor = jobId;
        lastJobId = jobId;
        pendingJobId = null;
        lastShownDescription = "";
        const marker = reviewed.get(jobId) || {};
        setHeader(marker.title || "", marker.company || "");
        showSeenOnly();
      }
      return;
    }
    seenOnlyShownFor = null;

    // Yeni bir ilana geçildi: önce anında geri bildirim ver.
    if (jobId !== lastJobId) {
      lastJobId = jobId;
      const cached = CACHE.get(jobId);
      if (cached) {
        console.log(LOG, "from cache:", jobId);
        pendingJobId = null;
        lastShownDescription = cached.description;
        renderSummary(cached.summary); // anında
        return;
      }
      console.log(LOG, "new job detected:", jobId);
      pendingJobId = jobId;
      pendingSince = Date.now();
      pendingDesc = ""; // yeni ilan için kararlılık izleyicisini sıfırla
      pendingDescSince = Date.now();
      setHeader("", ""); // yüklenirken önceki ilanın başlığını at
      showLoading(); // eski özeti hemen temizle
    }

    // Bekleyen ilanın açıklaması yüklenince özetle.
    if (pendingJobId) {
      // YALNIZCA sezgisel yöntem. Eski sınıf seçicileri hash'li yeni arayüzün açıklamasıyla
      // eşleşmiyor — onun yerine SOL sonuç sütununa (filtre çubuğu ya da ilan kartı yığını) düşüyorlar;
      // model onu hiçe ya da YANLIŞ ilana özetliyor. Daha kötüsü, o sütun statik; kararlılık kapısından
      // kolayca geçti ve gerçek açıklama yüklenmeden gönderildi. `findLongestVisibleTextEl` liste
      // kartlarını atlar ve tıklanan ilanın açıklamasına güvenilir şekilde düşer (yeni ve eski arayüz);
      // bu yüzden yalnızca ona güven; hiçbir şey bulamazsa sadece bekleriz (bkz. aşağıdaki zaman aşımı).
      let description = nonChrome(heuristicDescription());
      // Göndermeden önce açıklamanın OTURMASINI bekle: yalnızca metin DESC_STABLE_MS boyunca değişmeyi
      // bıraktıktan sonra özetle. Akışın ortasındaki kısa bir duraklama (art arda iki eşit okumanın
      // "bitti" sanacağı) artık yarım yüklenmiş parçanın erken gönderilmesini tetiklemez.
      if (description !== pendingDesc) {
        pendingDesc = description;
        pendingDescSince = Date.now(); // hâlâ büyüyor — oturma zamanlayıcısını yeniden başlat
      }
      const stable =
        !!description && Date.now() - pendingDescSince >= DESC_STABLE_MS;
      if (
        stable &&
        description.length >= 40 &&
        description !== lastShownDescription // bayat (eski) metni özetleme
      ) {
        const targetJob = pendingJobId;
        pendingJobId = null;
        lastShownDescription = description;
        requestSummary(targetJob, description);
      } else if (Date.now() - pendingSince > DESC_LOAD_TIMEOUT_MS) {
        // Açıklama bu ilan için hiç okunabilir olmadı (sezgisel yöntemin kaçırdığı bir yerleşim). Dönen
        // simgeyi durdur, kullanıcıya nasıl yeniden deneyeceğini söyle ve başarısız DOM yapıştırılmış bir
        // konsol logundan düzeltilebilsin diye bir tanı dök.
        const stuckJob = pendingJobId;
        pendingJobId = null;
        console.warn(LOG, "description not found before timeout for job", stuckJob);
        logDomDiagnosis();
        showError(DESC_HINT);
      }
    }
  }

  // --- Değişiklik algılama ---

  let debounceTimer = null;
  function scheduleUpdate() {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(maybeUpdate, 120);
  }

  const observer = new MutationObserver(scheduleUpdate);
  observer.observe(document.documentElement, { childList: true, subtree: true });
  const pollTimer = setInterval(maybeUpdate, 700);

  // Sayfanın herhangi bir yerindeki kapatma/geri al tıklamalarını yakala.
  document.addEventListener("click", onDocClick, true);

  // Eklenti yeniden yüklendikten sonra bu (artık yetim) örneği sök; ölü bir bağlamı yoklamayı ve
  // konsolu doldurmayı bıraksın.
  let torndown = false;
  function teardown() {
    if (torndown) return;
    torndown = true;
    try {
      observer.disconnect();
    } catch (_) {
      /* yok say */
    }
    clearInterval(pollTimer);
    clearTimeout(debounceTimer);
    document.removeEventListener("click", onDocClick, true);
    const panel = document.getElementById("jobsum-panel");
    if (panel) panel.remove();
    console.log(LOG, "extension context gone; content script stopped");
  }

  reviewed.load(); // kalıcı "reviewed" / "maybe" / "added" hafızasını yükle, sonra yansıt
  maybe.load();
  added.load();
  ensurePanel();
  scheduleUpdate();
})();
