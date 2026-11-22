import argparse
import logging
import sys
from pathlib import Path

# Add project root to sys.path
root_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root_dir))

from backend.database.connection import SessionLocal
from backend.database.models import Professor
from data_collection.publication_fetcher import PublicationFetcher

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def run(
    limit_professors: int = None,
    verify_with_crossref: bool = False
):
    logger.info("Starting publication collection and author disambiguation...")
    fetcher = PublicationFetcher()
    db = SessionLocal()
    try:
        query = db.query(Professor).order_by(Professor.id.asc())
        if limit_professors:
            query = query.limit(limit_professors)

        professors = query.all()
        logger.info(f"Processing publications for {len(professors)} professors...")

        totals = {
            "publications_added": 0,
            "publications_linked": 0,
            "ambiguous_candidates": 0,
            "skipped_existing": 0
        }

        for idx, prof in enumerate(professors, 1):
            logger.info(f"[{idx}/{len(professors)}] Fetching publications for: {prof.name}")
            try:
                stats = fetcher.fetch_for_professor(
                    db=db,
                    professor=prof,
                    verify_with_crossref=verify_with_crossref
                )
                for k, v in stats.items():
                    totals[k] += v
            except Exception as e:
                logger.error(f"Error fetching publications for {prof.name}: {e}")

        logger.info(f"Publication collection completed: {totals}")
        return totals
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Collect publications and perform author matching")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of professors")
    parser.add_argument("--crossref", action="store_true", help="Verify DOIs with Crossref")
    args = parser.parse_args()

    run(limit_professors=args.limit, verify_with_crossref=args.crossref)
