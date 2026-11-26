# Child session

A child session is a second Windows session of the same user, nested in the
current one. ok-script can run a Windows game there: the game, screen capture and
mouse and keyboard input all stay inside the child session, so automation never
moves the user's own mouse or types on their keyboard.

The feature is optional. An application opts in with a `child_session` section in
its config. That adds a **ChildSession** capture method and a **ChildSession**
interaction to the PC game window; the user opts in by selecting the ChildSession
capture (the interaction follows it).

## Requirements

- Windows 10 or 11 Pro, Enterprise or Education.
- Child sessions enabled once on the computer (the Child Session page has an
  **Enable** button; it needs ok-script to run as admin once).
- The Windows account must have a **password**. A Windows Hello PIN cannot sign in
  to a child session. For a Microsoft account the sign-in name is
  `MicrosoftAccount\<email>`; ok-script fills it in.

## Application config

```python
config = {
    'windows': {
        'exe': 'Game.exe',
        'hwnd_class': 'UnrealWindow',
        # ... the usual Windows game settings
    },
    'child_session': {
        'resolution': (1920, 1080),   # the child session's screen size
        'nick': 'Game (Child Session)',
    },
}
```

The child session uses the `windows` section to find and start the game, including
`calculate_pc_exe_path` and `launch_arguments`.

## How it works

- The **Child Session** page (Run section) sets things up and embeds the child
  session's screen. Starting a task with the ChildSession capture selected connects it
  if needed and starts the game inside the child session. Closing or
  minimizing the view keeps the session and the game running; capture is faster
  when the view is hidden.
- **Connect** signs in with the saved password. The password is asked once and
  kept in Windows Credential Manager (`ok-script/child-session/localhost`).
- A small agent (`ok/child_session/agent.py`) starts from a shortcut in the user's
  Startup folder (`ok-script-child-session-<id>.lnk`)
  when the child session signs in, and exits at once on the normal desktop. If the
  game runs as admin, the agent asks for admin with one UAC prompt inside the
  child session after each sign-in.
- The agent finds the game window, captures it with Windows Graphics Capture, and
  sends input with pynput, all inside the child session. ok-script talks to it over
  localhost with a random token.
- A child session is a full sign-in, so Windows also starts the user's startup apps
  there. The agent closes the apps listed on the page (QQ, OneDrive, ...) in the
  child session only, and dismisses the error boxes of Windows system apps that
  cannot run in a child session.
- **View only** blocks your mouse and keyboard from reaching the session while the
  agent runs, so a hand over the view cannot disturb a task.

## Limitations

- Tasks that call Win32 functions or Pynput on the host directly (for example to
  read a window handle or move the real cursor) do not reach the child session.
  Use the task's interaction methods instead.
- The game's own popup windows (for example a web announcement page) are separate
  windows and can cover the game; tasks should handle them as usual.
- Relative mouse moves are scaled by Windows pointer acceleration.
