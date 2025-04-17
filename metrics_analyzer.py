import argparse
import pandas as pd
import radon.metrics
import lizard
import warnings
import os
from collections import defaultdict
import time

from pathlib import Path
import re

import git
from pydriller import Repository


warnings.filterwarnings("ignore", category=SyntaxWarning)


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


def analyze_python_file(file_path):
    """Returns cyclomatic and Halstead metrics for a Python file."""
    file_path_str = str(file_path)
    result = {
        'file': file_path_str,
        'functions': [],
        'halstead': {}
    }

    try:
        with open(file_path_str, 'r', encoding='utf-8') as f:
            code = f.read()
            
            # Skip empty files
            if not code.strip():
                return result

    except Exception as e:
        return result

    # Cyclomatic Complexity (via lizard) - more resilient
    try:
        lizard_result = lizard.analyze_file(file_path_str)
        result['functions'] = [
            {
                'name': f.name,
                'cyclomatic': f.cyclomatic_complexity,
                'nloc': f.nloc,
                'token_count': f.token_count
            }
            for f in lizard_result.function_list
        ]
    except Exception:
        pass  # Silently skip lizard analysis failures

    # Halstead metrics (via radon) - with robust error handling
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            halstead = radon.metrics.h_visit(code)
            
            # Handle both old and new radon versions
            if hasattr(halstead, 'total'):
                halstead = halstead.total
                
            result['halstead'] = {
                'h1': getattr(halstead, 'h1', 0),
                'h2': getattr(halstead, 'h2', 0),
                'N1': getattr(halstead, 'N1', 0),
                'N2': getattr(halstead, 'N2', 0),
                'vocabulary': getattr(halstead, 'vocabulary', 0),
                'length': getattr(halstead, 'length', 0),
                'volume': getattr(halstead, 'volume', 0),
                'difficulty': getattr(halstead, 'difficulty', 0),
                'effort': getattr(halstead, 'effort', 0),
            }
    except (SyntaxError, ValueError, IndexError, AttributeError):
        pass  # Silently skip radon analysis failures

    return result


def get_metrics_for_commit(repo_path, commit_hash, output_dir="temp_analysis"):
    """Checkout a commit and analyze all Python files."""
    repo = git.Repo(repo_path)

    # Handle both string hashes and commit objects
    if isinstance(commit_hash, git.Commit):
        commit_hash_str = commit_hash.hexsha[:7]
        repo.git.checkout(commit_hash.hexsha)
    else:
        commit_hash_str = commit_hash[:7]
        repo.git.checkout(commit_hash)

    metrics = []
    for root, _, files in os.walk(repo_path):
        # Skip migrations and virtualenvs
        if 'migrations' in root or 'venv' in root or 'alembic' in root:
            continue

        for file in files:
            if file.endswith('.py'):
                full_path = Path(root) / file
                file_metrics = analyze_python_file(full_path)
                if file_metrics:  # Only append if analysis succeeded
                    metrics.append(file_metrics)

    # Save metrics to JSON for comparison
    output_path = Path(output_dir) / f"metrics_{commit_hash_str}.json"
    output_path.parent.mkdir(exist_ok=True)
    pd.DataFrame(metrics).to_json(output_path, indent=2, orient='records')

    return metrics


def compare_metrics(old_metrics, new_metrics):
    """Compare two sets of metrics and return a diff report."""
    report = {
        'files_added': [],
        'files_removed': [],
        'files_changed': [],
        'complexity_increased': [],
        'complexity_decreased': [],
        'summary': defaultdict(float)
    }

    old_files = {m['file']: m for m in old_metrics if m.get('halstead')}
    new_files = {m['file']: m for m in new_metrics if m.get('halstead')}

    # Find added/removed files
    report['files_added'] = list(set(new_files) - set(old_files))
    report['files_removed'] = list(set(old_files) - set(new_files))

    # Compare common files
    for file in set(new_files) & set(old_files):
        old = old_files[file]
        new = new_files[file]

        # Compare Halstead metrics
        halstead_diff = {}
        for metric in ['volume', 'difficulty', 'effort']:
            old_val = old['halstead'].get(metric, 0)
            new_val = new['halstead'].get(metric, 0)
            delta = new_val - old_val
            halstead_diff[metric] = delta
            report['summary'][f'total_{metric}_change'] += delta

        # Compare function complexities
        func_comparison = []
        old_funcs = {f['name']: f for f in old.get('functions', [])}
        new_funcs = {f['name']: f for f in new.get('functions', [])}

        for func_name in set(new_funcs) | set(old_funcs):
            if func_name in new_funcs and func_name not in old_funcs:
                status = 'added'
                delta = new_funcs[func_name]['cyclomatic']
            elif func_name in old_funcs and func_name not in new_funcs:
                status = 'removed'
                delta = -old_funcs[func_name]['cyclomatic']
            else:
                delta = new_funcs[func_name]['cyclomatic'] - \
                    old_funcs[func_name]['cyclomatic']
                status = 'increased' if delta > 0 else 'decreased' if delta < 0 else 'unchanged'

            if status in ('increased', 'decreased'):
                func_comparison.append({
                    'function': func_name,
                    'old_complexity': old_funcs.get(func_name, {}).get('cyclomatic'),
                    'new_complexity': new_funcs.get(func_name, {}).get('cyclomatic'),
                    'delta': delta,
                    'status': status
                })

        if func_comparison or any(v != 0 for v in halstead_diff.values()):
            report['files_changed'].append({
                'file': file,
                'halstead_diff': halstead_diff,
                'function_changes': func_comparison
            })

    return report



