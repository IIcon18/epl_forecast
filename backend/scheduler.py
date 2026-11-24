import logging
import os
import subprocess
import sys
import time

log = logging.getLogger("scheduler")
INTERVAL_HOURS = float(os.environ.get("SCHEDULE_INTERVAL_HOURS", "6"))
# (шаг, команда, шаг, без которого этот не имеет смысла)
STEPS = [
    ("сбор", [sys.executable, "-m", "pipeline.run", "all"], None),
    ("признаки", [sys.executable, "-m", "ml.build_features"], None),
    ("прогноз", [sys.executable, "-m", "ml.predict"], "признаки"),
]


def run_once() -> bool:
    done: dict[str, bool] = {}
    for name, command, requires in STEPS:
        if requires and not done[requires]:
            log.error("шаг «%s» пропущен: не выполнен шаг «%s»", name, requires)
            done[name] = False
            continue
        code = subprocess.run(command).returncode
        done[name] = code == 0
        if code:
            log.error("шаг «%s» завершился с ошибкой (код %d)", name, code)
        else:
            log.info("шаг «%s» выполнен", name)
    return all(done.values())


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    once = "--once" in sys.argv
    while True:
        started = time.time()
        success = run_once()
        log.info("цикл завершён %s", "успешно" if success else "с ошибками")
        if once:
            sys.exit(0 if success else 1)
        time.sleep(max(INTERVAL_HOURS * 3600 - (time.time() - started), 60))


if __name__ == "__main__":
    main()
