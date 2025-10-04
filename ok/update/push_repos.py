import sys
import os
import shutil
import stat
import subprocess
import shlex  # Added for safer command construction if needed, though not used in final simple tag messages

from ok.update.GitUpdater import remove_ok_requirements


# Updated run_command to handle allowed failures
def run_command(command, allow_fail=False, suppress_output=False):
    if not suppress_output:
        print(f'Running command: {command}')
    # Using a list for command is safer if not using shell=True, but current script uses shell=True extensively.
    # For shell=True, command is a string.
    result = subprocess.run(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                            encoding='utf-8')
    try:
        if result.returncode != 0:
            stderr_output = result.stderr.strip() if result.stderr else ""
            stdout_output = result.stdout.strip() if result.stdout else ""
            error_message = f"Command '{command}' failed with error code {result.returncode}:\nSTDERR: {stderr_output}\nSTDOUT: {stdout_output}"
            if not suppress_output or not allow_fail:  # Print warning unless fully suppressed and allowed to fail
                print(f"Warning: {error_message}")
            if not allow_fail:
                raise Exception(error_message)
        return result.stdout.strip() if result.stdout else ""
    except Exception as e:
        if not suppress_output or not allow_fail:
            print(f"Warning: Command '{command}' failed with exception:\n{e}")
        if not allow_fail:
            raise  # Re-raise the caught exception if not allowed to fail
        return ""


def on_rm_error(func, path, exc_info):
    # Handle read-only files, common on Windows
    os.chmod(path, stat.S_IWRITE)
    func(path)


def get_current_branch():
    return run_command("git rev-parse --abbrev-ref HEAD")


def get_latest_commit_message():
    # Get just the subject line for simplicity in tag messages
    return run_command("git log -1 --pretty=%s").strip()


def tag_exists_locally(tag_name, local_tags_set):
    # Check against a pre-fetched set of local tags for efficiency
    return tag_name in local_tags_set

