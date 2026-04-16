from pathlib import Path

from tinydb import TinyDB

from tools.core.config import CAMPAIGN_DB_PATH, CHARACTERS_DB_PATH, ENCOUNTERS_DB_PATH, EVENTS_DB_PATH


def _ensure_db_file(db_path: Path) -> Path:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if not db_path.exists() or db_path.stat().st_size == 0:
        db_path.write_text("{}", encoding="utf-8")
    return db_path


def get_db(db_path: Path) -> TinyDB:
    return TinyDB(_ensure_db_file(db_path), encoding="utf-8")


def get_encounters_state() -> TinyDB:
    return get_db(ENCOUNTERS_DB_PATH)


def get_characters_db() -> TinyDB:
    return get_db(CHARACTERS_DB_PATH)


def get_campaign_db() -> TinyDB:
    return get_db(CAMPAIGN_DB_PATH)


def get_events_db() -> TinyDB:
    return get_db(EVENTS_DB_PATH)
