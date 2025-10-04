import re
import subprocess

from ok import Logger

logger = Logger.get_logger(__name__)


def get_installed_packages(pip_command):
    try:
        output = subprocess.check_output(pip_command + ['freeze'], universal_newlines=True)
        return set(line.split('==')[0] for line in output.splitlines())
    except Exception as e:
        logger.info(f'Failed to get installed packages {str(e)}')


def get_package_required_by(package_name, pip_command):
    try:
        cmd = pip_command + ['show', package_name]
        logger.info(f'get_package_dependencies cmd {" ".join(cmd)}')
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   universal_newlines=True)
        output, error = process.communicate()

        if error or not output:
            logger.error("get_package_dependencies Error:", error)
            return set()
        dependencies = []
        for line in output.splitlines():
            if line.startswith('Required-by:'):
                dependencies = line.split(': ')[1].split(', ')
                break
        dep_set = set(dep for dep in dependencies if dep)
        logger.info(f'get_package_dependencies {package_name} {dep_set}')
        return dep_set
    except Exception as e:
        # Ignore the warning message and return an empty set
        logger.error("get_package_dependencies Exception:", e)
        return set()


def uninstall_packages(packages, pip_command):
    subprocess.check_call(pip_command + ['uninstall', '-y'] + list(packages))


def get_package_dependencies(packages, pip_command):
    try:
        packages = list(packages)
        output = subprocess.check_output(pip_command + ['show'] + packages, stderr=subprocess.STDOUT,
                                         universal_newlines=True, encoding='utf-8', errors='replace')
        dependencies = {}
        current_package = None
        for line in output.splitlines():
            if line.startswith('Name:'):
                current_package = line.split(': ')[1]
                dependencies[current_package] = set()
            elif line.startswith('Requires:') and current_package:
                deps = line.split(': ')[1].split(', ')
                dependencies[current_package].update(dep for dep in deps if dep)
        return dependencies
    except Exception as e:
        logger.error("get_package_dependencies error:", e)
        return {}


def get_all_dependencies(packages, pip_command):
    all_deps = {}
    visited = set()

    def _get_deps(package):
        if package in visited:
            return
        visited.add(package)

        if package not in all_deps:
            deps = get_package_dependencies([package], pip_command)
            all_deps.update(deps)

        for dep in all_deps.get(package, []):
            _get_deps(dep)

    for package in packages:
        _get_deps(package)

    return all_deps


def clean_packages(to_install, pip_command):
    installed_packages = get_installed_packages(pip_command)
    logger.info(f'installed_packages = {installed_packages}')
    if not installed_packages:
        logger.info("No installed_packages.")
        return

    dependency_map = get_package_dependencies(installed_packages,
                                              pip_command=[r'python\app_env\Scripts\python.exe', '-m', 'pip'])

    package_to_parents = build_reverse_map(dependency_map)

    to_uninstall = []
    for installed_package in installed_packages:
        if not is_required_by(installed_package, package_to_parents, to_install):
            to_uninstall.append(installed_package)

    # Uninstall unnecessary packages
    if to_uninstall:
        logger.info(f'to uninstall {to_uninstall}')
        uninstall_packages(to_uninstall, pip_command)
    else:
        logger.info("No unnecessary packages to uninstall.")


def parse_package_names(package_string):
    # Split the string by spaces
    packages = package_string.split()
    # Use regex to remove version specifications and the --no-deps flag
    return [re.split(r'[>=]', pkg)[0] for pkg in packages if not pkg.startswith('-') and not pkg.startswith('http')]


def build_reverse_map(dependency_map):
    reverse_map = {}
    for package, parents in dependency_map.items():
        for parent in parents:
            reverse_set = reverse_map.get(parent, set())
            reverse_set.add(package)
            reverse_map[parent] = reverse_set
    return reverse_map


def is_required_by(package, package_to_parents, to_install):
    visited = set()
    for to_i in to_install:
        if package in to_i:
            return True
    if package not in package_to_parents:
        return False
    if len(package_to_parents[package]) == 0:
        return False
    for parent in package_to_parents[package]:
        if parent in visited:
            continue
        visited.add(parent)
        if is_required_by(parent, package_to_parents, to_install):
            return True

# if __name__ == '__main__':
#     to_install = ['ok-script', 'pycaw', 'rapidocr-openvino', 'psutil', 'WMI', 'typing-extensions', 'numpy',
#                   'opencv-python', 'PySide6-Fluent-Widgets']
#     installed = ['six', 'nvidia-cufft-cu12', 'nvidia-cuda-runtime-cu12', 'charset-normalizer', 'nvidia-cusparse-cu12',
#                  'sniffio', 'rapidocr-openvino', 'gitdb', 'nvidia-cudnn-cu12', 'networkx', 'PySide6_Essentials',
#                  'PyYAML', 'nvidia-nvjitlink-cu12', 'openvino', 'smmap', 'nvidia-cublas-cu12', 'packaging', 'pywin32',
#                  'shapely', 'ok-script', 'GitPython', 'WMI', 'opencv-python', 'shiboken6', 'urllib3', 'pillow',
#                  'openvino-telemetry', 'comtypes', 'darkdetect', 'pycaw', 'opt-einsum', 'h11', 'nvidia-cusolver-cu12',
#                  'PySide6-Fluent-Widgets', 'nvidia-curand-cu12', 'astor', 'PySideSix-Frameless-Window', 'httpx',
#                  'pyclipper', 'protobuf', 'anyio', 'decorator', 'typing_extensions', 'numpy', 'idna', 'certifi',
#                  'nvidia-cuda-nvrtc-cu12', 'httpcore', 'psutil', 'requests']
#     dependency_map = get_package_dependencies(installed,
#                                               pip_command=[r'python\app_env\Scripts\python.exe', '-m', 'pip'])
#     # print(dependency_map)
#     package_to_parents = build_reverse_map(dependency_map)
#     print(package_to_parents)
#     to_uninstall = []
#     for installed_package in installed:
#         if not is_required_by(installed_package, package_to_parents, to_install):
#             to_uninstall.append(installed_package)
#     print(to_uninstall)
