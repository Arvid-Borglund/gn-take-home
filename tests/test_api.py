"""Tests of the ticket API from the outside: plain HTTP against a running API.

They check the contract the agent depends on: the status codes, and above all the
"detail" message of every business-rule error.

    docker compose run --rm tests

Every test creates the ticket it needs and removes it afterwards, so the tests can run
against a database that already has tickets in it.
"""

import os
import time

import httpx
import pytest

API_URL = os.environ.get("TICKET_API_URL", "http://localhost:8080")

# An id far above anything the tests create.
MISSING_ID = 999999999

# The user the API creates when it starts (SeedUser__Username and SeedUser__Password
# in compose.yaml).
LOGIN_USER = os.environ.get("WEB_LOGIN_USER", "demo")
LOGIN_PASSWORD = os.environ.get("WEB_LOGIN_PASSWORD", "demo")

http = httpx.Client(base_url=API_URL, timeout=10.0)


# ----- Setup -----

@pytest.fixture(scope="session", autouse=True)
def api_is_up():
    """Runs once before the first test. The API container may still be starting."""
    attempts = 0
    while attempts < 30:
        try:
            response = http.get("/health")
            if response.status_code == 200:
                return
        except httpx.HTTPError:
            pass
        attempts += 1
        time.sleep(1)

    pytest.exit(f"The ticket API did not become healthy at {API_URL}.", returncode=1)


@pytest.fixture
def ticket():
    """A new ticket for one test. A test gets it by having a parameter named ticket."""
    response = http.post(
        "/tickets",
        json={"title": "Test ticket", "description": "Created by the test suite"},
    )
    assert response.status_code == 201
    created = response.json()

    yield created

    # After the test. The answer may be 404, when the test deleted the ticket itself.
    http.delete(f"/tickets/{created['ticketId']}")


def ids_in(response: httpx.Response) -> list:
    assert response.status_code == 200
    ids = []
    for item in response.json():
        ids.append(item["ticketId"])
    return ids


# ----- Health -----

def test_health_answers_200_when_the_database_is_reachable():
    response = http.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


# ----- Login check -----
#
# The web interface is behind a login when it is deployed. nginx asks this endpoint
# whether the login in a request is valid; the ticket endpoints themselves ask for none.

def test_login_check_without_a_login_is_401_and_asks_for_one():
    response = http.get("/auth/check")

    assert response.status_code == 401
    # The header that makes a browser show its login dialog.
    assert response.headers["WWW-Authenticate"] == 'Basic realm="Ticket desk"'


def test_login_check_with_the_right_password_is_200_and_names_the_user():
    response = http.get("/auth/check", auth=(LOGIN_USER, LOGIN_PASSWORD))

    assert response.status_code == 200
    assert response.headers["X-User"] == LOGIN_USER


def test_login_check_with_a_wrong_password_is_401():
    response = http.get("/auth/check", auth=(LOGIN_USER, LOGIN_PASSWORD + "x"))

    assert response.status_code == 401


def test_login_check_with_an_unknown_user_is_401():
    response = http.get("/auth/check", auth=("someone-else", LOGIN_PASSWORD))

    assert response.status_code == 401


# ----- Create -----

def test_a_new_ticket_is_open_and_has_one_version(ticket):
    assert ticket["status"] == "OPEN"
    assert ticket["resolution"] is None
    assert ticket["versionNo"] == 1
    assert ticket["created"] == ticket["updated"]


def test_create_without_a_title_is_422():
    response = http.post("/tickets", json={"description": "No title given"})

    assert response.status_code == 422
    assert response.json()["detail"] == "The field 'title' is required and cannot be empty."


# ----- Read -----

def test_list_can_filter_by_status(ticket):
    open_ids = ids_in(http.get("/tickets", params={"status": "OPEN"}))
    closed_ids = ids_in(http.get("/tickets", params={"status": "CLOSED"}))

    assert ticket["ticketId"] in open_ids
    assert ticket["ticketId"] not in closed_ids


