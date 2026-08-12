"""G029 red-team keepers: adversarial attacks on the vertical slice.

Companion to docs/red_team/G029.md. Every test here is an attack that
found (or pins) live surface; strict-xfail tests are ratchets for open
defects (they XPASS loudly when the defect is fixed, forcing the marker
flip — the same discipline as the RT-G025..G035 ratchets).
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.leakage
