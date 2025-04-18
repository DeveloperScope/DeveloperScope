from __future__ import annotations

"""analyze_commits.py

Asynchronously analyse every **merge commit** in the target repository with GPT‑4 function‑calling and
store the results in a single JSON file.  For every commit we

1. Build a secure‑code‑review prompt that includes the full textual diff **plus** the
   Halstead **total volume** metric for the changed Python files.
2. Ask the model to return a `MergeRequestAnalysis` *via* JSON‑schema
   enforcement, with the helper function `get_file_contents` available so the
   model can pull any extra context it needs – but only for paths that really
   exist in that commit.
3. If the commit type is `Feature`, run a **second** review‑stage chat to prune
   the issues list to **HIGH/CRITICAL** (see the review prompt in the original
   notebook).
4. Persist all per‑commit analyses in one repo‑level JSON file with the shape

   ```json
   {
     "repo_name": "<TARGET_REPO>",
     "authors": {
       "<author>": {
         "merge_requests": [MergeRequestAnalysis, ...]
       }
     }
   }
   ```

The code keeps to *functions‑only* style (no classes), explicit type hints, and
pattern‑matching (PEP 636) where it improves clarity.
"""

from collections import defaultdict
from pathlib import Path
import asyncio
import json
import os
import re
from typing import Any, Coroutine, Literal, TypedDict

import git
from pydriller import Repository
from radon.metrics import h_visit  # Halstead
from openai import AsyncOpenAI,OpenAI, BaseModel

# ────────────────────────────────────────────────────────────────────────────────
#  Types (mirrored from developerscope/_types.py, duplicated here for clarity)
# ────────────────────────────────────────────────────────────────────────────────

MergeRequestEnum = Literal[
    "Feature",
    "Bug‑fix",
    "Refactor",
    "Performance",
    "Security‐patch",
    "Docs / comments",
    "Chore / dependency bump",
]

type IssueEnum = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
type EffortEnum = Literal["Trivial", "Minor", "Moderate", "Large", "Major"]


class PotentialIssue(TypedDict):
    filePath: str
    line: str
    issue: str
    level: IssueEnum


class MergeRequestAnalysis(TypedDict):
    hiddenReasoning: str
    type: MergeRequestEnum
    issues: list[PotentialIssue]
    effortEstimate: EffortEnum
    commitHash: str  # ⇐ we add this so downstream consumers know the commit id


# ────────────────────────────────────────────────────────────────────────────────
#  Repo helpers (imported from developerscope.analyzer where possible)
# ────────────────────────────────────────────────────────────────────────────────

TARGET_REPO = "devQ_testData_PythonProject"
CURRENT_REPO_PATH = Path(__file__).resolve().parent
REPO_PATH = CURRENT_REPO_PATH.parent / TARGET_REPO
GIT_REPO = git.Repo(str(REPO_PATH))


def extract_username(email: str) -> str:
    """Heuristic extraction copied from developerscope.analyzer."""
    email = email.lower()
    if m := re.match(r"^\d+\+([^@]+)@users\.noreply\.github\.com$", email):
        return m.group(1)
    if m := re.match(r"^([^@]+)@users\.noreply\.github\.com$", email):
        return m.group(1)
    return email.split("@")[0]


from developerscope.analyzer import (
    get_difference,
    get_current_state,
    get_current_state_paths,
    get_merge_commits_map,
)

# ────────────────────────────────────────────────────────────────────────────────
#  Halstead helpers
# ────────────────────────────────────────────────────────────────────────────────

def _is_python(path: str) -> bool:
    return path.endswith(".py")


def _halstead_volume_for_blob(blob: git.Blob) -> float:
    """Compute Halstead *volume* for a *single* blob – non‑blocking."""
    if not _is_python(blob.path):
        return 0.0
    code = blob.data_stream.read().decode("utf-8", errors="replace")
    if not code.strip():
        return 0.0
    try:
        h = h_visit(code).total if hasattr(h_visit(code), "total") else h_visit(code)
        return float(getattr(h, "volume", 0.0))
    except Exception:
        return 0.0


def halstead_volume(commit: git.Commit, *, changed_only: bool = True) -> float:
    """Return cumulative Halstead **volume** for the *Python* files in *commit*.

    If *changed_only* is True we look at the diff – cheaper and more relevant –
    otherwise we walk the whole tree.
    """
    total = 0.0
    if changed_only:
        parent = commit.parents[0]
        for diff in parent.diff(commit):
            blob = diff.b_blob or diff.a_blob
            if blob:
                total += _halstead_volume_for_blob(blob)
    else:
        for blob in commit.tree.traverse():
            if blob.type == "blob":
                total += _halstead_volume_for_blob(blob)
    return round(total, 2)

# ────────────────────────────────────────────────────────────────────────────────
#  GPT scaffolding
# ────────────────────────────────────────────────────────────────────────────────

MODEL_NAME = "gpt-4o"  # adjust as required
client = AsyncOpenAI()

SYSTEM_PROMPT = """
You are a secure‑code reviewer.

You will receive:
• the raw `git diff` of a **merge commit**
• the *Halstead total volume* for the changed Python files (objective metric)

Tasks:
1. **Classify** the merge‑request type – choose exactly one from the list.
2. **List potential issues** (security, logic, best practice, etc.) with a
   severity of LOW‑CRITICAL.
3. If the diff alone is insufficient, call **get_file_contents** with the exact
   file‑paths you still need.
Return the result strictly as JSON conforming to the `MergeRequestAnalysis`
 schema provided via `response_format`.
"""

