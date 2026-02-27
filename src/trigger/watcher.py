"""
Local polling daemon that watches the GCS bucket for new/changed PDFs
and triggers parsing automatically.

Run with: make watch  OR  python -m src.trigger.watcher
"""
import asyncio
import json
import logging
import sys
import time
from pathlib import Path

# Add project root to path when run as a module
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from config.settings import settings
from src.index.schema import init_db
from src.parser.pipeline import parse_one
from src.storage.gcs_client import GCSClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

STATE_FILE = Path("data/.gcs_state.json")


def load_state() -> dict[str, str]:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {}


def save_state(state: dict[str, str]) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


class GCSWatcher:
    def __init__(self):
        self.gcs_client = GCSClient()
        self.known: dict[str, str] = load_state()

    def check_for_changes(self) -> list[str]:
        current_objects = self.gcs_client.list_pdfs()
        current: dict[str, str] = {obj.name: obj.md5_hash for obj in current_objects}

        new_or_changed = [
            name
            for name, md5 in current.items()
            if self.known.get(name) != md5
        ]

        self.known = current
        save_state(self.known)
        return new_or_changed

    def run(self) -> None:
        logger.info(
            f"Watcher started. Polling every {settings.polling_interval_seconds}s. "
            f"Bucket: {settings.gcs_bucket_name}"
        )
        semaphore = asyncio.Semaphore(settings.max_concurrent_parses)

        while True:
            try:
                new_files = self.check_for_changes()
                if new_files:
                    logger.info(f"Detected {len(new_files)} new/changed file(s): {new_files}")
                    for name in new_files:
                        asyncio.run(parse_one(name, semaphore))
                else:
                    logger.debug("No changes detected")
            except KeyboardInterrupt:
                logger.info("Watcher stopped by user")
                break
            except Exception as e:
                logger.error(f"Watcher error: {e}")

            time.sleep(settings.polling_interval_seconds)


def main():
    init_db()
    watcher = GCSWatcher()
    watcher.run()


if __name__ == "__main__":
    main()
