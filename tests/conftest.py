import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("PYSPARK_PYTHON", sys.executable)

from reconcilegate.lakehouse import build_spark  # noqa: E402


@pytest.fixture(scope="session")
def spark():
    s = build_spark(app_name="reconcilegate-tests")
    yield s
    s.stop()
