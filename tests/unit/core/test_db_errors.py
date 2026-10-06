"""SQLSTATE helpers used by the database handler and by repositories that map unique races."""

from types import SimpleNamespace

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.db_errors import UNIQUE_VIOLATION, constraint_name, is_unique_violation, sqlstate


def _error(orig) -> IntegrityError:
    return IntegrityError("INSERT", {}, orig)


@pytest.mark.unit
class TestSqlstate:
    def test_reads_sqlstate_of_the_driver_error(self):
        assert sqlstate(_error(SimpleNamespace(sqlstate="23503"))) == "23503"

    def test_reads_pgcode_and_the_wrapped_cause(self):
        orig = SimpleNamespace(__cause__=SimpleNamespace(pgcode=UNIQUE_VIOLATION))

        assert sqlstate(_error(orig)) == UNIQUE_VIOLATION

    def test_falls_back_to_the_message_text(self):
        assert sqlstate(_error(Exception('duplicate key value violates unique constraint "x"'))) == UNIQUE_VIOLATION

    def test_unknown_error_has_no_sqlstate(self):
        assert sqlstate(_error(Exception("boom"))) is None


@pytest.mark.unit
class TestUniqueViolation:
    def test_true_only_for_unique_violations(self):
        assert is_unique_violation(_error(SimpleNamespace(sqlstate=UNIQUE_VIOLATION))) is True
        assert is_unique_violation(_error(SimpleNamespace(sqlstate="23503"))) is False

    def test_constraint_name_comes_from_the_driver_error(self):
        assert constraint_name(_error(SimpleNamespace(constraint_name="uq_feature_name"))) == "uq_feature_name"
        assert constraint_name(_error(Exception("x"))) is None
