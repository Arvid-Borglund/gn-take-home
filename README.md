# Ticketing API, GenAI agent, PR review bot and infrastructure

A support ticketing API with a database, an LLM agent that operates it, a GitHub Action
that reviews pull requests with the same LLM, and a Terraform description of how the API
would run on Azure.

| Part | What | Where |
|---|---|---|
| 1 | Ticketing API: ASP.NET Core and EF Core on PostgreSQL | `api/`, `db/` |
| 2 | GenAI agent: LangGraph in Python, with a web interface to talk to it | `agent/`, `web/` |
| 2, bonus | MCP server for the ticketing API. The agent gets its tools from it. | `agent/mcp_server.py`, `agent/mcp_client.py` |
| 3 | PR review bot: a Python script run by GitHub Actions | `pr_review/`, `.github/workflows/pr-review.yml` |
| 4 | Terraform skeleton for Azure | `infra/` |

Around the four parts there is what it takes to run the system for real: tests of the
API, evals of the agent, a CI workflow, a deploy to a server with Kamal, Terraform for
that server with remote state, and a nightly database backup. Each has its own section
below.

The assignment says that a command-line interface to the agent is sufficient. The
interface here is a web application instead (`web/`): the steps the agent takes, the
tickets and their history are easier to follow on a page than in a terminal.

The whole system runs at https://lundona.com, behind a login. The user name and the
password came with the link to this repository. The agent there calls the model with
the key from the assignment: when that key is closed the chat answers with the model's
error, and the rest (the API, the ticket viewer and the history) keeps working.

## Run it

You need Docker with Compose, and the Azure OpenAI key from the assignment. Nothing else
has to be installed: the database, the API, the agent and the web interface each run in
their own container.

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

3. Start everything.

   ```bash
   docker compose up -d --build
   ```

   The web interface is now at http://localhost:8081, and the API at
   http://localhost:8080 with Swagger at http://localhost:8080/swagger. The database
   starts empty. The first build takes a few minutes, because it installs the Angular
   toolchain inside the web image.

