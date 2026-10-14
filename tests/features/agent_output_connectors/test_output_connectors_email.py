"""FILE: tests/features/agent_output_connectors/test_output_connectors_email.py

PURPOSE: Prove EmailOutput sends one plain-text message over verified TLS, off the event loop, with the documented connection sequence, never retries, never falls back to plaintext, and maps every SMTP failure to the INV-11 codes; that the receipt is fixed once the server accepted the message, whatever QUIT answers; that sync run() returns at the delivery deadline even while an SMTP session stalls; and that a username with no "@" needs an explicit sender.
ROLE IN CODEBASE: Contract tests of vidbyte/lib/outputs/email.py EmailOutput and vidbyte/lib/outputs/delivery.py OutputSmtp, through the smtplib module that delivery.py imports, plus BaseAgent.run with the dispatcher's deadline shortened.
ARCHITECTURE NOTE: fake_smtp replaces smtplib.SMTP and smtplib.SMTP_SSL on the module object delivery.py imports, with classes that keep the real constructor signatures, __exit__, and quit, and record each step; the worker thread runs for real, so the recorded thread proves the session left the event loop.
FUNCTION INVENTORY: test_default_port_* (AC-16 a, INV-18, INV-19); test_port_465_* (AC-16 b); test_smtp_failure_maps_to_* (AC-16 c-f, EC-24 to EC-26); test_partial_refusal_* (AC-16 d, EC-24); test_quit_reply_after_the_server_accepted_* (EC-48, S4 R-12); test_sync_run_returns_at_the_delivery_deadline_* (NFR-2, EC-47, INV-19, S4 R-3); test_username_without_an_at_sign_* (AC-16 apikey case); test_explicit_sender_*.
COMMON MODIFICATION PATTERNS: Add a failure as one SMTP_FAILURES row (step, exception, code); keep the one-connection assertion on every row.
WHAT NOT TO DO IN THIS FILE: 1. Do not open a socket; socket.create_connection refuses during these tests. 2. Do not use a real mailbox address or password. 3. Do not assert elapsed time; the stalled-session test proves the deadline by ordering against a threading.Event.
KNOWN EDGE CASES: SMTPRecipientsRefused is raised only when every recipient is refused; a partial refusal is the dict send_message returns. SMTPNotSupportedError on STARTTLS must stop before login, or the password would travel in cleartext. set_content adds a trailing newline to the text body. smtplib's own __exit__ raises SMTPResponseException when QUIT is not answered 221, after the mail was accepted. A run() that wrongly waits for the SMTP thread fails the stalled-session test only after SmtpScript.HOLD_SAFETY_SECONDS.
RELATED DOCS: tests/features/agent_output_connectors/FEATURE.md; docs/spec/agent-output-connectors/spec.md (§6.1 INV-18, INV-19; §6.2 AC-16; §9.2 EmailOutput row)
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/agent_output_connectors/test_output_connectors_email.py
"""

from __future__ import annotations

import smtplib
import socket
import ssl
import threading

import pytest

from tests.agent_test_support import build_test_agent
from tests.features.agent_output_connectors.factories import (
    SECRET_MARKER,
    SMTP_PASSWORD,
    AnswerRunner,
    build_reply,
    receipt_rows,
)
from vidbyte.lib.errors import ConfigurationError

TITLE = "Nightly scan"
BODY = "Nightly scan: no regressions.\n\nAll 412 checks passed."


def _gmail(output_api, **overrides):
    options = {"to": "ops@acme.com", "host": "smtp.gmail.com", "username": "bot@acme.com", "password": SMTP_PASSWORD, **overrides}
    return output_api.EmailOutput(**options)


async def _send(output_api, connector):
    return await connector.send(build_reply(BODY), output_api.OutputContent(TITLE, BODY))


def _assert_verified_context(context: object) -> None:
    # INV-18: a default context verifies the server certificate and its host name.
    assert isinstance(context, ssl.SSLContext)
    assert context.verify_mode is ssl.CERT_REQUIRED
    assert context.check_hostname is True


