"""Kurzer Verbindungstest zu Claude mit dem Schlüssel aus der Anthropic-Integration.

Probiert die Modelle, die Home Assistant benutzt, mit einer Mini-Anfrage aus und gibt
eine lesbare Zusammenfassung aus (für Telegram). Der Schlüssel selbst wird nie ausgegeben,
nur seine letzten 4 Zeichen zum Abgleich mit console.anthropic.com.
Aufruf ohne Argument: immer testen. Mit "einmal": nur, wenn dieser Test noch nicht lief.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import garten_ki  # noqa: E402

MARKER = "/config/.claude_test_1"
MODELLE = ["claude-haiku-4-5", "claude-haiku-5-5", "claude-sonnet-5-5"]


def main():
    if sys.argv[1:] == ["einmal"]:
        if os.path.exists(MARKER):
            print("")
            return
        open(MARKER, "w").close()
    import anthropic

    try:
        schluessel = garten_ki.api_schluessel()
    except Exception as fehler:  # noqa: BLE001
        print(f"🔑 Claude-Test: {fehler}")
        return
    client = anthropic.Anthropic(api_key=schluessel, timeout=30, max_retries=0)
    zeilen = [f"🔑 Claude-Test (Schlüssel endet auf …{schluessel[-4:]})"]
    for modell in MODELLE:
        try:
            client.messages.create(model=modell, max_tokens=16,
                                   messages=[{"role": "user", "content": "Sag nur: ok"}])
            zeilen.append(f"✅ {modell}: funktioniert")
        except anthropic.APIStatusError as fehler:
            zeilen.append(f"❌ {modell}: Fehler {fehler.status_code} – {str(fehler.message)[:200]}")
        except Exception as fehler:  # noqa: BLE001
            zeilen.append(f"❌ {modell}: {type(fehler).__name__} – {str(fehler)[:200]}")
    print("\n".join(zeilen))


if __name__ == "__main__":
    main()
