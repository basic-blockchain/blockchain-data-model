from scripts.multiuser_terminal import (
    SessionState,
    _apply_result_to_session,
    _is_domain_error_result,
    _meter,
    _measure_units,
    _parse_optional_int,
    _sender_token_prompt,
    _print_pending_feedback,
    _resolve_sender_token,
    _short_json,
    _validate_numeric,
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


def test_validate_numeric_rejects_text_and_accepts_numbers():
    assert _validate_numeric("12.50", "amount") is None
    assert _validate_numeric("0", "fee") is None
    assert _validate_numeric("abc", "amount") == "Error: amount solo acepta numeros"
    assert _validate_numeric("", "amount") == "Error: amount es requerido y solo acepta numeros"


def test_resolve_sender_token_prefers_input_then_session():
    session = SessionState(last_token="TOKEN_LAST")

    assert _resolve_sender_token(session, "TOKEN_INPUT") == "TOKEN_INPUT"
    assert _resolve_sender_token(session, "") == ""
    assert _resolve_sender_token(SessionState(), "") == ""


def test_meter_render_has_expected_width():
    bar = _meter(50.0, width=10)
    assert len(bar) == 10
    assert bar.count("█") == 5
    assert bar.count("░") == 5


def test_is_domain_error_result_handles_wallet_invalida_and_error_prefix():
    assert _is_domain_error_result("Error: sender_token es requerido") is True
    assert _is_domain_error_result("Wallet invalida. Usa 20-30 caracteres") is True
    assert _is_domain_error_result({"ok": True}) is False


def test_sender_token_prompt_mentions_session_when_token_available():
    assert _sender_token_prompt() == "sender_token"


def test_apply_result_stores_pending_feedback():
    session = SessionState()
    _apply_result_to_session(
        session,
        action="create-user",
        result="Usuario creado",
        revision_id="rev-1",
        is_error=False,
    )
    assert session.pending_feedback_kind == "SUCCESS"
    assert session.pending_feedback_action == "create-user"
    assert session.pending_feedback_message == "Usuario creado"


def test_print_pending_feedback_clears_buffer(capsys):
    session = SessionState(
        pending_feedback_kind="SUCCESS",
        pending_feedback_action="test-action",
        pending_feedback_message="test",
    )
    _print_pending_feedback(session)
    captured = capsys.readouterr()
    assert "[SUCCESS] test-action" in captured.out
    assert "test" in captured.out
    assert session.pending_feedback_action == ""


def test_apply_result_tracks_command_metrics_and_exec_time():
    session = SessionState()

    first_result = {"status": "ok"}
    second_result = "Error: failed"

    _apply_result_to_session(
        session,
        action="transfer",
        result=first_result,
        revision_id="rev-1",
        is_error=False,
        elapsed_ms=25.0,
        input_units=50,
    )
    _apply_result_to_session(
        session,
        action="transfer",
        result=second_result,
        revision_id=None,
        is_error=True,
        elapsed_ms=15.0,
        input_units=30,
    )

    assert session.total_commands == 2
    assert session.successful_commands == 1
    assert session.failed_commands == 1
    assert session.total_exec_ms == 40.0
    assert session.last_exec_ms == 15.0
    expected_output_units = _measure_units(first_result) + _measure_units(second_result)
    assert session.total_input_units == 80
    assert session.total_output_units == expected_output_units
    assert session.total_saved_units == max(0, 50 - _measure_units(first_result)) + max(0, 30 - _measure_units(second_result))
    assert session.command_metrics["transfer"]["count"] == 2
    assert session.command_metrics["transfer"]["ok"] == 1
    assert session.command_metrics["transfer"]["input_units"] == 80


def test_transfer_feedback_is_uniform_in_header_and_body():
    session = SessionState()

    _apply_result_to_session(
        session,
        action="transfer",
        result="Error: sender_token es requerido para transferir.",
        revision_id=None,
        is_error=True,
    )
    assert session.pending_feedback_kind == "ERROR"
    assert session.pending_feedback_action == "transfer"
    assert "sender_token es requerido" in session.pending_feedback_message


def test_pending_feedback_message_omits_error_prefix():
    session = SessionState()
    _apply_result_to_session(
        session,
        action="transfer",
        result="Error: wallet emisor o receptor inexistente.",
        revision_id=None,
        is_error=True,
    )
    assert session.pending_feedback_message == "wallet emisor o receptor inexistente."
