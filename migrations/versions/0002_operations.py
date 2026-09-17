"""Add lifecycle, documents, exams, payroll and expenditure modules.

Revision ID: 0002_operations
Revises: 0001_initial
Create Date: 2026-09-18
"""

from alembic import op

from app.db.base import Base
from app.models import *  # noqa: F401,F403

revision = "0002_operations"
down_revision = "0001_initial"
branch_labels = None
depends_on = None

NEW_TABLES = [
    "lifecycle_events",
    "document_records",
    "exams",
    "exam_scores",
    "report_cards",
    "salary_structures",
    "payroll_runs",
    "payroll_items",
    "expense_categories",
    "expenses",
]


def upgrade() -> None:
    bind = op.get_bind()
    for table_name in NEW_TABLES:
        Base.metadata.tables[table_name].create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    for table_name in reversed(NEW_TABLES):
        Base.metadata.tables[table_name].drop(bind=bind, checkfirst=True)
