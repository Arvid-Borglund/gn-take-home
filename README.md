# Ticketing API, GenAI agent, PR review bot and infrastructure

A support ticketing API with a database, an LLM agent that operates it from the command
line, a GitHub Action that reviews pull requests with the same LLM, and a Terraform
description of how the API would run on Azure.

| Part | What | Where |
|---|---|---|
| 1 | Ticketing API: ASP.NET Core and EF Core on PostgreSQL | `api/`, `db/` |
| 2 | GenAI agent: LangGraph in Python, with a command-line interface | `agent/` |
| 3 | PR review bot: a Python script run by GitHub Actions | `pr_review/`, `.github/workflows/pr-review.yml` |
| 4 | Terraform skeleton for Azure | `infra/` |

Around the four parts there is what it takes to run the system for real: tests of the
API, evals of the agent, a CI workflow, a deploy to a server with Kamal, Terraform for
that server with remote state, and a nightly database backup. Each has its own section
below.

## Run it

You need Docker with Compose, and the Azure OpenAI key from the assignment. Nothing else
has to be installed: the database, the API and the agent each run in their own container.

1. Clone the repository and go into it.

   ```bash
   git clone https://github.com/Arvid-Borglund/gn-take-home.git
   cd gn-take-home
   ```

2. Create `.env` from the example.

   ```bash
   cp .env.example .env
   ```

   Open `.env` and paste the key after `AZURE_OPENAI_API_KEY=`. The endpoint, the
   deployment and the API version are already filled in. (In the Windows command prompt
   the copy command is `copy .env.example .env`.)

3. Start the database and the API.

   ```bash
   docker compose up -d --build
   ```

   The API is now at http://localhost:8080, with Swagger at http://localhost:8080/swagger.
   The database starts empty.

4. Run the agent.

   ```bash
   docker compose run --rm agent
   ```

   Type a request in plain language, or a number from the menu to run one of the
   scenarios from the assignment. To run all of them without typing anything:

   ```bash
   docker compose run --rm agent python main.py --demo
   ```

   [docs/demo.md](docs/demo.md) is the output of that command.

5. Run the API tests (optional).

   ```bash
   docker compose run --rm tests
   ```

To stop everything and remove the database volume:

```bash
docker compose down -v
```

Ports 8080 and 5432 must be free. If one of them is taken, set `API_PORT` or `DB_PORT`
in `.env` (see `.env.example`).

## Part 1: the ticketing API

| Method | Path | What it does | Errors |
|---|---|---|---|
| POST | `/tickets` | Creates a ticket from `title` and `description`. It starts as `OPEN`. | 422 if a field is empty |
| GET | `/tickets` | All tickets. `?status=OPEN` keeps only that status. | 422 for an unknown status |
| GET | `/tickets/{id}` | One ticket with its comments. | 404 |
| PATCH | `/tickets/{id}` | Changes `title`, `description`, `status` or `resolution`. Only the fields that are sent change. | 404, 422 |
| DELETE | `/tickets/{id}` | Deletes the ticket with its comments and history. | 404 |
| POST | `/tickets/{id}/comments` | Adds a comment (`body`). | 404, 422 if empty |
| GET | `/tickets/{id}/versions` | The history of the ticket: one snapshot per change. | 404 |

The business rules:

- An id that does not exist gives **404**.
- A status other than `OPEN`, `RESOLVED` or `CLOSED` gives **422**.
- Setting the status to `RESOLVED` without a resolution note gives **422**.

Every error body is ProblemDetails (RFC 9457), and `detail` says exactly what was wrong (shortened here):

```json
{
  "title": "Unprocessable Entity",
  "status": 422,
  "detail": "'PROGRESS' is not a valid status. Valid statuses are: OPEN, RESOLVED, CLOSED."
}
```

How it is built:

