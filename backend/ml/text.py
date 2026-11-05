import pandas as pd
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer


def score_news(news: pd.DataFrame) -> pd.DataFrame:
    if news.empty:
        return news.assign(compound=pd.Series(dtype=float))
    analyzer = SentimentIntensityAnalyzer()
    texts = news["title"].fillna("") + ". " + news["summary"].fillna("")
    return news.assign(compound=[analyzer.polarity_scores(t)["compound"] for t in texts])