def compare_two_commits(repo_path, old_hash, new_hash):
    """Helper function to compare two specific commits"""
    repo = git.Repo(str(repo_path))
    old_commit = repo.commit(old_hash)
    new_commit = repo.commit(new_hash)

    print(f"\n=== Comparing {old_hash[:7]} → {new_hash[:7]} ===")
    print(f"Date: {new_commit.committed_datetime}")
    print(f"Message: {new_commit.message.splitlines()[0]}")

    # Analyze both commits
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=SyntaxWarning)
        old_metrics = get_metrics_for_commit(repo_path, old_hash)
        new_metrics = get_metrics_for_commit(repo_path, new_hash)

    # Compare and print results
    comparison = compare_metrics(old_metrics, new_metrics)

    print("\n📈 Summary of Changes:")
    for metric, change in comparison['summary'].items():
        print(f"{metric.replace('_', ' ').title()}: {change:+.2f}")

    if comparison['files_changed']:
        print("\n📌 Significant Changes:")
        for change in comparison['files_changed']:
            print(f"\nFile: {change['file']}")
            for metric, delta in change['halstead_diff'].items():
                if abs(delta) > 5:
                    print(f"  {metric}: {delta:+.2f}")

            for func in change['function_changes']:
                if abs(func['delta']) > 2:
                    print(
                        f"  Function: {func['function']} ({func['status']} by {func['delta']:+d})")

    total_cc_change = 0
    changed_functions = []
    
    for change in comparison['files_changed']:
        for func in change['function_changes']:
            total_cc_change += func['delta']
            if abs(func['delta']) > 0:  # Record all changes
                changed_functions.append({
                    'file': change['file'],
                    'function': func['function'],
                    'old_cc': func['old_complexity'],
                    'new_cc': func['new_complexity'],
                    'delta': func['delta']
                })
    
    print("\n🧠 Cyclomatic Complexity Changes:")
    print(f"Total Complexity Change: {total_cc_change:+d}")
    
    if changed_functions:
        print("\n🔍 Function-Level Changes:")
        for func in sorted(changed_functions, key=lambda x: abs(x['delta']), reverse=True):
            trend = "↑↑" if func['delta'] > 0 else "↓↓" if func['delta'] < 0 else "→"
            print(f"{trend} {func['file']}::{func['function']}")
            print(f"   {func['old_cc']} → {func['new_cc']} ({func['delta']:+d})")
            
            # Add interpretation guide
            if func['new_cc'] > 15:
                print("   ⚠️ High complexity (consider refactoring)")
            elif func['new_cc'] > 10:
                print("   ⚠️ Moderate complexity")
    else:
        print("No significant cyclomatic complexity changes")


if __name__ == "__main__":
    # Set up command line arguments
    parser = argparse.ArgumentParser(description="Code quality analyzer")
    parser.add_argument('--all', action='store_true',
                        help='Analyze all commits sequentially')
    parser.add_argument('--user', type=str,
                        help='Specify which user to analyze')
    args = parser.parse_args()

    # Get merge commits and author mapping
    merge_commits_map, author_mapping = get_merge_commits_map(repo_path)

    if not merge_commits_map:
        print("No merge commits found")
        exit()

    # User selection logic
    selected_user = args.user if args.user else next(iter(merge_commits_map))
    if selected_user not in merge_commits_map:
        print(f"User {selected_user} not found in commit history")
        exit()

    user_commits = merge_commits_map[selected_user]
    repo = git.Repo(str(repo_path))

    if args.all:
        # Full history analysis mode
        print(
            f"\nAnalyzing ALL {len(user_commits)} commits for user: {selected_user}")
        sorted_commits = sorted(
            user_commits, key=lambda x: repo.commit(x).committed_datetime)

        for i in range(1, len(sorted_commits)):
            old_hash = sorted_commits[i-1]
            new_hash = sorted_commits[i]
            compare_two_commits(repo_path, old_hash, new_hash)
    else:
        # Default two-commit comparison mode
        if len(user_commits) < 2:
            print(
                f"Need at least 2 commits to compare (found {len(user_commits)})")
            exit()

        print(f"\nComparing LATEST TWO commits for user: {selected_user}")
        old_hash = user_commits[-2]  # Second to last
        new_hash = user_commits[-1]  # Most recent
        compare_two_commits(repo_path, old_hash, new_hash)
