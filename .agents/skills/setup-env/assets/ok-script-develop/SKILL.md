---
name: ok-script-develop
description: Develop and debug an application's automation with ok-script, including tasks, configuration, recognition assets, and tests. Discover the selected library's consumer skills and apply the project's conventions.
---

# Develop with ok-script

Work in the consuming application's project and use its configured Python
environment. This skill provides discovery and project integration for any game
or app using ok-script; the selected library supplies the development workflow
and API contracts. Library maintenance is outside this skill's scope.

## Locate the library instructions

Before changing automation behavior, locate the consumer skills matching the
library this application actually uses:

1. Check the project's local `ok` directory or configured source link. Resolve
   symlinks and junctions. A source checkout keeps skills at
   `<resolved-ok>/../.agents/skills`; a packaged directory keeps them at
   `<resolved-ok>/agent_resources/.agents/skills`.
2. If that source has no consumer skills, use the application's interpreter and
   `importlib.metadata.distribution('ok-script').locate_file('ok')` to locate its
   installed package, then check `agent_resources/.agents/skills` there. Do not
   use another environment's global installation.
3. Read `develop/SKILL.md` in the selected skill directory. Resolve its links
   relative to that original file, including the MCP guide and input references.
   Read `reload-tasks` for registered tasks, `generate-templates` for visual
   assets, and `write-test` for tests. Read setup skills when environment or
   runtime setup is needed.

When available, the selected package's `core/skills.py` provides `list_skills()`
and `get_skill()` with absolute source paths. Load that file with
`runpy.run_path` to discover instructions without importing the GUI runtime.
For example, with a local `ok` directory, run this using the project interpreter
from the application root:

```python
from pathlib import Path
import runpy

catalog = runpy.run_path(str(Path('ok').resolve() / 'core' / 'skills.py'))
for skill in catalog['list_skills']():
    print(skill['id'], skill['path'])
```

Keep the library's detailed instructions in their original location so they
follow its installed version. Inspect that version's source and signatures for
API details. If no consumer skills are available, report the missing resources
and use the project's setup guidance; do not invent MCP tools or silently upgrade
the dependency just to obtain instructions.

## Apply the workflow to this project

Follow the selected library's development skill for MCP startup, connection
discovery, task recovery, reloads, and runtime validation. Use ok-script APIs and
MCP for target capture and interaction. Do not use Computer Use skills, plugins,
or tools for this workflow.

Inspect the project's instructions, config, launchers, existing tasks, and local
skills before implementing changes. Reuse its task bases, registration style,
recovery helpers, assets, and localization conventions. Keep behavior in permanent
application modules and use thin MCP harnesses to exercise those implementations.

For new or changed named image features, read the library's `generate-templates`
skill before creating assets. Keep full screenshots in `ok_templates/`, annotate
them in `ok_templates/coco_annotations.json` with `CocoTemplateStore`, and call
`generate_templates` to produce split features in `assets/templates/` (or
`ok_tasks/assets/templates/` for custom scripts). Use the original names through
`find_feature`/`find_one`. Do not substitute hand-cropped runtime PNGs, a custom
template registry, or a separate `cv2.matchTemplate` loader for this pipeline.

The full images in `ok_templates/` can also be used directly as regression-test
fixtures with `TaskTestCase.set_image()` or `FeatureSet`. Read the library's
`write-test` skill, exercise real recognition with generated assets, and retain
independent positive/negative screenshots when available. The source-image
self-match alone verifies export consistency, not recognition robustness.

Use the configured project environment even when it is shared from a parent
workspace. Reuse this project's live runtime when suitable and follow the
library's process ownership rules when a restart is required. Validate observable
target behavior and relevant GUI lifecycle paths as described by the library.
If the target is unavailable, continue useful code and offline checks and report
the specific runtime checks that remain unverified.
