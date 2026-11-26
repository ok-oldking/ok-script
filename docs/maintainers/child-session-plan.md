# Child session device: implementation plan

Goal: run a Windows game inside a Windows **child session** (a nested RDP session for
the same user) so automation input is isolated from the user's real mouse and keyboard.
The feature is optional: an app opts in with a `child_session` config key, and the
user opts in by selecting the child session device.

Architecture: **option A**. A small agent process runs inside the child session and
does game launch, capture and input locally. The host ok-script (main session) talks
to it over localhost TCP and shows the session in an embedded RDP view tab.

```
Host ok-script (main session)                     Child session (same user)
┌────────────────────────────────────┐            ┌──────────────────────────────┐
│ ChildSessionTab: QAxWidget(MsTscAx)│  RDP view  │ Explorer + game              │
│   1920x1080, SmartSizing           │ ─────────► │                              │
│ DeviceManager device 'child_session'│           │ ok.child_session.agent       │
│   ChildSessionCaptureMethod        │  TCP 127.0.0.1 │  HwndWindow (game window)   │
│   ChildSessionInteraction          │ ◄────────► │  WGC / BitBlt capture        │
│ StartController -> agent.launch    │ frames/cmds│  agent_input (pynput)        │
└────────────────────────────────────┘            └──────────────────────────────┘
```

Tasks stay unchanged: they see a normal capture method, interaction and a window
adapter, the same way the browser device works today.

## Phase 0: feasibility spike (gate)

Standalone scripts, no framework changes. Stop and rethink if any check fails.

1. Enable child sessions on this machine (`WTSEnableChildSessions(TRUE)`, admin) and
   confirm with `WTSIsChildSessionsEnabled`.
2. Host `MsTscAx.MsTscAx` in PySide6 `QAxWidget`; find which settings interface exposes
   `ConnectToChildSession`, connect at 1920x1080 with SmartSizing.
3. Confirm how a process starts in the child session at logon: Startup folder entry,
   or a scheduled "At log on" task with highest privileges (needed if the agent must be
   elevated). The agent exits unless `ProcessIdToSessionId(pid) == WTSGetChildSessionId()`.
4. Start Wuthering Waves in the child session: it launches (no RDP/anti-cheat refusal),
   renders at an acceptable frame rate, and runs borderless/fullscreen at a 1920x1080 client area.
5. Inside the session: WGC (or BitBlt_RenderFull) captures the game, and pynput
   (SendInput) clicks, keys and mouse moves reach it, including camera drag. Check that
   the user's real mouse and keyboard are untouched, and whether the agent must be
   elevated for SendInput to reach the game (UIPI).
6. Measure frame transfer over localhost TCP (1920x1080x3 ≈ 6.2 MB) at the rate tasks need.
7. Check behaviour when the host tab is hidden, the host window is covered, and when it
   is minimized (`RemoteDesktop_SuppressWhenMinimized`).

### Phase 0 results (2026-11-26, Windows 11 Pro 10.0.26300, not elevated)

Prototype scripts: `cs_check.py`, `cs_viewer.py`, `cs_agent.py`, `cs_client.py`
(kept outside the repository).

