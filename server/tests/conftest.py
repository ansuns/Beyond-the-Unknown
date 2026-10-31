"""Test-suite defaults so the suite is runnable without CI environment variables.

``app.main`` resolves its settings at import time and its lifespan starts the
Redis presence listener unless ``APP_ENV`` is ``test``. Tests that are meant to
run without PostgreSQL/Redis therefore only work when ``APP_ENV=test`` is
exported, which CI does but a clean checkout does not.

The default is applied with ``setdefault`` so an explicit override (for example
``APP_ENV=local`` while debugging) still wins.
"""

import os

os.environ.setdefault("APP_ENV", "test")
