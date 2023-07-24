import argparse
import subprocess


def git_push(version: str, comment: str):
    print("Adding to git")
    subprocess.run(["git", "add", "."], check=True)

    if comment == "":
        comment = f"Updating to version {version}"

    print("Committing")
    subprocess.run(["git", "commit", "-m", comment], check=True)
    subprocess.run(["git", "push"], check=True)

    print("Tagging")
    subprocess.run(["git", "tag", "-a", version, "-m", comment], check=True)
    subprocess.run(["git", "push", "origin", "--tags"], check=True)

    print("Done")


def update_poetry(version: str):
    """
    Add version to pyproject.toml
    """
    subprocess.run(["poetry", "version", version], check=True)
    subprocess.run(["poetry", "build"], check=True)
    subprocess.run(["poetry", "publish", "-r", "tva_repo"], check=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Push version to git")
    parser.add_argument("--version", type=str, help="Version to push", default="")
    parser.add_argument("--comment", type=str, help="Comment to push", default="")

    args = parser.parse_args()
    version = args.version
    comment = args.comment

    update_poetry(version)
    git_push(version, comment)