SYSTEM_PROMPT_REVIEW = """
You are a senior secure‑code *defender* reviewing an *existing* analysis.

1. **If** you need more context, call `get_file_contents`.
2. **Then** copy the existing analysis but *keep only* issues with severity HIGH
   or CRITICAL.
3. Adjust `effortEstimate` if the filtered list changes the scope.
Output the same `MergeRequestAnalysis` object.
"""


def _run_chat(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    schema: dict[str, Any],
    *,
    max_rounds: int = 2,
) -> str:
    """Generic helper that loops model→function calls→model until we get JSON."""
    for _ in range(max_rounds):
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=messages,
            tools=tools,
            tool_choice="auto",
            response_format={"type": "json_schema", "schema": schema},
            temperature=0.2,
        )

        choice = response.choices[0]
        if choice.finish_reason != "tool_calls":
            # We either got the final JSON or regular text – return raw content
            return choice.message.content or "{}"

        # A tool call is requested; we currently support only *one* function call
        for tool_call in choice.message.tool_calls:
            if tool_call.name != "get_file_contents":
                continue
            args = json.loads(tool_call.function.arguments)
            files: list[str] = args.get("files", [])
            commit_hash = messages[1]["commit_hash"]  # stash earlier
            commit = GIT_REPO.commit(commit_hash)
            file_contents = get_current_state(commit, include_only=files)

            # Append the function output & continue the loop
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": tool_call.name,
                    "content": file_contents,
                }
            )
            break
    # If we exit loop without return, give up gracefully
    return "{}"


# ────────────────────────────────────────────────────────────────────────────────
#  Core analysis routine
# ────────────────────────────────────────────────────────────────────────────────

def analyze_commit(author: str, commit_hash: str) -> tuple[str, MergeRequestAnalysis]:
    """Analyse *one* merge commit – may issue up to two GPT calls."""
    commit = GIT_REPO.commit(commit_hash)

    # Build the user diff prompt
    diff_prompt = get_difference(commit)
    volume = halstead_volume(commit)

    user_message = (
        f"HALSTEAD_TOTAL_VOLUME: {volume}\n\n"  # objective metric
        f"{diff_prompt}"
    )

    # Commit‑specific tool definition prevents the model from inventing paths
    tools = [
    {
    "type": "function",
    "name": "get_file_contents",
    "description": "Function which accepts a list of files in a git repo and produces a their content",
    "strict": True,
    "parameters": {
        "type": "object",
        "required": [
            "files"
        ],
        "properties": {
            "files": {
                "type": "array",
                "description": "List of specific files to read from the git repository",
                "items": {
                    "type": "string",
                    "enum": get_current_state_paths(merge_commit),
                    "description": "File name that exists in the git repository"
                }
            }
        },
        "additionalProperties": False
    }
}]

    schema = json.loads((Path(__file__).parent / "schema.json").read_text())

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_message, "commit_hash": commit_hash},  # custom key to retrieve later
    ]

    # 1st round – base analysis
    raw_json = _run_chat(messages, tools, schema)
    analysis: MergeRequestAnalysis = json.loads(raw_json)
    analysis["commitHash"] = commit_hash  # attach hash for traceability

    # 2nd round – feature review
    match analysis["type"]:
        case "Feature":
            review_messages = [
                {"role": "system", "content": SYSTEM_PROMPT_REVIEW},
                {"role": "user", "content": raw_json},
            ]
            review_json = _run_chat(review_messages, tools, schema)
            analysis = json.loads(review_json)
            analysis["commitHash"] = commit_hash
        case _:
            pass  # No second round needed

    return author, analysis


# ────────────────────────────────────────────────────────────────────────────────
#  Orchestrator
# ────────────────────────────────────────────────────────────────────────────────

async def gather_all() -> dict[str, Any]:
    merge_commits_map, _ = get_merge_commits_map(REPO_PATH)

    sem = asyncio.Semaphore(4)  # keep to 4 concurrent OpenAI requests

    async def _bounded(author: str, commit: str):
        async with sem:
            return await analyze_commit(author, commit)

    tasks: list[Coroutine[Any, Any, tuple[str, MergeRequestAnalysis]]] = []
    for author, commits in merge_commits_map.items():
        for c in commits:
            tasks.append(_bounded(author, c))

    results = await asyncio.gather(*tasks)

    # Build the final aggregated structure
    output: dict[str, Any] = {"repo_name": TARGET_REPO, "authors": defaultdict(lambda: {"merge_requests": []})}
    for author, analysis in results:
        output["authors"][author]["merge_requests"].append(analysis)
    return output


# ────────────────────────────────────────────────────────────────────────────────
#  Script entry‑point
# ────────────────────────────────────────────────────────────────────────────────

def main() -> None:
    """Run the full analysis and dump one JSON report next to the script."""
    json_path = Path(__file__).with_name(f"{TARGET_REPO}_analysis.json")
    data = asyncio.run(gather_all())
    json_path.write_text(json.dumps(data, indent=2))
    print(f"✅ Analysis complete → {json_path}")


if __name__ == "__main__":
    main()
