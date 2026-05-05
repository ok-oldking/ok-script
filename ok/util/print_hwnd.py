import win32gui
import win32process
import psutil
from collections import defaultdict


def print_hwnd_tree():
    all_hwnds = set()

    # 1. Collect all window handles (Top-level and Children)
    def enum_windows_callback(hwnd, _):
        all_hwnds.add(hwnd)
        try:
            # Enumerate all descendants of the current top-level window
            win32gui.EnumChildWindows(hwnd, lambda child, _: all_hwnds.add(child) or True, None)
        except Exception:
            pass
        return True

    # Start enumeration from the desktop level
    win32gui.EnumWindows(enum_windows_callback, None)

    # 2. Gather info for each HWND and build the parent-child relationships
    nodes = {}
    tree = defaultdict(list)

    for hwnd in all_hwnds:
        # Visibility
        visible = win32gui.IsWindowVisible(hwnd) != 0

        # Size & Area
        try:
            left, top, right, bottom = win32gui.GetWindowRect(hwnd)
            width = right - left
            height = bottom - top
            area = width * height
        except Exception:
            width, height, area = 0, 0, 0

        # Class Name
        try:
            cls_name = win32gui.GetClassName(hwnd)
        except Exception:
            cls_name = "Unknown"

        # Process ID
        try:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
        except Exception:
            pid = 0

        # Executable Name
        exe_name = "Unknown"
        if pid > 0:
            try:
                exe_name = psutil.Process(pid).name()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                exe_name = "Access Denied / Exited"

        # Store node info
        nodes[hwnd] = {
            "hwnd": hwnd,
            "visible": visible,
            "width": width,
            "height": height,
            "area": area,
            "class": cls_name,
            "pid": pid,
            "exe": exe_name
        }

        # Determine structural parent
        try:
            parent = win32gui.GetParent(hwnd)
        except Exception:
            parent = 0

        # If parent is 0, or we somehow don't have the parent in our list, treat it as a root node
        if parent == 0 or parent not in all_hwnds:
            tree[0].append(hwnd)
        else:
            tree[parent].append(hwnd)

    # 3. Print the tree recursively
    def traverse_and_print(parent_hwnd=0, depth=0):
        if parent_hwnd not in tree:
            return

        children = tree[parent_hwnd]

        # Sort rule:
        # 1. not nodes[x]['visible'] -> False (0) for Visible, True (1) for Invisible. Puts Visible first.
        # 2. -nodes[x]['area']       -> Larger areas become smaller negative numbers. Puts Biggest first.
        children.sort(key=lambda x: (not nodes[x]['visible'], -nodes[x]['area']))

        for child_hwnd in children:
            info = nodes[child_hwnd]
            indent = "  " * depth

            # Formatting variables for clean output
            vis_str = "VIS" if info['visible'] else "INV"
            hwnd_hex = f"{info['hwnd']:08X}"
            size_str = f"{info['width']}x{info['height']}"

            print(f"{indent}[HWND: {hwnd_hex}] | {vis_str} | Size: {size_str:<9} (Area: {info['area']:<7}) | "
                  f"EXE: {info['exe']:<20} | PID: {info['pid']:<6} | Class: {info['class']}")

            # Recurse for children of this window
            traverse_and_print(child_hwnd, depth + 1)

    print("--- Window Hierarchy Tree ---")
    traverse_and_print(parent_hwnd=0, depth=0)


if __name__ == "__main__":
    print_hwnd_tree()
