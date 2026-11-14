import pytest

from backend.app.conditions import terrain_shadows
from backend.app.core.config import get_settings


@pytest.fixture(autouse=True)
def reset_global_caches():
    yield
    get_settings.cache_clear()
    terrain_shadows._default_analyzer = None
