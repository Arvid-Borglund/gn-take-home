"""Reviews a pull request with an LLM and posts the review as one comment.

Run by .github/workflows/pr-review.yml when a pull request is opened or gets new commits.

    1. get the pull request and its diff from the GitHub API
    2. send the diff to the model, asking for a summary and suggested improvements
    3. post the answer as a comment on the pull request. If the bot has already
       commented on this pull request, that comment is updated instead, so there is
       always exactly one.

    python analyze_pr.py             posts the comment
    python analyze_pr.py --dry-run   prints the comment instead of posting it

Settings come from environment variables: GITHUB_TOKEN, GITHUB_REPOSITORY (owner/name),
PR_NUMBER, and the four AZURE_OPENAI_* variables.
"""

import os
import sys
from typing import Optional

import httpx
from openai import AzureOpenAI

GITHUB_API = "https://api.github.com"

# A hidden HTML comment that marks the bot's comment, so a later run can find it.
COMMENT_MARKER = "<!-- pr-review-bot -->"

# A very large diff does not fit in one model call. The review then covers the start.
MAX_DIFF_CHARACTERS = 60000

REVIEW_INSTRUCTIONS = """You are reviewing a pull request. You get its title and its diff.

Write two short sections.
Summary: two to four sentences on what the pull request changes.
Suggestions: up to five concrete improvements, each naming the file it concerns. If nothing is worth changing, say so instead of inventing something.

Review only what is in the diff. Keep the whole answer under 300 words."""


def read_setting(name: str) -> str:
    value = os.environ.get(name, "")
    if value == "":
        print(f"The environment variable {name} is not set.")
        sys.exit(1)
    return value


def github_headers(token: str, accept: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": accept,
        "X-GitHub-Api-Version": "2022-11-28",
    }


def stop_on_error(response: httpx.Response, what: str) -> None:
    if response.status_code >= 400:
        print(f"GitHub answered {response.status_code} when trying to {what}: {response.text[:500]}")
        sys.exit(1)


def get_pull_request(http: httpx.Client, token: str, repository: str, pr_number: str) -> dict:
    url = f"{GITHUB_API}/repos/{repository}/pulls/{pr_number}"
    response = http.get(url, headers=github_headers(token, "application/vnd.github+json"))
    stop_on_error(response, "read the pull request")
    return response.json()


def get_diff(http: httpx.Client, token: str, repository: str, pr_number: str) -> str:
    # The same address as above. The Accept header asks for the diff instead of JSON.
    url = f"{GITHUB_API}/repos/{repository}/pulls/{pr_number}"
    response = http.get(url, headers=github_headers(token, "application/vnd.github.diff"))
    stop_on_error(response, "read the diff")
    return response.text


def ask_model_for_review(title: str, diff: str) -> str:
    client = AzureOpenAI(
        azure_endpoint=read_setting("AZURE_OPENAI_ENDPOINT"),
        api_key=read_setting("AZURE_OPENAI_API_KEY"),
        api_version=read_setting("AZURE_OPENAI_API_VERSION"),
    )

    note = ""
    if len(diff) > MAX_DIFF_CHARACTERS:
        diff = diff[:MAX_DIFF_CHARACTERS]
        note = f"\n\n(The diff was cut at {MAX_DIFF_CHARACTERS} characters. Say in the summary that the review covers only the first part.)"

    user_message = f"Pull request title: {title}\n\nDiff:\n{diff}{note}"

    response = client.chat.completions.create(
        model=read_setting("AZURE_OPENAI_DEPLOYMENT"),
        messages=[
            {"role": "system", "content": REVIEW_INSTRUCTIONS},
            {"role": "user", "content": user_message},
        ],
    )
    return response.choices[0].message.content


def find_bot_comment(http: httpx.Client, token: str, repository: str, pr_number: str) -> Optional[int]:
    """The id of the comment an earlier run posted on this pull request, or None."""
    # A pull request is also an issue, and its plain comments live under /issues.
    url = f"{GITHUB_API}/repos/{repository}/issues/{pr_number}/comments"
    response = http.get(
        url,
        headers=github_headers(token, "application/vnd.github+json"),
        params={"per_page": 100},
    )
    stop_on_error(response, "list the comments")

    for comment in response.json():
        if COMMENT_MARKER in comment["body"]:
            return comment["id"]
    return None


def post_comment(http: httpx.Client, token: str, repository: str, pr_number: str, body: str) -> None:
    headers = github_headers(token, "application/vnd.github+json")
    comment_id = find_bot_comment(http, token, repository, pr_number)

    if comment_id is None:
        url = f"{GITHUB_API}/repos/{repository}/issues/{pr_number}/comments"
        response = http.post(url, headers=headers, json={"body": body})
        stop_on_error(response, "post the comment")
        print("Posted the review comment.")
    else:
        url = f"{GITHUB_API}/repos/{repository}/issues/comments/{comment_id}"
        response = http.patch(url, headers=headers, json={"body": body})
        stop_on_error(response, "update the comment")
        print("Updated the existing review comment.")


def main() -> int:
    dry_run = "--dry-run" in sys.argv[1:]

    token = read_setting("GITHUB_TOKEN")
    repository = read_setting("GITHUB_REPOSITORY")
    pr_number = read_setting("PR_NUMBER")

    http = httpx.Client(timeout=30.0)

    pull_request = get_pull_request(http, token, repository, pr_number)
    diff = get_diff(http, token, repository, pr_number)

    if diff.strip() == "":
        print("The pull request has no diff. Nothing to review.")
        return 0

    review = ask_model_for_review(pull_request["title"], diff)

    short_sha = pull_request["head"]["sha"][:7]
    body = f"{COMMENT_MARKER}\n### Automated review\n\n{review}\n\n_Reviewed at commit {short_sha}._"

    if dry_run:
        print(body)
        return 0

    post_comment(http, token, repository, pr_number, body)
    return 0


if __name__ == "__main__":
    sys.exit(main())
