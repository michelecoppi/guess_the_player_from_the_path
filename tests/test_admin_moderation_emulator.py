"""Admin moderation on leagues and groups (#36), and the referral overview (#37), on a
real Firestore (the emulator).

What a fake cannot prove: that `delete_league` really removes every member subdocument
and the league code from each member's user document in one batch, that
`delete_group_round` really clears both the round and its players subcollection, and that
`referrals.admin_overview` counts documents by status with real `where()`/`count()`
aggregation queries.
"""
from domains.referrals import service as referrals
from services import firebase_service as fs

CHAT_ID = -100777


def test_delete_league_removes_members_and_the_league_code_from_their_profile(emulator_db):
    fs.save_user(1, "Ada")
    fs.save_user(2, "Bob")
    fs.create_league("MOD", "Da moderare", 1, "Ada")
    fs.join_league("MOD", 2, "Bob", max_members=10)

    assert fs.delete_league("MOD") is True

    assert fs.get_league("MOD") is None
    assert list(fs.league_ref("MOD").collection(fs.MEMBERS_SUBCOLLECTION).stream()) == []
    assert "MOD" not in (fs.get_user_data(1) or {}).get("leagues", [])
    assert "MOD" not in (fs.get_user_data(2) or {}).get("leagues", [])


def test_delete_league_on_an_unknown_code_is_a_clean_false(emulator_db):
    assert fs.delete_league("NOPE") is False


def test_list_groups_reports_the_open_round(emulator_db):
    from firebase_admin import firestore as fb_firestore

    fs.group_round_ref(CHAT_ID).set({
        "chat_id": CHAT_ID, "number": 1, "key": "pool:x", "player_id": "x",
        "difficulty": "hard", "solved_by": None, "solved_name": None,
        "started_at": fb_firestore.SERVER_TIMESTAMP,
    })

    groups = fs.list_groups(limit=10)

    assert any(g["chat_id"] == CHAT_ID and g["number"] == 1 for g in groups)


def test_delete_group_round_clears_the_round_and_its_players(emulator_db):
    fs.group_round_ref(CHAT_ID).set({"chat_id": CHAT_ID, "number": 2, "key": "pool:y"})
    fs.group_player_ref(CHAT_ID, 42).set({"telegram_id": 42, "points": 5})

    assert fs.delete_group_round(CHAT_ID) is True

    assert fs.get_group_round(CHAT_ID) is None
    assert list(fs.group_round_ref(CHAT_ID).collection(fs.GROUP_PLAYERS_SUBCOLLECTION).stream()) == []


def test_delete_group_round_on_an_unknown_chat_is_a_clean_false(emulator_db):
    assert fs.delete_group_round(-999) is False


def test_referral_admin_overview_counts_by_status(emulator_db):
    referrals.ref(1).set({"inviter_id": 100, "invitee_id": 1, "status": "pending"})
    referrals.ref(2).set({"inviter_id": 100, "invitee_id": 2, "status": "qualified"})
    referrals.ref(3).set({"inviter_id": 101, "invitee_id": 3, "status": "qualified"})
    referrals.ref(4).set({"inviter_id": 101, "invitee_id": 4, "status": "deleted"})

    overview = referrals.admin_overview()

    assert overview == {"total": 4, "pending": 1, "qualified": 2}


def test_referral_admin_overview_on_an_empty_collection(emulator_db):
    assert referrals.admin_overview() == {"total": 0, "pending": 0, "qualified": 0}
