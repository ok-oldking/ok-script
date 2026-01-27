import os
import re
import sys

from ok.update.copy_ok_folder import find_and_copy_site_package, get_file_in_path_or_cwd
from ok.util.logger import Logger

logger = Logger.get_logger(__name__)


def remove_ok_requirements(repo_dir, tag):
    config_file = get_file_in_path_or_cwd(repo_dir, 'config.py')
    with open(config_file, 'r', encoding='utf-8') as file:
        content = file.read()
    new_content = re.sub(r'version = ".+"', f'version = "{tag}"', content)
    with open(config_file, 'w', encoding='utf-8') as file:
        file.write(new_content)

    if os.path.exists(os.path.join(repo_dir, 'ok')):
        logger.info('ok-script is bundled with source code, skip downloading')
    file_path = os.path.join(repo_dir, 'requirements.txt')
    with open(file_path, 'r', encoding='utf-8') as file:
        lines = file.readlines()
    filtered_lines = [line for line in lines if 'ok-script' not in line]
    with open(file_path, 'w', encoding='utf-8') as file:
        file.writelines(filtered_lines)

if __name__ == "__main__":
    find_and_copy_site_package()
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