- `Controllers/TicketsController.cs` only does HTTP. The rules live in
  `Services/TicketService.cs`, which throws one exception for "not found" and one for
  "not valid". `Errors/TicketExceptionHandler.cs` is the one place where those become
  404 and 422.
- The data is in PostgreSQL, in three tables (`db/init/001_schema.sql`). `ticket` holds
  the current state. `ticket_version` is an append-only history: a database trigger
  writes a snapshot for every change, so the history cannot be forgotten by application
  code. `ticket_comment` points at the version that was current when the comment was
  written. `created` and `updated` are not columns: they are the times of the first and
  the latest version.
- The schema is plain SQL and is the source of truth. EF Core maps to it and creates
  nothing. The database also has CHECK constraints for the status rules, as a backstop
  behind the API.

## Part 2: the agent

```
START -> agent -+- answer for the user ------------------------> END
                +- tool calls ---------------------> tools -> agent
                +- tool calls, one is a delete -> confirm -> tools -> agent
```

The agent is a LangGraph graph with three nodes (`agent/graph.py`). `agent` calls the
model with the tools bound. `tools` runs the tool calls the model asked for and hands
the results back. The two take turns until the model answers the user.

**Tools.** There is one tool per endpoint, seven in total (`agent/tools.py`), on top of
a small HTTP client (`agent/api_client.py`). On success a tool returns the JSON from the
API.

**Error handling.** A 4xx from the API is not an exception in the agent, it is a result.
The path of an error:

1. The API answers 422 with a `detail` message.
2. The client reads `detail` out of the ProblemDetails body.
3. The tool returns `API ERROR 422: 'PROGRESS' is not a valid status. Valid statuses
   are: OPEN, RESOLVED, CLOSED.` to the model.
4. The system prompt (`agent/prompts.py`) tells the model what to do with a result like
   that: do not retry with a guess, tell the user what was rejected and why, using the
   specifics in the message, and say what they can do next.

The API owns the rules. The `status` argument of the tools is a free string, and neither
the tool descriptions nor the prompt list the valid statuses. The agent sends what the
user asked for and learns what is valid from the API's answer. If the API gets a new
status, the agent does not have to change.

```text
you> Update ticket 1 to have the status 'PROGRESS'.
  [tool call]   update_ticket(ticket_id=1, status='PROGRESS')
  [tool result] API ERROR 422: 'PROGRESS' is not a valid status. Valid statuses are: OPEN, RESOLVED, CLOSED.
agent> The API rejected PROGRESS; valid statuses are OPEN, RESOLVED, and CLOSED. Choose one of those to update ticket 1.

you> Update ticket 1001 to 'CLOSED'.
  [tool call]   update_ticket(ticket_id=1001, status='CLOSED')
  [tool result] API ERROR 404: Ticket 1001 does not exist.
agent> Ticket 1001 does not exist, so it wasn’t updated. List tickets to find the correct ticket ID.
```

**Confirmation before a delete.** Deleting is permanent, so the graph does not run a
delete on the model's word alone. When the model asks for `delete_ticket`, the `confirm`
node stops the graph with `interrupt()` and the CLI asks the user. The graph continues
with the answer; a delete that was not confirmed is not run, and the model is told so.

**Memory.** The graph is compiled with an in-memory checkpointer. It keeps the
conversation between turns ("now close that ticket" works), and it is what lets the
graph stop at the confirmation and continue afterwards.

**The model.** This deployment rejects tool calls on the chat completions endpoint while
reasoning is on, and the API version from the assignment is older than the Responses
API. The agent therefore sets `reasoning_effort="none"` (see `build_llm` in
`agent/main.py`).

In the chat, `new` starts a new conversation, `menu` shows the scenarios again and
`quit` exits.

## Part 3: the PR review bot

`.github/workflows/pr-review.yml` runs on every pull request that is opened or gets new
commits. It runs `pr_review/analyze_pr.py`, which:

