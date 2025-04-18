from collections import defaultdict

from pathlib import Path
import re

import git
from pydriller import Repository


TARGET_REPO = "devQ_testData_PythonProject"
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

            author_mapping[username].add((commit.author.email, commit.author.name))

            merge_commts_map[username].append(commit.hash)

    return merge_commts_map, author_mapping


def get_difference(commit: git.Commit) -> str:
    # if len(merge_commit.parents) != 2:
    #     raise ValueError("Only 2 parents allowed for merge request commits")

    first_parent = commit.parents[0]
    diff_index = first_parent.diff(commit, create_patch=True)

    difference = ''
    for diff in diff_index:
        diff_text = diff.diff.decode('utf-8')
        file_header = f"==== File: {diff.a_path or diff.b_path} ====\n"
        difference += file_header + diff_text + "\n\n"

    return difference


def get_prompt_for_merge_commit(commit: git.Commit) -> str:
    prompt = commit.message + '\n\n'
    # for file in get_current_state_paths(commit):
    #     prompt += file + '\n'
    prompt += '\n' + get_difference(commit)
    return prompt

def get_current_state(commit: git.Commit, include_only: list[str] | None = None):
    file_chunks = []

    for blob in commit.tree.traverse():
        if blob.type == 'blob':  # it's a file
            file_path = blob.path
            if include_only:
                if file_path not in include_only:
                    continue

            file_content = blob.data_stream.read().decode('utf-8', errors='replace')
            print(file_path)
            formatted = f"### FILE: `{file_path}`\n\n```\n{file_content}\n```\n"
            file_chunks.append(formatted)

    # Join all file contents into a single string
    final_string = "\n\n".join(file_chunks)
    return final_string

def get_current_state_paths(commit: git.Commit) -> list[str]:
    file_paths = []

    for blob in commit.tree.traverse():
        if blob.type == 'blob':  # it's a file
            file_paths.append(str(blob.path))
    return file_paths

