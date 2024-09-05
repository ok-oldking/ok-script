import os
import subprocess

from ok.gui.launcher.python_env import find_line_in_requirements, delete_files, \
    create_venv
from ok.logging.Logger import config_logger, get_logger

logger = get_logger(__name__)

# python -m ok.gui.launcher.init_lenv
if __name__ == '__main__':
    config_logger()
    lenv_path = create_venv('launcher_env')
    try:
        lenv_python_exe = os.path.join(lenv_path, 'Scripts', 'python.exe')
        params = [lenv_python_exe, "-m", "pip", "install", "PySide6-Fluent-Widgets>=1.5.5", '--no-deps',
                  '--no-cache-dir']
        result = subprocess.run(params, check=True, capture_output=True, text=True)
        logger.info("install PySide6-Fluent-Widgets success")
        logger.info(result.stdout)

        params = [lenv_python_exe, "-m", "pip", "install", find_line_in_requirements('requirements.txt', 'ok-script'),
                  '--no-cache-dir']
        result = subprocess.run(params, check=True, capture_output=True, text=True)
        logger.info("install ok-script success")
        logger.info(result.stdout)
        delete_files()
    except subprocess.CalledProcessError as e:
        logger.error("An error occurred while creating the virtual environment.")
        logger.error(e.stderr)
