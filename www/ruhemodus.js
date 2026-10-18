// Ruhemodus für den Touchmonitor im Flur: nach 7 Minuten ohne Berührung zeigt er das Ruhebild (Wappen, Uhr, Wetter,
// /flur-display/ruhe → www/ruhe.html). Antippen bringt die vorherige Seite zurück.
// Gilt nur für den Kiosk-Browser am Monitor (der öffnet Home Assistant über "localhost"), nicht für Handy/Laptop.
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
    if (Date.now() - zuletzt > WARTEN && location.pathname.startsWith("/flur-display/")
        && location.pathname !== RUHE && !location.pathname.includes("kamera")) {
      try { sessionStorage.setItem("ruhe-zurueck", location.pathname + location.hash); } catch (e) { /* egal */ }
      gehe(RUHE);
    }
  }, 5000);
})();