def test_list_with_an_unknown_status_is_422_and_names_the_valid_ones():
    response = http.get("/tickets", params={"status": "PROGRESS"})

    assert response.status_code == 422
    assert response.json()["detail"] == (
        "'PROGRESS' is not a valid status. Valid statuses are: OPEN, RESOLVED, CLOSED."
    )


def test_get_returns_the_ticket_with_its_comments(ticket):
    response = http.get(f"/tickets/{ticket['ticketId']}")

    assert response.status_code == 200
    body = response.json()
    assert body["ticket"]["title"] == "Test ticket"
    assert body["comments"] == []


def test_get_with_an_unknown_id_is_404():
    response = http.get(f"/tickets/{MISSING_ID}")

    assert response.status_code == 404
    assert response.json()["detail"] == f"Ticket {MISSING_ID} does not exist."


# ----- Update -----

def test_update_with_an_unknown_id_is_404():
    response = http.patch(f"/tickets/{MISSING_ID}", json={"status": "CLOSED"})

    assert response.status_code == 404
    assert response.json()["detail"] == f"Ticket {MISSING_ID} does not exist."


def test_update_with_an_invalid_status_is_422_and_changes_nothing(ticket):
    ticket_id = ticket["ticketId"]

    response = http.patch(f"/tickets/{ticket_id}", json={"status": "PROGRESS"})

    assert response.status_code == 422
    assert response.json()["detail"] == (
        "'PROGRESS' is not a valid status. Valid statuses are: OPEN, RESOLVED, CLOSED."
    )
    after = http.get(f"/tickets/{ticket_id}").json()["ticket"]
    assert after["status"] == "OPEN"
    assert after["versionNo"] == 1


def test_resolving_without_a_resolution_is_422_and_changes_nothing(ticket):
    ticket_id = ticket["ticketId"]

    response = http.patch(f"/tickets/{ticket_id}", json={"status": "RESOLVED"})

    assert response.status_code == 422
    assert response.json()["detail"] == (
        "A resolution note is required when the status is set to RESOLVED."
    )
    after = http.get(f"/tickets/{ticket_id}").json()["ticket"]
    assert after["status"] == "OPEN"


def test_resolving_with_a_resolution_works_and_adds_a_version(ticket):
    ticket_id = ticket["ticketId"]

    response = http.patch(
        f"/tickets/{ticket_id}",
        json={"status": "RESOLVED", "resolution": "Replaced faulty cable"},
    )

    assert response.status_code == 200
    updated = response.json()
    assert updated["status"] == "RESOLVED"
    assert updated["resolution"] == "Replaced faulty cable"
    assert updated["versionNo"] == 2

    versions = http.get(f"/tickets/{ticket_id}/versions").json()
    assert len(versions) == 2
    assert versions[0]["snapshot"]["status"] == "OPEN"
    assert versions[1]["snapshot"]["status"] == "RESOLVED"


def test_the_status_is_accepted_in_lower_case(ticket):
    response = http.patch(f"/tickets/{ticket['ticketId']}", json={"status": "closed"})

    assert response.status_code == 200
    assert response.json()["status"] == "CLOSED"


def test_an_update_that_changes_nothing_adds_no_version(ticket):
    response = http.patch(f"/tickets/{ticket['ticketId']}", json={"title": "Test ticket"})

    assert response.status_code == 200
    assert response.json()["versionNo"] == 1


# ----- Comments -----

def test_a_comment_is_stored_on_the_current_version(ticket):
    ticket_id = ticket["ticketId"]

    response = http.post(f"/tickets/{ticket_id}/comments", json={"body": "User called twice"})

    assert response.status_code == 201
    assert response.json()["versionNo"] == 1

    comments = http.get(f"/tickets/{ticket_id}").json()["comments"]
    assert len(comments) == 1
    assert comments[0]["body"] == "User called twice"


def test_a_comment_on_an_unknown_id_is_404():
    response = http.post(f"/tickets/{MISSING_ID}/comments", json={"body": "Hello"})

    assert response.status_code == 404


