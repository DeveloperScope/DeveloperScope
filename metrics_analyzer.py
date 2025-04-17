import os
from collections import defaultdict
import time

from pathlib import Path
import re

import git
from pydriller import Repository


TARGET_REPO = "devscope/devQ_testData_PythonProject"
current_repo_path = Path().resolve()

repo_path = current_repo_path.parent / TARGET_REPO


def extract_username(email: str) -> str:
    email = email.lower()

    # Case: GitHub no-reply with user ID + username
    match = re.match(r"^\d+\+([^@]+)@users\.noreply\.github\.com$", email)
    if match:
        return match.group(1)

    # Case: standard GitHub no-reply (old format)
    match = re.match(r"^([^@]+)@users\.noreply\.github\.com$", email)
    if match:
        return match.group(1)

    # Fallback: use the local part of the email
    return email.split("@")[0]


def get_all_branches(repo_path: str):
    git_repo = git.Repo(str(repo_path))

    return git_repo.branches


def get_merge_commits_map(repo_path: str):
    merge_commts_map: dict[str, list[str]] = defaultdict(list)
    author_mapping = defaultdict(set)

    for branch in get_all_branches(repo_path):
        repo = Repository(str(repo_path), only_in_branch=branch.name)

        for commit in repo.traverse_commits():
            if not commit.msg.startswith('Merge'):
                continue

            # print(commit.msg.__repr__())
            username = extract_username(commit.author.email)

            author_mapping[username].add(
                (commit.author.email, commit.author.name))

            merge_commts_map[username].append(commit.hash)

    return merge_commts_map, author_mapping


def get_difference(merge_commit: git.Commit) -> str:
    if len(merge_commit.parents) != 2:
        raise ValueError("Only 2 parents allowed for merge request commits")

    first_parent = merge_commit.parents[0]
    diff_index = first_parent.diff(merge_commit, create_patch=True)

    difference = merge_commit.message + '\n\n'
    for diff in diff_index:
        diff_text = diff.diff.decode('utf-8')
        file_header = f"==== File: {diff.a_path or diff.b_path} ====\n"
        difference += file_header + diff_text + "\n\n"

    return difference


def get_current_state(commit: git.Commit):
    file_chunks = []

    for blob in commit.tree.traverse():
        if blob.type == 'blob':  # it's a file
            file_path = blob.path
            file_content = blob.data_stream.read().decode('utf-8', errors='replace')
            print(file_path)
            formatted = f"### FILE: `{file_path}`\n\n```\n{file_content}\n```\n"
            file_chunks.append(formatted)
            print(file_chunks)
            time.sleep(3)

    # Join all file contents into a single string
    final_string = "\n\n".join(file_chunks)
    return final_string


def is_python_file(filepath: str) -> bool:
    """Check if file is a Python file by extension or shebang."""
    if filepath.endswith('.py'):
        return True

    # For files without extension but with Python shebang
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            first_line = f.readline()
            return first_line.startswith('#!/') and 'python' in first_line.lower()
    except:
        return False


def extract_python_code_from_chunk(chunk: str) -> str:
    """Extract the code between the triple backticks in a chunk."""
    lines = chunk.split('\n')
    in_code_block = False
    code_lines = []

    for line in lines:
        if line.startswith('```'):
            in_code_block = not in_code_block
            continue
        if in_code_block:
            code_lines.append(line)

    return '\n'.join(code_lines)


def save_python_files(commit: git.Commit, output_dir: str = 'python_files_export'):
    """Save all Python files from a commit to a directory."""
    output_path = Path(output_dir)
    output_path.mkdir(exist_ok=True)

    for blob in commit.tree.traverse():
        if blob.type != 'blob':  # Skip directories
            continue

        file_path = Path(blob.path)
        if not is_python_file(str(file_path)):
            continue

        try:
            file_content = blob.data_stream.read().decode('utf-8', errors='replace')

            # Create subdirectories if needed
            full_path = output_path / file_path
            full_path.parent.mkdir(parents=True, exist_ok=True)

            with open(full_path, 'w', encoding='utf-8') as f:
                f.write(file_content)

            print(f"Saved Python file: {full_path}")
        except Exception as e:
            print(f"Error processing {file_path}: {str(e)}")


if __name__ == "__main__":
    # Get merge commits and author mapping
    merge_commits_map, author_mapping = get_merge_commits_map(repo_path)

    # print("Author mapping:")
    # for username, emails_names in author_mapping.items():
    #     print(f"Username: {username}")
    #     for email, name in emails_names:
    #         print(f"  - Email: {email}, Name: {name}")
    #
    # print("\nMerge commits by user:")
    # for username, commits in merge_commits_map.items():
    #     print(f"{username}: {len(commits)} merge commits")

    # Example: Get differences for first merge commit of first user
    if merge_commits_map:
        first_user = next(iter(merge_commits_map))
        if merge_commits_map[first_user]:
            first_commit_hash = merge_commits_map[first_user][0]
            repo = git.Repo(str(repo_path))
            commit = repo.commit(first_commit_hash)

            # print(
            # f"\nDifferences for {first_user}'s merge commit {first_commit_hash}:")
            # print(get_difference(commit))

            output_dir = f"python_files_{first_commit_hash[:7]}"
            save_python_files(commit, output_dir)
            print(f"\nAll Python files saved to: {output_dir}")
            # print(f"\nCurrent state after {first_commit_hash}:")
            # print(get_current_state(commit))
