"""The child-session agent.

Runs inside the child session (started from a shortcut in the user's Startup folder) and serves game
launch, capture and input to the host ok-script over localhost TCP:

    pythonw.exe <ok>/child_session/agent.py --project <project dir>

It exits at once outside a child session, relaunches itself elevated when configured
(one UAC prompt inside the child session), closes the configured startup apps and the
error boxes of Windows system apps in its own session only, and writes its port and
token to a per-project file in ``%LOCALAPPDATA%``.
"""

import argparse
import os
import sys
import time
import traceback


def _boot_log(message: str) -> None:
    """Log before anything else is imported, so a crash at sign-in is never silent."""
    try:
        folder = os.path.join(os.environ.get('LOCALAPPDATA') or os.path.expanduser('~'), 'ok-script',
                              'child_session')
        os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, 'agent-boot.log'), 'a', encoding='utf-8') as f:
            f.write(time.strftime('%Y-%m-%d %H:%M:%S ') + f'pid={os.getpid()} ' + message + '\n')
    except OSError:
        pass


def _bootstrap(project_dir: str) -> None:
    """Make ``ok`` importable when run as a script from the Startup folder shortcut."""
    if sys.stdout is None or sys.stderr is None:
        # pythonw has no console; libraries that print must not fail.
        devnull = open(os.devnull, 'w', encoding='utf-8')
        sys.stdout = sys.stdout or devnull
        sys.stderr = sys.stderr or devnull
    here = os.path.dirname(os.path.abspath(__file__))
    # Running a file puts its folder first on sys.path; module names there must not
    # shadow top-level ones.
    sys.path[:] = [p for p in sys.path if os.path.abspath(p or os.curdir) != here]
    ok_root = os.path.dirname(os.path.dirname(here))
    for path in (ok_root, project_dir):
        if path and path not in sys.path:
            sys.path.insert(0, path)
    os.chdir(project_dir)


def main(argv=None):
    parser = argparse.ArgumentParser(description='ok-script child-session agent')
    parser.add_argument('--project', required=True)
    parser.add_argument('--elevated', action='store_true', help='internal: this is the elevated relaunch')
    parser.add_argument('--any-session', action='store_true', help='testing: run outside a child session')
    args = parser.parse_args(argv)
    project_dir = os.path.abspath(args.project)
    _boot_log(f'start {sys.executable} project={project_dir} elevated_flag={args.elevated}')
    try:
        _bootstrap(project_dir)
        from ok.child_session.agent_server import run
        return run(project_dir, elevated_relaunch=args.elevated, any_session=args.any_session)
    except BaseException:
        _boot_log('crashed:\n' + traceback.format_exc())
        raise


if __name__ == '__main__':
    sys.exit(main())
