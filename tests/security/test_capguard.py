from dataclasses import replace

import pytest
from mcp_capguard import CapabilityProfile, CapabilityViolation

from tests.capguard_profiles import capguard_profiles


async def test_declared_tool_policy(capguard_profile: CapabilityProfile) -> None:
    await capguard_profile.check()


async def test_readonly_policy_rejects_enabling_actual_write_tools() -> None:
    readonly = capguard_profiles()[0]
    write_enabled = readonly.settings.model_copy(update={"wiki_write": True})
    with pytest.raises(CapabilityViolation) as failure:
        await replace(readonly, settings=write_enabled).check()
    assert {"wiki_create_page", "wiki_update_page"} <= failure.value.forbidden