1. gets the diff of the pull request from the GitHub API,
2. sends it to the model and asks for a summary and suggested improvements,
3. posts the answer as a comment on the pull request.

If the bot has already commented on the pull request, the script updates that comment
instead of adding another, so a pull request always has exactly one review comment, and
it always describes the latest commit.

[Pull request #1](https://github.com/Arvid-Borglund/gn-take-home/pull/1), which added
the Terraform files, was reviewed by the bot.

To run it in your own copy of the repository, add these under Settings, Secrets and
variables, Actions, and open a pull request:

| Kind | Name | Value |
|---|---|---|
| Secret | `AZURE_OPENAI_API_KEY` | the key |
| Variable | `AZURE_OPENAI_ENDPOINT` | `https://external-api.openai.azure.com/` |
| Variable | `AZURE_OPENAI_DEPLOYMENT` | `gpt-6-luna-c1` |
| Variable | `AZURE_OPENAI_API_VERSION` | `2024-12-01-preview` |

The workflow's token can read the code and write to pull requests, nothing else.

## Part 4: Terraform for Azure

`infra/` describes the API running as a container in Azure App Service: a resource
group, an App Service plan and a Linux Web App. Nothing is applied.

```bash
cd infra
terraform init
terraform validate
```

The database is left out on purpose, since the task asks for the minimum. Its
connection string is a variable; in a real setup the database would be an Azure Database
for PostgreSQL in the same file.

`infra/hetzner/` is a second, separate Terraform configuration: the server the API is
actually deployed on. It is described under [The server as code](#the-server-as-code).

## Tests and CI

`tests/test_api.py` tests the API from the outside, over HTTP, against the running
containers. The tests check the status codes and the exact `detail` message of every
business-rule error, because those messages are what the agent builds its answers on.
Each test creates the ticket it needs and removes it afterwards.

`.github/workflows/ci.yml` runs on every pull request and on every push to main:

| Job | What it does |
|---|---|
| API tests | Starts the database and the API with the same compose command as above, and runs the tests. |
| Agent image | Builds the agent image and checks that the program loads. It makes no model call; the evals below do that, in a workflow of their own. |
| Terraform validate | `terraform fmt -check`, `init` and `validate` on `infra/`. |
| API image | Builds the API image. On main it is pushed to the GitHub container registry, tagged with the commit SHA. |

The image is built once per commit and never rebuilt for a deploy: a deploy points at
one of the published tags.

## Evals

The tests above say whether the API keeps its contract. The evals say whether the agent
behaves: `agent/evals/cases.yaml` holds 14 fixed questions with fixed expectations, and
`agent/evals/run.py` sends each one through the real graph, with the real model and the
real API.

```bash
docker compose run --rm agent python evals/run.py
```

Before every case the runner creates four known tickets, and afterwards it removes them.
A case states which tools the agent must call, with which arguments, and which state the
tickets must be in when it is done. Some examples:

- `'PROGRESS'` must lead to exactly one `update_ticket` call, with the status as the
  user wrote it, an answer that names the three valid statuses, and an unchanged ticket.
  A second call with a guessed status fails the case.
- "Close the ticket about the flickering monitor" must lead to `list_tickets` and then
  `update_ticket` on the monitor ticket. The printer ticket must still be open.
- "Delete ticket 4" with the confirmation declined: the ticket must still exist.
  With the confirmation given: it must be gone.

The checks are about what the agent did, not how it phrased it. The wording of an answer
is only checked where something specific has to be in it.

`.github/workflows/evals.yml` runs the evals on pull requests and pushes that touch the
agent, the API or the schema, and on request. It is a workflow of its own because it
calls a language model: it costs a little, takes a couple of minutes, and can fail for
reasons that are not in the code. It does not decide whether an image is published.
Without a model key in the repository it skips, with a notice.

## Deploy

`.github/workflows/deploy.yml` deploys the API and its database to a server with
[Kamal](https://kamal-deploy.org), over SSH. It is started by hand (Actions, Deploy, Run
workflow). That click is the approval; nothing is deployed automatically.

```
pull request     CI: tests, image build, Terraform validation (and the evals, when the agent changed)
merge to main    CI again, and the API image is pushed to GHCR, tagged with the commit SHA
Run workflow     Kamal points the server at the image of one commit
```

What a deploy does (`config/deploy.yml`):

- The server pulls the image of the chosen commit. Nothing is built.
- Kamal starts the new container next to the old one. kamal-proxy, which terminates TLS
  with a Let's Encrypt certificate, sends traffic to the new container only when
  `GET /health` answers 200. Then the old one is stopped.
- PostgreSQL runs as its own container on the same server. No port is published: only
  the API reaches it, over Docker's network. The schema is the same
  `db/init/001_schema.sql` as locally.
- Rolling back is deploying an older commit SHA.

What has to exist before the first deploy:

- the secret `SSH_PRIVATE_KEY`: a key pair made for the pipeline, with the public half
  in the server's `authorized_keys`,
- a GitHub environment named `production`, open to runs from main only, with the secret
  `POSTGRES_PASSWORD`,
- the server's host key in `.github/known_hosts`,
- DNS for the host names in `config/deploy.yml`, pointing at the server.

`scripts/setup-deploy-access.sh` does the first two. The first run is started with
`bootstrap` ticked: it installs Docker on the server and starts the database.

### The server as code

`infra/hetzner/` is the Terraform for the server at Hetzner: the machine, its reserved
address and the firewall (22 for the deploy, 80 and 443 for the proxy, and no 5432:
the database is never reachable from outside).

The server existed before this configuration did, so nothing was created from it. The
`import` blocks adopt the existing resources into the state, and from then on
`terraform plan` answers one question: does the machine still look like the code says?
An empty plan means yes.

- **State** is kept in Cloudflare R2 through the S3 backend, with a lock file, and not
  on the machine that happened to run Terraform. R2 rather than the server provider's
  own storage, so that the state does not live with the thing it describes.
- **`.github/workflows/terraform.yml`** makes a plan on every pull request that touches
  `infra/hetzner/`, and writes it to the summary of the run. Apply is only run by hand.
- **The Hetzner token in the repository is read-only.** A plan needs no more, and
  neither does adopting the existing resources. This repository can describe the server
  and check it, but not change it or delete it.

To check the files without any credentials:

```bash
cd infra/hetzner
terraform init -backend=false
terraform validate
```

### Backups

Two kinds, for two different losses:

- **The machine.** Hetzner's own backup takes a daily image of the whole server
  (`backups = true` in `infra/hetzner/main.tf`). It saves the server.
- **The data.** `.github/workflows/backup-db.yml` runs every night: `pg_dump` inside
  the postgres container, pulled out over SSH by the runner and uploaded to R2. It saves
  the data, and it can be restored anywhere.

Before a dump is uploaded it is restored into a scratch database on the same PostgreSQL,
and one rule of the schema is checked on the result (every ticket has at least one
version). A backup that has never been read back is not a backup. The newest 14 dumps
are kept.

The runner pulls the backup; the server does not push it. The R2 keys exist only as
GitHub secrets, so a server that has been taken over cannot delete its own backups.

## Layout

```
api/          the ticketing API (C#)
db/           the database image and the schema
agent/        the agent and its CLI (Python)
tests/        tests of the API over HTTP (Python)
pr_review/    the PR review script (Python)
infra/        Terraform for Azure (part 4), and in hetzner/ for the real server
docs/         the demo transcript
config/       the Kamal deploy configuration
.kamal/       the secrets Kamal expects (names only, no values)
scripts/      one-time setup of the pipeline's access to the server
.github/      the workflows: CI, evals, PR review, deploy, Terraform and backup
compose.yaml  database, API, agent and tests as containers
```
