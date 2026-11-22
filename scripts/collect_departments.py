import logging
import sys
from pathlib import Path

# Add project root to sys.path
root_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root_dir))

from backend.database.connection import SessionLocal
from data_collection.department_scraper import DepartmentScraper

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def run():
    logger.info("Starting department collection for IIT Kharagpur...")
    scraper = DepartmentScraper()
    db = SessionLocal()
    try:
        added, updated = scraper.scrape_and_save(db)
        logger.info(f"Department collection completed: {added} added, {updated} updated.")
    finally:
        db.close()


if __name__ == "__main__":
    run()
