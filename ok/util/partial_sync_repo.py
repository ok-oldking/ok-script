# index.py
import os
import sys
import shutil
import subprocess
import uuid
import argparse

def set_output(name, value):
    output_file = os.environ.get('GITHUB_OUTPUT')
    if output_file:
        with open(output_file, 'a', encoding='utf-8') as f:
            if '\n' in value:
                delimiter = uuid.uuid4().hex
                f.write(f"{name}<<{delimiter}\n{value}\n{delimiter}\n")
            else:
                f.write(f"{name}={value}\n")
    else:
        print(f"::set-output name={name}::{value}")

def run_command(command, ignore_return_code=False, silent=False):
    result = subprocess.run(command, shell=True, capture_output=True, text=True, encoding='utf-8')
    if result.returncode != 0 and not ignore_return_code:
        raise Exception(f'Command "{command}" failed with exit code {result.returncode}:\n{result.stderr}')
    return {"stdout": result.stdout.strip(), "stderr": result.stderr.strip()}

def generate_changes_message(source_repo_path, target_repo_path, current_tag, show_author):
    print('Generating changes for commit message...')
    
    os.chdir(target_repo_path)
    latest_target_tag = run_command('git describe --tags --abbrev=0', ignore_return_code=True, silent=True)['stdout']
    os.chdir(source_repo_path)

    start_tag = ''
    messages = ''

    if latest_target_tag:
        tag_exists_in_source = run_command(f'git tag --list {latest_target_tag}')['stdout']
        if tag_exists_in_source.strip() == latest_target_tag:
            print(f'Found latest target tag "{latest_target_tag}" in source. Creating log from that tag.')
            start_tag = latest_target_tag
            tag_range = f"{start_tag}..{current_tag}"
            log_format = '--pretty=format:"%s (%an)"' if show_author else '--pretty=format:"%s"'
            messages = run_command(f'git log --no-merges {log_format} {tag_range}', ignore_return_code=True)['stdout']

    if not messages:
        print('Could not find a common tag or no new commits in range. Using latest commit message.')
        messages = run_command(f'git log -1 --pretty=%s {current_tag}')['stdout']
        return {'messages': messages, 'start_tag': ''}

    unique_lines = list(dict.fromkeys(messages.split('\n')))
    messages = '\n'.join(unique_lines).replace('"', '')

    return {'messages': messages, 'start_tag': start_tag}

