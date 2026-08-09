# ok-script documentation

[简体中文](../index.md) | **English** · [Project home](https://github.com/ok-oldking/ok-script)

The documentation follows a practical path: understand the concepts, run a project, learn the visual tools and advanced workflows, then consult the API while implementing tasks.

## Learning path

| Guide | Audience | Topics |
| --- | --- | --- |
| [Introduction to game automation](intro_to_automation.md) | Readers new to computer vision or automation | Capture, analysis, decisions, input, and development tools |
| [Quick start](quick_start.md) | Developers creating their first project | Template setup, environment, device configuration, execution, and diagnostics |
| [Interface and developer tools](interface.md) | Developers learning the visual workflow | Tasks, capture, interaction, scripting, templates, and debug overlays |
| [Advanced guide](advanced.md) | Developers with a working template project | COCO templates, i18n, testing, packaging, and publishing |
| [API reference](api_reference.md) | Developers implementing task logic | `Box`, `BaseTask`, capture, input, OCR, and image matching APIs |

## Fastest route to a working project

1. Install Python 3.12. Python 3.11 or later is supported.
2. Create a repository from the [`ok-script-app`](https://github.com/ok-oldking/ok-script-app) template.
3. Follow the [quick-start guide](quick_start.md) to configure a Windows game or ADB device.
4. Run the application in debug mode and complete the capture test.
5. Use the [API reference](api_reference.md) while implementing your tasks.

## Useful links

- [ok-script source](https://github.com/ok-oldking/ok-script)
- [ok-script App Template](https://github.com/ok-oldking/ok-script-app)
- [ok-py visual scripting tool](https://github.com/ok-oldking/ok-py)
- [PyPI package](https://pypi.org/project/ok-script/)
- [Build the documentation website](building-site.md)

If the documentation differs from the behavior you observe, open a GitHub issue and include your ok-script version, Python version, and runtime environment.
