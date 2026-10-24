// Nebenkostenabrechnung in der Akte (Knopf "Nebenkosten"): Maske in der Reihenfolge der OLMESS-Bögen – Nutzerliste,
// Brennstoff, Heiznebenkosten, Betriebskosten, Zählerstände. Claude übernimmt Werte aus den Belegen der Akte und liest
// Zählerfotos; alles bleibt änderbar. Daten über script.akte_aktion (was: nk_…), gespeichert nur auf dem HA-Rechner.
// Braucht aus akte.html: hass(), skript(), toast(), esc(), datum().
(() => {
  let nk = null, zeitraum = "", zeitraeume = [], frist = "", BS = {}, HH = {}, speicherT = null, pollT = null, offen = false;
  let geloeschtFotos = [], geloeschtZaehler = [];
  const zahl = x => { if (x === "" || x == null) return null; const n = Number(String(x).replace(/\./g, "").replace(",", ".")); return isFinite(n) ? n : null; };
  const zahlText = (x, st = 2) => { const n = zahl(typeof x === "number" ? String(x).replace(".", ",") : x); return n == null ? "" : n.toLocaleString("de-DE", { minimumFractionDigits: st, maximumFractionDigits: st }); };
  const roh = x => x == null ? "" : typeof x === "number" ? String(x).replace(".", ",") : String(x);
  const laeuft = () => nk && /^Ich lese/.test(nk.status || "");

  const css = document.createElement("style");
  css.textContent = `
  #nk { background: rgba(0,0,0,.96); }
  #nk .einst-inhalt { gap: 14px; background: #F7F7FA; }
  :root.dunkel #nk .einst-inhalt { background: #1C1C1E; }
  #nk .nk-zeile { background: #fff; } :root.dunkel #nk .nk-zeile { background: #2C2C2E; }
  .nk-kopf { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
  .nk-kopf .chip { padding: 7px 12px; border-radius: 14px; background: var(--bg); font-weight: 600; font-size: 13px; }
  .nk-kopf .chip.an { background: var(--text); color: #fff; }
  .nk-karte { background: var(--bg); border-radius: 14px; padding: 12px; display: grid; gap: 10px; }
  .nk-karte h3 { margin: 0; font-size: 16px; display: flex; justify-content: space-between; align-items: center; gap: 8px; flex-wrap: wrap; }
  .nk-zeile { display: flex; gap: 8px; flex-wrap: wrap; align-items: flex-end; background: var(--karte); border-radius: 12px; padding: 8px 10px; }
  .nk-zeile.vorschlag { box-shadow: inset 4px 0 0 #F5C451; }
  .nk-feld { display: grid; gap: 2px; font-size: 11px; color: var(--grau); }
  .nk-feld input, .nk-feld select, .nk-feld textarea { font: inherit; font-size: 15px; color: var(--text); background: var(--bg); border: 1px solid #D1D1D6; border-radius: 9px; padding: 7px 8px; min-width: 0; }
  .nk-feld.s input { width: 92px; } .nk-feld.m input, .nk-feld.m select { width: 140px; } .nk-feld.l input { width: 230px; } .nk-feld.xl { flex: 1; min-width: 200px; } .nk-feld.xl input { width: 100%; }
  .nk-meta { font-size: 12px; color: var(--grau); width: 100%; display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
  .nk-meta button { color: var(--blau); font-weight: 600; font-size: 12px; }
  .nk-x { color: var(--rot); font-weight: 700; padding: 6px 8px; }
  .nk-banner { border-radius: 12px; padding: 10px 12px; font-size: 14px; line-height: 1.45; }
  .nk-banner.rot { background: #FF3B301A; color: #8E1B12; } .nk-banner.gelb { background: #FFF4D6; color: #6B4E00; } .nk-banner.blau { background: #007AFF14; color: #0B4A99; }
  .nk-summe { font-size: 13px; font-weight: 700; font-variant-numeric: tabular-nums; }
  .nk-foto { max-width: 100%; border-radius: 10px; margin-top: 4px; }
  :root.dunkel .nk-feld input, :root.dunkel .nk-feld select, :root.dunkel .nk-feld textarea { background: #2C2C2E; border-color: #48484A; color: #fff; }
  :root.dunkel .nk-banner.gelb { background: #3A3018; color: #F5D78A; } :root.dunkel .nk-banner.rot { color: #FF9F97; } :root.dunkel .nk-banner.blau { color: #8EC1FF; }`;
  document.head.appendChild(css);

  const huelle = document.createElement("div");
  huelle.className = "pdf"; huelle.id = "nk";
  huelle.innerHTML = `<div class="leiste"><b>🧾 Nebenkostenabrechnung</b><span class="pdf-knoepfe"><span id="nk-gespeichert" class="klein" style="color:#fff"></span>
    <button class="zu" data-n="zu">Schließen</button></span></div><div class="einst-inhalt" id="nk-inhalt"></div>
    <input type="file" id="nk-foto-datei" accept="image/*" multiple hidden>`;
  document.body.appendChild(huelle);

  async function laden(was, extra) {
    const a = await skript(Object.assign({ was: was || "nk_lesen", id: zeitraum }, extra || {}));
    if (!a || !a.ok || !a.daten) { if (was !== "nk_foto") toast("Nebenkosten konnten nicht geladen werden"); return a; }
    nk = a.daten; zeitraum = a.zeitraum; zeitraeume = a.zeitraeume || []; frist = a.frist || ""; BS = a.schluessel || {}; HH = a.hh_typen || {};
    geloeschtFotos = []; geloeschtZaehler = [];
    return a;
  }
  window.nkOeffnen = async () => {
    huelle.classList.add("offen"); offen = true;
    $("nk-inhalt").innerHTML = `<div class="leer">Wird geladen …</div>`;
    await laden(); zeichnen(); beobachten();
  };

  // ---------- Anzeige ----------
  const feld = (pfad, wert, titel, art, gr, extra) => `<label class="nk-feld ${gr || "m"}">${esc(titel)}<input data-f="${esc(pfad)}" value="${esc(roh(wert))}"
    ${art === "datum" ? 'type="date"' : art === "zahl" ? 'inputmode="decimal"' : ""} ${extra || ""}></label>`;
  const auswahl = (pfad, wert, titel, optionen, gr) => `<label class="nk-feld ${gr || "m"}">${esc(titel)}<select data-f="${esc(pfad)}">
    <option value=""></option>${Object.entries(optionen).map(([k, v]) => `<option value="${esc(k)}" ${String(wert) === k ? "selected" : ""}>${esc(k)} ${esc(v)}</option>`).join("")}</select></label>`;
  const summe = (liste, k) => liste.reduce((s, x) => s + (zahl(roh(x[k])) || 0), 0);
  function meta(x, liste, i) {
    return `<div class="nk-meta">${x.vorschlag ? `<span>✨ Vorschlag – bitte prüfen</span><button data-n="ok" data-w="${liste}.${i}">✓ stimmt</button>` : ""}
      ${x.beleg ? `<button data-a="ansehen" data-w="${esc(x.beleg)}">📄 ${esc(x.beleg_titel || "Beleg ansehen")}</button>` : ""}
      ${x.hinweis ? `<span>${esc(x.hinweis)}</span>` : ""}</div>`;
  }
  function zeichnen() {
    if (!nk) return;
    const heute = new Date().toISOString().slice(0, 10), tage = frist ? Math.round((new Date(frist) - new Date(heute)) / 864e5) : null;
    const gesperrt = laeuft() ? "disabled" : "";
    const z = nk, br = z.brennstoff || [], hn = z.heizneben || [], bk = z.betrieb || [];
    $("nk-inhalt").innerHTML = `
      <div class="nk-kopf">${zeitraeume.map(n => `<button class="chip ${n === zeitraum ? "an" : ""}" data-n="zeitraum" data-w="${esc(n)}">${datum(n.slice(0, 10))} – ${datum(n.slice(11))}</button>`).join("")}
        <button class="chip" data-n="neu">+ nächster Zeitraum</button></div>
      <div class="klein">${esc(z.objekt)} · Liegenschafts-Nr. ${esc(z.liegenschaft)} · Abrechnungsdienst OLMESS</div>
      ${tage == null ? "" : tage < 0 ? `<div class="nk-banner rot"><b>Frist abgelaufen am ${datum(frist)}.</b> Die Abrechnung hätte 12 Monate nach Ende des Zeitraums beim Mieter sein müssen.
          Eine Nachzahlung kann man dann in der Regel nicht mehr verlangen – ein Guthaben des Mieters muss aber trotzdem erstattet werden. Für einen bereits leer stehenden oder selbst genutzten Teil spielt das keine Rolle.</div>`
        : `<div class="nk-banner ${tage <= 60 ? "rot" : "blau"}"><b>Abrechnung an den Mieter bis ${datum(frist)}</b> (noch ${tage} Tage) – danach sind Nachzahlungen ausgeschlossen.</div>`}
      ${z.status ? `<div class="nk-banner gelb">${laeuft() ? "⏳ " : "✨ "}${esc(z.status)}</div>` : ""}
      ${(z.hinweise || []).length ? `<div class="nk-banner gelb">${z.hinweise.map(h => "• " + esc(h)).join("<br>")}</div>` : ""}
      <div class="aktionen">
        <button class="knopf blau gross-knopf" data-n="auswerten" ${gesperrt}>✨ Aus Belegen der Akte übernehmen</button>
        <button class="knopf gross-knopf" data-n="foto">📷 Zählerfoto auswerten</button>
        <button class="knopf gruen gross-knopf" data-n="pdf">📄 Als PDF an mein Telegram</button></div>
      <p class="klein">Rechnungen, Bescheide und Gasabrechnungen einfach wie immer in die Akte legen – „Aus Belegen übernehmen“ sucht die passenden heraus und trägt sie hier ein (gelb markiert = Vorschlag). Alles lässt sich ändern; gespeichert wird automatisch.</p>

      <div class="nk-karte"><h3>1 · Nutzerliste <span class="klein">wer wohnt wo – Flächen, Personen, Vorauszahlungen im Zeitraum</span></h3>
        ${(z.einheiten || []).map((e, i) => `<div class="nk-zeile">
          <b style="width:100%">${esc(e.lage)} · Nutzer-Nr. ${esc(e.nr)}</b>
          ${feld(`einheiten.${i}.nutzung`, e.nutzung, "Nutzung (Ferienwohnung, vermietet, Leerstand)", "", "l")}
          ${feld(`einheiten.${i}.nutzer`, e.nutzer, "Name Mieter/Nutzer", "", "l")}
          ${feld(`einheiten.${i}.einzug`, e.einzug, "Einzug", "datum")}${feld(`einheiten.${i}.auszug`, e.auszug, "Auszug", "datum")}
          ${feld(`einheiten.${i}.hz_flaeche`, e.hz_flaeche, "Heizfläche m² (S030)", "zahl", "s")}
          ${feld(`einheiten.${i}.ww_flaeche`, e.ww_flaeche, "WW-Fläche m² (S031)", "zahl", "s")}
          ${feld(`einheiten.${i}.personen`, e.personen, "Personen (S015)", "zahl", "s")}
          ${feld(`einheiten.${i}.vz_heizung`, e.vz_heizung, "Vorausz. Heizung € (Summe)", "zahl", "m")}
          ${feld(`einheiten.${i}.vz_neben`, e.vz_neben, "Vorausz. Nebenkosten € (Summe)", "zahl", "m")}</div>`).join("")}</div>

      <div class="nk-karte"><h3>2 · Brennstoff Erdgas <span class="nk-summe">${zahlText(summe(br, "kwh"), 0)} kWh · ${euro(summe(br, "brutto"))}</span></h3>
        ${br.map((x, i) => `<div class="nk-zeile ${x.vorschlag ? "vorschlag" : ""}">${feld(`brennstoff.${i}.datum`, x.datum, "Datum", "datum")}
          ${feld(`brennstoff.${i}.kwh`, x.kwh, "kWh", "zahl")}${feld(`brennstoff.${i}.brutto`, x.brutto, "Brutto €", "zahl")}
          <button class="nk-x" data-n="weg" data-w="brennstoff.${i}">✕</button>${meta(x, "brennstoff", i)}</div>`).join("")}
        <div class="aktionen"><button class="knopf" data-n="plus" data-w="brennstoff">+ Gasrechnung</button></div>
        <div class="nk-zeile ${z.abgaben_vorschlag ? "vorschlag" : ""}"><b style="width:100%">Darin enthaltene Abgaben (für die Mieter-Info nach HKVO)</b>
          ${feld("abgaben.co2", (z.abgaben || {}).co2, "CO2-Steuer €", "zahl")}${feld("abgaben.energiesteuer", (z.abgaben || {}).energiesteuer, "Energiesteuer €", "zahl")}
          ${feld("abgaben.netzentgelt", (z.abgaben || {}).netzentgelt, "Netzentgelt €", "zahl")}${feld("abgaben.weitere", (z.abgaben || {}).weitere, "Weitere Abgaben €", "zahl")}</div></div>

      <div class="nk-karte"><h3>3 · Heiznebenkosten <span class="nk-summe">${euro(summe(hn, "brutto"))}</span></h3>
        <p class="klein" style="margin:0">Wartung, Schornsteinfeger, Heizungsstrom, Zählermiete/Ablesung …</p>
        ${hn.map((x, i) => kostenZeile("heizneben", x, i, false)).join("")}
        <div class="aktionen"><button class="knopf" data-n="plus" data-w="heizneben">+ Heiznebenkosten</button></div></div>

      <div class="nk-karte"><h3>4 · Betriebskosten <span class="nk-summe">${euro(summe(bk, "brutto"))}</span></h3>
        <p class="klein" style="margin:0">Nur umlagefähige Kosten: Grundsteuer, Wasser/Abwasser, Müll, Versicherung, Allgemeinstrom, Garten … – keine Reparaturen.</p>
        ${bk.map((x, i) => kostenZeile("betrieb", x, i, true)).join("")}
        <div class="aktionen"><button class="knopf" data-n="plus" data-w="betrieb">+ Betriebskosten</button></div>
        <div class="nk-zeile ${z.wasser_vorschlag ? "vorschlag" : ""}">${feld("wasser_cbm", z.wasser_cbm, "Wasser laut Versorger m³ (gesamt)", "zahl", "m")}</div></div>

      <div class="nk-karte"><h3>5 · Zählerstände <span class="klein">Foto genügt – ich lese Art, Nummer und Stand selbst</span></h3>
        <p class="klein" style="margin:0">Wichtig sind die Stände zum Anfang und Ende des Zeitraums. Viele Wasser- und Wärmezähler speichern den Stand zum Stichtag – dafür auf das Display tippen, bis Datum und Wert erscheinen, und das fotografieren.</p>
        ${(z.zaehler || []).map((m, i) => zaehlerKarte(m, i)).join("")}
        <div class="aktionen"><button class="knopf" data-n="foto">📷 Zählerfoto</button><button class="knopf" data-n="zaehler-plus">+ Zähler von Hand</button></div></div>

      <div class="nk-karte"><h3>Notiz</h3><label class="nk-feld xl"><textarea data-f="notiz" rows="3" placeholder="z. B. Mieter OG seit …, Vorauszahlung monatlich …">${esc(z.notiz || "")}</textarea></label></div>`;
    if (gesperrt) $("nk-inhalt").querySelectorAll("[data-f]").forEach(el => el.disabled = true);
  }
  function kostenZeile(liste, x, i, mitBs) {
    return `<div class="nk-zeile ${x.vorschlag ? "vorschlag" : ""}">${feld(`${liste}.${i}.art`, x.art, "Kostenart", "", "l")}
      ${mitBs ? auswahl(`${liste}.${i}.bs`, x.bs, "Schlüssel (BS)", BS) : ""}
      ${feld(`${liste}.${i}.datum`, x.datum, "Datum", "datum")}${feld(`${liste}.${i}.brutto`, x.brutto, "Brutto €", "zahl", "s")}
      ${feld(`${liste}.${i}.mwst`, x.mwst, "MwSt %", "zahl", "s")}${feld(`${liste}.${i}.hhdl`, x.hhdl, "davon haushaltsnah €", "zahl", "s")}
      ${auswahl(`${liste}.${i}.hhtyp`, x.hhtyp, "HH-Typ", HH)}
      <button class="nk-x" data-n="weg" data-w="${liste}.${i}">✕</button>${meta(x, liste, i)}</div>`;
  }
  function zaehlerKarte(m, i) {
    const st = (m.staende || []);
    // Verbrauch im Abrechnungszeitraum: abgelesen, wenn es Stände am Anfang/Ende gibt (±7 Tage), sonst aus den
    // Ablesungen davor/danach geschätzt (gleichmäßiger Verbrauch angenommen) – Schätzungen sind als solche markiert
    const verbrauch = (() => {
      const pkt = st.map(s => ({ t: new Date(s.datum).getTime(), v: zahl(roh(s.stand)) })).filter(p => p.v != null && !isNaN(p.t)).sort((x, y) => x.t - y.t);
      if (pkt.length < 2) return "";
      const am = d => {
        const t = new Date(d).getTime(), nah = pkt.find(p => Math.abs(p.t - t) <= 7 * 864e5);
        if (nah) return { v: nah.v, art: "abgelesen" };
        let i = pkt.findIndex(p => p.t > t);
        const art = i > 0 ? "geschätzt" : "hochgerechnet";
        if (i <= 0) i = i === 0 ? 1 : pkt.length - 1;   // davor: erste zwei, danach: letzte zwei Ablesungen
        const p0 = pkt[i - 1], p1 = pkt[i];
        return { v: p0.v + (p1.v - p0.v) * (t - p0.t) / (p1.t - p0.t), art };
      };
      const a = am(nk.von), e = am(nk.bis), diff = e.v - a.v;
      const art = a.art === "abgelesen" && e.art === "abgelesen" ? "abgelesen" : a.art === "hochgerechnet" || e.art === "hochgerechnet" ? "hochgerechnet – ungenau" : "geschätzt aus den Ablesungen";
      return `Verbrauch ${datum(nk.von)} – ${datum(nk.bis)}: <b>${a.art === "abgelesen" && e.art === "abgelesen" ? "" : "≈ "}${zahlText(diff, 1)} ${esc(m.einheit || "")}</b> (${art})`;
    })();
    return `<div class="nk-zeile"><b style="width:100%;display:flex;justify-content:space-between">${esc(m.name || "Zähler")}<button class="nk-x" data-n="zaehler-weg" data-w="${i}">✕</button></b>
      ${feld(`zaehler.${i}.name`, m.name, "Bezeichnung", "", "l")}${feld(`zaehler.${i}.art`, m.art, "Art", "", "m")}
      ${feld(`zaehler.${i}.nummer`, m.nummer, "Zählernummer", "", "m")}${feld(`zaehler.${i}.einheit`, m.einheit, "Einheit", "", "s")}
      ${st.map((s, k) => `<div class="nk-zeile ${s.vorschlag ? "vorschlag" : ""}" style="width:100%;background:var(--bg)">
        ${feld(`zaehler.${i}.staende.${k}.datum`, s.datum, s.stichtag ? "Stichtag" : "Datum", "datum")}${feld(`zaehler.${i}.staende.${k}.stand`, s.stand, "Stand", "zahl", "m")}
        <button class="nk-x" data-n="stand-weg" data-w="${i}.${k}">✕</button>
        <div class="nk-meta">${s.vorschlag ? `<span>✨ abgelesen – bitte prüfen</span><button data-n="ok" data-w="zaehler.${i}.staende.${k}">✓ stimmt</button>` : ""}
          ${s.foto ? `<button data-n="foto-zeigen" data-w="${esc(s.foto)}">🖼 Foto</button>` : ""}${s.hinweis ? `<span>${esc(s.hinweis)}</span>` : ""}</div>
        <div id="foto-${esc(s.foto || "")}"></div></div>`).join("")}
      <div class="nk-meta">${verbrauch}<button data-n="stand-plus" data-w="${i}">+ Stand von Hand</button></div></div>`;
  }

  // ---------- Eingaben ----------
  function setzen(pfad, wert) {
    const teile = pfad.split("."); let o = nk;
    for (const t of teile.slice(0, -1)) o = o[/^\d+$/.test(t) ? Number(t) : t];
    o[teile[teile.length - 1]] = wert;
    // wer einen Vorschlag ändert, übernimmt ihn
    const zeile = teile.slice(0, -1).reduce((x, t) => x && x[/^\d+$/.test(t) ? Number(t) : t], nk);
    if (zeile && zeile.vorschlag) zeile.vorschlag = false;
    if (teile[0] === "abgaben") nk.abgaben_vorschlag = false;
    if (teile[0] === "wasser_cbm") nk.wasser_vorschlag = false;
  }
  function speichernBald() {
    clearTimeout(speicherT); $("nk-gespeichert").textContent = "…";
    speicherT = setTimeout(speichern, 1200);
  }
  async function speichern() {
    clearTimeout(speicherT); speicherT = null;
    const d = Object.assign({}, nk, { geloescht_fotos: geloeschtFotos, geloescht_zaehler: geloeschtZaehler });
    const a = await skript({ was: "nk_speichern", id: zeitraum, text: JSON.stringify(d) });
    $("nk-gespeichert").textContent = a && a.ok ? "gespeichert ✓" : "nicht gespeichert!";
    if (a && a.ok) { geloeschtFotos = []; geloeschtZaehler = []; }
  }
  document.addEventListener("input", ev => {
    const el = ev.target.closest && ev.target.closest("#nk [data-f]"); if (!el) return;
    setzen(el.dataset.f, el.value); speichernBald();
  });
  document.addEventListener("change", ev => {
    const el = ev.target.closest && ev.target.closest("#nk [data-f]");
    if (el) { setzen(el.dataset.f, el.value); speichernBald(); if (el.tagName === "SELECT") zeichnen(); }
  });
  // Neu zeichnen nur, wenn gerade nichts eingetippt wird
  const tippt = () => document.activeElement && document.activeElement.closest && document.activeElement.closest("#nk [data-f]");

  // im Hintergrund: Belege lesen / Zähler ablesen – so lange nachschauen
  function beobachten(sekunden) {
    clearTimeout(pollT);
    let ende = Date.now() + (sekunden || 0) * 1000;
    const schauen = async () => {
      if (!offen) return;
      if (speicherT) await speichern();
      if (!tippt()) { const vorher = JSON.stringify(nk); await laden(); if (JSON.stringify(nk) !== vorher) zeichnen(); }
      if (laeuft() || Date.now() < ende) pollT = setTimeout(schauen, 8000);
    };
    if (laeuft() || sekunden) pollT = setTimeout(schauen, 8000);
  }

  document.addEventListener("click", async ev => {
    const el = ev.target.closest("#nk [data-n]"); if (!el) return;
    const w = el.dataset.w;
    switch (el.dataset.n) {
      case "zu": if (speicherT) await speichern(); huelle.classList.remove("offen"); offen = false; clearTimeout(pollT); break;
      case "zeitraum": if (speicherT) await speichern(); zeitraum = w; await laden(); zeichnen(); break;
      case "neu": if (speicherT) await speichern(); await laden("nk_neu"); zeichnen(); toast("Neuer Abrechnungszeitraum angelegt – Nutzerliste übernommen"); break;
      case "auswerten":
        if (speicherT) await speichern();
        await laden("nk_auswerten"); zeichnen(); beobachten(240);
        toast("Ich lese die passenden Belege – dauert 1–3 Minuten", 6000); break;
      case "pdf":
        if (speicherT) await speichern();
        await skript({ was: "nk_pdf", id: zeitraum, wer: (hass().user && hass().user.name) || "" });
        toast("Die Übersicht kommt gleich per Telegram (PDF)", 6000); break;
      case "foto": $("nk-foto-datei").click(); break;
      case "plus": nk[w] = (nk[w] || []).concat([{}]); zeichnen(); break;
      case "weg": { const [l, i] = w.split("."); nk[l].splice(Number(i), 1); zeichnen(); speichernBald(); break; }
      case "ok": { const z = w.split(".").reduce((x, t) => x[/^\d+$/.test(t) ? Number(t) : t], nk); z.vorschlag = false; zeichnen(); speichernBald(); break; }
      case "zaehler-plus": nk.zaehler = (nk.zaehler || []).concat([{ id: Math.random().toString(36).slice(2, 10), name: "", art: "", nummer: "", einheit: "", staende: [] }]); zeichnen(); speichernBald(); break;
      case "zaehler-weg":
        if (el.dataset.scharf !== "1") { el.dataset.scharf = "1"; el.textContent = "Zähler löschen?"; return; }
        { const m = nk.zaehler.splice(Number(w), 1)[0]; if (m && m.id) geloeschtZaehler.push(m.id); (m.staende || []).forEach(s => s.foto && geloeschtFotos.push(s.foto)); }
        zeichnen(); speichernBald(); break;
      case "stand-plus": { const m = nk.zaehler[Number(w)]; m.staende = (m.staende || []).concat([{ datum: new Date().toISOString().slice(0, 10), stand: "" }]); zeichnen(); speichernBald(); break; }
      case "stand-weg": { const [i, k] = w.split(".").map(Number); const s = nk.zaehler[i].staende.splice(k, 1)[0]; if (s && s.foto) geloeschtFotos.push(s.foto); zeichnen(); speichernBald(); break; }
      case "foto-zeigen": {
        const ziel = document.getElementById("foto-" + w); if (!ziel) break;
        if (ziel.innerHTML) { ziel.innerHTML = ""; break; }
        ziel.textContent = "Foto wird geladen …";
        const a = await skript({ was: "nk_foto", id: zeitraum, text: w });
        ziel.innerHTML = a && a.bild ? `<img class="nk-foto" src="data:image/jpeg;base64,${a.bild}">` : "Foto nicht gefunden"; break;
      }
    }
  });

  // Zählerfotos hochladen (Original, damit das Aufnahmedatum erhalten bleibt) und auswerten lassen
  document.addEventListener("change", async ev => {
    if (ev.target.id !== "nk-foto-datei") return;
    const dateien = [...ev.target.files]; ev.target.value = "";
    if (speicherT) await speichern();
    for (const [n, d] of dateien.entries()) {
      try {
        const b64 = await alsBase64(d), STUECK = 200000;
        const kennung = Array.from(crypto.getRandomValues(new Uint8Array(10)), x => (x % 36).toString(36)).join("");
        const name = btoa(unescape(encodeURIComponent("nk-zaehler_" + d.name))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
        const teile = Math.max(1, Math.ceil(b64.length / STUECK));
        let ergebnis = null;
        for (let i = 0; i < teile; i++) {
          toast(`Zählerfoto ${n + 1}/${dateien.length} wird hochgeladen${teile > 1 ? " – " + Math.round((i + 1) / teile * 100) + " %" : ""}`);
          const r = await hass().callWS({ type: "call_service", domain: "script", service: "akte_hochladen", return_response: true,
            service_data: { kennung, teil: i, name, letzt: i === teile - 1, daten: b64.slice(i * STUECK, (i + 1) * STUECK) } });
          ergebnis = r && r.response && r.response.stdout;
        }
        let e = ergebnis; if (typeof e === "string") { try { e = JSON.parse(e); } catch (x) { e = null; } }
        if (!e || !e.foto) { toast("Foto ging nicht: " + ((e && e.fehler) || "unbekannter Fehler"), 8000); continue; }
        await skript({ was: "nk_zaehler", id: zeitraum, text: e.foto });
      } catch (x) { toast("Foto ging nicht (" + String((x && x.message) || x).slice(0, 80) + ")", 8000); }
    }
    toast("Ich lese die Zähler ab – in ca. 30 Sekunden stehen sie unten bei den Zählerständen", 7000);
    beobachten(120);
  });
})();
