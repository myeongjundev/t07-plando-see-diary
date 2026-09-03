"""Security primitives: password hashing, and later redaction and tokens.

Kept apart from `app/services` because these are the pieces a reviewer is asked
to find (T07-C126, T07-C128) and because they must have exactly one caller-facing
implementation each. A second place that hashes a password is a second place
that can hash it wrong.
"""
