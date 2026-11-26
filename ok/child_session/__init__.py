"""Run a Windows game inside a child session (a nested RDP session for the same user).

The game, capture and input run in the child session, so automation does not move
the user's own mouse or keyboard. A small agent process (``agent.py``) runs inside the
child session; the host ok-script talks to it over localhost TCP.

See ``docs/maintainers/child-session-plan.md``.
"""

CONFIG_KEY = 'child_session'
# The name of both the capture method and the interaction of the PC game window.
METHOD_NAME = 'ChildSession'