# ----- Delete -----

def test_delete_removes_the_ticket(ticket):
    ticket_id = ticket["ticketId"]

    response = http.delete(f"/tickets/{ticket_id}")
    assert response.status_code == 204

    response = http.get(f"/tickets/{ticket_id}")
    assert response.status_code == 404


def test_delete_with_an_unknown_id_is_404():
    response = http.delete(f"/tickets/{MISSING_ID}")

    assert response.status_code == 404
    assert response.json()["detail"] == f"Ticket {MISSING_ID} does not exist."


# ----- Search -----
#
# The search goes by meaning: the API keeps an embedding of every ticket's title and
# description, and returns the tickets closest to the question. The tests use a ticket
# about a monitor and questions that share no words with it.

@pytest.fixture
def monitor_ticket():
    """A ticket about a flickering monitor, for one test."""
    response = http.post(
        "/tickets",
        json={
            "title": "Monitor flickers",
            "description": "The screen on desk 14 flickers every few seconds.",
        },
    )
    assert response.status_code == 201
    created = response.json()

    yield created

    http.delete(f"/tickets/{created['ticketId']}")


def test_search_finds_a_ticket_by_meaning_without_shared_words(monitor_ticket):
    response = http.get("/tickets/search", params={"q": "the display keeps blinking"})

    assert response.status_code == 200
    matches = response.json()

    found = None
    for match in matches:
        if match["ticketId"] == monitor_ticket["ticketId"]:
            found = match

    assert found is not None
    # A match is a ticket as GET /tickets gives it, plus how well it fits.
    assert found["title"] == "Monitor flickers"
    assert found["status"] == "OPEN"
    assert found["match"] >= 0.3
    assert found["match"] <= 1


def test_search_returns_the_best_match_first(monitor_ticket):
    response = http.get("/tickets/search", params={"q": "the display keeps blinking", "limit": 20})

    assert response.status_code == 200
    scores = []
    for match in response.json():
        scores.append(match["match"])

    assert scores == sorted(scores, reverse=True)


def test_search_for_something_else_does_not_return_the_ticket(monitor_ticket):
    ids = ids_in(http.get("/tickets/search", params={"q": "the coffee machine"}))

    assert monitor_ticket["ticketId"] not in ids


def test_search_follows_a_changed_description(monitor_ticket):
    ticket_id = monitor_ticket["ticketId"]

    response = http.patch(
        f"/tickets/{ticket_id}",
        json={"title": "Printer out of toner", "description": "The printer on floor 2 prints blank pages."},
    )
    assert response.status_code == 200

    # The ticket is no longer about a monitor, and is found as what it is about now.
    assert ticket_id not in ids_in(http.get("/tickets/search", params={"q": "the display keeps blinking"}))
    assert ticket_id in ids_in(http.get("/tickets/search", params={"q": "no ink left in the printer"}))


def test_search_does_not_return_a_deleted_ticket(monitor_ticket):
    ticket_id = monitor_ticket["ticketId"]

    response = http.delete(f"/tickets/{ticket_id}")
    assert response.status_code == 204

    assert ticket_id not in ids_in(http.get("/tickets/search", params={"q": "the display keeps blinking"}))


def test_search_respects_the_limit(monitor_ticket):
    response = http.get("/tickets/search", params={"q": "the display keeps blinking", "limit": 1})

    assert response.status_code == 200
    assert len(response.json()) <= 1


def test_search_without_a_question_is_422():
    response = http.get("/tickets/search", params={"q": "  "})

    assert response.status_code == 422
    assert response.json()["detail"] == "The parameter 'q' is required and cannot be empty."


def test_search_with_a_limit_out_of_range_is_422_and_names_the_range():
    response = http.get("/tickets/search", params={"q": "monitor", "limit": 0})

    assert response.status_code == 422
    assert response.json()["detail"] == "'0' is not a valid limit. It must be between 1 and 20."
