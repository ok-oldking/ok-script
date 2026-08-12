"""Pure source transformations used by script editors."""

import re


def wrap_recorded_run_code(run_code, loop="none", count=1):
    lines = [line for line in str(run_code).strip("\n").split("\n") if line.strip()]
    if loop == "count":
        return "\n".join([f"for _ in range({max(1, int(count))}):"] +
                         ([f"    {line}" for line in lines] if lines else ["    pass"]))
    if loop == "forever":
        return "\n".join(["while True:"] +
                         ([f"    {line}" for line in lines] if lines else ["    pass"]))
    return "\n".join(lines) if lines else "pass"


def merge_recorded_code(source, init_code, run_code, loop="none", count=1):
    """Replace capture configuration and the run body in a task source file."""
    lines = str(source).split("\n")
    if str(init_code).strip():
        init_start = next((index for index, line in enumerate(lines)
                           if re.match(r'^\s*def\s+__init__\s*\(.*?\)\s*:', line)), -1)
        if init_start >= 0:
            match = re.match(r'^(\s*)def', lines[init_start])
            indentation = (match.group(1) if match else "") + "    "
            method_end = len(lines)
            for index in range(init_start + 1, len(lines)):
                if (re.match(r'^\s*def\s+', lines[index])
                        or (lines[index].strip() and not lines[index].startswith(indentation))):
                    method_end = index
                    break
            capture_start = next((index for index in range(init_start + 1, method_end)
                                  if re.match(r'^\s*self\.capture_config\s*=', lines[index])), -1)
            capture_end = capture_start
            if capture_start >= 0:
                brackets = 0
                for index in range(capture_start, method_end):
                    brackets += lines[index].count('{') - lines[index].count('}')
                    capture_end = index
                    if brackets <= 0:
                        break
            formatted = [indentation + line.rstrip() for line in str(init_code).strip("\n").split("\n")]
            if capture_start >= 0:
                lines[capture_start:capture_end + 1] = formatted
            else:
                lines[method_end:method_end] = formatted

    run_start = next((index for index, line in enumerate(lines)
                      if re.match(r'^\s*def\s+run\s*\(.*?\)\s*:', line)), -1)
    if run_start >= 0:
        match = re.match(r'^(\s*)def', lines[run_start])
        indentation = (match.group(1) if match else "") + "    "
        run_end = len(lines)
        for index in range(run_start + 1, len(lines)):
            if (re.match(r'^\s*def\s+', lines[index])
                    or (lines[index].strip() and not lines[index].startswith(indentation))):
                run_end = index
                break
        generated = wrap_recorded_run_code(run_code, loop, count).split("\n")
        lines[run_start + 1:run_end] = [indentation + line.rstrip() for line in generated]
    return "\n".join(lines)
