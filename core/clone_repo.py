import uuid
from pathlib import Path
from git import Repo

BASE_DIR = Path(__file__).resolve().parent.parent
TEMP_DIR = BASE_DIR / "temp_repos"


def clone_repository(repo_url):
    repo_name = repo_url.split("/")[-1].replace(".git", "")
    unique_id = str(uuid.uuid4())[:8]
    local_path = TEMP_DIR / f"{repo_name}_{unique_id}"

    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    Repo.clone_from(repo_url, str(local_path))

    return str(local_path)