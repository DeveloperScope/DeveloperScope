from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from git import Repo, GitCommandError
import os
from pathlib import Path
from typing import Optional, List, Dict, Any
import json
import asyncio
import git
from developerscope.analyzer import get_merge_commits_map
from developerscope.haslted import halstead_effort
from developerscope.gpt import anylyze_commit

app = FastAPI()

# Configuration
REPOSITORIES_BASE_DIR = "repositories"  # Base directory to store all repos
OUTPUT_DIR = "out"  # Directory to store analysis results
os.makedirs(OUTPUT_DIR, exist_ok=True)


class AnalysisRequest(BaseModel):
    repo_url: str
    author: str
    target_dir: Optional[str] = None  # Optional subdirectory name


async def analyze_commits(repo_path: str, author: str) -> Dict[str, Any]:
    """
    Analyze commits for a specific author in a repository.
    Returns a dictionary with the analysis results.
    """
    # Initialize git repo
    git_repo = git.Repo(repo_path)

    # Get merge commits for the author
    merge_commits_map, author_mapping = get_merge_commits_map(Path(repo_path))
    print(merge_commits_map)

    if author not in merge_commits_map:
        raise HTTPException(
            status_code=404,
            detail=f"Author '{author}' not found in repository"
        )

    # Convert hashes to git.Commit objects
    author_commits = [git_repo.commit(h) for h in merge_commits_map[author]]

    # Score commits by effort
    scored = [(c, halstead_effort(c)) for c in author_commits]

    # Take the top 4 highest-effort commits
    top4 = sorted(scored, key=lambda t: t[1], reverse=True)[:4]

    # Analyze each commit
    sem = asyncio.Semaphore(3)  # Limit concurrent analyses

    async def bounded_analyse(commit: git.Commit):
        async with sem:
            return await anylyze_commit(commit)

    tasks = [asyncio.create_task(bounded_analyse(c)) for c, _ in top4]
    analyses = await asyncio.gather(*tasks)

    # Prepare plot data
    EFFORT_SCORE = {
        "Trivial": 1, "Minor": 2, "Moderate": 3, "Large": 4, "Major": 5
    }

    plot_data = []
    for (commit, _), analysis in zip(top4, analyses):
        analysis_dict = json.loads(analysis)
        plot_data.append({
            "hash": commit.hexsha[:7],
            "effort": EFFORT_SCORE[analysis_dict["effortEstimate"]],
            "issues": len(analysis_dict["issues"]),
        })

    # Save analysis to JSON file
    output_path = os.path.join(OUTPUT_DIR, f"{author}.json")
    with open(output_path, 'w') as f:
        json.dump({
            "author": author,
            "commits": plot_data,
            "analyses": [json.loads(a) for a in analyses]
        }, f, indent=4)

    return {
        "author": author,
        "commits_analyzed": len(plot_data),
        "output_path": output_path,
        "data": {
            "commits": plot_data,
            "analyses": [json.loads(a) for a in analyses]
        }
    }


@app.post("/analyze/")
async def full_analysis_workflow(request: AnalysisRequest):
    """
    Complete analysis workflow:
    1. Clone repository if not already exists
    2. Analyze commits for specified author
    3. Return analysis results

    Args:
        repo_url: URL of the git repository to clone
        author: Author name to analyze
        target_dir: Optional subdirectory name (defaults to repo name from URL)

    Returns:
        dict: Analysis results and repository status
    """
    try:
        # Determine the target directory
        if request.target_dir:
            repo_dir = os.path.join(REPOSITORIES_BASE_DIR, request.target_dir)
        else:
            # Extract repo name from URL if target_dir not provided
            repo_name = request.repo_url.split('/')[-1].replace('.git', '')
            repo_dir = os.path.join(REPOSITORIES_BASE_DIR, repo_name)

        # Convert to absolute path and create parent directory if needed
        repo_dir = os.path.abspath(repo_dir)
        os.makedirs(REPOSITORIES_BASE_DIR, exist_ok=True)

        # Clone the repository if it doesn't exist
        repo_status = "existing"
        if not os.path.exists(repo_dir):
            try:
                Repo.clone_from(request.repo_url, repo_dir)
                repo_status = "cloned"
            except GitCommandError as e:
                raise HTTPException(
                    status_code=400,
                    detail=f"Git command error: {str(e)}"
                )

        # Verify .git directory exists
        if not os.path.exists(os.path.join(repo_dir, ".git")):
            raise HTTPException(
                status_code=400,
                detail=f"Path is not a git repository: {repo_dir}"
            )

        # Perform analysis
        analysis_result = await analyze_commits(repo_dir, request.author)

        return {
            "repository": {
                "status": repo_status,
                "path": repo_dir,
                "url": request.repo_url
            },
            "analysis": analysis_result
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"An error occurred during analysis: {str(e)}"
        )


@app.get("/get-analysis/{author}")
async def get_analysis(author: str):
    """
    Retrieve previously saved analysis for an author.

    Args:
        author: Author name to retrieve analysis for

    Returns:
        dict: Saved analysis data
    """
    try:
        file_path = os.path.join(OUTPUT_DIR, f"{author}.json")
        if not os.path.exists(file_path):
            raise HTTPException(
                status_code=404,
                detail=f"No analysis found for author '{author}'"
            )

        with open(file_path, 'r') as f:
            return json.load(f)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error loading analysis: {str(e)}"
        )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