4. Talk to the agent at http://localhost:8081.

   Type a request in plain language, or pick one of the seven example requests: the six
   from the assignment, and a delete that shows the confirmation step. They are listed
   on an empty conversation, and behind the Scenarios button next to the input during
   one. Above every answer are the tool calls the agent made and what the API returned.
   See [The web interface](#the-web-interface).

5. Run the API tests (optional).

   ```bash
   docker compose run --rm tests
   ```

6. Run the evals (optional): 14 fixed questions through the agent, with fixed
   expectations on what it does. See [Evals](#evals).

   ```bash
   docker compose run --rm agent python evals/run.py
   ```

To stop everything and remove the database volume:

```bash
docker compose down -v
```

Ports 8080, 5432 and 8081 must be free. If one of them is taken, set `API_PORT`,
`DB_PORT` or `WEB_PORT` in `.env` (see `.env.example`).

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

**Tools.** There is one tool per endpoint, seven in total. The agent does not call the
API itself: it gets the tools from an MCP server (`agent/mcp_server.py`), which calls
the API through a small HTTP client (`agent/api_client.py`). On success a tool returns
the JSON from the API. How the server and the agent's side of it are built is described
under [Bonus: the MCP server](#bonus-the-mcp-server).

**Error handling.** A 4xx from the API is not an exception in the agent, it is a result.
The path of an error:

1. The API answers 422 with a `detail` message.
2. The client reads `detail` out of the ProblemDetails body.
3. The tool returns `API ERROR 422: 'PROGRESS' is not a valid status. Valid statuses
   are: OPEN, RESOLVED, CLOSED.` to the model, as a tool result that is marked as an
   error.
4. The system prompt (`agent/prompts.py`) tells the model what to do with a result like
   that: do not retry with a guess, tell the user what was rejected and why, using the
   specifics in the message, and say what they can do next.

The API owns the rules. The `status` argument of the tools is a free string, and neither
the tool descriptions nor the prompt list the valid statuses. The agent sends what the
user asked for and learns what is valid from the API's answer. If the API gets a new
status, the agent does not have to change.

Two of the requests from the assignment, with the steps the web interface shows above
the answer:

```text
Update ticket 1 to have the status 'PROGRESS'.
  tool call    update_ticket(ticket_id=1, status='PROGRESS')
  tool result  API ERROR 422: 'PROGRESS' is not a valid status. Valid statuses are: OPEN, RESOLVED, CLOSED.
  answer       The API rejected PROGRESS; valid statuses are OPEN, RESOLVED, and CLOSED. Choose one of those to update ticket 1.

Update ticket 1001 to 'CLOSED'.
  tool call    update_ticket(ticket_id=1001, status='CLOSED')
  tool result  API ERROR 404: Ticket 1001 does not exist.
  answer       Ticket 1001 does not exist, so it wasn’t updated. List tickets to find the correct ticket ID.
```

**Confirmation before a delete.** Deleting is permanent, so the graph does not run a
delete on the model's word alone. When the model asks for `delete_ticket`, the `confirm`
node stops the graph with `interrupt()` and the web interface asks the user, with a
Delete and a Keep it button. The graph continues with the answer; a delete that was not
confirmed is not run, and the model is told so.

**Memory.** The graph is compiled with a checkpointer, which keeps its state in
PostgreSQL. It keeps the conversation between turns ("now close that ticket" works), and
it is what lets the graph stop at the confirmation and continue afterwards.

**The model.** This deployment rejects tool calls on the chat completions endpoint while
reasoning is on, and the API version from the assignment is older than the Responses
API. The agent therefore sets `reasoning_effort="none"` (see `build_llm` in
`agent/model.py`).

## Bonus: the MCP server

```
agent  --MCP over stdio-->  mcp_server.py  --HTTP-->  ticket API
```

`agent/mcp_server.py` exposes the ticketing API as an MCP server, built with the official
MCP Python SDK. The agent takes its tools from that server instead of calling the API
itself. That goes for everything that runs the agent: the web interface and the evals.

The four steps of the task:

1. **The server.** An `MCPServer` from the SDK, run over stdio: the client starts the
   file as a subprocess and the two talk over its stdin and stdout. No port is opened
   and no extra container is needed.
2. **The tools.** One tool per endpoint, seven in total. Each tool carries the MCP
   annotations that say what it does to the data: the three reading tools are marked
   read-only, and `delete_ticket` is marked destructive.
3. **The handlers.** A handler calls the API through the HTTP client
   (`agent/api_client.py`) and returns a text for the model. A 4xx from the API becomes
   a tool result with the API's `detail` message as text and with `isError` set, which
   is how MCP says that the call was made and failed. On the wire:

   ```json
   {"content": [{"type": "text", "text": "API ERROR 404: Ticket 424242 does not exist."}], "isError": true}
   ```

4. **The agent as MCP client** (`agent/mcp_client.py`). The agent starts the server,
   asks it which tools it has (`tools/list`) and wraps each one as a LangChain tool
   with the name, the description and the argument schema the server gave. When the
   model calls a tool, the wrapper forwards the call (`tools/call`) and hands the text
   of the result back. The client side is written directly on the SDK, without an
   adapter library, so those three steps are visible in the code.

What the split between the agent and the server means:

- **The graph does not know where its tools come from.** It gets a list of tools. The
  error handling of Part 2 is the same: the model reads the `API ERROR 422: ...` text
  and the rules in the system prompt apply.
- **The confirmation before a delete stays in the agent.** The server carries out a
  delete when it is asked to. Asking the user first is the client's job, and the
  `confirm` node of the graph does it.
- **The server gets only what it needs.** A subprocess started over stdio does not
  inherit the agent's environment. The agent passes the address of the API on, and
  not the model key.
- **The server lives as long as what started it.** The web server (`agent/server.py`)
  starts it once, when it starts itself, and uses it for every conversation. The evals
  start one for a run.
- **A dead server is started again.** If the MCP server process dies while the web
  server runs, the web server stays up. Before every tool call the connection
  (`McpConnection` in `agent/mcp_client.py`) asks the server a question that changes nothing
  (`tools/list`; MCP no longer has a ping). If there is no answer, it starts the
  server again and then makes the call. A lock makes sure that two calls at the same
  time start one server, not two. The call itself is never repeated: if the server
  dies in the middle of a call, nobody knows whether the ticket API was already
  called, and a repeated `create_ticket` would make a second ticket. That call comes
  back as an error, and the next one heals the connection.

**The agent without the server.** `--direct` runs the same agent with tools of its own
(`agent/tools.py`) that call the API without the MCP step. The web server and the evals
both take the flag. It is kept as a fallback, and as something to compare the MCP path
with. That means the seven tools are written down twice, in `agent/mcp_server.py` and in
`agent/tools.py`. Two checks keep the two the same:

```bash
docker compose run --rm agent python check_mcp.py
docker compose run --rm agent python evals/run.py --direct
```

The first starts the server, lists its tools and compares them with the direct tools:
names, descriptions and arguments. It needs no model and CI runs it. The second runs
the evals below without the MCP server; all 14 cases pass both ways.

A third check, also without a model and also run by CI, kills the server process and
checks that the next call starts it again, once:

```bash
docker compose run --rm agent python check_mcp_restart.py
```

Other MCP clients can use the server too. For a client that starts its servers by
command, the command is:

```bash
docker compose run --rm -T agent python mcp_server.py
```

## The web interface

The web interface is how the agent is used. The assignment says that a command-line
interface is sufficient; this is what was built instead.

```
browser -> nginx (web/) -+- /              the Angular app
                         +- /api/chat/     the agent server (agent/server.py) -> the graph
                         +- /api/tickets/  the ticket API, GET only
```

What is in it:

- **The chat** is the main area. Above every answer are the tool calls the agent made
  and what the API returned, so an error can be followed from the API's message to the
  agent's answer.
- **The example requests** are one click each: the six from the assignment and a
  delete, with the ids of real tickets filled in. They are listed on an empty
  conversation, and behind the Scenarios button next to the input during one.
- **The history** to the left lists the conversations.
- **Ticket numbers in an answer are links**, and the tickets an answer is about are
  listed under it. A click opens the ticket in a viewer next to the chat, one tab per
  ticket.
- **Version history** in the viewer is a timeline: one section per version of the
  ticket, coloured by its status, with a pin for every comment at the time it was
  written. A click on a section shows the ticket as it was in that version.
- **A delete** shows the agent's question with a Delete and a Keep it button. Behind it
  is the `confirm` node of the graph, stopped at `interrupt()`.

How it is built:

- `agent/server.py` puts the graph behind HTTP with FastAPI. A message is a POST, and
  the answer is a stream of server-sent events, one per thing that happens in the
  graph: a tool call, a tool result, the answer, or the question before a delete. The
  tools come from the MCP server: the web server starts it once, and
  `/api/chat/health` says `"tools": "mcp"`.
- **A turn runs to its end even if the browser hangs up.** The turn is a task of its
  own that runs the graph and puts every event in a queue; the HTTP response only reads
  from that queue. A closed tab or a reload stops the reader, not the turn. Otherwise
  the graph could be stopped after the model has asked for a tool and before the tool
  has answered, and the model refuses to continue a conversation that ends that way.
  A conversation runs one turn at a time: a message that arrives while a turn is
  running gets a 409. `agent/check_turns.py` checks this with the real graph, a
  scripted model and a real database, and CI runs it. A page that opens a conversation in the middle of a
  turn locks the input and reads the conversation again every other second until the
  turn is over, so the reply is seen growing there too. A 409 is shown above the input,
  with the text that was typed still in it.
- **The viewer only reads.** It gets the tickets straight from the ticket API, through
  nginx, and nginx refuses everything but GET on that path. Every change to a ticket
  goes through the agent.
- **A link is never taken from the model's text.** A ticket number becomes a link only
  when a tool call in the same turn was about that ticket and the API did not answer
  that it is missing (`agent/transcript.py`). A number the model made up stays text.
- **The conversations are stored in PostgreSQL**, in the same database as the tickets
  (`agent/conversations.py`). The list of them is the table `conversation`
  (`db/init/003_conversations.sql`), one row per conversation with the user it belongs
  to. Their messages are kept by the graph's checkpointer, which in the web server is
  LangGraph's PostgreSQL checkpointer; it creates its own tables when the server
  starts. A conversation is therefore still there after a restart of the container,
  including a question before a delete that has not been answered yet. The evals keep
  their state in memory.
- **A conversation belongs to the user who started it.** nginx does the login and puts
  the login name in the header `X-User` on what it passes on to the agent server.
  Listing, reading, writing and deleting only see the user's own conversations; someone
  else's conversation is a 404. Without a login in front (the local setup) everything
  belongs to one user, `local`.
- One thing is still only in the memory of the process: the task that runs a turn. A
  turn that is running when the container is restarted is not continued, and its
  conversation can be left ending in a tool call without a result.
- `web/` is an Angular app. Its image builds it with Node and serves the result with
  nginx; Node is not in the final image.

### The login

Locally the web interface is open. The deployed one is behind a login, and so is
everything else on that address: the chat, the API and its Swagger page.

```
browser -> nginx: is this request logged in? -> GET /auth/check on the API -> app_user in PostgreSQL
```

- **The users are in the database, and a password is never stored.** A row in
  `app_user` (`db/init/002_users.sql`) holds a random salt, made when the user is
  created, and the PBKDF2 hash of the salt and the password
  (`api/Services/PasswordHasher.cs`: HMAC-SHA512, 100 000 rounds, the settings ASP.NET
  Core Identity uses). The salt gives two users with the same password different
  hashes and makes ready-made tables of hashed passwords useless. The rounds make
  every guess slow for someone who has got hold of the table.
- **The browser logs in with basic auth.** It sends the user name and the password
  with every request, which is why the site is only served over HTTPS. nginx does not
  know the users: before it serves anything it passes the headers of the request to
  `GET /auth/check` on the API (`auth_request` in `web/nginx/private/on.conf`). The API
  hashes the given password with the user's salt and compares the result with the
  stored hash, in a way that takes the same time wherever the two differ. 200 lets
  the request through, 401 makes the browser ask for a login.
- **The API creates the first user when it starts**, from two settings
  (`SeedUser__Username` and `SeedUser__Password`), unless that user already exists. On
  the server the two come from GitHub secrets, like the other secrets of the deploy.
  The database, and so every backup of it, holds the salt and the hash only.
- **nginx tells the agent server who is logged in**, in the header `X-User`. The value
  comes from the API's answer to the check, and a header with that name sent by the
  browser is dropped. It is what makes a conversation belong to its user.
- **Every request pays for one hash**, about a tenth of a second on the server,
  because basic auth has no session: the password comes with every request and is
  checked every time. A session after one login would take that cost away and bring
  session handling with it. With a handful of users, the simple way was the better
  trade.

To see it locally, put `SITE_PRIVATE=on` in `.env` and start the web interface again.
The login is `demo` / `demo`, a local default like the database password in
`compose.yaml`.

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
Each test creates the ticket it needs and removes it afterwards. The login check is
tested the same way: no login, the right one, a wrong password and an unknown user.

`.github/workflows/ci.yml` runs on every pull request and on every push to main:

| Job | What it does |
|---|---|
| API tests | Starts the database and the API with compose and runs the tests. |
| Agent image | Builds the agent image, checks that the server loads, checks that the MCP server offers the same tools as the direct ones, checks that a killed MCP server is started again, and checks, against a real database, that a turn in the web server survives a reader that hangs up and that a conversation is kept for its user. It makes no model call; the evals below do that, in a workflow of their own. |
| Terraform validate | `terraform fmt -check`, `init` and `validate` on `infra/`. |
| API image | Builds the API image. On main it is pushed to the GitHub container registry, tagged with the commit SHA. |
| Agent and web images | Builds the agent image and the web image, which is also the check that the Angular app compiles. On main they are pushed like the API image. |

The images are built once per commit and never rebuilt for a deploy: a deploy points at
the published tags of one commit.

## Evals

The tests above say whether the API keeps its contract. The evals say whether the agent
behaves: `agent/evals/cases.yaml` holds 14 fixed questions with fixed expectations, and
`agent/evals/run.py` sends each one through the real graph, with the real model, the
MCP server and the real API.

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

`.github/workflows/deploy.yml` deploys the API with its database, the agent server and
the web interface to a server with [Kamal](https://kamal-deploy.org), over SSH. It is
started by hand (Actions, Deploy, Run workflow). That click is the approval; nothing is
deployed automatically.

The result is at https://lundona.com. The first deploy, onto an empty server, installed
Docker, started the database with the schema and brought up the three services in three
minutes.

```
pull request     CI: tests, image builds, Terraform validation (and the evals, when the agent changed)
merge to main    CI again, and the images are pushed to GHCR, tagged with the commit SHA
Run workflow     Kamal points the server at the images of one commit
```

What runs on the server (`config/deploy.yml`, `deploy.agent.yml`, `deploy.web.yml`):

```
internet -> kamal-proxy (TLS) -> web: nginx, asks for the login -+- the Angular app
                                                                 +- agent server -> language model
                                                                 +- API -> PostgreSQL
```

- **The web container is the only way in.** kamal-proxy terminates TLS with a Let's
  Encrypt certificate and knows one service, the web interface. The API and the agent
  server have no address of their own: nginx passes requests on to them over Docker's
  network.
- **Everything is behind one login.** nginx asks for a user name and a password (basic
  auth) on the app, the chat, the API and its Swagger page, and the API checks them
  against the users in the database ([The login](#the-login)). Behind the chat is a
  language model that costs money per message, so it is not left open. Two paths need
  no login: `/up`, which the proxy's health check uses, and `/health`, which says
  whether the API reaches its database. The deploy fails if the front page answers
  anything but 401 without a login, and if the login from the secrets is not accepted
  afterwards.
- The server pulls the images of the chosen commit. Nothing is built.
- For the web interface, Kamal starts the new container next to the old one, and the
  proxy sends traffic to the new one only when its health check answers 200. Then the
  old one is stopped.
- PostgreSQL runs as its own container on the same server. No port is published: it is
  only reached over Docker's network.
- **The schema is the files in `db/init/`, the same as locally.** Every statement in
  them only creates what is missing, and the deploy runs all of them on every deploy.
  That is how a new table reaches a database that already has data in it. It covers
  additions; changing a column that exists would take a migration tool.
- Rolling back is deploying an older commit SHA.

What has to exist before the first deploy:

- the secret `SSH_PRIVATE_KEY`: a key pair made for the pipeline, with the public half
  in the server's `authorized_keys`,
- a GitHub environment named `production`, open to runs from main only, with the
  secrets `POSTGRES_PASSWORD`, `WEB_LOGIN_USER` and `WEB_LOGIN_PASSWORD`. The last two
  are the login to the web interface: the API creates that user when it starts,
- the secret `AZURE_OPENAI_API_KEY`, the same one the PR review bot uses,
- the server's host key in `.github/known_hosts`,
- DNS for the host names in `config/deploy.web.yml`, pointing at the server.

`scripts/setup-deploy-access.sh` does the first two, except for the login. The first
run is started with `bootstrap` ticked: it installs Docker on the server and starts the
database.

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
agent/        the agent: the graph, its web server, the MCP server and the evals (Python)
web/          the web interface (Angular, served by nginx)
tests/        tests of the API over HTTP (Python)
pr_review/    the PR review script (Python)
infra/        Terraform for Azure (part 4), and in hetzner/ for the real server
config/       the Kamal deploy configuration
.kamal/       the secrets Kamal expects (names only, no values)
scripts/      one-time setup of the pipeline's access to the server
.github/      the workflows: CI, evals, PR review, deploy, Terraform and backup
compose.yaml  database, API, agent, tests and the web interface as containers
```
