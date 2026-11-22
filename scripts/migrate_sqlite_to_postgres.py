"""
Database migration and verification utility: SQLite -> PostgreSQL (Phase 2A Step 1).

Preserves all primary keys, foreign keys, M2M relationships, self-referential topic
hierarchies (parent_topic_id), and verification statuses, resets PostgreSQL sequences,
and performs a strict before-and-after verification audit.
"""
import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.engine import Engine

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend.database.models import (
    Base,
    DataSource,
    Department,
    Professor,
    ProfessorProject,
    ProfessorPublication,
    Publication,
    ResearchProject,
    ResearchTopic,
    University,
    VerificationRecord,
    professor_topics,
    publication_topics,
)

ORDERED_TABLES = [
    University.__table__,
    Department.__table__,
    Professor.__table__,
    Publication.__table__,
    ResearchProject.__table__,
    ResearchTopic.__table__,
    ProfessorPublication.__table__,
    ProfessorProject.__table__,
    professor_topics,
    publication_topics,
    DataSource.__table__,
    VerificationRecord.__table__,
]

TABLES_WITH_ID_SEQ = [
    "universities",
    "departments",
    "professors",
    "publications",
    "research_projects",
    "research_topics",
    "professor_publications",
    "professor_projects",
    "data_sources",
    "verification_records",
]


def collect_db_fingerprint(engine: Engine) -> Dict[str, Any]:
    """Collects table row counts, status distributions, and relationship join counts."""
    with engine.connect() as conn:
        table_counts = {}
        for tbl in ORDERED_TABLES:
            cnt = conn.execute(select( text("COUNT(*)") ).select_from(tbl)).scalar()
            table_counts[tbl.name] = int(cnt or 0)

        prof_status = dict(
            conn.execute(text("SELECT verification_status, COUNT(*) FROM professors GROUP BY verification_status")).fetchall()
        )
        pub_status = dict(
            conn.execute(text("SELECT verification_status, COUNT(*) FROM publications GROUP BY verification_status")).fetchall()
        )
        link_status = dict(
            conn.execute(
                text("SELECT verification_status, COUNT(*) FROM professor_publications GROUP BY verification_status")
            ).fetchall()
        )
        proj_cats = dict(
            conn.execute(
                text("SELECT project_category, COUNT(*) FROM research_projects GROUP BY project_category")
            ).fetchall()
        )
        topic_parents = int(
            conn.execute(text("SELECT COUNT(*) FROM research_topics WHERE parent_topic_id IS NOT NULL")).scalar() or 0
        )
        generic_roots = int(
            conn.execute(text("SELECT COUNT(*) FROM research_topics WHERE is_generic_root = TRUE")).scalar() or 0
        )
        noisy_artifacts = int(
            conn.execute(text("SELECT COUNT(*) FROM research_topics WHERE is_noisy_artifact = TRUE")).scalar() or 0
        )
        # Join integrity checks
        joined_prof_pubs = int(
            conn.execute(
                text(
                    "SELECT COUNT(*) FROM professor_publications pp "
                    "JOIN professors p ON p.id = pp.professor_id "
                    "JOIN publications pub ON pub.id = pp.publication_id"
                )
            ).scalar()
            or 0
        )
        joined_prof_projs = int(
            conn.execute(
                text(
                    "SELECT COUNT(*) FROM professor_projects pp "
                    "JOIN professors p ON p.id = pp.professor_id "
                    "JOIN research_projects rp ON rp.id = pp.project_id"
                )
            ).scalar()
            or 0
        )

    return {
        "table_counts": table_counts,
        "professor_status": prof_status,
        "publication_status": pub_status,
        "professor_publication_link_status": link_status,
        "project_categories": proj_cats,
        "topics_with_parent_id": topic_parents,
        "generic_root_topics": generic_roots,
        "noisy_artifact_topics": noisy_artifacts,
        "joined_professor_publications": joined_prof_pubs,
        "joined_professor_projects": joined_prof_projs,
    }


