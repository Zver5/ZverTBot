"""Persistent state handling for VPS monitoring."""

import json
import tempfile
from dataclasses import dataclass
from pathlib import Path

from services.vps_monitor import MonitorFailure, MonitorResult, MonitorState

DEFAULT_STATE_FILE = Path("data/vps_monitor_state.json")


@dataclass(frozen=True)
class StateUpdate:
    name: str
    previous: MonitorState | None
    current: MonitorState
    notify: bool
    failure: MonitorFailure | None = None
    details: str = ""


def load_states(path: Path = DEFAULT_STATE_FILE) -> dict[str, MonitorState]:
    """Load persisted monitor states."""
    if not path.exists():
        return {}

    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}

    if not isinstance(data, dict):
        return {}

    states: dict[str, MonitorState] = {}

    for name, value in data.items():
        try:
            states[name] = MonitorState(value)
        except (TypeError, ValueError):
            continue

    return states


def save_states(
    states: dict[str, MonitorState],
    path: Path = DEFAULT_STATE_FILE,
) -> None:
    """Persist monitor states atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        name: state.value
        for name, state in sorted(states.items())
    }

    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as tmp:
        tmp_path = Path(tmp.name)
        json.dump(payload, tmp, ensure_ascii=False, indent=2)
        tmp.write("\n")

    tmp_path.replace(path)


def update_state(
    result: MonitorResult,
    states: dict[str, MonitorState],
) -> StateUpdate:
    """Apply one monitor result and determine whether to notify."""
    current = (
        MonitorState.UP
        if result.healthy
        else MonitorState.DOWN
    )

    previous = states.get(result.name)

    # First observation establishes the baseline silently.
    if previous is None:
        notify = False
    else:
        notify = previous != current

    states[result.name] = current

    return StateUpdate(
        name=result.name,
        previous=previous,
        current=current,
        notify=notify,
        failure=result.failure,
        details=result.details,
    )


def prepare_results(
    results: list[MonitorResult],
    path: Path = DEFAULT_STATE_FILE,
) -> tuple[list[StateUpdate], dict[str, MonitorState]]:
    """Process results without persisting state."""
    states = load_states(path)

    updates = [
        update_state(result, states)
        for result in results
    ]

    return updates, states


def process_results(
    results: list[MonitorResult],
    path: Path = DEFAULT_STATE_FILE,
) -> list[StateUpdate]:
    """Process all monitor results and persist their states."""
    updates, states = prepare_results(results, path)
    save_states(states, path)
    return updates
