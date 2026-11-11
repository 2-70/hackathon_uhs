import pytest

from backend.app.ai import gemini


@pytest.fixture(autouse=True)
def forget_busy_models():
    """A model marked overloaded or out of quota by one test must not change which model the next test calls."""
    gemini.MODEL_BUSY_UNTIL.clear()
    gemini.QUOTA_SPENT_UNTIL.clear()
    yield
    gemini.MODEL_BUSY_UNTIL.clear()
    gemini.QUOTA_SPENT_UNTIL.clear()
