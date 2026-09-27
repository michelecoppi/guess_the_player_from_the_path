"""Un finto `daily_path` in memoria per il planner (#30) e per chi lo usa (buffer, rigenera).

Il planner legge una finestra di sfide, i sospesi e le esclusioni e scrive giorno per giorno:
qui ci sono esattamente quelle letture e scritture, con la stessa forma dei documenti veri."""
from services import firebase_service


class FakeDailyStore:
    def __init__(self):
        self.daily = {}
        self.blocked = []
        self.exclusions = {}
        self.saved = []

    def get_daily_paths_range(self, start, end, limit=180):
        return [dict(doc) for day, doc in sorted(self.daily.items()) if start <= day <= end][:limit]

    def get_daily_path(self, day_iso):
        doc = self.daily.get(day_iso)
        return dict(doc) if doc else None

    def save_daily_path(self, day_iso, doc):
        doc = dict(doc)
        doc["day"] = day_iso
        self.daily[day_iso] = doc
        self.saved.append(day_iso)

    def set_planner_exclusion(self, player_id, exclusion):
        self.exclusions[player_id] = dict(exclusion)

    def remove_planner_exclusion(self, player_id):
        self.exclusions.pop(player_id, None)


def install(monkeypatch, store=None):
    store = store or FakeDailyStore()
    monkeypatch.setattr(firebase_service, "get_daily_paths_range", store.get_daily_paths_range)
    monkeypatch.setattr(firebase_service, "get_daily_path", store.get_daily_path)
    monkeypatch.setattr(firebase_service, "save_daily_path", store.save_daily_path)
    monkeypatch.setattr(firebase_service, "get_blocked_player_ids", lambda: list(store.blocked))
    monkeypatch.setattr(firebase_service, "get_planner_exclusions", lambda: dict(store.exclusions))
    monkeypatch.setattr(firebase_service, "set_planner_exclusion", store.set_planner_exclusion)
    monkeypatch.setattr(firebase_service, "remove_planner_exclusion", store.remove_planner_exclusion)
    return store
