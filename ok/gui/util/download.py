import math
import os
import shutil
from typing import Callable, Optional

import requests

from ok import Logger
from ok.gui.util.Alert import alert_info

logger = Logger.get_logger(__name__)


def download_models(my_models):
    to_download = []
    for model in my_models:
        local_path = model['local_path']
        if not os.path.exists(local_path):
            to_download.append((model['url'], local_path))
    if not to_download:
        return
    if to_download_len := len(to_download):
        alert_info(f'Need to Download {to_download_len} models', True)
        for i in range(to_download_len):
            url, path = to_download[i]
            logger.info(f'Downloading {i + 1}/{len(to_download)} to {path}')
            alert_info(f'Downloading Model {i + 1}/{len(to_download)} to {path}')
            download_file_with_progress(url, path)


def get_size_of_file(file_path):
    try:
        file_size = os.path.getsize(file_path)
        logger.debug(f"Size of {file_path}: {file_size} bytes")
        return file_size
    except FileNotFoundError:
        logger.error(f"Error: File not found at {file_path}")
    except OSError as e:
        logger.error(f"Error accessing file: {e}")
    return 0


def format_size(size_bytes: int) -> str:
    """Converts a size in bytes to a human-readable string (KB, MB, GB)."""
    if size_bytes == 0:
        return "0B"
    size_name = ("B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB")
    i = int(math.floor(math.log(size_bytes, 1024))) if size_bytes > 0 else 0
    p = math.pow(1024, i)
    s = round(size_bytes / p, 2)
    return f"{s} {size_name[i]}"


def download_file_with_progress(
        url: str,
        save_path: str,
        callback: Optional[Callable[[float, str], None]] = None,
        chunk_size: int = 8192,
        temp_suffix: str = ".part"
) -> None:
    """
    Downloads a file from a URL, saving it to a temporary location first,
    and then moving it to the final save_path upon successful completion.
    Reports progress via an optional callback.
    Args:
        url: The URL of the file to download.
        save_path: The final local path where the file will be saved.
        callback: An optional function to call during download.
                  It receives:
                      - percentage (float): Download progress (0.0 to 100.0).
                      - downloaded_str (str): Human-readable downloaded size.
        chunk_size: The size of chunks to download in bytes.
        temp_suffix: Suffix to append to the filename while downloading.
    """
    temp_file_path = f"{save_path}{temp_suffix}"
    downloaded_size = 0
    total_size_in_bytes = 0
    resume_header = {}
    # --- Ensure target directory exists ---
    try:
        save_dir = os.path.dirname(save_path)
        if save_dir:  # Only create if save_path includes a directory
            os.makedirs(save_dir, exist_ok=True)
    except OSError as e:
        logger.error(f"Error creating directory {save_dir}: {e}")
        raise
    # --- Check if temp file exists to potentially resume ---
    # Note: Resuming requires server support for Range requests.
    # This adds complexity, so keeping it simple for now: always overwrite temp.
    # If resume is needed, add logic here to check temp_file_path size and set
    # 'Range' header in resume_header. For now, we ensure clean state.
    if os.path.exists(temp_file_path):
        logger.error(f"Warning: Temporary file {temp_file_path} already exists. Overwriting.")
        try:
            os.remove(temp_file_path)
        except OSError as e:
            logger.error(f"Error removing existing temp file {temp_file_path}: {e}")
            raise  # Fail fast if we can't ensure clean state
    try:
        # --- Start Download ---
        response = requests.get(url, stream=True, timeout=300, headers=resume_header)
        response.raise_for_status()
        total_size_in_bytes = int(response.headers.get('content-length', 0))
        with open(temp_file_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=chunk_size):
                if chunk:  # filter out keep-alive new chunks
                    chunk_len = len(chunk)
                    downloaded_size += chunk_len
                    f.write(chunk)
                    if callback:
                        percentage = 0.0
                        if total_size_in_bytes > 0:
                            percentage = (downloaded_size / total_size_in_bytes) * 100
                        percentage = min(percentage, 100.0)  # Cap at 100%
                        downloaded_str = format_size(downloaded_size)
                        try:
                            callback(percentage, downloaded_str)
                        except Exception as cb_err:
                            print(f"\nWarning: Callback function failed: {cb_err}")  # Start on new line
        # --- Download Complete - Move File ---
        logger.info(f"\nDownload finished. Moving {temp_file_path} to {save_path}")  # Start on new line
        shutil.move(temp_file_path, save_path)
        # --- Final Callback after successful move ---
        if callback:
            final_size_str = format_size(downloaded_size)
            try:
                # Ensure 100% is reported, especially if total_size was unknown
                callback(100.0, final_size_str)
            except Exception as cb_err:
                print(f"\nWarning: Final callback function failed: {cb_err}")
    except (requests.exceptions.RequestException, IOError, OSError, Exception) as e:
        logger.error(f"\nError during download or move: {e}")
        # --- Cleanup Failed/Partial Download ---
        if os.path.exists(temp_file_path):
            try:
                logger.error(f"Cleaning up temporary file: {temp_file_path}")
                os.remove(temp_file_path)
            except OSError as rm_err:
                logger.error(f"Warning: Could not remove temporary file {temp_file_path}: {rm_err}")
        # Re-raise the original error after attempting cleanup
        raise
