// Familienwappen für die Oberfläche: lädt das Wappen über die Home-Assistant-Anmeldung
// (script.akte_aktion, was: wappen_lesen – das Bild liegt nicht öffentlich), stellt es frei
// und merkt es sich im Browser. Dazu die Karte "custom:familie-gruss" für die Startseite.
(() => {
  if (window.familieWappen) return;
  const MERKER = "familie-wappen-v1";
  let laden = null;

  // Weißen Hintergrund um das Wappen durchsichtig machen: nur Weiß, das mit dem Bildrand verbunden ist
  // (weiße Flächen im Wappen selbst, z. B. das Schachbrett, bleiben), Kante weich auslaufen lassen
  async function freistellen(url, hoehe) {
    const img = new Image(); await new Promise((ok, f) => { img.onload = ok; img.onerror = f; img.src = url; });
    const faktor = Math.min(1, hoehe / img.height);
    const c = document.createElement("canvas"), w = c.width = Math.round(img.width * faktor), h = c.height = Math.round(img.height * faktor), g = c.getContext("2d");
    g.drawImage(img, 0, 0, w, h);
    const d = g.getImageData(0, 0, w, h), p = d.data, gesehen = new Uint8Array(w * h), stapel = [];
    const hell = i => Math.min(p[i * 4], p[i * 4 + 1], p[i * 4 + 2]);
    for (let x = 0; x < w; x++) stapel.push(x, (h - 1) * w + x);
    for (let y = 0; y < h; y++) stapel.push(y * w, y * w + w - 1);
    while (stapel.length) {
      const i = stapel.pop();
      if (gesehen[i] || hell(i) < 225) continue;
      gesehen[i] = 1;
      p[i * 4 + 3] = Math.max(0, Math.min(255, (255 - hell(i)) * 8));
      const x = i % w, y = (i / w) | 0;
      if (x > 0) stapel.push(i - 1); if (x < w - 1) stapel.push(i + 1);
      if (y > 0) stapel.push(i - w); if (y < h - 1) stapel.push(i + w);
    }
    // eingeschlossene, reinweiße Flächen zwischen Helmdecke und Schild (größer als ein Schachbrettfeld) auch ausblenden
    const gross = Math.max(400, w * h / 300);
    for (let s0 = 0; s0 < w * h; s0++) {
      if (gesehen[s0] || hell(s0) < 246) continue;
      const feld = [s0], rand = []; gesehen[s0] = 2;
      for (let k = 0; k < feld.length; k++) {
        const i = feld[k], x = i % w, y = (i / w) | 0;
        for (const n of [x > 0 ? i - 1 : -1, x < w - 1 ? i + 1 : -1, y > 0 ? i - w : -1, y < h - 1 ? i + w : -1]) {
          if (n < 0 || gesehen[n]) continue;
          if (hell(n) >= 246) { gesehen[n] = 2; feld.push(n); } else if (hell(n) >= 215) rand.push(n);
        }
      }
      if (feld.length > gross) {
        for (const i of feld) p[i * 4 + 3] = 0;
        for (const i of rand) p[i * 4 + 3] = Math.min(p[i * 4 + 3], Math.max(0, (255 - hell(i)) * 6));
      }
    }
    g.putImageData(d, 0, 0);
    return c.toDataURL("image/png");
  }

  // Liefert das freigestellte Wappen als Bild-Adresse (data:…) oder "" wenn noch keins hinterlegt ist.
  // Erst aus dem Browser-Speicher (schnell), dann im Hintergrund frisch vom Server.
  window.familieWappen = (hass) => {
    let gemerkt = "";
    try { gemerkt = localStorage.getItem(MERKER) || ""; } catch (e) { /* ohne Speicher */ }
    if (!laden && hass) {
      laden = (async () => {
        try {
          const r = await hass.callWS({ type: "call_service", domain: "script", service: "akte_aktion", service_data: { was: "wappen_lesen" }, return_response: true });
          let a = r && r.response && r.response.stdout; if (typeof a === "string") a = JSON.parse(a);
          if (!a || !a.bild) return gemerkt;
          const bild = await freistellen("data:image/jpeg;base64," + a.bild, 360);
          try { localStorage.setItem(MERKER, bild); } catch (e) { /* zu groß oder gesperrt */ }
          return bild;
        } catch (e) { laden = null; return gemerkt; }
      })();
    }
    return gemerkt ? Promise.resolve(gemerkt) : (laden || Promise.resolve(""));
  };

  // Begrüßung oben auf der Startseite: Wappen, Tageszeit-Gruß, Datum
  if (!window.customElements || customElements.get("familie-gruss")) return;
  class FamilieGruss extends HTMLElement {
    setConfig(config) { this.config = config || {}; }
    getCardSize() { return 2; }
    getGridOptions() { return { columns: "full", rows: 2 }; }
    set hass(hass) {
      this._hass = hass;
      if (!this.shadowRoot) this.aufbauen();
      if (!this._wappen) {
        this._wappen = true;
        window.familieWappen(hass).then(bild => {
          const img = this.shadowRoot.querySelector("img");
          if (bild) { img.src = bild; img.hidden = false; } else this._wappen = false;
        });
      }
      this.zeichnen();
    }
    aufbauen() {
      this.attachShadow({ mode: "open" }).innerHTML = `
        <style>
          ha-card { display:flex; align-items:center; gap:18px; padding:14px 20px; height:100%; box-sizing:border-box;
            background: linear-gradient(120deg, rgba(212,175,55,.16), rgba(212,175,55,0) 70%), var(--ha-card-background, var(--card-background-color)); }
          img { height:84px; width:auto; filter: drop-shadow(0 2px 4px rgba(0,0,0,.25)); }
          .gruss { font-family: Georgia, "Times New Roman", serif; font-size:28px; line-height:1.15; color:var(--primary-text-color); }
          .gruss i { color:#b8902f; }
          .datum { margin-top:4px; font-size:15px; color:var(--secondary-text-color); letter-spacing:.3px; }
        </style>
        <ha-card><img hidden alt="Familienwappen"><div><div class="gruss"></div><div class="datum"></div></div></ha-card>`;
      setInterval(() => this.zeichnen(), 60000);
    }
    zeichnen() {
      if (!this.shadowRoot) return;
      const d = new Date(), std = d.getHours();
      const tag = std < 5 ? "Gute Nacht" : std < 11 ? "Guten Morgen" : std < 18 ? "Guten Tag" : std < 22 ? "Guten Abend" : "Gute Nacht";
      this.shadowRoot.querySelector(".gruss").innerHTML = `${tag}, <i>Familie Schlag</i>`;
      this.shadowRoot.querySelector(".datum").textContent = d.toLocaleDateString("de-DE", { weekday: "long", day: "numeric", month: "long", year: "numeric" });
    }
  }
  customElements.define("familie-gruss", FamilieGruss);
  window.customCards = window.customCards || [];
  window.customCards.push({ type: "familie-gruss", name: "Familie: Begrüßung mit Wappen" });
})();