@pytest.mark.asyncio
async def test_default_port_uses_starttls_then_login_then_one_plain_text_message_off_the_event_loop(output_api, fake_smtp, monkeypatch) -> None:
    # AC-16 (a) / INV-18 / INV-19 / §9.3: the password comes from SMTP_PASSWORD; the session runs in a worker thread.
    monkeypatch.setenv("SMTP_PASSWORD", SMTP_PASSWORD)
    connector = output_api.EmailOutput(to="ops@acme.com", host="smtp.gmail.com", username="bot@acme.com")
    loop_thread = threading.get_ident()

    receipt = await _send(output_api, connector)

    assert receipt_rows([receipt]) == [("email", "sent", None, None)]
    [session] = fake_smtp.sessions
    assert (session.implicit_tls, session.host, session.port, session.timeout) == (False, "smtp.gmail.com", 587, 10.0)
    assert session.steps[:3] == ["starttls", "login", "send_message"]
    assert session.steps[-1] == "close"
    _assert_verified_context(session.starttls_context)
    assert session.login == ("bot@acme.com", SMTP_PASSWORD)
    assert session.thread_id != loop_thread
    message = session.message
    assert (message["From"], message["To"], message["Subject"]) == ("bot@acme.com", "ops@acme.com", TITLE)
    assert message.get_content_type() == "text/plain"
    assert message.get_content().rstrip("\n") == BODY


@pytest.mark.asyncio
async def test_port_465_uses_implicit_tls_with_a_verified_context_and_no_starttls(output_api, fake_smtp) -> None:
    # AC-16 (b) / INV-18: SMTP_SSL carries the context; STARTTLS is never attempted on an implicit-TLS connection.
    receipt = await _send(output_api, _gmail(output_api, port=465))

    assert receipt_rows([receipt]) == [("email", "sent", None, None)]
    [session] = fake_smtp.sessions
    assert (session.implicit_tls, session.host, session.port, session.timeout) == (True, "smtp.gmail.com", 465, 10.0)
    _assert_verified_context(session.context)
    assert "starttls" not in session.steps
    assert session.steps[:2] == ["login", "send_message"]