def run():
    parser = argparse.ArgumentParser()
    parser.add_argument('--repos', nargs='+', required=True)
    parser.add_argument('--sync_list', required=True)
    parser.add_argument('--tag', required=True)
    parser.add_argument('--gitignore_file', default='')
    parser.add_argument('--show_author', action='store_true')

    try:
        args = parser.parse_args()
        repo_urls = args.repos
        sync_list_file = args.sync_list
        current_tag = args.tag
        gitignore_file = args.gitignore_file
        show_author = args.show_author

        print('Applying Git network configurations to fix Schannel errors...')
        try:
            run_command('git config --global http.sslBackend openssl')
            run_command('git config --global http.version HTTP/1.1')
            run_command('git config --global http.postBuffer 524288000')
        except Exception as config_error:
            print(f"::warning::Warning: Failed to apply some Git network configs: {config_error}")

        set_output('end_tag', current_tag)
        set_output('start_tag', '')

        source_repo_path = os.getcwd()
        sync_list_path = os.path.join(source_repo_path, sync_list_file)

        if not os.path.exists(sync_list_path):
            raise Exception(f"Sync list file not found at: {sync_list_path}")
            
        with open(sync_list_path, 'r', encoding='utf-8') as f:
            files_to_sync = [line.strip() for line in f.readlines() if line.strip() != '']

        print(f"Source Repo Path: {source_repo_path}")
        print(f"Syncing tag: {current_tag}")
        print(f"Files to sync: {', '.join(files_to_sync)}")

        os.chdir(source_repo_path)
        source_commit = run_command(f"git rev-list -n 1 {current_tag}")['stdout']
        source_tags_raw = run_command('git tag')['stdout']
        source_tags = set(filter(None, source_tags_raw.split('\n')))
        special_tags_raw = run_command(f"git tag --points-at {source_commit}")['stdout']
        special_tags = [t for t in special_tags_raw.split('\n') if t and t != current_tag]

        for repo_url in repo_urls:
            repo_name = os.path.splitext(os.path.basename(repo_url))[0]
            target_repo_path = os.path.abspath(os.path.join(source_repo_path, '..', f"target_{repo_name}"))

            print(f"\n--- Processing repository: {repo_url} ---")

            if os.path.exists(target_repo_path):
                shutil.rmtree(target_repo_path)

            run_command(f"git clone {repo_url} {target_repo_path}")

            changes_data = generate_changes_message(source_repo_path, target_repo_path, current_tag, show_author)
            changes = changes_data['messages']
            start_tag = changes_data['start_tag']
            
            changes_with_asterisk = '\n'.join([f"* {line}" for line in changes.split('\n') if line])
            set_output('changes', changes)
            set_output('changes_with_asterisk', changes_with_asterisk)
            set_output('start_tag', start_tag)
            
            os.chdir(target_repo_path)
            print('Syncing files...')
            
            for item in files_to_sync:
                src_path = os.path.join(source_repo_path, item)
                dest_path = os.path.join(target_repo_path, item)

                if os.path.exists(src_path):
                    if os.path.isdir(src_path):
                        if os.path.exists(dest_path):
                            shutil.rmtree(dest_path)
                        shutil.copytree(src_path, dest_path)
                    else:
                        if os.path.exists(dest_path):
                            os.remove(dest_path)
                        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                        shutil.copy2(src_path, dest_path)
                else:
                    print(f"Source item '{item}' not found, ensuring it's removed from target.")
                    if os.path.exists(dest_path):
                        if os.path.isdir(dest_path):
                            shutil.rmtree(dest_path)
                        else:
                            os.remove(dest_path)

            if gitignore_file:
                gitignore_source_path = os.path.join(source_repo_path, gitignore_file)
                if os.path.exists(gitignore_source_path):
                    gitignore_dest_path = os.path.join(target_repo_path, '.gitignore')
                    print(f"Copying {gitignore_file} to {gitignore_dest_path}")
                    shutil.copy2(gitignore_source_path, gitignore_dest_path)
                else:
                    print(f"::warning::Optional gitignore_file '{gitignore_file}' not found. Skipping.")

            commit_msg_path = os.path.abspath('.commit_msg')
            with open(commit_msg_path, 'w', encoding='utf-8') as f:
                f.write(changes)

            run_command('git add .')
            commit_result = run_command(f'git commit -F "{commit_msg_path}"', ignore_return_code=True)
            
            if 'nothing to commit' in commit_result['stdout'] or 'nothing to commit' in commit_result['stderr']:
                print('No file changes to commit.')
                if os.path.exists(commit_msg_path):
                    os.remove(commit_msg_path)
                os.chdir(source_repo_path)
                continue
            else:
                print('Changes committed.')

            print('Synchronizing tags...')
            target_tags_raw = run_command('git tag')['stdout']
            target_tags = set(filter(None, target_tags_raw.split('\n')))

            for tag in target_tags:
                if tag not in source_tags:
                    print(f'Deleting tag "{tag}" from target repo as it does not exist in source.')
                    run_command(f'git push origin --delete {tag}', ignore_return_code=True)

            print(f'Applying current version tag: {current_tag}')
            run_command(f'git tag -af {current_tag} -F "{commit_msg_path}"')

            if special_tags:
                print(f"Applying special tags: {', '.join(special_tags)}")
                for tag in special_tags:
                    run_command(f'git tag -f {tag} {current_tag}')

            main_branch = run_command('git rev-parse --abbrev-ref HEAD')['stdout']
            print(f'Pushing branch "{main_branch}" and all tags...')
            run_command(f'git push origin {main_branch} --force')
            run_command('git push origin --tags --force')

            if os.path.exists(commit_msg_path):
                os.remove(commit_msg_path)

            os.chdir(source_repo_path)

        print('\nOperation completed successfully for all repositories.')

    except Exception as error:
        print(f"::error::{str(error)}")
        sys.exit(1)

if __name__ == '__main__':
    run()