import argparse
import logging
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from sqlalchemy.orm import Session

root_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root_dir))

from backend.database.connection import SessionLocal, init_db
from backend.database.models import (
    University,
    Department,
    Professor,
    Publication,
    ProfessorPublication,
    ResearchTopic,
    DataSource,
    VerificationRecord,
    VerificationStatus
)
from backend.services.reporting_service import ReportingService
from data_collection.department_scraper import DepartmentScraper
from data_collection.faculty_scraper import FacultyScraper
from data_collection.publication_fetcher import PublicationFetcher
from data_processing.cleaning import clean_author_name, clean_designation, normalize_email, normalize_url, infer_appointment_category
from data_processing.topic_extraction import extract_topics_from_text, get_or_create_topic
from verification.csv_export import CSVExporter
from verification.csv_import import CSVImporter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("PipelineRunner")


class PipelineRunner:
    def __init__(self, export_dir: Optional[str] = None):
        self.export_dir = Path(export_dir or root_dir / "data" / "exports")
        self.export_dir.mkdir(parents=True, exist_ok=True)
        self.exporter = CSVExporter(export_dir=str(self.export_dir))
        self.importer = CSVImporter()
        self.reporter = ReportingService()

    def stage_1_init_db(self):
        """Stage 1: Initialize or migrate database."""
        logger.info("=== STAGE 1: Initializing / Migrating Database & Seed University ===")
        init_db()
        db = SessionLocal()
        try:
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
                logger.info(f"Seeded university record: {univ.name}")
            else:
                logger.info(f"University record verified: {univ.name} (ID: {univ.id})")
        finally:
            db.close()

    def stage_2_discover_academic_units(self) -> Tuple[int, int]:
        """Stage 2: Discover IIT Kharagpur academic units (departments, schools, centres)."""
        logger.info("=== STAGE 2: Discovering IIT Kharagpur Academic Units ===")
        scraper = FacultyScraper()
        dept_scraper = DepartmentScraper()
        db = SessionLocal()
        try:
            added, updated = dept_scraper.scrape_and_save(db)
            logger.info(f"Academic units discovery: {added} new added, {updated} updated/existing.")
            return added, updated
        finally:
            db.close()

    def stage_3_4_5_collect_clean_persist_faculty(
        self,
        dept_codes: Optional[List[str]] = None,
        max_departments: Optional[int] = None,
        max_research_areas: Optional[int] = 0,
        max_faculty_per_dept: Optional[int] = None,
        enrich_profiles: bool = False,
        enrich_limit: Optional[int] = None
    ) -> Tuple[int, int]:
        """
        Stages 3, 4 & 5:
        - Stage 3: Collect faculty from official sources.
        - Stage 4: Clean and deduplicate faculty.
        - Stage 5: Persist faculty candidates independently of publications.
        """
        logger.info("=== STAGES 3, 4 & 5: Collecting, Cleaning & Persisting Faculty Candidates ===")
        scraper = FacultyScraper()
        db = SessionLocal()
        try:
            query = db.query(Department).order_by(Department.id.asc())
            if dept_codes:
                query = query.filter(Department.code.in_(dept_codes))
            depts = query.all()
            if max_departments:
                depts = depts[:max_departments]

            total_added = 0
            total_updated = 0
            for idx, dept in enumerate(depts, 1):
                logger.info(f"[{idx}/{len(depts)}] Scraping faculty for [{dept.code}] {dept.name}")
                try:
                    added, updated = scraper.scrape_department_faculty(
                        db=db,
                        department=dept,
                        max_research_areas=max_research_areas,
                        max_faculty=max_faculty_per_dept,
                        enrich_profiles=False
                    )
                    total_added += added
                    total_updated += updated
                except Exception as e:
                    logger.error(f"Error scraping faculty for {dept.code}: {e}")
                    dept.collection_status = "error"
                    dept.source_access_notes = str(e)
                    db.commit()

            if enrich_profiles:
                already_inspected = {
                    r[0] for r in db.query(DataSource.entity_id).filter(
                        DataSource.entity_type == "professor",
                        DataSource.source_name == "iitkgp_profile_page",
                        DataSource.http_status == 200
                    ).all()
                }
                q_profs = (
                    db.query(Professor)
                    .filter(
                        Professor.verification_status != VerificationStatus.REJECTED.value,
                        Professor.profile_url.isnot(None)
                    )
                    .order_by(Professor.id.asc())
                )
                if already_inspected:
                    q_profs = q_profs.filter(~Professor.id.in_(already_inspected))
                if enrich_limit and enrich_limit > 0:
                    q_profs = q_profs.limit(enrich_limit)
                target_profs = q_profs.all()
                logger.info(f"Enriching {len(target_profs)} faculty profiles with biographies, research areas & projects...")
                scraper.enrich_existing_professors(db, target_profs)

            scraper.validate_and_clean_existing_projects(db)
            self._clean_and_reconcile_faculty_records(db)
            logger.info(f"Faculty collection & persistence: {total_added} added, {total_updated} updated.")
            return total_added, total_updated
        finally:
            db.close()

    def _clean_and_reconcile_faculty_records(self, db: Session):
        """
        Stage 4 reconciliation:
        - Cleans names, designations, emails, and URLs.
        - Marks non-person/broken records (e.g. 'Data not found' headers) as rejected.
        - Reconciles primary department from official profile URL where unambiguous.
        - Updates has_publications, has_research_interests, has_biography, has_projects flags.
        """
        all_depts = db.query(Department).all()
        code_to_dept = {d.code.upper(): d for d in all_depts if d.code}
        dept_names_lower = {d.name.lower() for d in all_depts}

        professors = db.query(Professor).order_by(Professor.id.asc()).all()
        seen_url_to_prof: Dict[str, Professor] = {}

        for p in professors:
            p.name = clean_author_name(p.name) or p.name
            p.designation = clean_designation(p.designation) or p.designation
            p.email = normalize_email(p.email)
            p.profile_url = normalize_url(p.profile_url)
            p.appointment_category = infer_appointment_category(p.designation, p.appointment_category)

            # Reject broken profile pages where department header was scraped as professor name
            if p.name.lower() in dept_names_lower or "centre for " in p.name.lower() or "department of " in p.name.lower():
                if p.verification_status != VerificationStatus.REJECTED.value:
                    prev = p.verification_status
                    p.verification_status = VerificationStatus.REJECTED.value
                    db.add(VerificationRecord(
                        entity_type="professor",
                        entity_id=p.id,
                        previous_status=prev,
                        new_status=VerificationStatus.REJECTED.value,
                        verified_by="system_audit",
                        evidence_or_notes="Rejected: Broken official profile URL returned department header instead of faculty member",
                        source_url=p.profile_url
                    ))
                continue

            # Check for duplicate profile_url across departments
            if p.profile_url:
                if p.profile_url in seen_url_to_prof:
                    primary_prof = seen_url_to_prof[p.profile_url]
                    if p.id != primary_prof.id and p.verification_status != VerificationStatus.REJECTED.value:
                        prev = p.verification_status
                        p.verification_status = VerificationStatus.REJECTED.value
                        db.add(VerificationRecord(
                            entity_type="professor",
                            entity_id=p.id,
                            previous_status=prev,
                            new_status=VerificationStatus.REJECTED.value,
                            verified_by="deduplication_audit",
                            evidence_or_notes=f"Rejected duplicate candidate: same official profile_url as professor_id={primary_prof.id}",
                            source_url=p.profile_url
                        ))
                        continue
                else:
                    seen_url_to_prof[p.profile_url] = p

                # Reconcile primary department if URL specifies /department/<CODE>/faculty/
                m_dept = re.search(r"/department/([A-Za-z0-9]+)/faculty/", p.profile_url)
                if m_dept:
                    true_code = m_dept.group(1).upper()
                    if true_code in code_to_dept:
                        true_dept = code_to_dept[true_code]
                        if p.department_id != true_dept.id:
                            # Ensure no name collision in target department before moving
                            collision = db.query(Professor).filter(
                                Professor.department_id == true_dept.id,
                                Professor.name.ilike(p.name),
                                Professor.id != p.id
                            ).first()
                            if not collision:
                                p.department_id = true_dept.id
                                p.academic_unit = true_dept.academic_unit
                            elif p.verification_status != VerificationStatus.REJECTED.value:
                                prev = p.verification_status
                                p.verification_status = VerificationStatus.REJECTED.value
                                db.add(VerificationRecord(
                                    entity_type="professor",
                                    entity_id=p.id,
                                    previous_status=prev,
                                    new_status=VerificationStatus.REJECTED.value,
                                    verified_by="deduplication_audit",
                                    evidence_or_notes=f"Rejected cross-listed duplicate of professor_id={collision.id} in {true_code}",
                                    source_url=p.profile_url
                                ))

            if not p.academic_unit and p.department and p.department.academic_unit:
                p.academic_unit = p.department.academic_unit

            # Clean placeholder biography text if it was just 'Personal WebpageBio Sketch'
            if p.biography and p.biography.strip() in ("Personal WebpageBio Sketch", "Personal Webpage Bio Sketch"):
                p.biography = None

            # Update availability flags
            p.has_biography = bool(p.biography and len(p.biography.strip()) > 10)
            p.has_research_interests = bool(p.research_interests and len(p.research_interests.strip()) > 2)
            p.has_projects = len(p.professor_projects) > 0
            # has_publications means VERIFIED publication links only (pending/needs_review are candidates)
            p.has_publications = any(
                l.verification_status == VerificationStatus.VERIFIED.value
                for l in p.professor_publications
            )

        # Reconcile publication statuses (keep publications missing abstracts as pending unless manually verified)
        # and ensure Crossref provenance records exist for Crossref-verified DOIs
        existing_cr_ids = {
            r[0] for r in db.query(DataSource.entity_id).filter(DataSource.source_name == "crossref").all()
        }
        for l in db.query(ProfessorPublication).all():
            pub = l.publication
            if not pub:
                continue
            if l.affiliation_evidence and "Crossref" in l.affiliation_evidence and pub.doi and pub.id not in existing_cr_ids:
                db.add(DataSource(
                    entity_type="publication",
                    entity_id=pub.id,
                    source_name="crossref",
                    source_url=f"https://api.crossref.org/works/{pub.doi}",
                    http_status=200,
                    verification_status=pub.verification_status
                ))
                existing_cr_ids.add(pub.id)
            if l.verification_status == VerificationStatus.VERIFIED.value and not pub.abstract and l.id > 15:
                l.verification_status = VerificationStatus.PENDING.value
                pub.verification_status = VerificationStatus.PENDING.value

        db.commit()

    def stage_6_export_faculty_review(self) -> Path:
        """Stage 6: Export faculty review queues."""
        logger.info("=== STAGE 6: Exporting Faculty Candidates for Review ===")
        db = SessionLocal()
        try:
            csv_path = self.exporter.export_faculty_candidates(db, filename="faculty_review_queue.csv")
            logger.info(f"Exported faculty candidates to: {csv_path}")
            return csv_path
        finally:
            db.close()

    def stage_7_import_approved_faculty(self, reviewed_csv_path: Optional[Path] = None, auto_approve_confident: bool = False):
        """Stage 7: Import approved faculty records."""
        logger.info("=== STAGE 7: Importing Approved Faculty Records ===")
        target_path = reviewed_csv_path or (self.export_dir / "faculty_approved.csv")
        db = SessionLocal()
        try:
            if target_path.exists():
                stats = self.importer.import_reviewed_faculty(db, target_path)
                logger.info(f"Imported approved faculty records from {target_path}: {stats}")
            if auto_approve_confident:
                approved_count = 0
                needs_review_count = 0
                profs = db.query(Professor).filter(Professor.verification_status == VerificationStatus.PENDING.value).all()
                for p in profs:
                    if (
                        p.email
                        and p.profile_url
                        and "iitkgp.ac.in" in p.profile_url
                        and "iitkgp.ac.in" in p.email.lower()
                        and p.designation
                        and p.designation != "Faculty Member"
                    ):
                        prev = p.verification_status
                        p.verification_status = VerificationStatus.VERIFIED.value
                        db.add(VerificationRecord(
                            entity_type="professor",
                            entity_id=p.id,
                            previous_status=prev,
                            new_status=VerificationStatus.VERIFIED.value,
                            verified_by="institutional_profile_verification",
                            evidence_or_notes="Verified via official iitkgp.ac.in profile URL, designation, and institutional email domain",
                            source_url=p.profile_url
                        ))
                        approved_count += 1
                    elif not p.email or not p.profile_url:
                        prev = p.verification_status
                        p.verification_status = VerificationStatus.NEEDS_REVIEW.value
                        db.add(VerificationRecord(
                            entity_type="professor",
                            entity_id=p.id,
                            previous_status=prev,
                            new_status=VerificationStatus.NEEDS_REVIEW.value,
                            verified_by="institutional_profile_verification",
                            evidence_or_notes="Flagged needs_review: missing institutional email or profile URL",
                            source_url=p.profile_url or p.source_url
                        ))
                        needs_review_count += 1
                db.commit()
                logger.info(
                    f"Verified {approved_count} faculty with confirmed institutional email & profile; "
                    f"{needs_review_count} flagged needs_review; remaining kept pending."
                )
            else:
                logger.info(f"No manual review file found at {target_path}. Candidates remain in review queue.")
        finally:
            db.close()

    def stage_8_to_12_publications_pipeline(
        self,
        limit_professors: Optional[int] = None,
        verify_with_crossref: bool = True
    ) -> Dict[str, int]:
        """
        Stages 8, 9, 10, 11 & 12:
        - Stage 8: Discover publication authors.
        - Stage 9: Fetch publication candidates.
        - Stage 10: Verify publication metadata (Crossref).
        - Stage 11: Perform author disambiguation.
        - Stage 12: Persist publication candidates.
        Resumes automatically from professors not yet searched in OpenAlex.
        """
        logger.info("=== STAGES 8-12: Publication Discovery, Verification, Disambiguation & Persistence ===")
        fetcher = PublicationFetcher()
        db = SessionLocal()
        try:
            already_searched = {
                r[0] for r in db.query(DataSource.entity_id).filter(
                    DataSource.entity_type == "professor",
                    DataSource.source_name.in_(["openalex_author_lookup", "crossref_author_lookup"])
                ).all()
            }
            already_have_pubs = {
                r[0] for r in db.query(ProfessorPublication.professor_id).distinct().all()
            }
            skip_ids = already_searched | already_have_pubs

            query = (
                db.query(Professor)
                .filter(Professor.verification_status != VerificationStatus.REJECTED.value)
                .order_by(Professor.id.asc())
            )
            if skip_ids:
                query = query.filter(~Professor.id.in_(skip_ids))
            if limit_professors and limit_professors > 0:
                query = query.limit(limit_professors)
            professors = query.all()

            logger.info(f"Processing {len(professors)} professors for OpenAlex & Crossref publication discovery (skipping {len(skip_ids)} already processed)...")
            totals = fetcher.fetch_for_professors_batch(
                db=db,
                professors=professors,
                verify_with_crossref=verify_with_crossref,
                max_workers=4,
                batch_size=50
            )
            logger.info(f"Publication pipeline stages 8-12 complete: {totals}")
            return totals
        finally:
            db.close()

    def stage_13_export_publication_review(self) -> Path:
        """Stage 13: Export publication review queues."""
        logger.info("=== STAGE 13: Exporting Publication Records for Review ===")
        db = SessionLocal()
        try:
            csv_path = self.exporter.export_publication_candidates(
                db,
                filename="publication_review_queue.csv"
            )
            logger.info(f"Exported publication review queue to: {csv_path}")
            return csv_path
        finally:
            db.close()

    def stage_14_import_approved_publications(self, reviewed_csv_path: Optional[Path] = None, auto_approve_confident: bool = False):
        """Stage 14: Import approved publication relationships."""
        logger.info("=== STAGE 14: Importing Approved Publications ===")
        target_path = reviewed_csv_path or (self.export_dir / "publication_approved.csv")
        db = SessionLocal()
        try:
            if target_path.exists():
                stats = self.importer.import_reviewed_publications(db, target_path)
                logger.info(f"Imported approved publications from {target_path}: {stats}")
            if auto_approve_confident:
                approved_count = 0
                links = (
                    db.query(ProfessorPublication)
                    .filter(
                        ProfessorPublication.verification_status == VerificationStatus.PENDING.value,
                        ProfessorPublication.confidence_score >= 0.85
                    )
                    .all()
                )
                for l in links:
                    if not l.publication or not l.publication.doi or not l.publication.abstract:
                        continue
                    prev = l.verification_status
                    l.verification_status = VerificationStatus.VERIFIED.value
                    l.publication.verification_status = VerificationStatus.VERIFIED.value
                    if l.professor:
                        l.professor.has_publications = True
                    db.add(VerificationRecord(
                        entity_type="professor_publication",
                        entity_id=l.id,
                        previous_status=prev,
                        new_status=VerificationStatus.VERIFIED.value,
                        verified_by="high_confidence_disambiguation",
                        evidence_or_notes=l.affiliation_evidence,
                        source_url=l.publication.source_url or l.publication.openalex_id
                    ))
                    approved_count += 1
                db.commit()
                logger.info(f"Verified {approved_count} high-confidence publications.")
            else:
                logger.info(f"No manual review file found at {target_path}. Publications remain in review queue.")
        finally:
            db.close()

    def stage_15_extract_research_topics(self) -> int:
        """Stage 15: Extract and link normalized research topics across professors and publications."""
        logger.info("=== STAGE 15: Extracting & Normalizing Research Topics ===")
        db = SessionLocal()
        try:
            profs = db.query(Professor).filter(Professor.research_interests.isnot(None)).all()
            linked_count = 0
            for p in profs:
                topics = extract_topics_from_text(p.research_interests)
                for t_name in topics:
                    topic = get_or_create_topic(db, t_name)
                    if topic and topic not in p.topics:
                        p.topics.append(topic)
                        linked_count += 1
            db.commit()
            total_topics = db.query(ResearchTopic).count()
            logger.info(f"Topic extraction complete: {linked_count} new links created, {total_topics} total unique topics.")
            return total_topics
        finally:
            db.close()

    def stage_16_and_17_generate_reports(self) -> Dict:
        """
        Stages 16 & 17:
        - Stage 16: Generate collection summary report (collection_summary_report.json).
        - Stage 17: Generate department-wise, faculty-wise, and publication coverage CSV reports.
        """
        logger.info("=== STAGES 16 & 17: Generating Summary & Coverage Reports ===")
        db = SessionLocal()
        try:
            self._clean_and_reconcile_faculty_records(db)
            report = self.reporter.generate_all_reports(db)
            fac = report["faculty"]
            pub = report["publications"]
            dept = report["departments"]

            logger.info("=" * 65)
            logger.info("COLLECTION & COVERAGE SUMMARY REPORT")
            logger.info("=" * 65)
            logger.info(f"Institution: {report['institution']}")
            logger.info(f"Database: {report['active_database']['type']} ({report['active_database']['url_configured']})")
            logger.info(f"Departments Collected: {dept['total_departments_collected']} (With Faculty: {dept['departments_with_faculty']})")
            logger.info(
                f"Faculty Candidates: {fac['total_candidates_collected']} "
                f"(Verified: {fac['verified']}, Pending: {fac['pending_review']}, "
                f"Needs Review: {fac['needs_review']}, Rejected: {fac['rejected']})"
            )
            logger.info(
                f"Faculty Publications Breakdown: With Publications={fac['faculty_with_publications']}, "
                f"Without Publications={fac['faculty_without_publications']}"
            )
            logger.info(
                f"Publications: {pub['total_candidates_collected']} "
                f"(Verified: {pub['verified']}, Pending: {pub['pending_review']}, "
                f"Needs Review: {pub['needs_review']}, Unique DOIs: {pub['unique_dois']})"
            )
            logger.info(
                f"Author-Publication Links: {pub['total_author_publication_links']} "
                f"(Verified: {pub['verified_professor_publication_links']}, "
                f"Ambiguous/Needs Review: {pub['ambiguous_author_matches']})"
            )
            logger.info(f"Research Topics: {report['research_topics']['total_topics_extracted']}")
            logger.info(f"Research Projects: {report['research_projects']['total_projects_extracted']}")
            logger.info("=" * 65)
            return report
        finally:
            db.close()


