import argparse
import logging
import sys
from pathlib import Path

# Add project root to sys.path
root_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root_dir))

from backend.database.connection import SessionLocal
from backend.database.models import Department
from data_collection.faculty_scraper import FacultyScraper

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def run(
    dept_codes: list = None,
    max_departments: int = None,
    max_research_areas: int = None,
    max_faculty_per_dept: int = None
):
    logger.info("Starting faculty candidate collection...")
    scraper = FacultyScraper()
    db = SessionLocal()
    try:
        query = db.query(Department).order_by(Department.id.asc())
        if dept_codes:
            query = query.filter(Department.code.in_(dept_codes))
        departments = query.all()

        if max_departments:
            departments = departments[:max_departments]

        total_added = 0
        total_updated = 0

        for idx, dept in enumerate(departments, 1):
            logger.info(f"[{idx}/{len(departments)}] Processing department {dept.code}: {dept.name}")
            try:
                added, updated = scraper.scrape_department_faculty(
                    db=db,
                    department=dept,
                    max_research_areas=max_research_areas,
                    max_faculty=max_faculty_per_dept
                )
                total_added += added
                total_updated += updated
            except Exception as e:
                logger.error(f"Error scraping faculty for {dept.code}: {e}")

        logger.info(f"Faculty collection finished. Total added: {total_added}, total updated: {total_updated}")
        return total_added, total_updated
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Collect faculty profiles for IIT Kharagpur")
    parser.add_argument("--dept", nargs="+", help="Specific department codes (e.g. CS AI EE ME)")
    parser.add_argument("--max-depts", type=int, default=None, help="Limit number of departments")
    parser.add_argument("--max-areas", type=int, default=None, help="Limit research areas per dept")
    parser.add_argument("--max-faculty", type=int, default=None, help="Limit faculty per dept")
    args = parser.parse_args()

    run(
        dept_codes=args.dept,
        max_departments=args.max_depts,
        max_research_areas=args.max_areas,
        max_faculty_per_dept=args.max_faculty
    )
