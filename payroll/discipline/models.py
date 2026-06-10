"""
Discipline management models.

Currently re-exported from accounting.models for backward compatibility.
A future migration will physically move these models here.

Migration plan (for a future release):
1. Create concrete models in this file matching accounting.models signatures
2. Run makemigrations to create new tables
3. Write a data migration to copy all rows from accounting_* tables
4. Update all ForeignKey references to point here
5. Remove old models from accounting/models.py
6. Run makemigrations to drop old tables
"""

from accounting.models import (
    DisciplinaryCase,
    DisciplinarySanction,
    DisciplinaryEvidence,
    DisciplinaryAppeal,
)

__all__ = [
    "DisciplinaryCase",
    "DisciplinarySanction",
    "DisciplinaryEvidence",
    "DisciplinaryAppeal",
]
