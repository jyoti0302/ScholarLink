import re
from typing import List, Optional
from sqlalchemy.orm import Session
from backend.database.models import ResearchTopic
from data_processing.cleaning import clean_text


def normalize_topic_name(name: str) -> str:
    """Normalizes topic/keyword name for consistent association."""
    cleaned = clean_text(name)
    if not cleaned:
        return ""
    # Strip leading/trailing punctuation or bullet marks
    cleaned = re.sub(r"^[\s\-\*\•\d\.\:]+", "", cleaned)
    cleaned = re.sub(r"[\s\.\:\;]+$", "", cleaned)
    # Title-case for display consistency
    return cleaned.strip()


def get_or_create_topic(db: Session, topic_name: str, description: Optional[str] = None) -> Optional[ResearchTopic]:
    """Retrieves or creates a ResearchTopic by normalized name."""
    norm_name = normalize_topic_name(topic_name)
    if not norm_name or len(norm_name) < 2:
        return None

    existing = db.query(ResearchTopic).filter(
        ResearchTopic.topic_name.ilike(norm_name)
    ).first()

    if existing:
        return existing

    new_topic = ResearchTopic(
        topic_name=norm_name,
        description=clean_text(description)
    )
    db.add(new_topic)
    db.flush()
    return new_topic


def extract_topics_from_text(text: Optional[str]) -> List[str]:
    """Splits comma/semicolon/newline-delimited text into topic strings."""
    if not text:
        return []
    parts = re.split(r"[,;\n\r\|]+", text)
    topics = []
    for p in parts:
        normalized = normalize_topic_name(p)
        if normalized and len(normalized) > 2 and normalized not in topics:
            topics.append(normalized)
    return topics
