// Ruhemodus für den Touchmonitor im Flur: nach 7 Minuten ohne Berührung zeigt er das Ruhebild (Wappen, Uhr, Wetter,
// /flur-display/ruhe → www/ruhe.html). Antippen bringt die vorherige Seite zurück.
// Gilt nur für den Kiosk-Browser am Monitor (der öffnet Home Assistant über "localhost"), nicht für Handy/Laptop.
// Hausschriften (Cormorant Garamond + Montserrat, wie das Handbuch „Zuhause“) für das Theme – auf allen Geräten
(function () {
  if (document.getElementById("hausschrift")) return;
  const l = document.createElement("link");
  l.id = "hausschrift"; l.rel = "stylesheet";
  l.href = "https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@500;600;700&family=Montserrat:wght@400;500;600;700&display=swap";
  document.head.appendChild(l);
})();
(function () {
  if (location.hostname !== "localhost" || window.__ruhemodus) return;
  window.__ruhemodus = true;
  const WARTEN = 7 * 60 * 1000, RUHE = "/flur-display/ruhe";
  let zuletzt = Date.now();
  const aktiv = () => {
    zuletzt = Date.now();
    if (location.pathname === RUHE) {   // aus dem Ruhebild zurück
      let ziel = "/flur-display/start";
      try { ziel = sessionStorage.getItem("ruhe-zurueck") || ziel; } catch (e) { /* egal */ }
      gehe(ziel);
    }
  };
  function gehe(pfad) {
    history.pushState(null, "", pfad);
    window.dispatchEvent(new CustomEvent("location-changed", { detail: { replace: false } }));
  }
  ["pointerdown", "touchstart", "keydown", "wheel"].forEach(t => window.addEventListener(t, aktiv, { capture: true, passive: true }));
  // Im Ruhebild die Kopfleiste von Home Assistant dunkel färben (auch wenn das Design gerade hell ist)
  const DUNKEL = { "--app-header-background-color": "#0E1012", "--app-header-text-color": "#C9CED6",
    "--app-header-border-bottom": "none", "--primary-text-color": "#C9CED6", "--sidebar-icon-color": "#C9CED6" };
  function suche(wurzel, name) {
    for (const el of wurzel.querySelectorAll("*")) {
      if (el.tagName === name) return el;
      if (el.shadowRoot) { const t = suche(el.shadowRoot, name); if (t) return t; }
    }
    return null;
  }
  let gefaerbt = null;
  function kopfleiste() {
    const ruhe = location.pathname === RUHE;
    if (ruhe && !gefaerbt) {
      gefaerbt = suche(document, "HUI-ROOT");
      if (gefaerbt) Object.entries(DUNKEL).forEach(([k, v]) => gefaerbt.style.setProperty(k, v));
    } else if (!ruhe && gefaerbt) {
      Object.keys(DUNKEL).forEach(k => gefaerbt.style.removeProperty(k));
      gefaerbt = null;
    }
  }
  window.addEventListener("location-changed", () => setTimeout(kopfleiste, 50));
  // Berührungen in eingebetteten Seiten (Garten, Akte, Eingang …) zählen auch: Zuhörer in alle Iframes hängen
  function iframes(wurzel, liste) {
    wurzel.querySelectorAll("*").forEach(el => {
      if (el.tagName === "IFRAME") liste.push(el);
      if (el.shadowRoot) iframes(el.shadowRoot, liste);
    });
    return liste;
  }
  setInterval(() => {
    iframes(document, []).forEach(f => {
      try {
        const w = f.contentWindow;
        if (w && !w.__ruheZuhoerer) {
          w.__ruheZuhoerer = true;
          ["pointerdown", "touchstart", "keydown", "wheel"].forEach(t => w.addEventListener(t, aktiv, { capture: true, passive: true }));
        }
      } catch (e) { /* fremde Seite */ }
    });
    kopfleiste();
    if (Date.now() - zuletzt > WARTEN && location.pathname.startsWith("/flur-display/")
        && location.pathname !== RUHE && !location.pathname.includes("kamera")) {
      try { sessionStorage.setItem("ruhe-zurueck", location.pathname + location.hash); } catch (e) { /* egal */ }
      gehe(RUHE);
    }
  }, 5000);
})();
