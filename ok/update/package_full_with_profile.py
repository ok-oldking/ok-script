import json
import os.path
import subprocess
import sys

from ok import config_logger, Logger
from ok import delete_if_exists
from ok.update.init_launcher_env import create_app_env

logger = Logger.get_logger(__name__)

if __name__ == "__main__":
    config_logger(name='build')
    try:
        # Get the folder path from the command line arguments
        tag = sys.argv[1]
        profile_index = int(sys.argv[2])
        logger.info(f'Tag: {tag} profile {profile_index}')

        build_dir = os.path.join(os.getcwd(), 'dist')
        repo_dir = os.path.join(build_dir, 'repo', tag)

        logger.info(f'Build directory: {repo_dir}')

        launcher_json = os.path.join(repo_dir, 'launcher.json')
        with open(launcher_json, 'r', encoding='utf-8') as file:
            launch_profiles = json.load(file)
            if not launch_profiles:
                logger.error('not launch profiles')
                sys.exit(1)

        profile = launch_profiles[profile_index]

        logger.info(f'package profile {profile_index} {profile}')

        delete_if_exists(os.path.join(build_dir, 'python', 'app_env'))

        launcher_config_json = os.path.join(build_dir, 'configs', 'launcher.json')

        with open(launcher_config_json, 'r', encoding='utf-8') as file:
            config = json.load(file)
            config['profile_index'] = profile_index

        with open(launcher_config_json, 'w', encoding='utf-8') as file:
            json.dump(config, file, ensure_ascii=False, indent=4)

        if not create_app_env(repo_dir, build_dir, profile['install_dependencies']):
            logger.error('not create app env')
            sys.exit(1)

        if profile['install_dependencies']:
            for dependency in profile['install_dependencies']:
                if "paddleocr" in dependency:
                    app_env_python_exe = os.path.join(build_dir, 'python', 'app_env', 'Scripts',
                                                      'python.exe')
                    logger.info('start download paddle ocr model')
                    subprocess.run([app_env_python_exe, "-m",
                                    "ok.ocr.download_paddle_model"], cwd=build_dir)
                    break

        logger.info(f'installed profile: {profile_index} {profile}')

    except Exception as e:
        logger.info(f'Error: {e}')
        sys.exit(1)
