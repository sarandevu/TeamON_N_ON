"""EdgePPG baseline PC verifier.

This is the **standalone PC verifier** required by `Requirements §FR-VER-1, -2`:
  * Office-Kit-independent
  * Verifies the ECDSA signature over the canonical envelope
  * Checks nonce freshness and replay
  * Prints a human-readable result
  * Writes an offline receipt

The actual ECDSA verification is implemented here so the verifier is fully
self-contained — no Office Kit, no vendor SDK, no cloud.

A tiny demo HTTP server lives in `verifier.server`. It accepts an envelope via
HTTP POST and prints a textual dashboard. A QR-paste path is documented in
`docs/transport.md` (planned) and implemented inline in `verify.py`.
"""
__all__ = ["verify", "canonical", "server", "receipt"]
