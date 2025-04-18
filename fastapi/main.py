from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from git import Repo, GitCommandError
import os
from pathlib import Path
from typing import Optional

app = FastAPI()

# Configuration
REPOSITORIES_BASE_DIR = "repositories"  # Base directory to store all repos


class RepositoryRequest(BaseModel):
    repo_url: str
    target_dir: Optional[str] = None  # Optional subdirectory name


@app.post("/clone-repo/")
async def clone_repository(request: RepositoryRequest):
    """
    Clone a git repository to the local filesystem.

    Args:
        repo_url: URL of the git repository to clone
        target_dir: Optional subdirectory name (defaults to repo name from URL)

    Returns:
        dict: Status and path of the cloned repository
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

        # Check if directory already exists
        if os.path.exists(repo_dir):
            return {
                "status": "exists",
                "path": repo_dir,
                "message": f"Directory already exists at {repo_dir}"
            }

        # Clone the repository
        Repo.clone_from(request.repo_url, repo_dir)

        return {
            "status": "success",
            "path": repo_dir,
            "message": f"Repository cloned successfully to {repo_dir}"
        }

    except GitCommandError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Git command error: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"An error occurred: {str(e)}"
        )


@app.get("/list-repos/")
async def list_repositories():
    """
    List all repositories that have been cloned.

    Returns:
        dict: List of repository directories
    """
    try:
        if not os.path.exists(REPOSITORIES_BASE_DIR):
            return {"repositories": []}

        repos = []
        for item in os.listdir(REPOSITORIES_BASE_DIR):
            item_path = os.path.join(REPOSITORIES_BASE_DIR, item)
            if os.path.isdir(item_path):
                # Check if it's a git repository
                git_dir = os.path.join(item_path, '.git')
                repos.append({
                    "name": item,
                    "path": item_path,
                    "is_git_repo": os.path.exists(git_dir)
                })

        return {"repositories": repos}
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"An error occurred while listing repositories: {str(e)}"
        )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