def main():
    if '--repos' not in sys.argv or '--files' not in sys.argv:
        print("Usage: python update_repos.py --repos repo1 repo2 ... --files file1 file2 ...")
        sys.exit(1)

    # Assuming --tag is optional for this specific change, but keeping if used elsewhere
    tag_name_arg = None
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
        repos_index = sys.argv.index('--repos') + 1
        files_index = sys.argv.index('--files') + 1
        # Adjust slicing if --tag is not last
        # This part of arg parsing might need to be more robust if arg order can vary
        repo_urls = sys.argv[repos_index:sys.argv.index('--files')]
        files_filename = sys.argv[sys.argv.index('--files') + 1:sys.argv.index('--tag')]
    else:  # Original parsing if --tag is mandatory or for other structures
        repos_index = sys.argv.index('--repos') + 1
        files_index = sys.argv.index('--files') + 1
        # Check if --tag is the next argument or something else
        end_files_index = len(sys.argv)
        # This simplified parsing assumes fixed order or specific terminators
        # For robust parsing, consider argparse module
        if '--tag' in sys.argv:
            end_files_index = sys.argv.index('--tag')

        repo_urls = sys.argv[repos_index:files_index - 1]  # Original
        files_filename = sys.argv[files_index:end_files_index]  # Adjusted
        if tag_name_arg:
            print(f"Tag from args: {tag_name_arg}")

    # Simplified example assuming files_filename is a single file path string
    if isinstance(files_filename, list):
        if not files_filename:
            print("Error: No file specified for --files.")
            sys.exit(1)
        files_filename = files_filename[0]  # Take the first element if it's a list

    print(f"Repositories: {repo_urls}")
    print(f"Files list file: {files_filename}")

    try:
        with open(files_filename, 'r') as file:
            files_to_copy = [line.strip() for line in file.readlines() if line.strip()]
    except FileNotFoundError:
        print(f"Error: File '{files_filename}' not found.")
        sys.exit(1)

    if not repo_urls or not files_to_copy:
        print("Both repository URLs and files must be specified.")
        sys.exit(1)

    source_repo_path = os.getcwd()
    for item in files_to_copy:
        if not os.path.exists(os.path.join(source_repo_path, item)):
            print(f"Error: {item} does not exist in the source directory '{source_repo_path}'.")
            sys.exit(1)

    parent_dir = os.path.abspath(os.path.join(source_repo_path, os.pardir))

    # Get information from the source repository BEFORE looping
    os.chdir(source_repo_path)
    latest_commit_message_subject = get_latest_commit_message()  # Gets subject line
    all_tags_in_source_repo = set(t for t in run_command("git tag", suppress_output=True).split('\n') if t)
    print(f"All tags in source repo ({source_repo_path}): {all_tags_in_source_repo}")
    current_branch_in_source = get_current_branch()
    tags_at_head_in_source_repo = set(
        t for t in run_command("git tag --points-at HEAD", suppress_output=True).split('\n') if t)
    print(f"Tags at HEAD in source repo ({source_repo_path}): {tags_at_head_in_source_repo}")

    for index, repo_url in enumerate(repo_urls):
        repo_name = f"repo_{index}_{os.path.basename(repo_url).replace('.git', '')}"
        target_repo_path = os.path.join(parent_dir, repo_name)

        print(f"\nProcessing target repository: {repo_url} into {target_repo_path}")

        if os.path.exists(target_repo_path):
            print(f"Removing existing target directory: {target_repo_path}")
            shutil.rmtree(target_repo_path, onerror=on_rm_error)

        print(f"Cloning {repo_url} into {target_repo_path}...")
        run_command(f"git clone {repo_url} {target_repo_path}")
        os.chdir(target_repo_path)

        print(f"Current branch in target repo: {current_branch_in_source}")

        # Delete files/folders in target that are not in source_repo_path's files_to_copy list (more precise)
        # This part of original logic for deleting files needs care.
        # The original logic was: delete if not in os.path.join(cwd, item) - cwd was source_repo_path
        # This means if a file exists in target but not in source AT ALL (not just not in files_to_copy), it's deleted.
        print("Synchronizing files/folders...")
        target_items = [item for item in os.listdir(target_repo_path) if item not in ('.git', '.gitignore')]
        for item_in_target in target_items:
            source_item_path = os.path.join(source_repo_path, item_in_target)
            if not os.path.exists(source_item_path):  # If item from target doesn't exist at all in source root
                print(f"Removing '{item_in_target}' from target as it's not in source root.")
                # Git rm is better than os.remove/shutil.rmtree for repo contents
                run_command(f"git rm -rf --ignore-unmatch {shlex.quote(item_in_target)}")
            # If item *does* exist in source root, but is NOT in files_to_copy, should it be deleted?
            # Current logic: if it exists in source root, it's kept, then overwritten if in files_to_copy.
            # If it exists in source root but not in files_to_copy, it's kept as is from clone.
            # This might be desired. If precise sync of ONLY files_to_copy is needed, logic is more complex.

        # Copy specified files and folders
        for item_to_copy in files_to_copy:
            src_path = os.path.join(source_repo_path, item_to_copy)
            dest_path = os.path.join(target_repo_path, item_to_copy)

            # Remove existing destination if it's of a different type (file/dir) or to ensure clean copy
            if os.path.lexists(dest_path):  # lexists to handle symlinks correctly if they were copied
                if os.path.isdir(dest_path) and not os.path.islink(dest_path):
                    shutil.rmtree(dest_path, onerror=on_rm_error)
                else:
                    os.remove(dest_path)

            print(f"Copying '{src_path}' to '{dest_path}'")
            if os.path.isdir(src_path):
                shutil.copytree(src_path, dest_path, dirs_exist_ok=True)
            else:
                os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                shutil.copy2(src_path, dest_path)

        if tag_name_arg:  # If --tag was provided and parsed
            remove_ok_requirements(target_repo_path, tag_name_arg)

        print("Adding changes to git index...")
        run_command("git add .")

        print("Committing changes...")
        # Use allow_fail=True if it's possible no changes were made.
        commit_output = run_command(f'git commit -m "{latest_commit_message_subject}"', allow_fail=True)
        if "nothing to commit, working tree clean" in commit_output or \
                (
                        not commit_output and "failed with error code 1" in commit_output and "nothing to commit" in commit_output):  # check for failure message too
            print("No changes to commit.")
        else:
            print(f"Commit successful. Pushing branch {current_branch_in_source}...")
            run_command(f"git push origin {current_branch_in_source} --force")

        # --- TAG SYNCHRONIZATION LOGIC ---
        print("\nSynchronizing tags...")
        # 1. Get remote tags from the target repository
        target_repo_remote_tags_output = run_command("git ls-remote --tags origin", suppress_output=True)
        target_repo_remote_tags = set()
        if target_repo_remote_tags_output:
            for line in target_repo_remote_tags_output.split('\n'):
                if line:
                    parts = line.split('\t')
                    if len(parts) == 2 and parts[1].startswith('refs/tags/'):
                        tag_name_full = parts[1][len('refs/tags/'):]
                        tag_name = tag_name_full.replace('^{}', '')  # Handle annotated tag pointers
                        target_repo_remote_tags.add(tag_name)

        print(f"Target repo remote tags before cleanup: {target_repo_remote_tags}")

        # 2. Identify and delete tags from target remote that are NOT in all_tags_in_source_repo
        tags_to_delete_on_remote = target_repo_remote_tags - all_tags_in_source_repo
        if tags_to_delete_on_remote:
            print(f"Tags to delete from target remote: {tags_to_delete_on_remote}")
            for tag_to_delete in tags_to_delete_on_remote:
                print(f"Deleting tag '{tag_to_delete}' from target remote...")
                run_command(f"git push origin --delete {shlex.quote(tag_to_delete)}",
                            allow_fail=True)  # Allow fail if tag doesn't exist or already deleted
        else:
            print("No extraneous tags found on target remote.")

        # 3. Clean up local tags in the target clone.
        #    Keep only those that are part of tags_at_head_in_source_repo (they will be re-created).
        #    This prevents pushing unwanted/dangling old tags from the clone.
        current_local_tags_in_target_clone = set(
            t for t in run_command("git tag", suppress_output=True).split('\n') if t)
        for local_tag in current_local_tags_in_target_clone:
            if local_tag not in tags_at_head_in_source_repo:
                print(f"Deleting local tag '{local_tag}' from target clone (not a source HEAD tag).")
                run_command(f"git tag -d {shlex.quote(local_tag)}", allow_fail=True)

        # 4. Re-create/update tags from source HEAD on the new commit in target repo
        if tags_at_head_in_source_repo:
            print(f"Creating/updating source HEAD tags in target repo: {tags_at_head_in_source_repo}")
            for tag_name in tags_at_head_in_source_repo:
                # Delete locally first (if it survived the cleanup or to change type e.g. lightweight to annotated)
                run_command(f"git tag -d {shlex.quote(tag_name)}", allow_fail=True, suppress_output=True)
                # Create as an annotated tag
                tag_message = f"Release {tag_name} (commit: {latest_commit_message_subject})"
                run_command(
                    f'git tag -a {shlex.quote(tag_name)} -m "{tag_message.replace("\"", "\\\"")}"')  # Basic quote escaping for message
                print(f"Locally created/updated tag '{tag_name}' in target repo.")
        else:
            print("No tags at HEAD in source repo to apply to target repo.")

        # 5. Push all current local tags (now should only be tags_at_head_in_source_repo)
        # Using --force to update tags if they exist, matching behavior of branch push.
        if tags_at_head_in_source_repo:  # Only push if there are tags to push
            print("Pushing synchronized tags to target remote...")
            run_command(f"git push origin --tags --force")
        else:
            # If there were no source HEAD tags, we might want to ensure no tags are on remote
            # if the goal is strict mirroring of source HEAD tags *only*.
            # Current logic: extraneous tags deleted, no new tags pushed if source_head_tags is empty.
            # This means old tags (part of all_source_tags but not head_tags) might remain on remote.
            # If strict "only head tags" desired: tags_to_delete_on_remote should be target_repo_remote_tags - tags_at_head_in_source_repo
            print("No source HEAD tags to push.")

        # (Original remove_history_before_tag logic was here, can be re-added if needed)
        # if tag_name_arg and tag_name_arg == 'lts': # Example condition
        #    remove_history_before_tag('lts') # Ensure this function is robust

        os.chdir(source_repo_path)  # Change back to source repo path before next iteration

    print("\nOperation completed successfully for all repositories.")


if __name__ == "__main__":
    # Example of how remove_history_before_tag and tag_exists could be defined if not imported
    def remove_history_before_tag(tag_name_to_remove_before):
        print(f"Attempting to remove history before tag: {tag_name_to_remove_before}")
        # Need to get local tags in current context (target repo clone)
        local_tags = set(t for t in run_command("git tag", suppress_output=True).split('\n') if t)
        if tag_name_to_remove_before in local_tags:
            print(f"Tag {tag_name_to_remove_before} exists locally. Proceeding with history removal (stubbed).")
            # Complex git operations for history removal would go here.
            # e.g. run_command(f"git checkout {tag_name_to_remove_before}")
            #      run_command(f"git checkout -b new-main") # or current branch name
            #      run_command(f"git branch -M new-main main") # or current branch name
            #      run_command(f"git push --force origin main") # or current branch name
        else:
            print(f"Tag {tag_name_to_remove_before} does not exist locally. Skipping history removal.")


    main()