def migrate_database(source_url: str, target_url: str, batch_size: int = 1000) -> Dict[str, Any]:
    """
    Migrates all tables from `source_url` to `target_url`, preserving all IDs and relationships,
    resetting PostgreSQL sequences if applicable, and verifying 100% parity.
    """
    src_engine = create_engine(source_url)
    tgt_engine = create_engine(target_url)

    try:
        before_fp = collect_db_fingerprint(src_engine)

        # Ensure target schema is created cleanly
        Base.metadata.create_all(bind=tgt_engine)

        # Check that target tables are empty before migrating
        with tgt_engine.connect() as tgt_conn:
            for tbl in ORDERED_TABLES:
                existing = tgt_conn.execute(select(text("COUNT(*)")).select_from(tbl)).scalar()
                if existing and int(existing) > 0:
                    raise RuntimeError(
                        f"Target table '{tbl.name}' is not empty ({existing} rows). "
                        "Refusing to overwrite existing target data."
                    )

        with src_engine.connect() as src_conn, tgt_engine.begin() as tgt_conn:
            for tbl in ORDERED_TABLES:
                rows = [dict(r._mapping) for r in src_conn.execute(select(tbl)).fetchall()]
                if not rows:
                    continue

                if tbl.name == "research_topics":
                    # Insert with parent_topic_id=None first so self-referential FK never fails on ordering,
                    # then restore parent_topic_id in the same transaction.
                    parent_links: List[Dict[str, int]] = []
                    stripped_rows = []
                    for r in rows:
                        r_copy = dict(r)
                        if r_copy.get("parent_topic_id") is not None:
                            parent_links.append({"tid": r_copy["id"], "pid": r_copy["parent_topic_id"]})
                        r_copy["parent_topic_id"] = None
                        stripped_rows.append(r_copy)

                    for i in range(0, len(stripped_rows), batch_size):
                        tgt_conn.execute(tbl.insert(), stripped_rows[i : i + batch_size])

                    if parent_links:
                        tgt_conn.execute(
                            text("UPDATE research_topics SET parent_topic_id = :pid WHERE id = :tid"),
                            parent_links,
                        )
                else:
                    for i in range(0, len(rows), batch_size):
                        tgt_conn.execute(tbl.insert(), rows[i : i + batch_size])

            # Reset PostgreSQL sequences so future autoincrement inserts do not collide
            if tgt_engine.dialect.name == "postgresql":
                for tname in TABLES_WITH_ID_SEQ:
                    tgt_conn.execute(
                        text(
                            f"SELECT setval(pg_get_serial_sequence('{tname}', 'id'), "
                            f"COALESCE((SELECT MAX(id) FROM {tname}), 1), "
                            f"(SELECT MAX(id) IS NOT NULL FROM {tname}))"
                        )
                    )

        after_fp = collect_db_fingerprint(tgt_engine)

        if before_fp != after_fp:
            raise RuntimeError(
                f"Migration verification failed! Source vs Target mismatch:\n"
                f"Source: {json.dumps(before_fp, indent=2)}\n"
                f"Target: {json.dumps(after_fp, indent=2)}"
            )

        return {
            "status": "verified_identical",
            "source_dialect": src_engine.dialect.name,
            "target_dialect": tgt_engine.dialect.name,
            "fingerprint": after_fp,
        }
    finally:
        src_engine.dispose()
        tgt_engine.dispose()


def main():
    parser = argparse.ArgumentParser(description="Migrate SQLite database to PostgreSQL and verify parity.")
    parser.add_argument(
        "--source",
        default="sqlite:///data/processed/professor_discovery.db",
        help="Source SQLAlchemy database URL",
    )
    parser.add_argument(
        "--target",
        default=os.getenv("POSTGRES_DATABASE_URL", ""),
        help="Target PostgreSQL SQLAlchemy database URL",
    )
    args = parser.parse_args()
    if not args.target:
        raise SystemExit("Error: --target (or POSTGRES_DATABASE_URL) must be provided.")
    report = migrate_database(args.source, args.target)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
