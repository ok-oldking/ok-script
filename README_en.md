# ok-script

[简体中文](README.md) | **English**

**Spend tokens once to build reusable Python automation.**

Describe what you want to a coding agent. Connect it to ok-script through MCP, let it inspect the application and installed APIs, then have it write and test a Python task. Save the result and run it repeatedly from your application's GUI or command line without an agent or LLM calls.

Development can take multiple iterations; changed applications may need later repairs. The goal is to spend tokens on creating and maintaining scripts. Ordinary execution uses local Python capture, recognition, and input.

ok-script supports Windows applications and games, Android emulators, and ADB devices, with template matching, OCR, background input where supported, a desktop UI, and task packaging.

[Start with MCP](docs/en/quick_start.md) · [Prompts for your coding agent](docs/en/agent-prompts.md) · [MCP connection guide](docs/mcp.md)

## Ask your coding agent

For a new environment:

> Install ok-script and set up this project's environment. First read https://raw.githubusercontent.com/ok-oldking/ok-script/master/docs/agent-setup.md and follow its setup skills. Preserve this project's existing dependency constraints.

The [agent setup guide](docs/agent-setup.md) includes a small instruction for your project's `AGENTS.md` so future setup requests use these instructions. It works before installation or MCP startup.

For task development:

> Connect to this project's ok-script MCP server and read its development skill. Inspect the installed capture, matching, and input APIs and show their exact signatures and source locations. Build a reusable Python task that opens Settings, enables "Show details", saves, and verifies the result. Restore and verify the starting screen before every attempt, test repeated runs, and save the task in the project. Use ok-script APIs and MCP, not Computer Use tools. Give me the exact command to run the finished task without an agent or LLM calls.

## Features

- Pure Python and open source, with access to the full pip ecosystem
- One task implementation can support Windows clients, Android emulators, and ADB devices
- OCR, OpenCV template matching, and integration with vision frameworks such as YOLO
- COCO-based template asset management with automatic resolution scaling
- Built-in capture, input, device control, and visual debugging tools
- Automated tests, GitHub Actions builds, and installer publishing
- Internationalization and online incremental updates

## Connect through MCP

Use an automation application's own virtual environment and preserve its existing requirements. For a new project, start from the [application template](https://github.com/ok-oldking/ok-script-app) and ask the agent to configure the target. Python 3.11 or later is supported.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install "ok-script[default]"
.\.venv\Scripts\python.exe -m ok mcp --config src.config:config
```

The command assumes the application's configuration exists; use its actual import target or existing development launcher. MCP is installed automatically with ok-script starting in 2.0.17; no extra is needed. Install exactly one compatible OpenCV variant separately; add Qt, ADB, and OCR dependencies only as needed.

Connect the agent's MCP client to the URL in the live `logs/mcp/connections/<pid>-<port>.json` record, with `Authorization: Bearer <token>` from that record. Keep credentials private. Have the agent call `list_skills`, read the relevant skills with `get_skill`, and verify the target with `screenshot`.

See the [MCP quick start](docs/en/quick_start.md) for setup, connection, and running the saved task without an agent. The [MCP guide](docs/mcp.md) covers execution and reload behavior.

## Documentation

- [MCP quick start](docs/en/quick_start.md)
- [Ask an agent to discover APIs and develop a task](docs/en/agent-prompts.md)
- [Documentation home](docs/en/index.md)
- [Maintain and share reusable tasks](docs/en/advanced.md)

The coding agent discovers Python APIs from the installed package's source and signatures. MCP supplies development skills and execution tools; there is no separate API lookup tool. Finished tasks can run headlessly or in the desktop GUI. See the [runtime architecture](docs/architecture.md) for details.

## Screenshots

| Task configuration | Capture and interaction |
| --- | --- |
| ![Task configuration interface](docs/ok_py/image_tasks.png) | ![Capture and interaction interface](docs/ok_py/image_capture.png) |

| Scripting and APIs | Template management |
| --- | --- |
| ![Scripting and API interface](docs/ok_py/image_scripting.png) | ![Template management interface](docs/ok_py/image_template.webp) |

[Read the complete interface and developer-tools guide](docs/en/interface.md), including the template-matching debug overlay.

## Projects built with ok-script

- [ok-script App Template](https://github.com/ok-oldking/ok-script-app)
- [Wuthering Waves](https://github.com/ok-oldking/ok-wuthering-waves)
- [Genshin Impact](https://github.com/ok-oldking/ok-genshin-impact) (unmaintained; background story automation still works)
- [Girls' Frontline 2](https://github.com/ok-oldking/ok-gf2)
- [Honkai: Star Rail](https://github.com/Shasnow/ok-starrailassistant)
- [Blue Protocol: Star Resonance](https://github.com/Sanheiii/ok-star-resonance)
- [Duet Night Abyss](https://github.com/BnanZ0/ok-duet-night-abyss)
- [Chaos Zero Nightmare](https://github.com/baoxin1100/ok-kes)
- [Onmyoji](https://github.com/YunLiuZ/ok-Onmyoji)
- [Ash Echoes](https://github.com/ok-oldking/ok-baijing) (unmaintained)
- [Arknights: Endfield](https://github.com/AliceJump/ok-end-field)
- [Neverness to Everness](https://github.com/BnanZ0/ok-nte)

## Community and releases

- Developer QQ group: 938132715
- [Discord](https://discord.gg/vVyCatEBgA)
- [PyPI](https://pypi.org/project/ok-script/)
- [GitHub](https://github.com/ok-oldking/ok-script)

## Credits

ok-script is made possible by these open-source projects:

- [PyAppify](https://github.com/ok-oldking/pyappify) — application updating
  and packaging.
- [OnnxOCR](https://github.com/ok-oldking/OnnxOCR) — OCR with Intel NPU
  support through OpenVINO or ONNX Runtime, using a PaddleOCR v5 model.
- [PySide6](https://wiki.qt.io/Qt_for_Python) — Qt-based desktop UI bindings.
- [PyQt-Fluent-Widgets](https://github.com/zhiyiYo/PyQt-Fluent-Widgets) —
  Fluent UI components used by the Qt interface.
- [OpenCV](https://opencv.org/), [NumPy](https://numpy.org/), and
  [Pillow](https://python-pillow.org/) — image processing and computer vision.
- [adbutils](https://github.com/openatx/adbutils) — Android device
  connectivity.

Each dependency remains subject to its own license. See the respective
project pages for details.

## License

This project is licensed under [Apache License 2.0 with Commons Clause and
additional terms](LICENSE.txt).

The following uses are allowed:

- Use in closed-source and commercial projects.
- Forking the project, making improvements, and keeping the fork open source
  and free.

The following restrictions apply:

- Do not take this project, rename it or make only minor changes, and sell it
  or market it as a competing product.
- Do not use it for hacking, unauthorized access, malware, fraud, or any other
  illegal activity.
- Any project using ok-script must mention it and link to [ok-script.com](https://ok-script.com/)
  or the [ok-script GitHub repository](https://github.com/ok-oldking/ok-script)
  on the project's website, GitHub repository, or in the software itself.
- Qt UI use is separately subject to the license of
  [PyQt-Fluent-Widgets](https://github.com/zhiyiYo/PyQt-Fluent-Widgets).
