import importlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def pytest_addoption(parser):
    parser.addoption("--impl", default="v1", choices=["v0", "v1"],
                     help="which calculation to test: v0 (original) or v1 (fixed)")


@pytest.fixture(scope="session")
def impl(request):
    return importlib.import_module(f"distance.calc_{request.config.getoption('--impl')}")
