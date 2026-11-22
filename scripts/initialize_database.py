import logging
import sys
from pathlib import Path

# Add project root to sys.path
root_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root_dir))

from backend.database.connection import engine, init_db, SessionLocal
from backend.database.models import University

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def initialize():
    logger.info("Initializing database tables...")
    init_db()

    db = SessionLocal()
    try:
        # Check or seed IIT Kharagpur
        univ_name = "Indian Institute of Technology Kharagpur"
        univ = db.query(University).filter(University.name == univ_name).first()
        if not univ:
            univ = University(
                name=univ_name,
                country="India",
                region="West Bengal",
                city="Kharagpur",
                website="https://www.iitkgp.ac.in/"
            )
            db.add(univ)
            db.commit()
            logger.info(f"Seeded university: {univ_name} (ID: {univ.id})")
        else:
            logger.info(f"University already exists: {univ.name} (ID: {univ.id})")
    finally:
        db.close()


if __name__ == "__main__":
    initialize()
