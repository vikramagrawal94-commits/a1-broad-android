from __future__ import annotations
from .models import StrategyProfile

A1_V1 = StrategyProfile(code='A1-V1', name='A1_CANONICAL_REVERSAL', priority=1)
ALL_PROFILES = (A1_V1,)
PROFILE_BY_CODE = {p.code:p for p in ALL_PROFILES}
