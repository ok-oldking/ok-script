# Validate Windows input through MCP

Use this reference when capture works but input fails, a log reports access
denied, or an operation may need foreground input. Diagnose the particular
action before changing the application's configured interaction backend.

## Separate permission, delivery, and recognition

- Confirm the configured target, capture dimensions, coordinate mapping, and a
  fresh frame. A cached observation or a successful input API return does not
  prove that the game received the action.
- For `PostMessage` error 5 / access denied, inspect the privilege level of the
  **serving ok-script process** and the target process using available read-only
  diagnostics. `ok.util.process.is_admin()` called through an MCP observation
  task describes the runtime; calling it in the agent's client describes a
  different process. Working capture does not establish matching input rights.
- If a lower-privilege runtime is confirmed against an elevated target, restart
  only the verified, owned runtime at the required privilege level before
  experimenting with recognition thresholds or input backends. Do not elevate
  by default, disable security controls, automate UAC, or bypass execution
  policy. If elevation is unavailable, report the specific blocker.
- When there is no access-denied error, inspect focus, input coordinates,
  scaling, press duration, drag endpoints, and release coordinates. Failure of
  one drag is not evidence that all background input is unsupported.

## Restart an owned runtime when elevation is needed

1. Preserve the failing log and observation. Respect ownership: an existing user
   GUI is not an agent-owned console to terminate merely for development.
2. For an owned MCP runtime, request `exit_process(reason=...)`, wait locally for
   its returned PID to exit, then relaunch with the consuming project's absolute
   venv interpreter, working directory, and actual launcher/config arguments.
3. On Windows, an allowed elevation path is PowerShell `Start-Process` with
   `-Verb RunAs` and `-WindowStyle Hidden`. The user handles any OS UAC prompt;
   explain why it appears. Preserve the project's config and selected target.
4. Rediscover the connection and validate the new PID, listener, and project.
   Do not reuse the old URL, credentials, or run IDs. Verify runtime privilege,
   capture freshness, and the same input action again. Restarting ok-script does
   not reset the game UI.

## Verify input by action and window state

Use a small MCP harness that restores and verifies an appropriate starting
state. Exercise an action with a known, visible effect; bound retries and stop
to diagnose repeated no-effects instead of continuing the full task.

| Action | Evidence of delivery |
| --- | --- |
| Ordinary button click | The intended page, selection, or modal changes |
| Key | Its intended visible menu or state changes |
| Drag or swipe | The item actually moves, the list scrolls, or the game accepts the move |

For example, a successful match-three swap changes pieces and an accepted-move
counter or elimination result. Mouse motion alone is insufficient evidence.

Test required actions in the foreground first, then test PostMessage while the
game is unfocused or covered. Observe the real foreground window and cursor as
well as the target's response. Record each tested state; do not infer minimized
support from covered-window support, or drag support from a working menu click.
Change one factor at a time so privilege changes are not confused with backend
changes. Preserve pre-action and post-action evidence for failed and successful
cases, including the actual backend and fresh capture timestamps.

## Use a narrow foreground fallback

If an action still has no observed background effect after permission and
coordinate checks, a foreground fallback can be appropriate within the user's
task. Describe the evidence as an observed limitation of that action and tested
backend; do not assert that the game intrinsically requires foreground input.

- Prefer the library's existing interaction APIs. Inspect the installed backend
  before naming its OS APIs or assuming timing/coordinate behavior. For example,
  a tested `PynputInteraction.swipe()` may delegate cursor positioning to pynput's
  Windows `SetCursorPos` and button events to `SendInput`; verify the local code.
- Limit the fallback to actions that need it. Keep working background buttons
  and keys on the configured backend rather than changing global settings.
- Inform the user that the operation brings the game forward and occupies the
  real cursor. After activation, verify the current target is foreground before
  injecting input; some swipe implementations do not enforce `clickable()`.
  If focus cannot be obtained or is lost, pause the gesture or fail clearly.
- Keep coordinates relative to the captured target and use its capture-to-screen
  conversion. Ensure button release in cleanup if constructing a custom gesture.
  Restore temporary interaction overrides in `finally`.
- Re-run the actual registered task through MCP. Report background and foreground
  validation separately, naming the action, backend, tested target state, visible
  result, cursor/focus side effects, and any remaining untested cases.

Do not use Computer Use skills, plugins, or tools for input validation or desktop
task-card testing. Keep capture and interaction in ok-script APIs and MCP. If the
GUI Start action cannot be tested through permitted APIs or an application-local
test harness, report that check as unverified.
