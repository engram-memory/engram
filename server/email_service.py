"""Email service — sends transactional emails via Resend."""

from __future__ import annotations

import logging
import os

log = logging.getLogger(__name__)

RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
FROM_EMAIL = os.environ.get("ENGRAM_FROM_EMAIL", "Engram <noreply@engram-ai.dev>")


def _get_resend():
    """Lazy-load resend to avoid import errors when not installed."""
    if not RESEND_API_KEY:
        return None
    try:
        import resend

        resend.api_key = RESEND_API_KEY
        return resend
    except ImportError:
        log.warning("resend package not installed. Emails disabled.")
        return None


def send_welcome_email(to_email: str, api_key: str) -> bool:
    """Send welcome email to new Pro subscriber with API key and quickstart."""
    resend = _get_resend()
    if not resend:
        log.info("Email skipped (no RESEND_API_KEY): welcome to %s", to_email)
        return False

    html = f"""
    <div style="font-family: 'Inter', system-ui, sans-serif; max-width: 600px; margin: 0 auto;
                background: #0a0a0f; color: #e8e8f0; padding: 40px; border-radius: 16px;">
      <h1 style="font-size: 1.8rem; margin-bottom: 8px;">
        Welcome to <span style="background: linear-gradient(135deg, #6B46C1, #06B6D4);
        -webkit-background-clip: text; -webkit-text-fill-color: transparent;">Engram Pro</span>
      </h1>
      <p style="color: #8888a8; font-size: 1rem; margin-bottom: 32px;">
        Your AI agents now have persistent memory. Here's everything you need to get started.
      </p>

      <div style="background: #12121e; border: 1px solid #1e1e35; border-radius: 12px;
                  padding: 24px; margin-bottom: 24px;">
        <p style="color: #8888a8; font-size: 0.85rem; margin-bottom: 8px;">Your API Key:</p>
        <code style="color: #22D3EE; font-family: 'JetBrains Mono', monospace; font-size: 0.9rem;
                     word-break: break-all; display: block; padding: 12px; background: #0a0a0f;
                     border: 1px solid #1e1e35; border-radius: 8px;">{api_key}</code>
        <p style="color: #F59E0B; font-size: 0.8rem; margin-top: 8px;">
          Save this key securely. It cannot be retrieved again.
        </p>
      </div>

      <div style="background: #12121e; border: 1px solid #1e1e35; border-radius: 12px;
                  padding: 24px; margin-bottom: 24px;">
        <p style="font-weight: 700; margin-bottom: 12px;">Quick Start</p>
        <pre style="color: #e8e8f0; font-family: 'JetBrains Mono', monospace; font-size: 0.85rem;
                    line-height: 1.8; overflow-x: auto;"><span style="color:#C084FC">pip install</span> engram-core

<span style="color:#C084FC">from</span> engram <span style="color:#C084FC">import</span> Memory

mem = Memory()
mem.store(<span style="color:#34D399">"User prefers dark mode"</span>, importance=<span style="color:#F59E0B">8</span>)
results = mem.search(<span style="color:#34D399">"dark mode"</span>)</pre>
      </div>

      <div style="background: #12121e; border: 1px solid #1e1e35; border-radius: 12px;
                  padding: 24px; margin-bottom: 24px;">
        <p style="font-weight: 700; margin-bottom: 12px;">Using the Cloud API</p>
        <pre style="color: #e8e8f0; font-family: 'JetBrains Mono', monospace; font-size: 0.85rem;
                    line-height: 1.8; overflow-x: auto;">curl -X POST https://api.engram-ai.dev/v1/memories \\
  -H <span style="color:#34D399">"X-API-Key: {api_key[:20]}..."</span> \\
  -H <span style="color:#34D399">"Content-Type: application/json"</span> \\
  -d '{{"content": "Hello Engram!", "importance": 8}}'</pre>
      </div>

      <div style="margin-bottom: 24px;">
        <p style="font-weight: 700; margin-bottom: 8px;">Your Pro Features:</p>
        <ul style="color: #8888a8; font-size: 0.9rem; line-height: 2; padding-left: 20px;">
          <li>250,000 Cloud Memories</li>
          <li>Memory Links &amp; Graph Traversal</li>
          <li>Agent AutoSave (trigger-based)</li>
          <li>Synapse Message Bus</li>
          <li>Semantic Search &amp; Smart Context</li>
          <li>Analytics Dashboard</li>
        </ul>
      </div>

      <div style="text-align: center; margin-top: 32px;">
        <a href="https://engram-ai.dev/account.html"
           style="display: inline-block; padding: 14px 32px;
                  background: linear-gradient(135deg, #6B46C1, #06B6D4);
                  color: white; text-decoration: none; border-radius: 12px;
                  font-weight: 600; font-size: 0.95rem;">
          Go to Dashboard
        </a>
      </div>

      <hr style="border: none; border-top: 1px solid #1e1e35; margin: 32px 0;">

      <p style="color: #55556a; font-size: 0.8rem; text-align: center;">
        Engram — Memory that sticks.<br>
        <a href="https://engram-ai.dev" style="color: #6B46C1;">engram-ai.dev</a> |
        <a href="https://github.com/engram-memory/engram" style="color: #6B46C1;">GitHub</a> |
        <a href="mailto:support@engram-ai.dev" style="color: #6B46C1;">Support</a>
      </p>
    </div>
    """

    try:
        resend.Emails.send(
            {
                "from": FROM_EMAIL,
                "to": [to_email],
                "subject": "Welcome to Engram Pro — Your API Key Inside",
                "html": html,
            }
        )
        log.info("Welcome email sent to %s", to_email)
        return True
    except Exception as e:
        log.error("Failed to send welcome email to %s: %s", to_email, e)
        return False
