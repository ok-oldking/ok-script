# Quick start

[Documentation](index.md) · [Advanced guide](advanced.md) · [API reference](api_reference.md) · [简体中文](../quick_start/README.md)

This guide uses the `ok-script-app` template to create and run an automation project. By the end, you will have connected a Windows game or Android device, run the diagnostics, and be ready to implement tasks.

## Prerequisites

- Windows 10 or Windows 11
- Python 3.11 or later (Python 3.12 recommended)
- Git
- A Windows client, or an Android emulator/device with ADB enabled

## 1. Fork the template

Open [`ok-script-app`](https://github.com/ok-oldking/ok-script-app) and select **Use this template** to create a repository in your GitHub account.

## 2. Clone your project

```powershell
git clone https://github.com/YOUR_USERNAME/your-project-name.git
cd your-project-name
```

Replace `YOUR_USERNAME` and `your-project-name` with your GitHub account and repository name.

## 3. Install Python

The framework supports Python 3.11 and later. Python **3.12** is recommended.

Download Python from [Python.org Downloads](https://www.python.org/downloads/).

On 64-bit Windows, select the installer whose name contains `amd64.exe`. Enable **Add Python to PATH** during installation, then verify it:

```powershell
python --version
```

## 4. Create a virtual environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

If PowerShell blocks activation scripts, use `.\.venv\Scripts\python.exe` directly for the remaining commands.

## 5. Install dependencies

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## 6. Configure the target

Open `src/config.py`. Configure at least one of the `windows` or `adb` sections.

For a Windows client:

- `exe`: accepted executable names, such as `['StarRail.exe']`
- `start_exe`: whether the application starts and checks the game process; defaults to `True`
- `start_method`: process launch method; defaults to `start`, with `os.startfile` also available
- `interaction`: input backend, such as `Genshin`, `PostMessage`, or `Pynput`

For an Android emulator or physical device:

- `packages`: accepted package names, such as `['com.example.game']`

Both sections may remain configured. The application selects the available window or device at runtime.

## 7. Run the application

Debug mode enables additional logging and draws overlays around recognition targets:

```powershell
python main_debug.py
```

Production mode omits the visual debug overlays:

```powershell
python main.py
```

> **Important:** Some Windows input backends require administrator privileges. If input does not work, launch the terminal or IDE as administrator. ADB devices and emulators usually do not require elevation.

## 8. Test capture

Select **Screenshot Test** in the application. Confirm that a new image appears in the project's `screenshots` directory.

## 9. Run diagnostics

Select **Run Diagnostic Task**. The built-in task checks the environment and target configuration.

## 10. Implement a task

Use the template tasks as starting points:

- `src/tasks/MyOneTimeTask.py`: a task that runs once, such as claiming a daily reward
- `src/tasks/MyTriggerTask.py`: a task repeatedly activated by a trigger, such as automated combat

## Next steps

- Read the [advanced guide](advanced.md) for templates, tests, localization, and releases.
- Consult the [API reference](api_reference.md) for capture, input, OCR, and matching methods.
- Read the [automation introduction](intro_to_automation.md) if the computer-vision workflow is unfamiliar.
