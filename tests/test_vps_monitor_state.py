from pathlib import Path

from services.vps_monitor import (
    MonitorCategory,
    MonitorResult,
    MonitorState,
)
from services.vps_monitor_state import (
    load_states,
    process_results,
    save_states,
    update_state,
)


def result(name: str, healthy: bool) -> MonitorResult:
    return MonitorResult(
        name=name,
        category=MonitorCategory.CRITICAL,
        healthy=healthy,
    )


def test_missing_state_file_returns_empty(tmp_path: Path):
    assert load_states(tmp_path / "state.json") == {}


def test_save_and_load_states(tmp_path: Path):
    path = tmp_path / "state.json"

    states = {
        "zvertbot": MonitorState.UP,
        "stats-http": MonitorState.DOWN,
    }

    save_states(states, path)

    assert load_states(path) == states


def test_invalid_json_returns_empty(tmp_path: Path):
    path = tmp_path / "state.json"
    path.write_text("{broken", encoding="utf-8")

    assert load_states(path) == {}


def test_invalid_state_values_are_ignored(tmp_path: Path):
    path = tmp_path / "state.json"
    path.write_text(
        '{"zvertbot":"up","broken":"something"}',
        encoding="utf-8",
    )

    assert load_states(path) == {
        "zvertbot": MonitorState.UP,
    }


def test_first_up_observation_is_silent():
    states = {}

    update = update_state(result("zvertbot", True), states)

    assert update.previous is None
    assert update.current == MonitorState.UP
    assert update.notify is False
    assert states["zvertbot"] == MonitorState.UP


def test_first_down_observation_is_silent():
    states = {}

    update = update_state(result("zvertbot", False), states)

    assert update.previous is None
    assert update.current == MonitorState.DOWN
    assert update.notify is False


def test_up_to_down_notifies():
    states = {"zvertbot": MonitorState.UP}

    update = update_state(result("zvertbot", False), states)

    assert update.previous == MonitorState.UP
    assert update.current == MonitorState.DOWN
    assert update.notify is True


def test_down_to_down_is_silent():
    states = {"zvertbot": MonitorState.DOWN}

    update = update_state(result("zvertbot", False), states)

    assert update.previous == MonitorState.DOWN
    assert update.current == MonitorState.DOWN
    assert update.notify is False


def test_down_to_up_notifies():
    states = {"zvertbot": MonitorState.DOWN}

    update = update_state(result("zvertbot", True), states)

    assert update.previous == MonitorState.DOWN
    assert update.current == MonitorState.UP
    assert update.notify is True


def test_up_to_up_is_silent():
    states = {"zvertbot": MonitorState.UP}

    update = update_state(result("zvertbot", True), states)

    assert update.previous == MonitorState.UP
    assert update.current == MonitorState.UP
    assert update.notify is False


def test_process_results_persists_all_states(tmp_path: Path):
    path = tmp_path / "state.json"

    updates = process_results(
        [
            result("zvertbot", True),
            result("stats-http", False),
        ],
        path,
    )

    assert [update.notify for update in updates] == [False, False]
    assert load_states(path) == {
        "zvertbot": MonitorState.UP,
        "stats-http": MonitorState.DOWN,
    }


def test_process_results_detects_transitions(tmp_path: Path):
    path = tmp_path / "state.json"

    process_results(
        [
            result("zvertbot", True),
            result("stats-http", True),
        ],
        path,
    )

    updates = process_results(
        [
            result("zvertbot", False),
            result("stats-http", True),
        ],
        path,
    )

    assert updates[0].notify is True
    assert updates[0].previous == MonitorState.UP
    assert updates[0].current == MonitorState.DOWN

    assert updates[1].notify is False


def test_state_survives_monitor_restart(tmp_path: Path):
    path = tmp_path / "state.json"

    process_results([result("zvertbot", False)], path)

    # New process/state dictionary.
    updates = process_results([result("zvertbot", False)], path)

    assert updates[0].previous == MonitorState.DOWN
    assert updates[0].notify is False


def test_recovery_after_persisted_down_state(tmp_path: Path):
    path = tmp_path / "state.json"

    process_results([result("zvertbot", False)], path)
    updates = process_results([result("zvertbot", True)], path)

    assert updates[0].previous == MonitorState.DOWN
    assert updates[0].current == MonitorState.UP
    assert updates[0].notify is True
