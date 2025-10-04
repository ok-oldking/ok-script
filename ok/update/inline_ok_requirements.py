import os
import sys

from ok.update.GitUpdater import remove_ok_requirements
from ok.update.copy_ok_folder import find_and_copy_site_package

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
