# Audit remediation (16 September 2026)

Scope: corrective changes only, no new AI OS feature development.

1. Fail closed when Bubblewrap is disabled, including direct runtime API calls.
2. Until agent-write versioning can be demonstrated, prevent Pi tools from modifying workspace documents. Preserve writable Pi session/config state in a narrow mount and verify confinement with the actual Bubblewrap gate on CachyOS/Wayland.
3. Correct accessibility contrast for informational text, update architectural documentation and test coverage.
4. Re-run all CI jobs and record remaining gates accurately. Do not claim real GPU/Wayland or LAN tests without evidence.

This file tracks the corrective branch and will be replaced by the final remediation report.
