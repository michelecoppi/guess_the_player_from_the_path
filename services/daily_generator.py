"""Il buffer di sfide giornaliere dei prossimi giorni, riempito dal job notturno.

La scelta dei giocatori non sta qui ma nel planner (services/daily_planner.py, #30): questo
modulo resta come punto d'ingresso stabile per chi chiama "assicurati che i prossimi giorni
abbiano una sfida" (job notturno, /admin_generate, `get_today_challenge`, dashboard)."""
from services import daily_planner
from services.player_pool import load_config


def ensure_daily_buffer(days_ahead=None):
    """Genera in anticipo le sfide giornaliere mancanti per i prossimi N giorni, cosi' la
    sfida di oggi non dipende da un'esecuzione esatta a mezzanotte (requisito 'generare in
    anticipo i giocatori dei giorni successivi').

    Le regole di scelta sono quelle del planner (services/daily_planner.py, #30): lo stesso
    giocatore non torna entro `history_days_no_repeat` giorni, la fascia segue la rotazione,
    club e nazionalita' non si ripetono a ridosso. Qui si riempiono solo i buchi: un giorno
    gia' programmato, a mano o dal planner, non si tocca."""
    config = load_config()
    days_ahead = days_ahead if days_ahead is not None else config.get("buffer_days_ahead", 3)
    if days_ahead <= 0:
        return []
    plan = daily_planner.plan_calendar(days=days_ahead, mode=daily_planner.MODE_FILL, config=config)
    return daily_planner.apply_plan(plan, source=daily_planner.SOURCE_AUTO)["written"]