| Step | Result |
|---|---|
| 1. Enable child sessions | Already enabled (`WTSIsChildSessionsEnabled` = true). |
| 2. Host the RDP control | Works. ok-script's minimal PySide6 build has no `QtAxContainer`, so the control (`MsRdpClient9NotSafeForScripting`, version 10.0.26100) is hosted in an ATL `AtlAxWin` child window via comtypes and parented to a Qt widget. No new dependency. `ConnectToChildSession` is not in the type library; it is set by name through `IMsRdpExtendedSettings.Property` and reads back true. |
| Session lifetime | Closing the viewer disconnects; the child session keeps running. `logoff <id>` cannot see child sessions; `WTSLogoffSession` needs admin for another account's session. |
| 3. Start the agent in the session | Works through the user's `HKCU\...\Run` list: a child session is a full logon, so Explorer runs the startup list there (~40–120 s after logon). The RDP `StartProgram` / alternate shell is **ignored** on Windows 11 Pro (Explorer still starts). Session check: `WTSGetChildSessionId` only works from the parent; inside the child use "not the console session, `WTSIsRemoteSession`, client name == this computer". Verified: exits on the console session, runs in the child. |
| Startup apps | The child logon also starts all of the user's startup apps (QQ, QQMusic, OneDrive, MuMu service…). No per-session switch exists. The agent closes a configurable list **only in its own session** for the first 3 minutes; verified: closed in the child, untouched in the console session. |
| Windows system apps | Some packaged system apps started at logon (`CrossDeviceResume.exe`, `ClickToDo.exe`, `AIXHost.exe`) cannot run in a child session and each leaves an error box ("Windows cannot access the specified device, path, or file") on top of the game. The agent must dismiss these (`#32770` dialogs whose title is a `SystemApps` path) in its session, since they can take focus and catch clicks. |
| Elevation | **Required.** Wuthering Waves runs elevated, so UIPI silently drops input from a normal agent (`SetCursorPos` returns 0 with no error; `SendInput` reports success but nothing moves). After an elevated restart (one UAC prompt inside the child session) the cursor moves. A restart spawned by the elevated agent stays elevated. |
| 4. Game in the child session | Works. Launched by the agent (`os.startfile`, `-krqlv=uhd`), compiles shaders on first launch, then reaches the start screen at a 1920x1080 client area. No RDP refusal. |
| 5. Capture | PrintWindow returns black. ok-script's `WindowsGraphicsCaptureMethod` with a minimal window adapter works inside the session (live 1920x1080 frames). **Game popups are separate windows**: the announcement page is a full-screen `KRWebClientWindow`, invisible when offline, that swallows all clicks and does not appear in a capture of the game window. The agent must report or capture top-level windows of the game process, not only `UnrealWindow`. |
| 5. Input (pynput, elevated agent) | Works. Click on 设置 opened the settings menu and Esc closed it, verified with whole-screen captures. Host cursor unchanged during the click. Click needs a small move and ~0.1 s settle before press. Relative moves are scaled by pointer acceleration (+50 → +70). The RDP viewer forwards the host mouse into the session when it hovers the view, so a view-only mode is needed while tasks run. |
| 6. Frame transfer | Raw 1920x1080 BGR over localhost TCP: 15.7 fps including capture with PrintWindow; WGC 7–14 fps with the viewer shown, ~30 fps with it minimized or covered (WGC waits for the game's next frame). Enough for ok-ww tasks; optimise later if needed. |
| Sign-in | Works with the account password (Windows Hello PIN cannot be used). For a Microsoft-account user the name must be `MicrosoftAccount\<email>`; `COMPUTER\user` and the display name are rejected. Several wrong guesses happened first, so lockout risk is real. |
| Sign-in name | Detected automatically with `NetUserGetInfo` level 24 (`usri24_internet_provider_name` + `usri24_internet_principal_name`), falling back to `COMPUTERNAME\USERNAME` for local accounts. No admin needed. |
| Credential saving | The control itself stores nothing (no `TERMSRV/localhost` entry). The prototype asks for the password once, writes a generic credential `ok-script/child-session/localhost` with `CredWrite`, and passes it with `UserName` + `AdvancedSettings9.ClearTextPassword`. Verified: first connect signs in with no Windows prompt; closing and reopening the viewer finds the saved credential and reconnects to the same child session in ~2 s with no dialog. |
| 7. Minimized / covered viewer | Works, with no client-side registry change. Viewer normal, minimized (`SW_MINIMIZE`), and covered (bottom of z-order): the session screen stays live, WGC keeps delivering 1920x1080 frames, and a pynput click opens Settings and Esc closes it in all three states. WGC was faster when the viewer was not shown (13.7 fps normal, 28.5 minimized, 30.9 covered), probably because the host no longer decodes and draws the RDP stream. The viewer stayed connected throughout. |

Consequences for Phase 1:
- The tab must check for a usable password before connecting and explain the
  PIN-only / passwordless case, instead of letting users fail sign-in repeatedly
  (repeated failures risk the account lockout policy).
- Fill the sign-in name automatically (`NetUserGetInfo` level 24) and ask only for the
  password, once; store it in Credential Manager and pass it to the control (verified).
- On a logon error, stop and ask again instead of retrying the saved password, and offer
  "Forget saved password".
- A dedicated local account with a generated password would avoid the problem for
  PIN-only users, but needs admin to create and a per-account game setup. Not chosen
  for now.
- The agent must run elevated in the child session. Run-key autostart cannot elevate,
  so either prompt UAC once per child logon or register a scheduled "At log on" task
  with highest privileges (admin once). Decide in Phase 1.
- Autostart the agent from the user's Run list with the in-child session check, and close
  the configured startup apps in the child session only.
- Capture must include the game's own popup windows (or the whole session screen), and
  the agent should report or close invisible game web windows that block input.
- Add a view-only overlay on the RDP view while tasks run; route keyboard focus into the
  control when the user interacts (Win+R currently reaches the host).

## Phase 1 status

Implemented as a **capture method and interaction of the PC game window**, both named
`ChildSession`, instead of a separate device: they appear next to WGC / PostMessage when
the app config has `child_session`, and selecting the capture selects the interaction.
Code: `ok/child_session/` (agent, pynput input, protocol, client, host setup),
`ok/device/capture_methods/child_session.py`, `ok/device/interaction_methods/child_session.py`,
`ok/ui/qt/child_session/` (the Child Session page in the Run section). User docs:
`docs/en/child-session.md`. The original plan below said "device type"; read it as the
ChildSession capture.

Agent autostart uses a Startup-folder shortcut, not a registry Run entry. On the test PC
the Run entry was removed around child-session sign-ins and, when present, Explorer's
startup run in the child session skipped it (Shell-Core events 9705-9707 list every
other entry); a Startup-folder shortcut started the agent. Installing the shortcut also
removes an old Run entry.

## Phase 1: framework (ok-script)

### 1. Win32 helpers: `ok/child_session/win_api.py`
- `is_enabled()`, `enable()` (admin), `child_session_id()`, `current_session_id()`,
  `in_child_session()` via `wtsapi32` / `kernel32` ctypes.

### 2. Protocol: `ok/child_session/protocol.py`
- Length-prefixed messages on `127.0.0.1:<port>`: a JSON header plus an optional binary
  payload (frames as raw BGR with width/height/stride in the header).
- Auth: a random token and the port written to a per-project file under
  `%LOCALAPPDATA%`, readable by both sessions (same user). Reject connections without it.
- Commands: `hello`, `find_window`, `window_info`, `launch(path, args)`, `frame`,
  `click`, `mouse_down/up`, `move`, `scroll`, `key_down/up`, `send_key`, `input_text`,
  `swipe`, `shutdown`. Failures return an error message the host logs and raises.
- Frames go over TCP first. A file-backed shared mapping is a later optimisation, used
  only if the Phase 0 numbers need it.

### 3. Agent: `ok/child_session/agent.py` (`python -m ok.child_session.agent --project <dir>`)
- Exits unless it is in the child session; single instance per project.
- Reads the project's `windows` config (exe, hwnd_class, top_hwnd_class, capture list)
  and reuses `HwndWindow` and the existing capture methods, running locally in the session.
  It does not use the `windows.interaction` list.
- Input is a separate module, `ok/child_session/agent_input.py`, built on pynput
  (SendInput). SendInput is safe here because the child session has its own input
  queue. The module:
  - keeps the game window in front inside the session before sending input;
  - converts game client coordinates to session screen coordinates (`ClientToScreen`,
    per-monitor DPI aware);
  - implements click, mouse down/up, move, relative move, scroll, key down/up,
    send_key, input_text and swipe, mapping ok-script key names to pynput keys.
- `launch` runs `ok.util.process.execute` inside the session, so the game starts there.
- Logs to the project's `logs/child_session_agent.log`.

### 4. Host device classes
- `ok/device/capture_methods/child_session.py`: `ChildSessionCaptureMethod(BaseCaptureMethod)`
  sends `frame` requests; `connected()` means the agent is connected and the window was found.
- `ok/device/interaction_methods/child_session.py`: `ChildSessionInteraction(BaseInteraction)`,
  a separate interaction method (not a variant of `PynputInteraction`). It forwards each
  call to the agent's pynput input module and never touches the host's input.
- `ChildSessionWindowAdapter`, modelled on `BrowserWindowAdapter`, so `task.hwnd` keeps
  working (`exists`, `width`, `height`, `visible`, `hwnd_title`, `bring_to_front` forwarded).

### 5. DeviceManager (`ok/device/DeviceManager.py`)
- `self.child_session_config = app_config.get('child_session')`; device type
  `'child_session'` built by `update_child_session_device()`, added in `do_refresh`.
- Branches in `do_start`, `available_capture_methods` (`['child_session']`),
  `available_interaction_methods`, `device_connected`, `get_devices` sort order.
- `get_exe_path` reuses the `windows.calculate_pc_exe_path` logic; the path is resolved
  on the host and passed to the agent.

### 6. StartController (`ok/core/start_controller.py`)
- For `child_session`: make sure the RDP view is connected (the tab, or auto-connect),
  wait for the agent `hello`, send `launch(path, args)` with the same launch arguments
  as `windows`, then wait until the window is stable using `window_info`.
- `check_resolution`: report a clear error when the client area is not the configured
  resolution (for example the game is windowed and its title bar takes space).
  Remote resizing is out of scope.

### 7. Qt tab: `ok/ui/qt/child_session/ChildSessionTab.py`
- Added in `MainWindow` (Game section) only when the app config has `child_session`.
- Status rows: feature enabled, admin, viewer connected, agent connected, game window found.
- Actions: **Enable child sessions** (admin), **Install agent autostart** / remove,
  **Connect** / **Disconnect**.
- View: `QAxWidget("MsTscAx.MsTscAx")` with `DesktopWidth/Height` from the config and
  SmartSizing, created only on Connect, kept alive when navigating to other pages, and
  owned by the GUI thread. Show a warning that minimizing may stop rendering.
- The user types any sign-in credentials themselves.

### 8. Optional user settings
- Global `ConfigOption('Child Session', {'Auto Connect': True})`, registered only when
  the app opts in. Selecting the device is what enables the feature.

### 9. App config contract
```python
'child_session': {                 # optional; omit to disable the feature
    'resolution': (1920, 1080),    # session desktop and expected game client size
    'nick': 'Game (Child Session)',
    # exe, hwnd_class, launch arguments and capture list come from 'windows';
    # input is always the agent's pynput module
},
```

### 10. Docs, i18n and tests
- `docs/en/child-session.md`: requirements (Windows Pro/Enterprise, admin once),
  setup, limitations. New UI strings go through `docs/maintainers/translations.md`.
- Unit tests with a fake agent server: protocol framing and auth, capture and
  interaction forwarding, DeviceManager device list and branches, tab created only
  when configured. No real RDP in CI.

## Phase 2: test on ok-wuthering-waves

The WW project symlinks `ok -> E:/projects/ok-script/ok`, so framework changes apply
there directly.

1. Add to `E:/projects/ok-wuthering-waves/config.py`:
   ```python
   'child_session': {
       'resolution': (1920, 1080),
       'nick': 'Wuthering Waves (Child Session)',
   },
   ```
2. In the child session, set WW to borderless/fullscreen at 1920x1080 once.
3. Run `main_debug.py` as admin, open the Child Session tab: enable, install the
   autostart, connect, select the child session device, start the game from the GUI.
4. Check: frames in the Diagnosis screenshot, the resolution check passes, a daily task
   runs end to end, and the real mouse and keyboard stay free during the task.
5. Run the same task through MCP (`list_tasks`, run, `get_run_status`).

Known WW limitations in this mode (they use the host's own Win32 input or window
handles): `MultiAccountDailyTask` and `MultiAccountConfigTask` (login combo, `SetCursorPos`),
`CombatCheck` cursor moves, `RahaiBlocksTask` (builds its own host `PynputInteraction`),
`MouseResetTask`. Since the child session input is already pynput, these can mostly be
routed through `ChildSessionInteraction` (or hidden in child session mode). Decide after
Phase 2 shows which ones matter.

## Risks
- `ConnectToChildSession` access from Qt may need a raw COM interface (Phase 0 step 2).
- Starting the agent elevated inside the child session may need a UAC click there (step 3).
- GPU acceleration and frame pacing inside RDP sessions (step 4).
- Anti-cheat or RDP detection in the game (step 4).
