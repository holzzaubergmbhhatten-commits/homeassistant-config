#!/usr/bin/env python3
"""Prüft die eigenen Monitor-Seiten (www/*.html): Wer Emojis benutzt, muss die Emoji-Schrift einbinden –
der Flur-Monitor hat selbst keine und zeigt sonst Kästchen. Aufruf vor dem Hochladen: python3 claude_tools/emoji_check.py"""
import glob
import os
import re
import sys

EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿]")
WWW = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "www")
fehler = []
for f in sorted(glob.glob(os.path.join(WWW, "*.html"))):
    s = open(f, encoding="utf-8").read()
    if EMOJI.search(s) and ("Noto+Color+Emoji" not in s or '"Noto Color Emoji"' not in s):
        fehler.append(os.path.basename(f))
print("Emoji-Schrift fehlt in: " + ", ".join(fehler) if fehler else "ok – alle Seiten mit Emojis haben die Emoji-Schrift")
sys.exit(1 if fehler else 0)
