"""Persistent state handling for VPS monitoring."""

import json
import tempfile
from dataclasses import dataclass
from pathlib import Path

from services.vps_monitor import MonitorFailure, MonitorResult, MonitorState

DEFAULT_STATE_FILE = Path("data/vps_monitor_state.json")
DOWN_CONFIRMATIONS = 3
UP_CONFIRMATIONS = 2


class MonitorStateMap(dict[str, MonitorState]):
    """Monitor states with persistent consecutive-check counters."""

    def __init__(self, *args, checks=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.checks = checks if isinstance(checks, dict) else {}


@dataclass(frozen=True)
class StateUpdate:
    name: str
    previous: MonitorState | None
    current: MonitorState
    notify: bool
    failure: MonitorFailure | None = None
    details: str = ""


def load_states(path: Path = DEFAULT_STATE_FILE) -> MonitorStateMap:
    """Load states and counters; accept the legacy flat JSON format."""
    if not path.exists():
        return MonitorStateMap()

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return MonitorStateMap()

    if not isinstance(data, dict):
        return MonitorStateMap()

    if isinstance(data.get("states"), dict):
        raw_states = data["states"]
        raw_checks = data.get("checks", {})
    else:
        raw_states = data
        raw_checks = {}

    states = MonitorStateMap(checks=raw_checks)
    for name, value in raw_states.items():
        try:
            states[name] = MonitorState(value)
        except (TypeError, ValueError):
            continue

    return states


def save_states(
    states: dict[str, MonitorState],
    path: Path = DEFAULT_STATE_FILE,
) -> None:
    """Persist states and debounce counters atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 2,
        "states": {name: state.value for name, state in sorted(states.items())},
        "checks": getattr(states, "checks", {}),
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
    """Apply a result with persistent consecutive-check confirmation."""
    previous = states.get(result.name)
    target = MonitorState.UP if result.healthy else MonitorState.DOWN

    # Plain dict compatibility: first observation establishes a silent baseline.
    if not isinstance(states, MonitorStateMap):
        if previous is None:
            states[result.name] = target
            return StateUpdate(
                result.name,
                None,
                target,
                False,
                result.failure,
                result.details,
            )
        notify = previous != target
        states[result.name] = target
        return StateUpdate(
            result.name, previous, target, notify, result.failure, result.details
        )

    baseline = previous or MonitorState.UP
    counters = states.checks.setdefault(result.name, {"up": 0, "down": 0})

    if result.healthy:
        counters["up"] = int(counters.get("up", 0)) + 1
        counters["down"] = 0
        required = UP_CONFIRMATIONS if baseline == MonitorState.DOWN else 1
        count = counters["up"]
    else:
        counters["down"] = int(counters.get("down", 0)) + 1
        counters["up"] = 0
        required = DOWN_CONFIRMATIONS if baseline != MonitorState.DOWN else 1
        count = counters["down"]

    confirmed = count >= required
    current = target if confirmed else baseline

    if confirmed:
        states[result.name] = target

    notify = confirmed and (
        (previous is None and target == MonitorState.DOWN)
        or (previous is not None and previous != target)
    )
    return StateUpdate(
        result.name, previous, current, notify, result.failure, result.details
    )


def prepare_results(
    results: list[MonitorResult],
    path: Path = DEFAULT_STATE_FILE,
) -> tuple[list[StateUpdate], dict[str, MonitorState]]:
    """Process results without persisting state."""
    states = load_states(path)
    skipped = {result.name for result in results if result.skipped}

    for name in skipped:
        states.pop(name, None)
        if isinstance(states, MonitorStateMap):
            states.checks.pop(name, None)

    updates = [update_state(result, states) for result in results if not result.skipped]
    return updates, states


def process_results(
    results: list[MonitorResult],
    path: Path = DEFAULT_STATE_FILE,
) -> list[StateUpdate]:
    """Process all monitor results and persist their states."""
    updates, states = prepare_results(results, path)
    save_states(states, path)
    return updates
