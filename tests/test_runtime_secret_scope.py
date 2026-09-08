from __future__ import annotations

from pathlib import Path

from core.agent.runtime import build_launch_spec
from core.settings import AgentSettings


def test_keyless_runtime_does_not_copy_named_secret_even_if_dataclass_is_unvalidated(
    tmp_path: Path,
) -> None:
    spec = build_launch_spec(
        AgentSettings(
            auth_mode="none",
            api_key_env="HOST_SECRET",
        ),
        working_directory=tmp_path,
        base_environment={
            "USER": "tester",
            "HOST_SECRET": "must-stay-on-host",
        },
    )

    assert "HOST_SECRET" not in spec.environment
    assert "must-stay-on-host" not in "\0".join(spec.arguments)
