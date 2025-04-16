from pydriller import Repository
from collections import defaultdict

from pathlib import Path

TARGET_REPO = "devQ_testData_PythonProject"
# put the target repo next to the current folder

# Get the path to the current project (assumes script is run from the project directory)
current_repo_path = Path(__file__).resolve().parent

# Go up one level, then into the sibling directory
repo_path = current_repo_path.parent / TARGET_REPO

author_stats = defaultdict(lambda: {"commits": 0, "insertions": 0, "deletions": 0})
author_mapping = defaultdict(lambda: set())

repo = Repository(str(repo_path))

for commit in repo.traverse_commits():
    if not commit.msg.startswith('Merge'):
        continue

    print(commit.msg.__repr__())
    author_username = commit.author.email.split('@')[0].lower()

    author_mapping[author_username].add((commit.author.email, commit.author.name))

    author_stats[(commit.author.email, commit.author.name)]["commits"] += 1
    author_stats[(commit.author.email, commit.author.name)]["insertions"] += commit.insertions
    author_stats[(commit.author.email, commit.author.name)]["deletions"] += commit.deletions

for author_username, stats in author_stats.items():
    print(f"{author_username}: {stats['commits']} commits, {stats['insertions']} insertions, {stats['deletions']} deletions")

for author_username, pairs in author_mapping.items():
    print(f'{author_username}: ')
    for pair in pairs:
        print(' - ', pair[0], pair[1])