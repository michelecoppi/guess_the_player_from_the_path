"""La mini app in locale, senza Telegram e senza Firestore.

Serve a **guardare** i cosmetici prima di venderli. Un tema, una cornice o una figurina si
giudicano solo addosso a una pagina vera: sulla scheda del negozio sono francobolli, e nel
JSON sono sei stringhe esadecimali. Qui la pagina e' la stessa che vede un utente
(`webapp/index.html`), servita dalle stesse funzioni del server vero
(`services/webapp_api.py`, `services/shop.py`), con l'unica differenza che sotto non c'e'
Firestore ma un dizionario in memoria.

    python scripts/preview_webapp.py        # poi http://localhost:8888/app

L'utente finto **ha gia' tutto**: ogni cosmetico del catalogo, cinque trofei e dei contatori
alti, cosi' ogni traguardo e' sbloccato e ogni oggetto si puo' indossare con un click. Il
negozio funziona: "Compra" consegna subito senza fattura, perche' non c'e' niente da pagare
e il punto e' vedere l'oggetto addosso.

Niente di quello che si fa qui esce da questo processo: si riparte e l'utente finto torna
come prima. Il file non viene importato da bot.py e non finisce nell'immagine di produzione.
"""
import base64
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("BOT_TOKEN", "preview-bot-token")

from fastapi import Body, FastAPI  # noqa: E402
from fastapi.responses import HTMLResponse, Response  # noqa: E402

from services import firebase_service, shop, trophies  # noqa: E402
from services.daily_challenge import MAX_ATTEMPTS, challenge_number  # noqa: E402
from services.share import card_image  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEBAPP_DIR = os.path.join(ROOT, "webapp")
USER_ID = 1000
PORT = int(os.environ.get("PREVIEW_PORT", "8888"))


# ---------------------------------------------------------------------------
# L'utente finto
# ---------------------------------------------------------------------------

def _new_user():
    """Uno che ha giocato per mesi: contatori alti perche' ogni traguardo sia gia' sbloccato,
    e tutto il catalogo comprato perche' non si debba pagare niente per guardarlo."""
    # Tutto quello che si puo' avere comprando, esclusivi dei pacchetti compresi. Restano
    # fuori solo le cose che si guadagnano (traguardi, premi di completamento, podio): quelle
    # arrivano da sole, perche' i contatori qui sotto sono alti e i trofei ci sono.
    buyable = [item["id"] for item in shop.all_items()
               if item.get("kind") != "bundle" and not item.get("achievement")
               and not item.get("completes") and not item.get("trophy")]
    return {
        "first_name": "Marco",
        "telegram_id": USER_ID,
        "language": os.environ.get("PREVIEW_LANG", "it"),
        "points_totali": 812,
        "monthly_points": 96,
        "players_guessed": 154,
        "referral_qualified": 10,
        "bonus_first_guessed": 12,
        "current_streak": 9,
        "best_streak": 31,
        "archive_solved": 63,
        "training_solved": 44,
        "solved_in": {"1": 41, "2": 68, "3": 45},
        "last_played_day": None,
        "has_guessed_today": False,
        "daily_attempts": 0,
        "daily_hints": 0,
        # Codici veri: posizione, id del template (data/event_templates.json), giorno di
        # chiusura. Ce ne sono tanti apposta: una bacheca si giudica piena, non con tre
        # targhe in fila. Uno con l'id a piu' pezzi c'e' perche' e' il caso che si rompe.
        "trophies": [
            "1_giramondo_20260907", "2_un_amore_una_maglia_20260713", "3_campionato_top_20260525",
            "1_sudamerica_20260420", "2_squadra_sorpresa_20260316", "3_carriera_a_squadre_20260209",
            "1_weekend_transfer_20260112", "2_esperti_del_pallone_20251208",
            "3_coppie_leggendarie_20251103", "1_giramondo_20251006", "2_campionato_top_20250901",
            "3_sudamerica_20250804", "1_un_amore_una_maglia_20250707", "2_giramondo_20240610",
            "MON_July_3_2026_1", "MON_March_3_2026_2", "MON_November_2_2025_3",
            "MON_June_2_2025_1",
        ],
        "leagues": ["AMICI"],
        "cosmetics": {"owned": buyable, "earned": [], "equipped": {}, "looks": []},
    }


STATE = {"user": _new_user()}


def _players():
    with open(os.path.join(ROOT, "data", "players.json"), encoding="utf-8") as f:
        return json.load(f)["players"]


