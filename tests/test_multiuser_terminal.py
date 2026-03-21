from scripts.multiuser_terminal import (
    SessionState,
    _apply_result_to_session,
    _meter,
    _parse_optional_int,
    _resolve_sender_token,
    _short_json,
)


def test_short_json_truncates_long_values():
    value = {"message": "x" * 300}
    out = _short_json(value, max_len=40)
    assert len(out) == 40
    assert out.endswith("...")


def test_apply_result_to_session_updates_token_and_revision():
    session = SessionState()
    result = {"auth_token": "TOKEN_ABC", "wallet_id": "wallet_user_alpha_01"}

    _apply_result_to_session(
        session,
        action="create-wallet",
        result=result,
        revision_id="rev-123",
        is_error=False,
    )

    assert session.last_action == "create-wallet"
    assert session.last_status == "OK"
    assert session.last_revision_id == "rev-123"
    assert session.last_token == "TOKEN_ABC"


def test_apply_result_to_session_error_path():
    session = SessionState(last_token="TOKEN_OLD")

    _apply_result_to_session(
        session,
        action="transfer",
        result="Error: token expirado",
        revision_id=None,
        is_error=True,
    )

    assert session.last_action == "transfer"
    assert session.last_status == "ERROR"
    assert session.last_revision_id == "-"
    assert session.last_token == "TOKEN_OLD"
    assert "token expirado" in session.last_message


def test_parse_optional_int_accepts_empty_and_valid_int():
    value, error = _parse_optional_int("", "expected_nonce")
    assert value is None
    assert error is None

    value, error = _parse_optional_int("7", "expected_nonce")
    assert value == 7
    assert error is None


def test_parse_optional_int_rejects_invalid_value():
    value, error = _parse_optional_int("abc", "expected_nonce")
    assert value is None
    assert error == "Error: expected_nonce debe ser entero"


def test_resolve_sender_token_prefers_input_then_session():
    session = SessionState(last_token="TOKEN_LAST")

    assert _resolve_sender_token(session, "TOKEN_INPUT") == "TOKEN_INPUT"
    assert _resolve_sender_token(session, "") == "TOKEN_LAST"
    assert _resolve_sender_token(SessionState(), "") == ""


def test_meter_render_has_expected_width():
    bar = _meter(50.0, width=10)
    assert len(bar) == 10
    assert bar.count("#") == 5
    assert bar.count("-") == 5


def test_apply_result_tracks_command_metrics_and_exec_time():
    session = SessionState()

    _apply_result_to_session(
        session,
        action="transfer",
        result={"status": "ok"},
        revision_id="rev-1",
        is_error=False,
        elapsed_ms=25.0,
    )
    _apply_result_to_session(
        session,
        action="transfer",
        result="Error: failed",
        revision_id=None,
        is_error=True,
        elapsed_ms=15.0,
    )

    assert session.total_commands == 2
    assert session.successful_commands == 1
    assert session.failed_commands == 1
    assert session.total_exec_ms == 40.0
    assert session.last_exec_ms == 15.0
    assert session.command_metrics["transfer"]["count"] == 2
    assert session.command_metrics["transfer"]["ok"] == 1