def run_pipeline(
    stages: Optional[List[int]] = None,
    dept_codes: Optional[List[str]] = None,
    max_departments: Optional[int] = None,
    max_research_areas: Optional[int] = 0,
    max_faculty_per_dept: Optional[int] = None,
    limit_professors_for_pubs: Optional[int] = None,
    enrich_profiles: bool = False,
    enrich_limit: Optional[int] = None,
    auto_approve: bool = False
):
    runner = PipelineRunner()
    all_stages = not stages

    def should_run(*st_nums):
        if all_stages:
            return True
        return any(s in stages for s in st_nums)

    if should_run(1):
        runner.stage_1_init_db()

    if should_run(2):
        runner.stage_2_discover_academic_units()

    if should_run(3, 4, 5):
        runner.stage_3_4_5_collect_clean_persist_faculty(
            dept_codes=dept_codes,
            max_departments=max_departments,
            max_research_areas=max_research_areas,
            max_faculty_per_dept=max_faculty_per_dept,
            enrich_profiles=enrich_profiles,
            enrich_limit=enrich_limit
        )

    if should_run(6):
        runner.stage_6_export_faculty_review()

    if should_run(7):
        runner.stage_7_import_approved_faculty(auto_approve_confident=auto_approve)

    if should_run(8, 9, 10, 11, 12):
        runner.stage_8_to_12_publications_pipeline(limit_professors=limit_professors_for_pubs)

    if should_run(13):
        runner.stage_13_export_publication_review()

    if should_run(14):
        runner.stage_14_import_approved_publications(auto_approve_confident=auto_approve)

    if should_run(15):
        runner.stage_15_extract_research_topics()

    if should_run(16, 17):
        runner.stage_16_and_17_generate_reports()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="IIT Kharagpur Data Collection & Verification Pipeline (Stages 1-17)")
    parser.add_argument("--stages", type=int, nargs="+", help="Specific stage numbers to execute (1-17)")
    parser.add_argument("--dept", nargs="+", help="Specific department codes to scrape")
    parser.add_argument("--max-depts", type=int, default=None, help="Limit number of departments to collect")
    parser.add_argument("--max-areas", type=int, default=0, help="Max research areas per department to explore on fallback")
    parser.add_argument("--max-faculty", type=int, default=None, help="Max faculty candidates per department")
    parser.add_argument("--limit-pubs", type=int, default=None, help="Limit professors for publication fetch (default: all unprocessed)")
    parser.add_argument("--enrich-profiles", action="store_true", help="Enrich faculty from individual profile pages")
    parser.add_argument("--enrich-limit", type=int, default=None, help="Limit profiles to enrich in a single run (default: all unprocessed)")
    parser.add_argument("--auto-approve", action="store_true", help="Auto-approve high-confidence records")
    args = parser.parse_args()

    auto_approve_flag = args.auto_approve or os.getenv("AUTO_APPROVE_HIGH_CONFIDENCE", "false").lower() == "true"

    run_pipeline(
        stages=args.stages,
        dept_codes=args.dept,
        max_departments=args.max_depts,
        max_research_areas=args.max_areas,
        max_faculty_per_dept=args.max_faculty,
        limit_professors_for_pubs=args.limit_pubs,
        enrich_profiles=args.enrich_profiles,
        enrich_limit=args.enrich_limit,
        auto_approve=auto_approve_flag
    )
