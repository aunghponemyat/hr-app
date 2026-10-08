import sys

from sqlalchemy.exc import SQLAlchemyError

from app.core.database import SessionLocal
from app.services.reference_service import seed_reference_data

__all__ = ["seed_reference_data"]


def main() -> int:
    try:
        with SessionLocal() as session, session.begin():
            seed_reference_data(session)
    except SQLAlchemyError:
        # Never print connection URLs or driver exceptions: they may contain credentials.
        print(
            "Seeding failed. Check database connectivity and run Alembic migrations.",
            file=sys.stderr,
        )
        return 1
    print("Reference data seeded successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
