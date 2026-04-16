from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BASE_DIR / "data" / "db"
KNOWLEDGE_DIR = BASE_DIR / "data" / "knowledge"

ENCOUNTERS_DB_PATH = DATA_DIR / "encounters.json"
EVENTS_DB_PATH = DATA_DIR / "events.json"
CHARACTERS_DB_PATH = DATA_DIR / "characters.json"
CAMPAIGN_DB_PATH = DATA_DIR / "campaign.json"
SPELL_DEFINITIONS_PATH = KNOWLEDGE_DIR / "spell_definitions.json"
WEAPON_DEFINITIONS_PATH = KNOWLEDGE_DIR / "weapon_definitions.json"
ZONE_DEFINITIONS_PATH = KNOWLEDGE_DIR / "zone_definitions.json"
ENTITY_DEFINITIONS_PATH = KNOWLEDGE_DIR / "entity_definitions.json"
