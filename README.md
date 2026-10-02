# Ticketing API, GenAI agent, PR review bot and infrastructure

A support ticketing API with a database, an LLM agent that operates it, a GitHub Action
that reviews pull requests with the same LLM, and a Terraform description of how the API
would run on Azure.

| Part | What | Where |
|---|---|---|
| 1 | Ticketing API: ASP.NET Core and EF Core on PostgreSQL, with a search by meaning (pgvector) | `api/`, `db/`, `embedder/`, [Part 1 in the wiki](https://github.com/Arvid-Borglund/gn-take-home/wiki/Part-1-The-ticketing-API) |
| 2 | GenAI agent: LangGraph in Python, with a web interface to talk to it | `agent/`, `web/`, [Part 2](https://github.com/Arvid-Borglund/gn-take-home/wiki/Part-2-The-agent) and [The web interface](https://github.com/Arvid-Borglund/gn-take-home/wiki/The-web-interface) in the wiki |
| 2, bonus | MCP server for the ticketing API. The agent gets its tools from it. | `agent/mcp_server.py`, `agent/mcp_client.py`, [The MCP server](https://github.com/Arvid-Borglund/gn-take-home/wiki/The-MCP-server) in the wiki |
| 3 | PR review bot: a Python script run by GitHub Actions | `pr_review/`, `.github/workflows/pr-review.yml`, [Part 3 in the wiki](https://github.com/Arvid-Borglund/gn-take-home/wiki/Part-3-The-PR-review-bot) |
| 4 | Terraform skeleton for Azure | `infra/`, [Part 4 in the wiki](https://github.com/Arvid-Borglund/gn-take-home/wiki/Part-4-Terraform-for-Azure) |
| 5, bonus | One design decision I would change in production | [Part 5](#part-5-what-i-would-change-in-production) |

**To try it without any setup:** the whole system runs at https://lundona.com, behind a
login. The user name and the password came with the link to this repository. Nothing
has to be installed and no API key is needed.

Everything was developed against the Azure OpenAI model from the assignment, and that
is what the instructions below use. Just before handing in, the deployed agent was
switched to a model of my own, because the key from the assignment stops working: Qwen
3.6 (27B), served by Ollama on a machine with an RTX 5090 in my living room. The server
is at Hetzner in Helsinki and reaches the model through a reverse SSH tunnel. The evals
pass 16 of 16 with both models. If that machine is off, the chat answers with the
model's error, and the rest (the API, the ticket viewer and the history) keeps working.

## Run it

You need Docker with Compose, and the Azure OpenAI key from the assignment. Nothing else
has to be installed: the database, the embedding service, the API, the agent and the web
interface each run in their own container.

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
   starts with ten example tickets. The first build takes a few minutes, because it
   installs the Angular toolchain inside the web image.

4. Talk to the agent at http://localhost:8081.

   Type a request in plain language, or pick one of the seven example requests: the six
   from the assignment, and a delete that shows the confirmation step. They are listed
   on an empty conversation, and behind the Scenarios button next to the input during
   one. Above every answer are the tool calls the agent made and what the API returned.
   See [The web interface](https://github.com/Arvid-Borglund/gn-take-home/wiki/The-web-interface).

5. Run the API tests (optional).

   ```bash
   docker compose run --rm tests
   ```

6. Run the evals (optional): 16 fixed questions through the agent, with fixed
   expectations on what it does. See [Evals](https://github.com/Arvid-Borglund/gn-take-home/wiki/Tests-CI-and-evals#evals).

   ```bash
   docker compose run --rm agent python evals/run.py
   ```

To stop everything and remove the database volume:

```bash
docker compose down -v
```

Ports 8080, 5432 and 8081 must be free. If one of them is taken, set `API_PORT`,
`DB_PORT` or `WEB_PORT` in `.env` (see `.env.example`).

## Part 5: what I would change in production

**The design decision: the login.** The web interface has a user system of its own: a
table of users with a salted hash each, and basic auth in front of everything. It could
hold many users, but it is built as a standalone application with accounts of its own.
A tool like this is normally one of many that a company gives its employees, and it
should not need a separate account. In production I would not have a user system of my
own at all. The people who would use this already have an account with their employer,
and the application should accept that account: single sign-on through the identity
provider the organisation already runs. For an organisation on Azure that is Microsoft
Entra ID.

What that changes:

- Nobody gets one more password to remember, and people can start using the
  application the day it is there, with the login they already use for everything else.
- There is no user table, no password hashing and no password reset to build, run and
  keep safe. An account that is closed when someone leaves is closed here too.
- The application gets to know who the user is from a source it can trust, with the
  groups that person is in. Today everyone who is logged in can do everything. With
  the directory behind it, who may delete a ticket can follow from a group there.
- The slow hash on every request goes away: a signed token is checked without one.

What is already there stays: one way in, the user name passed on to the agent server,
and conversations that belong to their user. Only where the user name comes from changes.

**Also, in short: the infrastructure.** Everything runs on one machine. In production
the application would run as several instances behind a load balancer and scale with
the load, in a cloud or on the organisation's own hardware. One thing in the code has
to change first: the agent server keeps the task of a running turn in its own memory,
and with several instances that has to live outside the process.

### Beyond the assignment: agents that follow a ticket from start to finish

This is outside what the assignment asks for, and it is how I imagine it, not something
I have built. The agent here carries out one request at a time. I would make the whole
handling of a ticket more agentic than that.

**Where a ticket comes from.** A ticket starts somewhere: in a meeting, in a call with a
customer, in a report about something that went wrong. I would have an agent present
there as an observer. When it sees something that should become a ticket, it proposes
one, and when the person responsible for tickets says yes, the ticket is created.

**While the ticket is being solved.** The agent stays with the ticket. It can sit along
as an observer while the person responsible works on it, or take a more active part and
solve it together with that person. Either way it builds up a memory of the ticket:
every turn the work takes, who was contacted, what was said and what was promised.

An example of what I have in mind. The ticket is about a fault in the supply chain. The
person responsible calls the supplier, a factory abroad, and speaks to the factory
manager. The manager is told about the problem and says that he will talk to three
people at the factory about it. He also says that he goes on holiday on the Friday two
weeks from now, that it should be solved before then, and that contact during his
holiday goes through his second in command.

A person who handles hundreds of tickets over several months does not have all of that
in their head three weeks later. The agent does. When the ticket is flagged as still
unresolved, the agent tells the person responsible and gives a full brief: what has been
done on the ticket so far, who should be contacted now, and how to reach them.

**What it comes down to.** Every ticket has an agent of its own, with a memory of that
ticket and of the turns it has taken. Anyone who is allowed to work on the ticket can
start that agent and have the full background at once. And the agent can reach out by
itself to remind people of a ticket that has stopped moving.

## More in the wiki

The [wiki](https://github.com/Arvid-Borglund/gn-take-home/wiki) holds how each part is built and why.

- [Part 1: the ticketing API](https://github.com/Arvid-Borglund/gn-take-home/wiki/Part-1-The-ticketing-API): the endpoints, the business rules, the error bodies, the database with its history, and the search by meaning.
- [Part 2: the agent](https://github.com/Arvid-Borglund/gn-take-home/wiki/Part-2-The-agent): the graph, the tools, the error handling, the confirmation before a delete, the memory and the model.
- [The MCP server](https://github.com/Arvid-Borglund/gn-take-home/wiki/The-MCP-server): the bonus of part 2. The server, its tools and handlers, and the agent as MCP client.
- [The web interface](https://github.com/Arvid-Borglund/gn-take-home/wiki/The-web-interface): what is in it, how it is built, and the login.
- [Part 3: the PR review bot](https://github.com/Arvid-Borglund/gn-take-home/wiki/Part-3-The-PR-review-bot): what the workflow does, and how to run it in your own copy of the repository.
- [Part 4: Terraform for Azure](https://github.com/Arvid-Borglund/gn-take-home/wiki/Part-4-Terraform-for-Azure): what `infra/` describes, and how to validate it.
- [Tests, CI and evals](https://github.com/Arvid-Borglund/gn-take-home/wiki/Tests-CI-and-evals): the tests of the API, the jobs of the CI workflow, and the 16 eval cases for the agent.
- [Deploy](https://github.com/Arvid-Borglund/gn-take-home/wiki/Deploy): the deploy to the server with Kamal, the server as code (Terraform with remote state), and the backups.
- [Architecture](https://github.com/Arvid-Borglund/gn-take-home/wiki/Architecture): the whole system in two pictures, and where things are in the repository.
- [Design decisions](https://github.com/Arvid-Borglund/gn-take-home/wiki/Design-decisions): the choices behind the code, each with its reason and what it cost.
- [Found along the way](https://github.com/Arvid-Borglund/gn-take-home/wiki/Found-along-the-way): things that did not behave as expected, in the model, the MCP SDK, Docker, Terraform and Kamal.
