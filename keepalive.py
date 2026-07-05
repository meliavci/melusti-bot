"""Winziger HTTP-Server – nur damit Render den Bot als "Web Service" laufen
lässt (der kostenlose Tarif braucht einen HTTP-Port). Ein externer Pinger
(z.B. UptimeRobot) ruft die Adresse regelmäßig auf, damit der Service nicht
nach 15 Minuten Inaktivität einschläft."""
import threading

from flask import Flask

import config

app = Flask(__name__)


@app.get("/")
def status():
    return "Melusti läuft 🌱"


def start():
    thread = threading.Thread(
        target=lambda: app.run(host="0.0.0.0", port=config.PORT),
        daemon=True,
    )
    thread.start()
