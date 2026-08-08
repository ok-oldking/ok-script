import argparse
import os
import re

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


def _get_inlined_requirement_folders(repo_dir, inlined_requirements=None):
    if inlined_requirements is None:
        inlined_requirements = INLINED_REQUIREMENTS
    deploy_entries = _read_deploy_entries(repo_dir)
    if not deploy_entries:
        return []
    return [
        package_folder
        for package_folder in inlined_requirements.values()
        if _deploy_includes_folder(deploy_entries, package_folder)
    ]


def _add_folders_to_deploy(repo_dir, folders):
    deploy_file = os.path.join(repo_dir, 'deploy.txt')
    deploy_entries = _read_deploy_entries(repo_dir)
    missing_folders = []
    for folder in folders:
        normalized_folder = folder.replace('\\', '/').strip('/')
        if (
            normalized_folder not in missing_folders
            and not _deploy_includes_folder(deploy_entries, normalized_folder)
        ):
            missing_folders.append(normalized_folder)
    if not missing_folders:
        return

    existing_content = ''
    if os.path.exists(deploy_file):
        with open(deploy_file, 'r', encoding='utf-8') as file:
            existing_content = file.read()
    with open(deploy_file, 'a', encoding='utf-8') as file:
        if existing_content and not existing_content.endswith(('\n', '\r')):
            file.write('\n')
        file.writelines(f'{folder}\n' for folder in missing_folders)


def _parse_inlined_requirement(value):
    package_name, separator, package_folder = value.partition('=')
    package_name = package_name.strip()
    package_folder = package_folder.strip().replace('\\', '/').strip('/')
    if not separator or not package_name or not package_folder:
        raise argparse.ArgumentTypeError(
            f"invalid inlined requirement '{value}'; expected PACKAGE=FOLDER"
        )
    return package_name, package_folder


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


def remove_ok_requirements(repo_dir, tag, additional_inlined_requirements=None):
    inlined_requirements = dict(INLINED_REQUIREMENTS)
    if additional_inlined_requirements:
        inlined_requirements.update(additional_inlined_requirements)
        _add_folders_to_deploy(repo_dir, additional_inlined_requirements.values())

    package_folders = _get_inlined_requirement_folders(repo_dir, inlined_requirements)
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
        for package_name, package_folder in inlined_requirements.items()
        if package_folder in package_folders
    ]
    if inlined_packages:
        requirement_pattern = r'^\s*({})\b'.format('|'.join(re.escape(name) for name in inlined_packages))
        filtered_lines = [line for line in lines if not re.match(requirement_pattern, line, re.IGNORECASE)]
    else:
        filtered_lines = lines
    with open(file_path, 'w', encoding='utf-8') as file:
        file.writelines(filtered_lines)

def main(argv=None):
    parser = argparse.ArgumentParser(description='Inline deployment requirements.')
    parser.add_argument('--tag', help='Set the application version and remove inlined packages from requirements.txt.')
    parser.add_argument(
        '--add-inlined-requirement',
        action='append',
        default=[],
        metavar='PACKAGE=FOLDER',
        type=_parse_inlined_requirement,
        help='Add an inlined package mapping. Repeat this option to add multiple packages.',
    )
    args = parser.parse_args(argv)
    additional_inlined_requirements = dict(args.add_inlined_requirement)
    repo_dir = os.getcwd()

    if args.tag:
        print(f'remove ok_requirements from tag {args.tag} cwd {repo_dir}')
        remove_ok_requirements(repo_dir, args.tag, additional_inlined_requirements)
    else:
        inlined_requirements = dict(INLINED_REQUIREMENTS)
        inlined_requirements.update(additional_inlined_requirements)
        _add_folders_to_deploy(repo_dir, additional_inlined_requirements.values())
        inline_site_packages(repo_dir, inlined_requirements.values())


if __name__ == "__main__":
    main()
