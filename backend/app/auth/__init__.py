"""Where requests are refused for who is asking. Design section 3.

`guards.py` answers "is anyone logged in", `cookies.py` carries the values that
answer it. Ownership -- "is this yours" -- lives in `app/services/ownership.py`.

Kept to as few files as possible on purpose: T07-C126 asks the submission to
point at the source that produces the refusals, and that is only answerable if
there are few enough places to point at.
"""
