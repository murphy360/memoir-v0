from sqlalchemy.orm import Session

from app.models import LifePeriod, Question
from app.services.periods import unique_period_slug


SEED_QUESTIONS = [
    "What is your name, where are you recording from, and when is this memory from (day, month, year, or decade)?",
    "When and where were you born? If you are unsure of the date, tell us the closest year or decade.",
    "Tell me about your family - who are the most important people in your life?",
]


def normalize_question_text(value: str | None) -> str:
    return " ".join((value or "").split()).strip().casefold()


def add_unique_pending_questions(
    db: Session, question_texts: list[str], source_memory_id: int
) -> None:
    existing_pending = db.query(Question).filter(Question.status == "pending").all()
    seen_pending = {
        normalized
        for question in existing_pending
        for normalized in [normalize_question_text(question.text)]
        if normalized
    }

    for question_text in question_texts:
        normalized = normalize_question_text(question_text)
        if not normalized or normalized in seen_pending:
            continue
        db.add(
            Question(
                text=question_text, source_memory_id=source_memory_id, status="pending"
            )
        )
        seen_pending.add(normalized)


def ensure_default_starter_period(db: Session) -> None:
    if db.query(LifePeriod).first() is not None:
        return

    title = "Birth and Early Childhood"
    starter = LifePeriod(
        title=title,
        slug=unique_period_slug(db, title),
        start_date_text="Birth",
        end_date_text="Early years",
        summary="A starter period for first memories. You can rename or delete it anytime.",
    )
    db.add(starter)
    db.commit()


def seed_initial_questions(db: Session) -> None:
    if db.query(Question).count() == 0:
        for question_text in SEED_QUESTIONS:
            db.add(Question(text=question_text, status="pending"))
        db.commit()
    ensure_default_starter_period(db)
