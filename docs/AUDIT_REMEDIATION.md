# Audit remediation — 16 September 2026

Status: **corrective branch; not accepted on the target desktop and not a completed M1 milestone.** This report supersedes the temporary `_audit-remediation-plan.md` on the branch. It does not modify the historical M0 evidence: M0 verified the earlier read-write workspace policy; today's changes must be tested again.

## Source and ownership inventory

- `core/sandbox.py` is the single Bubblewrap mount policy for runtime and active gate; `core/agent/runtime.py` constructs the mandatory Pi RPC launch specification.
- `core/agent/bootstrap.py` prepares Pi runtime paths, model configuration and credentials; Qt `QProcess` starts and owns the process in `ui/native`.
- Pi is canonical for session data; `.pi-agent` inside the workspace holds app-isolated Pi configuration and session files.
- `AgentController` owns workspace selection and current Pi connection; `WorkspaceBrowserController` and `WorkspaceDocumentController` do not write documents.
- `WorkspacePanel.qml` and `DocumentPanel.qml` are presentation only. The flat lazy `WorkspaceTreeListModel` is a deliberate current implementation; a future hierarchical model needs measured justification rather than a cosmetic migration.

## Changes actually made

1. **Mandatory sandbox:** `build_launch_spec` rejects `sandbox_enabled=False`. The unsandboxed launch branch and unsandboxed environment construction were removed. Missing Bubblewrap remains a startup failure, not a fallback.
2. **Protect unversioned documents:** `build_bubblewrap_arguments` mounts `/workspace` read-only, then mounts only `/workspace/.pi-agent` read-write, so Pi can persist sessions/model configuration. The writable state path rejects a pre-existing symlink/non-directory; runtime path preparation also rejects symlinked `.pi-agent` and `sessions`. `--share-net` is unchanged: this is filesystem isolation, not network egress control.
3. **State is explicit in the GUI:** Knowledge panel displays the disabled agent-document-write policy; selected rows use orange text and a lightweight inset cue, with no per-row expensive shader.
4. **Contrast improvements:** Knowledge/browser status and Document path/status text use the existing `textSecondary` token instead of low-contrast `textMuted`, preserving the canonical RGB tokens in `Theme.qml`.
5. **Regression tests:** runtime rejects direct launch and symlinked state paths; the sandbox arguments must contain one writable bind for `.pi-agent` and a read-only bind for the document workspace. The CI gate covers Python 3.12–3.14, compileall, zero-warning QML lint, pytest and offscreen smoke.
6. **Documentation:** AGENTS.md and ADR-020 describe current behavior and explicitly distinguish historical M0 tests from the newly required target test.

## Deliberate functional change and limitations

- The M0 test where Pi modified a document is *historical* and will no longer succeed with this branch. This is intentional: the prior path could overwrite important files without pre-write snapshots. Do not advertise agent document editing until the complete versioning/conflict/recovery path is proven. The app's read-only preview and chat are supposed to remain functional.
- `.pi-agent` remains writable to Pi itself. Protect its own config/session integrity and consider recovery/backup separately; the document write block does not establish provenance or rollback for state stored there.
- The existing active Bubblewrap gate tests a write *inside* `.pi-agent`, historically called `workspace-write`; it does not yet dynamically test a rejected document write. Its old label is not evidence of full workspace writability. The actual document-denial assertion below is a new required target gate.
- All file-level protections depend on the real Bubblewrap setup. Static argv tests alone do not prove mount behavior. The pre-existing M1 preview target gate (#27) also remains open.
- Remaining code audit debt is tracked separately: `AgentController` growth, `Main.qml` informational `textMuted` uses and visual contrast/focus on a real GPU, settings-level rejection of legacy `sandbox_enabled=false`, reproducible installer, PSS measurements and updating the older 'proposed architecture' headings. None of these is falsely marked complete here.

## Mandatory real-desktop gate before merge

Use a **disposable workspace containing only synthetic files**, never the personal archive. Record the tested commit, CachyOS, Qt/PySide6, Pi, Bubblewrap versions and results. Do not alter the actual personal archive to test this policy.

1. Create the disposable workspace with a sentinel text file at its root, and preserve its hash/content externally before testing. Select it in Pi_UI.
2. Run the GUI host preflight and active Bubblewrap gate. Confirm no fallback to direct Pi. Existing gate checks should continue to pass, with the writable `.pi-agent` storage remaining functional.
3. Connect to Pi and attempt a simple **tool** write to the root sentinel and creation of a new file in `/workspace`. Both must fail due to the read-only mount; the original bytes/hash and directory entries must remain unchanged. If Pi finds an alternate writing path, the gate fails.
4. Disconnect and reconnect to the *same exact* session. Verify session history still persists in `.pi-agent/sessions`, and a response from Ornith can still stream. Test stop and normal application shutdown with no app-owned orphan processes.
5. Try an external sentinel path and a symlink from the workspace to an outside file. Both must remain inaccessible, as under the earlier M0 confinement gate. Test that injected symlinks for `.pi-agent` or `sessions` fail startup instead of redirecting writes.
6. Repeat preview checks from issue #27 on actual Wayland: UTF-8 content, reload after external change, CRLF/Unicode copy, binary explicit state, drawer minimum layout, scrolling, focus.
7. Confirm the Knowledge panel visibly explains that agent document writes are disabled. Inspect readability of status text and orange selected rows on the actual GPU and at minimum supported geometry; record PSS for GUI, Pi and workers separately if making any performance claim.

Record results in this file only after execution. **No target execution occurred during this corrective branch work.**

## Remaining acceptance gates / follow-up

- Implement proper pre-write snapshot/hash revision service, error handling and crash recovery for *every* autonomous shell/tool writer before allowing writable document mounts again. A watcher after mutation is insufficient.
- Eliminate the remaining semantic low-contrast status text from `Main.qml`, then check keyboard/focus/contrast visually.
- Reassess whether the flat list model is adequate under measured realistic tree sizes; keep it if performance is acceptable and update architecture prose accordingly.
- Update outdated roadmap/architecture phase language, and only add an installer when its end-to-end behavior can be tested. Do not turn these into placeholder features.
- Keep PR in draft until CI and target gate are observed; do not merge based on historical M0 results alone.
