"""Verification: the safety-net checks."""

from .verifier import Severity, Status, VerificationReport, verify

__all__ = ["verify", "VerificationReport", "Severity", "Status"]
