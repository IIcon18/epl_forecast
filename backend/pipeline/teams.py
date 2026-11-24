import re

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from db.models import Match, Team, TeamAlias

CANONICAL_TEAMS = [
    "Arsenal", "Aston Villa", "Birmingham", "Blackburn", "Blackpool", "Bolton", "Bournemouth",
    "Bradford", "Brentford", "Brighton", "Burnley", "Cardiff", "Charlton", "Chelsea", "Coventry",
    "Crystal Palace", "Derby", "Everton", "Fulham", "Huddersfield", "Hull", "Ipswich", "Leeds",
    "Leicester", "Liverpool", "Luton", "Man City", "Man United", "Middlesbrough", "Newcastle",
    "Norwich", "Nottingham", "Portsmouth", "QPR", "Reading", "Sheffield", "Southampton", "Stoke",
    "Sunderland", "Swansea", "Tottenham", "Watford", "West Brom", "West Ham", "Wigan", "Wolves",
]

EXTRA_ALIASES = {
    "Aston Villa": ["villa"],
    "Brighton": ["brighton and hove albion", "brighton hove"],
    "Leeds": ["leeds united"],
    "Man City": ["manchester city"],
    "Man United": ["manchester united", "man utd", "manchester utd"],
    "Newcastle": ["newcastle united", "newcastle utd"],
    "Nottingham": ["nottingham forest", "nottm forest"],
    "QPR": ["queens park rangers"],
    "Sheffield": ["sheffield united", "sheffield utd"],
    "Tottenham": ["tottenham hotspur", "spurs"],
    "West Brom": ["west bromwich albion"],
    "West Ham": ["west ham united"],
    "Wolves": ["wolverhampton wanderers", "wolverhampton"],
}

# 'Sheffield Wednesday' нельзя сводить к 'Sheffield' по общему началу названия
NO_PREFIX_MATCH = ("sheffield wednesday",)


def normalize(text: str) -> str:
    text = text.lower().replace("&", " and ")
    text = re.sub(r"[.'’]", "", text)
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"^afc ", "", text)
    return re.sub(r" a?fc$", "", text)


def seed_teams(session: Session) -> None:
    for name in CANONICAL_TEAMS:
        session.execute(
            insert(Team).values(name=name).on_conflict_do_nothing(index_elements=["name"])
        )
    ids = dict(session.execute(select(Team.name, Team.id)).all())
    for name in CANONICAL_TEAMS:
        for alias in [normalize(name), *EXTRA_ALIASES.get(name, [])]:
            session.execute(
                insert(TeamAlias)
                .values(alias=alias, team_id=ids[name])
                .on_conflict_do_nothing(index_elements=["alias"])
            )


class TeamRegistry:
    def __init__(self, session: Session):
        self.session = session
        self.aliases: dict[str, int] = dict(
            session.execute(select(TeamAlias.alias, TeamAlias.team_id)).all()
        )
        self.external_ids = {
            fid for (fid,) in session.execute(select(Team.football_data_id)) if fid
        }

    def resolve(self, name: str, short_name: str | None = None,
                external_id: int | None = None) -> int:
        keys = [normalize(n) for n in (name, short_name) if n]
        team_id = next((self.aliases[k] for k in keys if k in self.aliases), None)
        if team_id is None:
            team_id = self._by_name_prefix(keys[0])
        if team_id is None:
            team_id = self._create(short_name or name)
        self._remember(team_id, keys, external_id)
        return team_id

    def _by_name_prefix(self, key: str) -> int | None:
        if key.startswith(NO_PREFIX_MATCH):
            return None
        words = key.split()
        for n in range(len(words) - 1, 0, -1):
            if (team_id := self.aliases.get(" ".join(words[:n]))) is not None:
                return team_id
        return None

    def _create(self, name: str) -> int:
        display = re.sub(r"( A?FC)$", "", re.sub(r"^AFC ", "", name))
        team_id = self.session.scalar(select(Team.id).where(Team.name == display))
        if team_id is None:
            team_id = self.session.scalar(insert(Team).values(name=display).returning(Team.id))
        return team_id

    def _remember(self, team_id: int, keys: list[str], external_id: int | None) -> None:
        for key in keys:
            if key not in self.aliases:
                self.session.execute(
                    insert(TeamAlias)
                    .values(alias=key, team_id=team_id)
                    .on_conflict_do_nothing(index_elements=["alias"])
                )
                self.aliases[key] = team_id
        if external_id and external_id not in self.external_ids:
            self.session.execute(
                update(Team)
                .where(Team.id == team_id, Team.football_data_id.is_(None))
                .values(football_data_id=external_id)
            )
            self.external_ids.add(external_id)


def mention_patterns(session: Session, since_season: int) -> list[tuple[re.Pattern, int]]:
    active = select(Match.home_team_id).where(Match.season >= since_season).union(
        select(Match.away_team_id).where(Match.season >= since_season)
    )
    rows = session.execute(
        select(TeamAlias.alias, TeamAlias.team_id).where(TeamAlias.team_id.in_(active))
    ).all()
    return [
        (re.compile(rf"(?<!\w){re.escape(alias)}(?!\w)"), team_id)
        for alias, team_id in rows
        if len(alias) >= 4
    ]


def find_mentions(text: str, patterns: list[tuple[re.Pattern, int]]) -> set[int]:
    text = normalize(text)
    return {team_id for pattern, team_id in patterns if pattern.search(text)}
