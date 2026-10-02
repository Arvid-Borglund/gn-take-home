"""HTTP client for the ticket API: one method per endpoint.

Every method returns an ApiResult instead of raising on a 4xx. A business-rule error
(404, 422) is an expected answer, not a crash: the caller gets the status code and the
message the API wrote, and decides what to do with it.
"""

import time
from typing import Optional

import httpx


class ApiResult:
    def __init__(self):
        self.ok = False        # True for a 2xx answer
        self.status_code = 0   # HTTP status code; 0 when the API could not be reached
        self.data = None       # parsed JSON body of a successful answer (None for 204)
        self.error = ""        # what went wrong, in the API's own words when it gave any


class TicketApiClient:
    def __init__(self, base_url: str):
        self.base_url = base_url
        self._http = httpx.Client(base_url=base_url, timeout=10.0)

    # POST /tickets
    def create_ticket(self, title: str, description: str) -> ApiResult:
        body = {"title": title, "description": description}
        return self._send("POST", "/tickets", body, None)

    # GET /tickets  or  GET /tickets?status=OPEN
    def list_tickets(self, status: Optional[str]) -> ApiResult:
        params = None
        if status is not None:
            params = {"status": status}
        return self._send("GET", "/tickets", None, params)

    # GET /tickets/search?q=...&limit=...
    def search_tickets(self, query: str, limit: int) -> ApiResult:
        params = {"q": query, "limit": limit}
        return self._send("GET", "/tickets/search", None, params)

    # GET /tickets/{id}
    def get_ticket(self, ticket_id: int) -> ApiResult:
        return self._send("GET", f"/tickets/{ticket_id}", None, None)

    # PATCH /tickets/{id}: only the fields that were given are sent, so only they change.
    def update_ticket(
        self,
        ticket_id: int,
        title: Optional[str],
        description: Optional[str],
        status: Optional[str],
        resolution: Optional[str],
    ) -> ApiResult:
        body = {}
        if title is not None:
            body["title"] = title
        if description is not None:
            body["description"] = description
        if status is not None:
            body["status"] = status
        if resolution is not None:
            body["resolution"] = resolution
        return self._send("PATCH", f"/tickets/{ticket_id}", body, None)

    # DELETE /tickets/{id}
    def delete_ticket(self, ticket_id: int) -> ApiResult:
        return self._send("DELETE", f"/tickets/{ticket_id}", None, None)

    # POST /tickets/{id}/comments
    def add_comment(self, ticket_id: int, body_text: str) -> ApiResult:
        body = {"body": body_text}
        return self._send("POST", f"/tickets/{ticket_id}/comments", body, None)

    # GET /tickets/{id}/versions
    def list_versions(self, ticket_id: int) -> ApiResult:
        return self._send("GET", f"/tickets/{ticket_id}/versions", None, None)

    def _send(self, method: str, path: str, body: Optional[dict], params: Optional[dict]) -> ApiResult:
        result = ApiResult()

        try:
            response = self._http.request(method, path, json=body, params=params)
        except httpx.HTTPError as error:
            # No answer at all: the API is down, the address is wrong, or it timed out.
            result.error = f"The ticket API could not be reached at {self.base_url} ({type(error).__name__})."
            return result

        result.status_code = response.status_code

        if response.status_code >= 200 and response.status_code < 300:
            result.ok = True
            if len(response.content) > 0:
                result.data = response.json()
            return result

        result.error = self._read_error(response)
        return result

    def _read_error(self, response: httpx.Response) -> str:
        # The API answers errors as ProblemDetails (RFC 9457):
        #   {"title": "Unprocessable Entity", "status": 422, "detail": "'PROGRESS' is not ..."}
        # "detail" is the specific message: which id is missing, which statuses are valid.
        try:
            problem = response.json()
        except ValueError:
            problem = None

        if isinstance(problem, dict):
            detail = problem.get("detail")
            if detail:
                return detail

            # ASP.NET's own model validation (a field of the wrong type, broken JSON)
            # has no "detail" but a list of messages per field under "errors".
            errors = problem.get("errors")
            if isinstance(errors, dict):
                parts = []
                for field in errors:
                    for message in errors[field]:
                        parts.append(f"{field}: {message}")
                if len(parts) > 0:
                    return "; ".join(parts)

            title = problem.get("title")
            if title:
                return title

        return f"The API answered {response.status_code} without an explanation."


def wait_for_api(client: TicketApiClient) -> bool:
    """True when the ticket API answers. Tries for about 15 seconds, because the API
    container may still be starting when the agent container does."""
    attempts = 0
    while attempts < 15:
        result = client.list_tickets(None)
        if result.status_code != 0:
            return True
        attempts += 1
        time.sleep(1)
    return False
