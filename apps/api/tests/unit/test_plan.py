import pytest

from app.domain import PlanRequiredError
from app.models.user import User, UserPlan
from app.utils.plan import requires_pro


def _make_user(plan: UserPlan) -> User:
    return User(
        id=1,
        name="Santi",
        email="santi@example.com",
        password_hash="x",
        plan=plan,
    )


# --- requires_pro ---


class TestRequiresPro:
    def test_pro_user_passes(self):
        # A Pro user does not raise.
        requires_pro(_make_user(UserPlan.pro))

    def test_free_user_raises(self):
        # A free user is gated.
        with pytest.raises(PlanRequiredError):
            requires_pro(_make_user(UserPlan.free))