def _challenge():
    """Una sfida vera presa dal dataset locale: il percorso disegnato conta, perche' e' il
    blocco su cui si giudica se un tema resta leggibile."""
    players = [p for p in _players() if len(p.get("career") or []) >= 3]
    player = players[len(players) // 3]
    return {
        "player_id": player["id"],
        "correct_answers": player.get("aliases") or [player["id"]],
        "difficulty": "media",
        "career_path": player["career"],
        "first_correct_user": False,
    }


LEADERBOARD = [
    {"telegram_id": 21, "username": "Giulia", "points": 1180},
    {"telegram_id": USER_ID, "username": "Marco", "points": 812},
    {"telegram_id": 22, "username": "Sara", "points": 774},
    {"telegram_id": 23, "username": "Dario", "points": 610},
    {"telegram_id": 24, "username": "Elisa", "points": 588},
]


# ---------------------------------------------------------------------------
# Firestore, sostituito da un dizionario
#
# Si sostituiscono le funzioni e non il client: cosi' tutto quello che sta sopra - il
# profilo, la vetrina, le regole su cosa si puo' indossare - resta il codice vero, e quello
# che si vede qui e' quello che vedra' un utente.
# ---------------------------------------------------------------------------

def _fake_firestore():
    def get_user_data(user_id):
        return STATE["user"] if int(user_id) == USER_ID else None

    def equip_cosmetic(user_id, kind, item_id):
        STATE["user"]["cosmetics"].setdefault("equipped", {})[kind] = item_id

    def equip_look(user_id, slots):
        STATE["user"]["cosmetics"].setdefault("equipped", {}).update(slots)

    def save_looks(user_id, looks):
        STATE["user"]["cosmetics"]["looks"] = looks

    def deliver_purchase(user_id, charge_id, item_id, granted_ids, stars, day_iso=None):
        STATE["user"]["cosmetics"]["owned"] += [one for one in granted_ids
                                                if one not in STATE["user"]["cosmetics"]["owned"]]
        return True

    def get_league(code):
        return {"name": "Gli amici del bar", "members_count": 4} if code == "AMICI" else None

    def get_league_leaderboard(code, limit=20):
        return [{"telegram_id": row["telegram_id"], "name": row["username"], "points": row["points"] // 3}
                for row in LEADERBOARD[:4]]

    stubs = {
        "get_user_data": get_user_data,
        "equip_cosmetic": equip_cosmetic,
        "equip_look": equip_look,
        "save_looks": save_looks,
        "deliver_purchase": deliver_purchase,
        "get_league": get_league,
        "get_league_leaderboard": get_league_leaderboard,
        "get_daily_path": lambda day_iso: _challenge(),
        "get_top_users": lambda field="points_totali", limit=10: LEADERBOARD[:limit],
        "get_user_purchases": lambda user_id, limit=None: [],
        "get_past_daily_paths": lambda *args, **kwargs: [],
        "get_daily_paths_range": lambda *args, **kwargs: [],
        "get_daily_history": lambda *args, **kwargs: {},
        "get_solved_archive_days": lambda *args, **kwargs: set(),
        "get_archive_result": lambda *args, **kwargs: None,
        "save_user": lambda *args, **kwargs: None,
        "reserve_checkout": lambda *args, **kwargs: "ok",
        "pin_trophies": lambda user_id, codes: STATE["user"]["cosmetics"].__setitem__("pinned", list(codes)),
        "record_daily_history": lambda *args, **kwargs: None,
        "register_daily_outcome": lambda *args, **kwargs: None,
    }
    for name, stub in stubs.items():
        setattr(firebase_service, name, stub)


_fake_firestore()

from services.webapp_api import build_calendar, build_profile, build_public_profile  # noqa: E402

app = FastAPI(title="Anteprima mini app")


def _lang():
    return STATE["user"].get("language") or "it"


# Il finto Telegram. La pagina si rifiuta di disegnare senza `initData` firmato - ed e'
# giusto cosi', e' quello che impedisce di chiedere i dati di un altro - quindi in anteprima
# gliene diamo uno finto insieme alle poche funzioni che chiama davvero. Si inietta qui e non
# in webapp/index.html: la pagina servita in produzione non deve sapere che esiste
# un'anteprima, e cosi' quello che si guarda e' il file vero, non una sua variante.
TELEGRAM_SHIM = """<script>
window.Telegram = { WebApp: {
  initData: "preview",
  initDataUnsafe: { user: { id: %d, first_name: "Marco", language_code: "%s" } },
  ready: function () {}, expand: function () {},
  openInvoice: function (url, cb) { if (cb) cb("paid"); },
  openTelegramLink: function (url) { window.open(url, "_blank"); },
  switchInlineQuery: function () {},
  HapticFeedback: { notificationOccurred: function () {}, impactOccurred: function () {} },
  MainButton: { setText: function () { return this; }, show: function () { return this; },
                hide: function () { return this; }, onClick: function () { return this; } },
} };
window.addEventListener("load", function () {
  var p = new URLSearchParams(window.location.search);
  var mode = p.get("mock_guess") || p.get("view");
  if (mode === "wrong" || mode === "solved") {
    setTimeout(function () {
      var inp = document.querySelector("#answer");
      if (inp) {
        inp.value = mode === "solved" ? "Vitolo" : "Messi";
        inp.dispatchEvent(new Event("input", { bubbles: true }));
        var btn = document.querySelector("#submit");
        if (btn) btn.click();
      }
    }, 350);
  }
});
</script>"""



@app.get("/", response_class=HTMLResponse)
@app.get("/app", response_class=HTMLResponse)
async def page(lang: str | None = None, referrals: int | None = None, scenario: str | None = None):
    if scenario == "solved":
        from services.dates import today_iso
        STATE["user"]["last_played_day"] = today_iso()
        STATE["user"]["has_guessed_today"] = True
        STATE["user"]["daily_attempts"] = 2
    elif scenario == "wrong":
        from services.dates import today_iso
        STATE["user"]["last_played_day"] = today_iso()
        STATE["user"]["has_guessed_today"] = False
        STATE["user"]["daily_attempts"] = 1
    elif scenario == "reset":
        STATE["user"]["last_played_day"] = None
        STATE["user"]["has_guessed_today"] = False
        STATE["user"]["daily_attempts"] = 0
    if lang in ("it", "en", "es"):
        STATE["user"]["language"] = lang
    if referrals is not None:
        STATE["user"]["referral_qualified"] = max(0, min(referrals, 10))
    with open(os.path.join(WEBAPP_DIR, "index.html"), encoding="utf-8") as f:
        html = f.read()
    shim = TELEGRAM_SHIM % (USER_ID, _lang())
    return HTMLResponse(html.replace("<body>", "<body>" + shim, 1))


def _page(name):
    with open(os.path.join(WEBAPP_DIR, name), encoding="utf-8") as f:
        return HTMLResponse(f.read())


def _script(name):
    with open(os.path.join(WEBAPP_DIR, name), encoding="utf-8") as f:
        return Response(f.read(), media_type="text/javascript")


@app.get("/app/client.js")
async def client_logic():
    """La stessa rotta del server vero (bot.py): senza, la pagina si carica a meta' perche'
    `index.html` cerca qui le funzioni pure che usa gia' nella prima riga di script."""
    return _script("client.js")


@app.get("/app/strings.js")
async def client_strings():
    """Come sopra per le stringhe nelle tre lingue: senza, `L` resta indefinita e la
    pagina non disegna niente."""
    return _script("strings.js")


@app.get("/app/arena.js")
async def client_arena():
    return _script("arena.js")


@app.get("/app/arena.css")
async def client_arena_css():
    with open(os.path.join(WEBAPP_DIR, "arena.css"), encoding="utf-8") as f:
        return Response(f.read(), media_type="text/css")


@app.get("/privacy", response_class=HTMLResponse)
async def privacy():
    return _page("privacy.html")


@app.get("/terms", response_class=HTMLResponse)
async def terms():
    return _page("terms.html")


@app.get("/legal.css")
async def legal_css():
    with open(os.path.join(WEBAPP_DIR, "legal.css"), encoding="utf-8") as f:
        return Response(f.read(), media_type="text/css")


DIST_DIR = os.path.join(WEBAPP_DIR, "dist")


@app.get("/app/v2", response_class=HTMLResponse)
async def webapp_v2_page(lang: str | None = None, scenario: str | None = None):
    if scenario == "solved":
        from services.dates import today_iso
        STATE["user"]["last_played_day"] = today_iso()
        STATE["user"]["has_guessed_today"] = True
        STATE["user"]["daily_attempts"] = 2
    elif scenario == "wrong":
        from services.dates import today_iso
        STATE["user"]["last_played_day"] = today_iso()
        STATE["user"]["has_guessed_today"] = False
        STATE["user"]["daily_attempts"] = 1
    elif scenario == "reset":
        STATE["user"]["last_played_day"] = None
        STATE["user"]["has_guessed_today"] = False
        STATE["user"]["daily_attempts"] = 0
    if lang in ("it", "en", "es"):
        STATE["user"]["language"] = lang
    dist_index = os.path.join(DIST_DIR, "index.html")
    if not os.path.exists(dist_index):
        return HTMLResponse(
            "<h2>Mini App V2 non compilata</h2><p>Esegui <code>npm run build</code> per compilare il bundle Vite.</p>",
            status_code=503,
        )
    with open(dist_index, encoding="utf-8") as f:
        html = f.read()
    shim = TELEGRAM_SHIM % (USER_ID, _lang())
    if "<body>" in html:
        return HTMLResponse(html.replace("<body>", "<body>" + shim, 1))
    return HTMLResponse(html + shim)


@app.get("/app/v2/assets/{file_path:path}")
async def webapp_v2_assets(file_path: str):
    base_assets = Path(DIST_DIR).resolve() / "assets"
    try:
        target = (base_assets / file_path).resolve()
    except (ValueError, RuntimeError):
        return Response("Forbidden", status_code=403)
    if not target.is_relative_to(base_assets) or target == base_assets:
        return Response("Forbidden", status_code=403)
    if not target.is_file():
        return Response("Not Found", status_code=404)
    with open(target, "rb") as f:
        content = f.read()
    suffix = target.suffix.lower()
    media_type = "application/javascript" if suffix == ".js" else (
        "text/css" if suffix == ".css" else (
            "application/json" if suffix == ".map" else "application/octet-stream"
        )
    )
    return Response(content, media_type=media_type)


@app.post("/app/api/me")
async def me(payload: dict = Body(default={})):
    return build_profile(USER_ID, lang=_lang())


@app.get("/app/referrals.js")
def referrals_script():
    return _script("referrals.js")


@app.get("/app/referrals.css")
def referrals_style():
    return Response(open(os.path.join(WEBAPP_DIR, "referrals.css"), encoding="utf-8").read(), media_type="text/css")


@app.post("/app/api/referrals")
def referrals_preview():
    from services.referrals import REWARDS
    user = firebase_service.get_user_data(USER_ID)
    names = ["Giulia", "Sara", "Dario", "Elisa", "Paolo", "Davide", "Sofia", "Matteo", "Chiara", "Nico"]
    return {"qualified": user.get("referral_qualified", 0), "required_days": 5,
            "link": "https://t.me/preview_bot?start=ref_demo", "next_cursor": None,
            "friends": [{"name": name, "days": days, "status": "qualified" if days == 5 else "pending"}
                        for name, days in [("Luca", 3), ("Andrea", 1)] + [(name, 5) for name in names[:user.get("referral_qualified", 0)]]],
            "rewards": [{"target": n, "items": [shop._card(shop.get_item(i), user, _lang(), shop.equipped(user)) for i in ids]}
                        for n, ids in REWARDS.items()]}


@app.post("/app/api/profile/public")
async def public_profile(payload: dict = Body(default={})):
    """Il profilo di un altro. Qui e' sempre il proprio, che e' l'unico che esiste: serve a
    guardare come si vede da fuori quello che si ha addosso."""
    return build_public_profile(USER_ID, lang=_lang()) or {}


@app.post("/app/api/calendar")
async def calendar(payload: dict = Body(default={})):
    return build_calendar(USER_ID, lang=_lang())


@app.post("/app/api/players")
async def players(payload: dict = Body(default={})):
    return {"players": sorted(p["full_name"] for p in _players())}


@app.post("/app/api/shop")
async def shop_window(payload: dict = Body(default={})):
    return shop.catalogue_for(STATE["user"], _lang())


@app.post("/app/api/shop/equip")
async def shop_equip(payload: dict = Body(default={})):
    status = shop.equip(USER_ID, STATE["user"], payload.get("item"))
    if status != "ok":
        return {"status": status}
    return {"status": "ok", "cosmetics": shop.appearance(STATE["user"], _lang())}


@app.post("/app/api/shop/buy")
async def shop_buy(payload: dict = Body(default={})):
    """Consegna e basta: in anteprima non c'e' niente da pagare, e quello che si vuole
    vedere e' l'oggetto addosso, non la fattura di Telegram."""
    item = shop.get_item(payload.get("item"))
    if not item:
        return {"status": "unknown_item"}
    granted = [one for one in shop.grants_of(item)
               if one not in STATE["user"]["cosmetics"]["owned"]]
    STATE["user"]["cosmetics"]["owned"] += granted
    return {"status": "ok", "granted": granted, "preview": True}


@app.post("/app/api/shop/look")
async def shop_look(payload: dict = Body(default={})):
    action, name = payload.get("action"), payload.get("name")
    if action == "save":
        return {"status": shop.save_look(USER_ID, STATE["user"], name)}
    if action == "wear":
        return {"status": shop.use_look(USER_ID, STATE["user"], name)}
    if action == "delete" and isinstance(name, str):
        looks = [look for look in STATE["user"]["cosmetics"].get("looks", []) if look["name"] != name]
        STATE["user"]["cosmetics"]["looks"] = looks
        return {"status": "ok"}
    return {"status": "unknown_item"}


@app.post("/app/api/shop/history")
async def shop_history(payload: dict = Body(default={})):
    return {"purchases": [], "support_url": ""}


@app.post("/app/api/card")
async def result_card(payload: dict = Body(default={})):
    pinned = trophies.showcase(STATE["user"], _lang())
    buffer = card_image(
        STATE["user"], _lang(), challenge_number(payload.get("day")),
        int(payload.get("attempts") or 2), int(payload.get("max_attempts") or MAX_ATTEMPTS),
        solved=bool(payload.get("solved", True)), streak=int(payload.get("streak") or 0),
        hints=int(payload.get("hints") or 0),
        honour=f"{pinned[0]['label']} - {pinned[0]['detail']}" if pinned else "",
    )
    return {"image": "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()}


@app.post("/app/api/trophies/pin")
async def pin_trophies(payload: dict = Body(default={})):
    status = trophies.pin(USER_ID, STATE["user"], payload.get("codes"))
    if status != "ok":
        return {"status": status}
    return {"status": "ok", "pinned": trophies.showcase(STATE["user"], _lang())}


@app.post("/app/api/league")
async def league(payload: dict = Body(default={})):
    return {"status": "ok", "leagues": build_profile(USER_ID, lang=_lang())["leagues"]}


@app.post("/app/api/guess")
async def preview_guess(payload: dict = Body(default={})):
    answer = (payload.get("answer") or payload.get("guess") or "").strip()
    if not answer:
        return {"status": "error", "reason": "empty_guess"}

    if answer.lower() in ("vitolo", "correct", "solve"):
        STATE["user"]["has_guessed_today"] = True
        STATE["user"]["daily_attempts"] = 2
        return {
            "status": "correct",
            "attempts_used": 2,
            "attempts_left": 3,
            "points": 100,
            "streak": 10,
            "best_streak": 31,
            "squares": "🟥🟩⬜⬜⬜",
            "player_name": "Vitolo",
            "share": {
                "text": "Guess the Player #462 2/5\n🟥🟩⬜⬜⬜",
                "url": "https://t.me/share/url?url=https%3A%2F%2Ft.me%2Fpreview_bot",
            },
        }

    STATE["user"]["daily_attempts"] = 1
    return {
        "status": "wrong",
        "attempts_used": 1,
        "attempts_left": 4,
        "comparison": {
            "name": answer,
            "clues": [
                {"key": "feedback.nationality_diff"},
                {"key": "feedback.position_same"},
                {"key": "feedback.birth_before", "args": {"year": 1989}},
            ],
        },
    }


@app.post("/app/api/hint")
async def preview_hint(payload: dict = Body(default={})):
    STATE["user"]["daily_hints"] = (STATE["user"].get("daily_hints") or 0) + 1
    return {
        "status": "ok",
        "hint": "Ha vinto 4 Europa League con il Siviglia",
        "hints_used": STATE["user"]["daily_hints"],
        "hints_left": max(0, 3 - STATE["user"]["daily_hints"]),
    }



@app.post("/app/api/preview/reset")
async def reset(payload: dict = Body(default={})):
    STATE["user"] = _new_user()
    return {"status": "ok"}


@app.post("/app/api/preview/wear")
async def wear(payload: dict = Body(default={})):
    """Indossa un intero set in un colpo, per nome del pacchetto: comodo per confrontare due
    collezioni senza cinque click ciascuna."""
    item = shop.get_item(payload.get("bundle"))
    if not item or item.get("kind") != "bundle":
        return {"status": "unknown_item"}
    slots = {shop.get_item(one)["kind"]: one for one in shop.grants_of(item)}
    STATE["user"]["cosmetics"]["equipped"].update(slots)
    return {"status": "ok", "equipped": slots}


def main():
    import uvicorn

    from scripts.preview_arena import install

    install(app, STATE, _lang)

    catalogue = len(shop.all_items())
    print(f"Anteprima mini app su http://localhost:{PORT}/app")
    print(f"Catalogo: {catalogue} oggetti, tutti gia' posseduti dall'utente finto.")
    print("Firestore non viene toccato: e' tutto in memoria e si azzera alla chiusura.")
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")


if __name__ == "__main__":
    main()
