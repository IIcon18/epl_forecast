import argparse
import logging
import sys

from pipeline.collectors import csv_history, football_data, rss_news

COLLECTORS = {
    "csv": csv_history.run,
    "football_data": football_data.run,
    "rss": rss_news.run,
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Загрузка данных во все источники")
    parser.add_argument("source", nargs="?", default="all", choices=["all", *COLLECTORS])
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    failed = []
    for name in COLLECTORS if args.source == "all" else [args.source]:
        try:
            COLLECTORS[name]()
        except Exception:
            logging.getLogger(name).exception("источник %s завершился с ошибкой", name)
            failed.append(name)
    if failed:
        logging.error("не загружено: %s", ", ".join(failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
