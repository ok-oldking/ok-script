import os
import re
import sys

from ok.update.copy_ok_folder import find_and_copy_site_package, get_file_in_path_or_cwd
from ok.util.logger import Logger

logger = Logger.get_logger(__name__)

INLINED_REQUIREMENTS = {
    'ok-script': 'ok',
    'pyappify': 'pyappify',
}


def _read_deploy_entries(repo_dir):
    deploy_file = os.path.join(repo_dir, 'deploy.txt')
    if not os.path.exists(deploy_file):
        return []

    with open(deploy_file, 'r', encoding='utf-8') as file:
        return [
            line.strip().replace('\\', '/').strip('/')
            for line in file
            if line.strip() and not line.lstrip().startswith('#')
        ]


def _deploy_includes_folder(deploy_entries, folder):
    folder = folder.replace('\\', '/').strip('/')
    return any(entry == folder or entry.startswith(f'{folder}/') for entry in deploy_entries)


def _get_inlined_requirement_folders(repo_dir):
    deploy_entries = _read_deploy_entries(repo_dir)
    if not deploy_entries:
        return []
    return [
        package_folder
        for package_folder in INLINED_REQUIREMENTS.values()
        if _deploy_includes_folder(deploy_entries, package_folder)
    ]


def inline_site_packages(repo_dir, package_folders=None):
    if package_folders is None:
        package_folders = INLINED_REQUIREMENTS.values()

    for package_folder in package_folders:
        if os.path.exists(os.path.join(repo_dir, package_folder)):
            logger.info(f'{package_folder} is bundled with source code, skip downloading')
            continue
        exit_code = find_and_copy_site_package(package_folder, repo_dir)
        if exit_code != 0:
            raise RuntimeError(f'Failed to inline {package_folder} from site-packages')


def remove_ok_requirements(repo_dir, tag):
    package_folders = _get_inlined_requirement_folders(repo_dir)
    inline_site_packages(repo_dir, package_folders)

    config_file = get_file_in_path_or_cwd(repo_dir, 'config.py')
    with open(config_file, 'r', encoding='utf-8') as file:
        content = file.read()
    new_content = re.sub(r'version = ".+"', f'version = "{tag}"', content)
    with open(config_file, 'w', encoding='utf-8') as file:
        file.write(new_content)

    file_path = os.path.join(repo_dir, 'requirements.txt')
    with open(file_path, 'r', encoding='utf-8') as file:
        lines = file.readlines()
    inlined_packages = [
        package_name
        for package_name, package_folder in INLINED_REQUIREMENTS.items()
        if package_folder in package_folders
    ]
    if inlined_packages:
        requirement_pattern = r'^\s*({})\b'.format('|'.join(re.escape(name) for name in inlined_packages))
        filtered_lines = [line for line in lines if not re.match(requirement_pattern, line, re.IGNORECASE)]
    else:
        filtered_lines = lines
    with open(file_path, 'w', encoding='utf-8') as file:
        file.writelines(filtered_lines)

if __name__ == "__main__":
    if '--tag' in sys.argv:
        try:
            tag_index = sys.argv.index('--tag') + 1
            if tag_index < len(sys.argv) and not sys.argv[tag_index].startswith('--'):
                tag_name_arg = sys.argv[tag_index]
            else:
                print("Error: --tag option requires a value.")
                sys.exit(1)
        except ValueError:
            print("Error: --tag option used incorrectly.")
            sys.exit(1)
        if tag_name_arg:  # If --tag was provided and parsed
            print('remove ok_requirements from tag {} cwd {}'.format(tag_name_arg, os.getcwd()))
            remove_ok_requirements(os.getcwd(), tag_name_arg)
    else:
        inline_site_packages(os.getcwd())
