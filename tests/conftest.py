"""共享测试夹具。"""

from __future__ import annotations

from typing import Any

import pytest

from tests.helpers import valid_sample_dict


@pytest.fixture
def sample_dict() -> dict[str, Any]:
    return valid_sample_dict()
