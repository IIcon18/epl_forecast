import os
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def current_season(today: date | None = None) -> int:
    today = today or date.today()
    return today.year if today.month >= 7 else today.year - 1


DATA_DIR = Path(os.environ.get("DATA_DIR", Path(__file__).resolve().parents[2] / "data"))
CSV_PATH = DATA_DIR / "epl_matches_2000_2026.csv"
CSV_URL = os.environ.get(
    "CSV_URL",
    "https://raw.githubusercontent.com/RezaGooner/english-premier-league-match-dataset/"
    "2e54f4a124f63a4878145ea5b2e25f178a99ec77/Data/EPL_Match_Data_2000_2026.csv",
)

FOOTBALL_DATA_URL = "https://api.football-data.org/v4"
FOOTBALL_DATA_TOKEN = os.environ.get("FOOTBALL_DATA_TOKEN", "")
FOOTBALL_DATA_SEASONS = [
    int(s)
    for s in os.environ.get(
        "FOOTBALL_DATA_SEASONS", f"{current_season() - 1},{current_season()}"
    ).split(",")
]

RSS_URL = os.environ.get("RSS_URL", "https://feeds.bbci.co.uk/sport/football/rss.xml")
HTTP_TIMEOUT = int(os.environ.get("HTTP_TIMEOUT", "20"))
