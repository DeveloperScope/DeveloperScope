import os
from git import Repo


def download_repo(repo_url, target_dir, token=None):
    """
    Download a Git repository (public or private) to a target directory.

    Args:
        repo_url (str): URL of the Git repository
        target_dir (str): Local directory to clone into
        token (str, optional): Personal access token for private repos,
                               only needed for private
    """
    try:
        if os.path.exists(target_dir):
            print(
                '''Target directory already exists and has content,
                delete this directory or specify new''')

        if token:
            if repo_url.startswith('https://'):
                auth_url = repo_url.replace('https://', f'https://{token}@')
            else:
                raise ValueError(
                    "Supporting only HTTPS based clone with PAT token")
        else:
            auth_url = repo_url

        print("Cloning repository...")

        if token and repo_url.startswith('https://'):
            Repo.clone_from(auth_url, target_dir)
        else:
            Repo.clone_from(repo_url, target_dir)

        print(f"Repository successfully cloned to {target_dir}")

    except Exception as e:
        print(f"Error cloning repository: {str(e)}")


def main():
    TOKEN = ""

    download_repo(
        repo_url="https://github.com/muhammaduss/nvim-config.git",
        target_dir="dir",
        token=TOKEN
    )


if __name__ == "__main__":
    main()
