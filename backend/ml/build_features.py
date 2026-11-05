import logging

import numpy as np
import pandas as pd
from sqlalchemy import literal_column
from sqlalchemy.dialects.postgresql import insert

from db.models import MatchFeatures
from db.session import SessionLocal, engine
from ml import data, text
from ml.features import FEATURE_COLUMNS, FEATURE_VERSION, build_features

log = logging.getLogger(__name__)
CHUNK = 1000


def to_json_value(value):
    if pd.isna(value):
        return None
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, (np.floating, float)):
        return float(value)
    return value


def run() -> None:
    with engine.connect() as conn:
        matches = data.load_matches(conn)
        news = text.score_news(data.load_news(conn))
    frame = build_features(matches, news)
    rows = [
        {
            "match_id": int(r["match_id"]),
            "feature_version": FEATURE_VERSION,
            "features": {c: to_json_value(r[c]) for c in FEATURE_COLUMNS},
        }
        for r in frame.to_dict("records")
    ]
    inserted = updated = 0
    with SessionLocal.begin() as session:
        for start in range(0, len(rows), CHUNK):
            stmt = insert(MatchFeatures).values(rows[start:start + CHUNK])
            stmt = stmt.on_conflict_do_update(
                index_elements=["match_id"],
                set_={"feature_version": stmt.excluded.feature_version,
                      "features": stmt.excluded.features},
                where=(MatchFeatures.features.is_distinct_from(stmt.excluded.features)
                       | (MatchFeatures.feature_version != stmt.excluded.feature_version)),
            ).returning(literal_column("(xmax = 0)"))
            for (is_insert,) in session.execute(stmt):
                inserted, updated = inserted + is_insert, updated + (not is_insert)
    log.info("match_features %s: матчей %d, вставлено %d, обновлено %d, без изменений %d",
             FEATURE_VERSION, len(rows), inserted, updated, len(rows) - inserted - updated)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    run()
