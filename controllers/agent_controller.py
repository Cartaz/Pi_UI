"""Application controller for the first Pi_UI chat workflow."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from enum import StrEnum
from pathlib import Path
from typing import Any, TypeAlias

from core.agent import (
    AgentClient,
    AgentInactivityTimeoutError,
    AgentRequestTimeoutError,
    AgentTransport,
    DeadlineScheduler,
    DiscoveredModelProfile,
    ExistingModelsConfig,
    PiLaunchSpec,
    PiModelsConfigDiscovery,
    PiRuntimeBootstrap,
    PiRuntimePaths,
    TransportState,
    TurnState,
)
from core.session_id import is_valid_session_id
from core.settings import AgentSettings, AppSettings, SettingsStore

TransportFactory: TypeAlias = Callable[[PiLaunchSpec, int, int], AgentTransport]
DeadlineSchedulerFactory: TypeAlias = Callable[[], DeadlineScheduler]
StateHandler: TypeAlias = Callable[[], None]
ProfilesHandler: TypeAlias = Callable[[tuple["AgentProfile", ...], int], None]
MessagesResetHandler: TypeAlias = Callable[[tuple["ConversationMessage", ...]], None]
MessageHandler: TypeAlias = Callable[[int, "ConversationMessage"], None]
RecoveredQueueHandler: TypeAlias = Callable[[tuple[str, ...], tuple[str, ...]], None]


class AgentControllerError(RuntimeError):
    """Raised when a requested chat workflow is not currently valid."""


class ConnectionState(StrEnum):
    DISCONNECTED = "disconnected"
    STARTING = "starting"
    LOADING_SESSION = "loading-session"
    READY = "ready"
    STOPPING = "stopping"
    FAILED = "failed"


class RuntimeProfileSource(StrEnum):
    EXISTING = "existing"
    SETTINGS = "settings"


class MessageState(StrEnum):
    SENDING = "sending"
    ACCEPTED = "accepted"
    STREAMING = "streaming"
    COMPLETE = "complete"
    UNCERTAIN = "uncertain"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class AgentProfile:
    key: str
    provider: str
    model: str
    base_url: str | None
    api: str | None
    source: RuntimeProfileSource
    discovered: DiscoveredModelProfile | None = None

    @property
    def label(self) -> str:
        return f"{self.model} · {self.provider}"


@dataclass(frozen=True, slots=True)
class ConversationMessage:
    message_id: str
    role: str
    text: str
    state: MessageState


class AgentController:
    """Coordinate workspace discovery, Pi process lifecycle and chat state.

    The controller has no Qt dependency. It never edits an existing unmanaged
    ``models.json``: discovered baselines are launched through
    ``PiRuntimeBootstrap.prepare_existing`` with a SHA-256 recheck immediately
    before process start.
    """

    def __init__(
        self,
        settings_store: SettingsStore,
        transport_factory: TransportFactory,
        *,
        settings: AppSettings | None = None,
        discovery: PiModelsConfigDiscovery | None = None,
        bootstrap: PiRuntimeBootstrap | None = None,
        deadline_scheduler_factory: DeadlineSchedulerFactory | None = None,
    ) -> None:
        self._settings_store = settings_store
        self._settings = settings or settings_store.load()
        self._transport_factory = transport_factory
        self._deadline_scheduler_factory = deadline_scheduler_factory
        self._discovery = discovery or PiModelsConfigDiscovery()
        self._bootstrap = bootstrap or PiRuntimeBootstrap(discovery=self._discovery)

        self._workspace: Path | None = None
        self._existing_config: ExistingModelsConfig | None = None
        self._profiles: tuple[AgentProfile, ...] = ()
        self._selected_profile_index = -1

        self._transport: AgentTransport | None = None
        self._client: AgentClient | None = None
        self._connection_state = ConnectionState.DISCONNECTED
        self._turn_state = TurnState.IDLE
        self._session_ready = False
        self._requested_session_id: str | None = None
        self._requires_reconciliation = False
        self._inactivity_warning = False
        self._last_error: str | None = None
        self._status_text = "Choose an AIOS workspace"
        self._disconnect_requested = False
        self._diagnostic_tail = ""

        self._messages: list[ConversationMessage] = []
        self._message_counter = 0
        self._prompt_requests: dict[str, int] = {}
        self._active_assistant_index: int | None = None

        self._state_handler: StateHandler = lambda: None
        self._profiles_handler: ProfilesHandler = lambda _profiles, _selected: None
        self._messages_reset_handler: MessagesResetHandler = lambda _messages: None
        self._message_added_handler: MessageHandler = lambda _index, _message: None
        self._message_changed_handler: MessageHandler = lambda _index, _message: None
        self._recovered_queue_handler: RecoveredQueueHandler = (
            lambda _steering, _follow_up: None
        )

        if self._settings.workspace_root:
            candidate = Path(self._settings.workspace_root).expanduser()
            if candidate.is_dir():
                self._workspace = candidate.resolve()
                self._refresh_profiles()
            else:
                self._status_text = "Saved workspace is unavailable"

    @property
    def settings(self) -> AppSettings:
        return self._settings

    @property
    def workspace(self) -> Path | None:
        return self._workspace

    @property
    def profiles(self) -> tuple[AgentProfile, ...]:
        return self._profiles

    @property
    def selected_profile_index(self) -> int:
        return self._selected_profile_index

    @property
    def selected_profile(self) -> AgentProfile | None:
        if 0 <= self._selected_profile_index < len(self._profiles):
            return self._profiles[self._selected_profile_index]
        return None

    @property
    def messages(self) -> tuple[ConversationMessage, ...]:
        return tuple(self._messages)

    @property
    def connection_state(self) -> ConnectionState:
        return self._connection_state

    @property
    def turn_state(self) -> TurnState:
        return self._turn_state

    @property
    def session_ready(self) -> bool:
        return self._session_ready

    @property
    def last_error(self) -> str | None:
        return self._last_error

    @property
    def status_text(self) -> str:
        return self._status_text

    @property
    def diagnostic_tail(self) -> str:
        return self._diagnostic_tail

    @property
    def can_connect(self) -> bool:
        return (
            self._client is None
            and self._workspace is not None
            and self.selected_profile is not None
            and self._connection_state in {ConnectionState.DISCONNECTED, ConnectionState.FAILED}
        )

    @property
    def can_disconnect(self) -> bool:
        return self._client is not None and self._connection_state != ConnectionState.STOPPING

    @property
    def can_send(self) -> bool:
        return (
            self._client is not None
            and self._connection_state == ConnectionState.READY
            and self._session_ready
            and not self._requires_reconciliation
            and self._turn_state == TurnState.IDLE
        )

    @property
    def can_stop(self) -> bool:
        return (
            self._client is not None
            and self._connection_state == ConnectionState.READY
            and self._turn_state in {TurnState.RUNNING, TurnState.CANCELLING}
        )

    def set_state_handler(self, handler: StateHandler) -> None:
        self._state_handler = handler

    def set_profiles_handler(self, handler: ProfilesHandler) -> None:
        self._profiles_handler = handler

    def set_messages_reset_handler(self, handler: MessagesResetHandler) -> None:
        self._messages_reset_handler = handler

    def set_message_added_handler(self, handler: MessageHandler) -> None:
        self._message_added_handler = handler

    def set_message_changed_handler(self, handler: MessageHandler) -> None:
        self._message_changed_handler = handler

    def set_recovered_queue_handler(self, handler: RecoveredQueueHandler) -> None:
        self._recovered_queue_handler = handler

    def set_workspace(self, path: Path) -> None:
        if self._client is not None:
            raise AgentControllerError("disconnect Pi before changing workspace")
        resolved = path.expanduser().resolve()
        if not resolved.is_dir():
            raise AgentControllerError(f"workspace does not exist: {resolved}")

        same_workspace = self._workspace == resolved
        updated = replace(
            self._settings,
            workspace_root=str(resolved),
            last_session_id=(
                self._settings.last_session_id if same_workspace else None
            ),
        )
        self._settings_store.save(updated)
        self._settings = updated
        self._workspace = resolved
        self._last_error = None
        self._connection_state = ConnectionState.DISCONNECTED
        self._refresh_profiles()
        self._state_handler()

    def refresh_profiles(self) -> None:
        if self._client is not None:
            raise AgentControllerError("disconnect Pi before rescanning model configuration")
        if self._workspace is None:
            self._profiles = ()
            self._selected_profile_index = -1
            self._existing_config = None
            self._status_text = "Choose an AIOS workspace"
            self._profiles_handler(self._profiles, self._selected_profile_index)
            self._state_handler()
            return
        self._refresh_profiles()
        self._state_handler()

    def select_profile(self, index: int) -> None:
        if self._client is not None:
            raise AgentControllerError("disconnect Pi before switching model profile")
        if not 0 <= index < len(self._profiles):
            raise AgentControllerError("model profile index is out of range")
        if index == self._selected_profile_index:
            return
        self._selected_profile_index = index
        self._status_text = f"Selected {self._profiles[index].label}"
        self._profiles_handler(self._profiles, index)
        self._state_handler()

    def connect_agent(self) -> None:
        if not self.can_connect:
            raise AgentControllerError("Pi cannot be connected in the current state")
        assert self._workspace is not None
        profile = self.selected_profile
        assert profile is not None

        self._last_error = None
        self._inactivity_warning = False
        self._requires_reconciliation = False
        self._diagnostic_tail = ""
        self._disconnect_requested = False
        self._session_ready = False
        self._requested_session_id = self._settings.last_session_id
        self._connection_state = ConnectionState.STARTING
        self._status_text = f"Starting {profile.label}"
        self._state_handler()

        try:
            session_id = self._requested_session_id
            if profile.source == RuntimeProfileSource.EXISTING:
                existing = self._existing_config
                if existing is None or existing.sha256 is None or profile.discovered is None:
                    raise AgentControllerError("existing Pi model configuration is unavailable")
                prepared = self._bootstrap.prepare_existing(
                    self._settings.agent,
                    workspace=self._workspace,
                    profile=profile.discovered,
                    expected_sha256=existing.sha256,
                    session_id=session_id,
                )
            else:
                prepared = self._bootstrap.prepare(
                    self._settings.agent,
                    workspace=self._workspace,
                    session_id=session_id,
                )

            agent_settings = self._settings.agent
            transport = self._transport_factory(
                prepared.launch_spec,
                agent_settings.startup_timeout_ms,
                agent_settings.shutdown_timeout_ms,
            )
            transport.set_diagnostic_handler(self._on_diagnostic)
            scheduler = (
                self._deadline_scheduler_factory()
                if self._deadline_scheduler_factory is not None
                else None
            )
            client = AgentClient(
                transport,
                deadline_scheduler=scheduler,
                request_timeout_ms=(
                    agent_settings.request_timeout_ms if scheduler is not None else None
                ),
                inactivity_timeout_ms=(
                    agent_settings.inactivity_timeout_ms if scheduler is not None else None
                ),
            )
            client.set_event_handler(self._on_event)
            client.set_response_handler(self._on_response)
            client.set_queue_cleared_handler(self._on_queue_cleared)
            client.set_turn_state_handler(self._on_turn_state)
            client.set_transport_state_handler(self._on_transport_state)
            client.set_error_handler(self._on_client_error)
            client.set_request_timeout_handler(self._on_request_timeout)
            client.set_inactivity_timeout_handler(self._on_inactivity_timeout)
            self._transport = transport
            self._client = client
            client.start()
        except BaseException as exc:
            self._transport = None
            self._client = None
            self._requested_session_id = None
            self._fail(exc)
            raise

    def disconnect_agent(self) -> None:
        if self._client is None:
            return
        self._disconnect_requested = True
        self._connection_state = ConnectionState.STOPPING
        self._status_text = "Stopping Pi"
        self._state_handler()
        self._client.shutdown()

    def shutdown(self) -> None:
        self.disconnect_agent()

    def send_message(self, text: str) -> None:
        if not isinstance(text, str) or not text.strip():
            raise AgentControllerError("message must not be empty")
        if not self.can_send or self._client is None:
            raise AgentControllerError("Pi is not ready for a new message")

        index = self._append_message("user", text, MessageState.SENDING)
        try:
            request_id = self._client.prompt(text)
        except BaseException as exc:
            self._replace_message(index, state=MessageState.FAILED)
            self._fail(exc)
            raise
        self._prompt_requests[request_id] = index
        self._status_text = "Sending prompt"
        self._state_handler()

    def request_stop(self) -> None:
        if not self.can_stop or self._client is None:
            raise AgentControllerError("there is no active turn to stop")
        self._status_text = "Stopping current turn"
        self._state_handler()
        self._client.request_stop()

    def _refresh_profiles(self) -> None:
        assert self._workspace is not None
        previous_key = self.selected_profile.key if self.selected_profile else None
        paths = PiRuntimePaths.for_workspace(self._workspace)
        existing = self._discovery.inspect(paths)
        self._existing_config = existing

        choices: list[AgentProfile] = []
        for discovered in existing.profiles:
            choices.append(
                AgentProfile(
                    key=_profile_key(
                        RuntimeProfileSource.EXISTING,
                        discovered.provider,
                        discovered.model,
                        discovered.base_url,
                    ),
                    provider=discovered.provider,
                    model=discovered.model,
                    base_url=discovered.base_url,
                    api=discovered.api,
                    source=RuntimeProfileSource.EXISTING,
                    discovered=discovered,
                )
            )

        configured = self._settings.agent
        if configured.provider and configured.model and configured.base_url:
            configured_key = _profile_key(
                RuntimeProfileSource.SETTINGS,
                configured.provider,
                configured.model,
                configured.base_url,
            )
            if not any(
                item.provider == configured.provider
                and item.model == configured.model
                and item.base_url == configured.base_url
                and item.api == configured.api
                for item in choices
            ):
                choices.append(
                    AgentProfile(
                        key=configured_key,
                        provider=configured.provider,
                        model=configured.model,
                        base_url=configured.base_url,
                        api=configured.api,
                        source=RuntimeProfileSource.SETTINGS,
                    )
                )

        self._profiles = tuple(choices)
        self._selected_profile_index = _restore_selection(self._profiles, previous_key)
        if self._profiles:
            selected = self.selected_profile
            assert selected is not None
            source = (
                "existing Pi config"
                if selected.source == RuntimeProfileSource.EXISTING
                else "Pi_UI settings"
            )
            self._status_text = f"Ready to connect · {source}"
        elif existing.sha256 is not None:
            self._status_text = "models.json found, but no usable model profiles were discovered"
        else:
            self._status_text = "No Pi model profile found in this workspace"
        self._profiles_handler(self._profiles, self._selected_profile_index)

    def _on_transport_state(self, state: TransportState) -> None:
        if state == TransportState.STARTING:
            self._connection_state = ConnectionState.STARTING
            self._status_text = "Starting Pi sandbox"
        elif state == TransportState.READY:
            self._connection_state = ConnectionState.LOADING_SESSION
            self._status_text = "Resolving Pi session"
            self._session_ready = False
            client = self._client
            if client is not None:
                try:
                    client.get_state(self._on_session_state_response)
                except BaseException as exc:
                    self._fail_and_stop(exc)
        elif state == TransportState.STOPPING:
            self._connection_state = ConnectionState.STOPPING
            self._status_text = "Stopping Pi"
        elif state == TransportState.FAILED:
            self._connection_state = ConnectionState.FAILED
            self._session_ready = False
            if self._last_error is None:
                self._status_text = "Pi process failed"
        elif state == TransportState.STOPPED:
            self._session_ready = False
            self._requested_session_id = None
            self._active_assistant_index = None
            self._prompt_requests.clear()
            self._transport = None
            self._client = None
            self._requires_reconciliation = False
            self._inactivity_warning = False
            if self._disconnect_requested or self._last_error is None:
                self._connection_state = ConnectionState.DISCONNECTED
                self._status_text = "Disconnected"
            else:
                self._connection_state = ConnectionState.FAILED
            self._disconnect_requested = False
        self._state_handler()

    def _on_turn_state(self, state: TurnState) -> None:
        self._turn_state = state
        self._clear_inactivity_warning()
        if self._connection_state == ConnectionState.READY:
            if self._requires_reconciliation:
                if state == TurnState.RUNNING:
                    self._status_text = "Prompt outcome uncertain · Pi is still working"
                elif state == TurnState.CANCELLING:
                    self._status_text = "Outcome uncertain · stopping current turn"
                elif state == TurnState.IDLE:
                    self._status_text = "Prompt outcome uncertain · reconnect to reconcile"
            elif state == TurnState.RUNNING:
                self._status_text = "Ornith is working"
            elif state == TurnState.CANCELLING:
                self._status_text = "Stopping current turn"
            elif state == TurnState.IDLE and self._session_ready:
                self._status_text = "Ready"
        self._state_handler()

    def _on_session_state_response(self, response: dict[str, Any]) -> None:
        if response.get("success") is not True:
            self._fail_and_stop(AgentControllerError("Pi rejected get_state"))
            return
        data = response.get("data")
        session_id = data.get("sessionId") if isinstance(data, dict) else None
        if not is_valid_session_id(session_id):
            self._fail_and_stop(
                AgentControllerError("Pi returned an invalid active session id")
            )
            return

        expected = self._requested_session_id
        if expected is not None and session_id != expected:
            self._fail_and_stop(
                AgentControllerError(
                    "Pi opened a different session than Pi_UI requested; "
                    "history was not replaced"
                )
            )
            return

        if self._settings.last_session_id != session_id:
            try:
                updated = replace(self._settings, last_session_id=session_id)
                self._settings_store.save(updated)
                self._settings = updated
            except BaseException as exc:
                self._fail_and_stop(exc)
                return

        client = self._client
        if client is None:
            return
        self._status_text = "Loading Pi session"
        self._state_handler()
        try:
            client.get_messages(self._on_history_response)
        except BaseException as exc:
            self._fail_and_stop(exc)

    def _on_history_response(self, response: dict[str, Any]) -> None:
        if response.get("success") is not True:
            self._fail_and_stop(AgentControllerError("Pi rejected get_messages"))
            return
        data = response.get("data")
        raw_messages = data.get("messages") if isinstance(data, dict) else None
        if not isinstance(raw_messages, list):
            self._fail_and_stop(
                AgentControllerError("Pi returned an invalid message history")
            )
            return

        loaded: list[ConversationMessage] = []
        for raw in raw_messages:
            if not isinstance(raw, dict):
                continue
            role = raw.get("role")
            if role not in {"user", "assistant"}:
                continue
            text = _message_text(raw)
            if not text:
                continue
            loaded.append(
                ConversationMessage(
                    message_id=self._next_message_id(),
                    role=role,
                    text=text,
                    state=MessageState.COMPLETE,
                )
            )
        self._messages = loaded
        self._messages_reset_handler(tuple(self._messages))
        self._session_ready = True
        self._requires_reconciliation = False
        self._connection_state = ConnectionState.READY
        self._status_text = "Ready"
        self._state_handler()

    def _on_response(self, response: dict[str, Any]) -> None:
        self._clear_inactivity_warning()
        if response.get("command") != "prompt":
            return
        request_id = response.get("id")
        if not isinstance(request_id, str):
            return
        index = self._prompt_requests.pop(request_id, None)
        if index is None or not 0 <= index < len(self._messages):
            return
        if response.get("success") is True:
            self._replace_message(index, state=MessageState.ACCEPTED)
            self._status_text = "Prompt accepted"
        else:
            self._replace_message(index, state=MessageState.FAILED)
            self._last_error = _response_error(response) or "Pi rejected the prompt"
            self._status_text = self._last_error
        self._state_handler()

    def _on_event(self, event: dict[str, Any]) -> None:
        self._clear_inactivity_warning()
        event_type = event.get("type")
        if event_type == "message_update":
            assistant_event = event.get("assistantMessageEvent")
            if isinstance(assistant_event, dict) and assistant_event.get("type") == "text_delta":
                delta = assistant_event.get("delta")
                if isinstance(delta, str) and delta:
                    self._append_assistant_delta(delta)
        elif event_type == "message_end":
            message = event.get("message")
            if isinstance(message, dict) and message.get("role") == "assistant":
                self._finalize_assistant(message)
        elif event_type == "tool_execution_start":
            tool_name = event.get("toolName")
            if isinstance(tool_name, str):
                self._status_text = f"Running tool · {tool_name}"
                self._state_handler()
        elif event_type == "tool_execution_end":
            if self._turn_state == TurnState.RUNNING:
                self._status_text = "Ornith is working"
                self._state_handler()
        elif event_type == "auto_retry_start":
            attempt = event.get("attempt")
            self._status_text = f"Retrying model request · attempt {attempt}"
            self._state_handler()
        elif event_type == "compaction_start":
            self._status_text = "Compacting conversation context"
            self._state_handler()
        elif event_type == "extension_error":
            error = event.get("error")
            self._last_error = (
                f"Extension error: {error}"
                if isinstance(error, str)
                else "Extension error"
            )
            self._status_text = self._last_error
            self._state_handler()
        elif event_type == "agent_settled":
            if self._active_assistant_index is not None:
                self._replace_message(
                    self._active_assistant_index,
                    state=MessageState.COMPLETE,
                )
                self._active_assistant_index = None

    def _append_assistant_delta(self, delta: str) -> None:
        index = self._active_assistant_index
        if index is None:
            index = self._append_message("assistant", "", MessageState.STREAMING)
            self._active_assistant_index = index
        current = self._messages[index]
        self._replace_message(
            index,
            text=current.text + delta,
            state=MessageState.STREAMING,
        )

    def _finalize_assistant(self, raw_message: dict[str, Any]) -> None:
        text = _message_text(raw_message)
        index = self._active_assistant_index
        if index is None:
            if text:
                self._append_message("assistant", text, MessageState.COMPLETE)
            return
        self._replace_message(index, text=text, state=MessageState.COMPLETE)
        self._active_assistant_index = None

    def _on_queue_cleared(
        self,
        steering: tuple[str, ...],
        follow_up: tuple[str, ...],
    ) -> None:
        if steering or follow_up:
            self._recovered_queue_handler(steering, follow_up)

    def _on_diagnostic(self, text: str) -> None:
        if not text:
            return
        combined = (self._diagnostic_tail + text)[-4000:]
        self._diagnostic_tail = combined
        self._state_handler()

    def _on_request_timeout(self, error: AgentRequestTimeoutError) -> None:
        if error.command == "prompt":
            index = self._prompt_requests.pop(error.request_id, None)
            if index is not None and 0 <= index < len(self._messages):
                self._replace_message(index, state=MessageState.UNCERTAIN)
            self._requires_reconciliation = True
            self._inactivity_warning = False
            self._last_error = (
                "Prompt acknowledgement timed out; outcome is unknown. "
                "Pi_UI did not resend it. Reconnect to reconcile the session."
            )
            self._status_text = self._last_error
            self._state_handler()
            return

        if error.command in {"clear_queue", "abort", "steer", "follow_up"}:
            self._requires_reconciliation = True
            self._inactivity_warning = False
            self._last_error = (
                f"{error.command} acknowledgement timed out; outcome is unknown. "
                "Pi_UI did not retry it. Reconnect before sending more work."
            )
            self._status_text = self._last_error
            self._state_handler()
            return

        self._fail(error)

    def _on_inactivity_timeout(self, error: AgentInactivityTimeoutError) -> None:
        self._inactivity_warning = True
        self._last_error = str(error)
        self._status_text = (
            f"No Pi RPC activity for {error.timeout_ms} ms. "
            "The turn was not killed or retried; Stop remains available."
        )
        self._state_handler()

    def _clear_inactivity_warning(self) -> None:
        if not self._inactivity_warning:
            return
        self._inactivity_warning = False
        self._last_error = None

    def _on_client_error(self, error: BaseException) -> None:
        self._fail(error)

    def _fail(self, error: BaseException) -> None:
        self._inactivity_warning = False
        self._last_error = str(error) or error.__class__.__name__
        self._connection_state = ConnectionState.FAILED
        self._session_ready = False
        self._status_text = self._last_error
        self._state_handler()

    def _fail_and_stop(self, error: BaseException) -> None:
        self._fail(error)
        client = self._client
        if client is not None:
            self._disconnect_requested = False
            client.shutdown()

    def _append_message(self, role: str, text: str, state: MessageState) -> int:
        message = ConversationMessage(
            message_id=self._next_message_id(),
            role=role,
            text=text,
            state=state,
        )
        index = len(self._messages)
        self._messages.append(message)
        self._message_added_handler(index, message)
        return index

    def _replace_message(
        self,
        index: int,
        *,
        text: str | None = None,
        state: MessageState | None = None,
    ) -> None:
        current = self._messages[index]
        updated = replace(
            current,
            text=current.text if text is None else text,
            state=current.state if state is None else state,
        )
        self._messages[index] = updated
        self._message_changed_handler(index, updated)

    def _next_message_id(self) -> str:
        self._message_counter += 1
        return f"message-{self._message_counter}"


def _profile_key(
    source: RuntimeProfileSource,
    provider: str,
    model: str,
    base_url: str | None,
) -> str:
    return f"{source}:{provider}:{model}:{base_url or ''}"


def _restore_selection(profiles: tuple[AgentProfile, ...], previous_key: str | None) -> int:
    if not profiles:
        return -1
    if previous_key is not None:
        for index, profile in enumerate(profiles):
            if profile.key == previous_key:
                return index
    return 0


def _message_text(message: dict[str, Any]) -> str:
    content = message.get("content")
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for item in content:
        if not isinstance(item, dict) or item.get("type") != "text":
            continue
        text = item.get("text")
        if isinstance(text, str):
            parts.append(text)
    return "".join(parts)


def _response_error(response: dict[str, Any]) -> str | None:
    error = response.get("error")
    if isinstance(error, str) and error:
        return error
    if isinstance(error, dict):
        message = error.get("message")
        if isinstance(message, str) and message:
            return message
    return None