# (step that fails, exception it raises, expected error code, steps that must never run)
SMTP_FAILURES = [
    pytest.param("login", smtplib.SMTPAuthenticationError(535, b"5.7.8 Username and Password not accepted for S3CRETsmtp"), "smtp_535", ("send_message",), id="auth-535"),
    pytest.param("send_message", smtplib.SMTPDataError(554, b"5.7.1 Message rejected"), "smtp_554", (), id="data-554"),
    pytest.param("send_message", smtplib.SMTPSenderRefused(553, b"5.7.1 Sender address rejected", "bot@acme.com"), "smtp_553", (), id="sender-refused-553"),
    pytest.param("send_message", smtplib.SMTPRecipientsRefused({"ops@acme.com": (550, b"5.1.1 No such user")}), "smtp_recipients_refused", (), id="all-recipients-refused"),
    pytest.param("starttls", smtplib.SMTPNotSupportedError("STARTTLS extension not supported by server."), "smtp_error", ("login", "send_message"), id="no-starttls-never-plaintext"),
    pytest.param("login", smtplib.SMTPServerDisconnected("Connection unexpectedly closed"), "smtp_error", ("send_message",), id="server-disconnected"),
    pytest.param("starttls", ssl.SSLCertVerificationError(1, "certificate verify failed: hostname mismatch"), "network", ("login", "send_message"), id="certificate-rejected"),
    pytest.param("connect", TimeoutError("timed out"), "network", ("starttls", "login", "send_message"), id="connect-timeout"),
    pytest.param("connect", ConnectionRefusedError(111, "Connection refused"), "network", ("starttls", "login", "send_message"), id="connection-refused"),
    pytest.param("connect", socket.gaierror(-2, "Name or service not known"), "network", ("starttls", "login", "send_message"), id="unknown-host"),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(("step", "error", "error_code", "never"), SMTP_FAILURES)
async def test_smtp_failure_maps_to_its_code_after_one_connection_and_stops_at_that_step(output_api, fake_smtp, step, error, error_code, never) -> None:
    # AC-16 (c)-(f) / EC-24 to EC-26 / INV-10 / INV-11: no SMTP failure is retried, and no code repeats server text.
    fake_smtp.fail(step, error)

    receipt = await _send(output_api, _gmail(output_api))

    assert receipt_rows([receipt]) == [("email", "failed", None, error_code)]
    assert len(fake_smtp.sessions) == 1
    assert not set(never) & set(fake_smtp.sessions[0].steps)
    assert SECRET_MARKER not in repr(receipt)


@pytest.mark.asyncio
async def test_partial_refusal_returned_by_send_message_is_failed_recipients_refused(output_api, fake_smtp) -> None:
    # AC-16 (d) / EC-24: one recipient got the mail, but a retry would duplicate it, so the receipt is FAILED and not retried.
    fake_smtp.refused = {"ghost@acme.com": (550, b"5.1.1 No such user")}

    receipt = await _send(output_api, _gmail(output_api, to=("ops@acme.com", "ghost@acme.com")))

    assert receipt_rows([receipt]) == [("email", "failed", None, "smtp_recipients_refused")]
    [session] = fake_smtp.sessions
    assert session.message["To"] == "ops@acme.com, ghost@acme.com"


# (QUIT reply or exception, recipients send_message refused, expected status, expected error code)
QUIT_FAILURES = [
    pytest.param((250, b"2.0.0 OK"), {}, "sent", None, id="quit-answers-250"),
    pytest.param((421, b"4.4.2 closing transmission channel"), {}, "sent", None, id="quit-answers-421"),
    pytest.param(smtplib.SMTPServerDisconnected("Connection unexpectedly closed"), {}, "sent", None, id="connection-dropped-at-quit"),
    pytest.param((421, b"4.4.2 closing transmission channel"), {"ghost@acme.com": (550, b"5.1.1 No such user")}, "failed", "smtp_recipients_refused", id="partial-refusal-then-quit-421"),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(("quit_reply", "refused", "status", "error_code"), QUIT_FAILURES)
async def test_quit_reply_after_the_server_accepted_the_message_never_changes_the_receipt(output_api, fake_smtp, quit_reply, refused, status, error_code) -> None:
    # EC-48 / S4 R-12: the receipt is decided once send_message returns; a false FAILED smtp_421 invites a resend that mails twice.
    fake_smtp.quit_reply = quit_reply
    fake_smtp.refused = refused
    to = ("ops@acme.com", "ghost@acme.com") if refused else "ops@acme.com"

    receipt = await _send(output_api, _gmail(output_api, to=to))

    assert receipt_rows([receipt]) == [("email", status, None, error_code)]
    [session] = fake_smtp.sessions
    assert "send_message" in session.steps
    assert session.steps[-1] == "close"


def test_sync_run_returns_at_the_delivery_deadline_without_waiting_for_a_stalled_smtp_session(output_api, fake_smtp, dispatcher_module, monkeypatch) -> None:
    # NFR-2 / EC-47 / INV-19 / S4 R-3: on Python 3.11 asyncio.run joins the loop's default executor with no timeout, so a session there holds run().
    # Ordering, not timing: the server stalls until the test opens the gate, and the gate opens only after run() has returned.
    monkeypatch.setattr(dispatcher_module, "OUTPUT_DELIVERY_DEADLINE_SECONDS", 0.5)
    gate = fake_smtp.hold("send_message")
    agent = build_test_agent(name="nightly", system_prompt="Summarize the nightly scan.", runner=AnswerRunner("Nightly scan: no regressions."), outputs=[_gmail(output_api)])

    try:
        with pytest.raises(output_api.OutputDeliveryError) as info:
            agent.run("Run the nightly scan")
        # Only a run() that waited for the worker thread can see the stalled step already over (released by the safety backstop).
        session_was_over_before_run_returned = fake_smtp.released.is_set()
    finally:
        gate.set()
        if fake_smtp.sessions:
            # Let the worker finish the session it started, so no thread from this test outlives it.
            fake_smtp.released.wait(fake_smtp.HOLD_SAFETY_SECONDS)

    assert not session_was_over_before_run_returned, "run() waited for the SMTP worker thread instead of returning at the deadline"
    assert receipt_rows(info.value.receipts) == [("email", "failed", None, "network")]


def test_username_without_an_at_sign_and_no_sender_is_rejected_naming_sender(output_api) -> None:
    # AC-16 / §9.2 a-6: SendGrid's "apikey" and Resend's "resend" are not addresses, so From would be invalid.
    with pytest.raises(ConfigurationError, match="sender") as info:
        output_api.EmailOutput(to="ops@acme.com", host="smtp.sendgrid.net", username="apikey", password=SMTP_PASSWORD)

    assert SECRET_MARKER not in str(info.value)
    assert SECRET_MARKER not in repr(info.value.details)


@pytest.mark.asyncio
async def test_explicit_sender_becomes_from_while_login_keeps_the_username(output_api, fake_smtp) -> None:
    # §12.3 row 13: sender is the From address; username is only the SMTP login.
    connector = output_api.EmailOutput(to="ops@acme.com", host="smtp.sendgrid.net", username="apikey", password=SMTP_PASSWORD, sender="alerts@acme.com")

    await _send(output_api, connector)

    [session] = fake_smtp.sessions
    assert session.message["From"] == "alerts@acme.com"
    assert session.login == ("apikey", SMTP_PASSWORD)
