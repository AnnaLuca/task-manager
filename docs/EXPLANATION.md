# Explanation – everything you need to understand for this project

This note is not part of the submission. It is here so you understand why everything in the
project is the way it is, and can answer confidently during the demo. It goes from the basics to
the actual files, and ends with the demo script and the likely questions with answers.

---

## 1. The big picture, as an analogy

Picture a restaurant:

- **Frontend (Nginx)** = the waiter. The only person the guest ever meets. Brings out the menu
  (the web page) and carries orders to the kitchen.
- **Backend (API)** = the cook. This is where the work happens: the order gets processed.
  Guests never walk into the kitchen.
- **Database (PostgreSQL)** = the pantry. Whatever needs to last is stored here.
  Only the cook may touch it.
- **Docker Swarm** = the restaurant manager. Makes sure exactly as many waiters and cooks are
  working as you asked for. If someone collapses, a replacement is put in straight away.
- **Replicas** = several people in the same role. Two waiters can serve twice as many tables, and
  if one of them drops out, the guests don't even notice.
- **TryCloudflare** = a free courier who brings guests in from the street, even though the
  restaurant is in a closed courtyard (your laptop, behind a router).

---

## 2. Docker basics

### Container vs virtual machine
A **virtual machine** emulates a whole computer with its own operating system (heavy, slow to start).
A **container** is just an isolated process on the host's kernel: it sees its own filesystem,
network and process list, but has no separate operating system inside it. It starts in seconds
and uses few resources.

### Image vs container
- An **image** is the recipe or template: a read-only filesystem package (Python + your code + dependencies).
- A **container** is a running instance of an image. You can start any number of containers from one image.
  That is exactly what replicas rely on.

### Dockerfile
The steps for building an image, in a text file. For example, `api/Dockerfile`:

```dockerfile
FROM python:3.12.8-slim            # base image: Debian + Python, pinned version
COPY requirements.txt .            # copy in the dependency list
RUN pip install -r requirements.txt
COPY main.py .                     # copy in the code
USER appuser                       # don't run as root
CMD ["uvicorn", "main:app", ...]   # what runs when the container starts
```

Every instruction creates a **layer**, and Docker caches layers. That's why we copy
`requirements.txt` and install *first*, and the code only *afterwards*: if only the code changes,
the slow `pip install` step doesn't need to run again.

### Registry
An online image store, e.g. **GHCR** (GitHub Container Registry) or **Docker Hub**.
It's needed because Swarm doesn't build. Every node must be able to *pull* the image from a
shared location. (With a single node a local image would work too, but the assignment asks for a
registry, and it makes the deployment reproducible.)

### Pinned version (tag)
`nginx:latest` means something different today than it will in six months. `nginx:1.27.3-alpine`
is always the same. Pinning makes the deployment reproducible, and the assignment explicitly asks for it.
Our own images get versions too (`:1.0.0`), and an update becomes `:1.0.1`.

---

## 3. What is Nginx, and why do we need it?

**Nginx** is a very fast, widely used web server. It has two jobs here:

1. **Serving static files.** `index.html`, `app.js` and `style.css` are ready-made files that just
   need to be handed to the browser. You don't need Python for that, and Nginx is far more efficient at it.
2. **Reverse proxy.** The browser sends every request to Nginx. If the path starts with `/api/...`,
   Nginx forwards it to the internal `api` service and passes the answer back.

Why is this good?
- **A single entry point:** only port 8080 is visible from outside; the API and the database stay hidden.
  The assignment asks for this too ("only the necessary web entry point should be published").
- **No CORS problem:** to the browser, the UI and the API come from the same address.
- **Flexibility:** the API behind Nginx can be scaled or replaced at any time.

The key part of `frontend/nginx.conf`:

```nginx
resolver 127.0.0.11 valid=10s;          # Docker's internal DNS
set $api_upstream http://api:8000;      # "api" = the service name
location /api/ { proxy_pass $api_upstream; }
```

The name `api` resolves because Docker automatically gives every service a DNS name on the
shared network. Using `proxy_pass` with a variable is a small trick: it makes Nginx resolve the
name at runtime, so it doesn't crash if the API doesn't exist yet when Nginx starts.

---

## 4. Networking

### Publishing a port
A container lives on its own isolated network. `8080:80` means traffic arriving on the machine's
port 8080 goes to the container's port 80. **Only the frontend has this.**

### Bridge vs overlay network
- A **bridge** network is a virtual network inside a single machine. Docker Compose uses it.
- An **overlay** network is a virtual network **spanning several machines**. Two containers talk
  over it as if they were on the same network, even when they run on different servers. This is
  Swarm's network type, and the assignment requires it.

### Two networks for security
```
frontend-net:  frontend  ←→  api        (and the tunnel)
backend-net:   api       ←→  db         (internal: no route to the internet)
```
The frontend **cannot see** the database; only the API is on both networks. Even if someone
compromised the frontend, they couldn't reach the DB directly. This is *network segmentation*.

### Service discovery (reaching services by name)
The API reaches the database at `db:5432`, and Nginx reaches the API at `api:8000`. No IP
addresses are needed, because Docker's built-in DNS resolves service names.

### VIP and the ingress routing mesh (Swarm-specific)
- In Swarm, the name `api` resolves to a **virtual IP (VIP)**, not to one specific container.
  Behind the VIP, Swarm **distributes requests across the replicas** (round-robin load balancing).
  That's what the "20 requests" button in the UI shows.
- The **ingress routing mesh** means the published port 8080 is open on *every* Swarm node.
  Whichever node a request arrives at, Swarm delivers it to a live frontend replica.

---

## 5. Volumes: why the data doesn't disappear

A container is **disposable**: if you delete it or it restarts, changes inside its filesystem are lost.
So the database files go into a **volume**, a Docker-managed folder outside the container:

```yaml
volumes:
  - db-data:/var/lib/postgresql/data
```

If you throw away the `db` container, the new one mounts the same volume and all the data is there.
That's what the **persistence test** shows (`docker service update --force project_db`).

A `local` volume lives on one specific **node's** disk. That's why the DB is pinned to the manager
node (`placement: node.role == manager`); otherwise, with several nodes, it could start on another
machine with an empty volume.

---

## 6. Secrets: how the password is handled

The wrong way: `POSTGRES_PASSWORD: secret123` in the YAML. It would end up on GitHub, and anyone
could read it with `docker inspect`.

The right way is a **Docker secret**:
```bash
printf 'StrongPassword' | docker secret create db_password -
```
Swarm stores it encrypted and only hands it to the containers that request it in stack.yml.
Inside them it appears as the file `/run/secrets/db_password`, kept in memory. The official Postgres
image supports the `POSTGRES_PASSWORD_FILE` variable, and the API code (`read_db_password()`)
reads the same file.

Under Compose, a local file (`secrets/db_password.txt`) provides it, and `.gitignore` keeps it out of the repo.

---

## 7. Docker Compose vs Docker Swarm – the key difference

**Docker Compose:** a tool for starting several containers on *one machine* from a YAML file.
Ideal for development and building. If a container dies, at most a `restart:` rule starts it again.
No cluster, no built-in load balancer, no rolling updates.

**Docker Swarm:** Docker's built-in **container orchestrator**. It turns several machines (nodes)
into a cluster and maintains a **desired state**. You say "always run 2 of `api`", and Swarm keeps
watching the actual state and steps in whenever it differs. This is the *reconciliation loop*.
Kubernetes works on the same principle, just with more complexity.

| | Docker Compose | Docker Swarm |
|---|---|---|
| Scope | one machine | cluster (1..N nodes) |
| Command | `docker compose up` | `docker stack deploy` |
| Images | can build (`build:`) | **ready-made images only** (`image:`); `build` is ignored |
| Network | bridge | overlay |
| Replicas and load balancing | limited | `deploy.replicas` + VIP |
| Self-healing | restart only | desired state: a dead task is replaced by a new task |
| Rolling update and rollback | no | `update_config`, `rollback_config` |
| `depends_on` | works | **ignored** |
| Secrets | from a file | encrypted Swarm secret |

**That's why the project has two YAML files:**
- `compose.yml`: you develop locally, build the images and push them;
- `stack.yml`: Swarm deploys this, using the images pulled from the registry.

### Swarm concepts: node, service, task, stack
- **Node:** a machine in the Swarm. A **manager** is in charge (this is where `stack deploy` runs);
  a **worker** only runs containers. We have one node, which is both manager and worker.
- **Service:** the description of a service: "from this image, with this many replicas, configured like this".
  For example `project_api`.
- **Task:** one instance of a service, the unit Swarm schedules. Each task has exactly one container.
  If the container dies, the task becomes *Failed* and Swarm creates a **new task**.
- **Stack:** a group of related services from one YAML file. Its name appears as a prefix:
  `project_frontend`, `project_api`, `project_db`.

---

## 8. Replicas – what they are and when you need them

A **replica** is another, fully identical instance (container) of the same service.
`replicas: 2` means two identical API containers are running, and Swarm splits the requests between them.

### Why is this useful?
1. **Fault tolerance:** if one replica dies, the other keeps serving and the user notices nothing.
   Meanwhile Swarm replaces the dead one.
2. **Capacity (horizontal scaling):** twice as many instances handle roughly twice as many requests.
   Under heavy traffic: `docker service scale project_api=10`, and that's it.
3. **Zero-downtime updates:** a rolling update replaces replicas one at a time, so there is always a live instance.

### When can something be replicated? (The key question)
- A **stateless** service keeps nothing inside itself between two requests; it gets everything
  from the database every time. The API and Nginx are like this. **Safe to replicate**, because it
  doesn't matter which instance gets the request.
- A **stateful** service stores data; the database is one. **It can't simply be replicated.**
  If two Postgres containers wrote the same volume, the data would get corrupted. If each had its
  own volume, the two datasets would drift apart. A database can only be replicated with the
  database's own replication mechanism (primary–replica), which is a separate, complex topic.

**Hence: `frontend` 2 replicas, `api` 2 replicas (3 during the demo), `db` 1 replica.** This split is
also what the assignment requires: "at least one stateless service with two or more replicas".

### What do replicas prove on a single machine?
On one node, replicas handle **container-level** failures (crashes, kills) and load. But if the
laptop itself goes down, everything stops. That's **node-level** fault tolerance, which needs more machines.
The assignment explicitly accepts this, but **say it yourself** in the demo, because it earns you points.

---

## 9. Healthcheck, restart policy, rolling update

- **Healthcheck:** Docker periodically runs a command inside the container (e.g. calls the `/health` endpoint).
  If it fails several times in a row, the container becomes **unhealthy** and Swarm replaces it.
  This also catches the case where the process is running but has frozen and stopped responding.
  - `interval`: how often, `retries`: how many failures before unhealthy, `start_period`: grace period at startup.
- **restart_policy:** what Swarm does when the container *exits*.
  `on-failure` starts a new one only after an error exit; `any` always does.
- **The difference:** the restart policy handles *exits*; the healthcheck handles a container that is *running but sick*.
- **update_config** (rolling update): `parallelism: 1` = replace one replica at a time;
  `order: start-first` = start the new one first and only then stop the old one, so there's no downtime;
  `failure_action: rollback` = if the new version is broken, roll back to the old one automatically.
- For the DB the order is **`stop-first`**, because two Postgres instances must never write the same volume at once.

The API's `/health` endpoint deliberately does **not** check the database. If the DB is down for
half a minute, we don't want Swarm to restart every API container, since that would fix nothing.

### Why does the API have a wait loop?
In Swarm `depends_on` doesn't work; services start at the same time. If the API is ready before
Postgres, the first connection fails. So `wait_for_db_and_migrate()` retries every 2 seconds for
60 seconds. If it still can't connect, it exits and the restart policy starts it again.

---

## 10. How does TryCloudflare work?

Your laptop is behind a router and can't be reached from outside (no public IP, no port forwarding).
The `cloudflared` program opens a persistent connection **outwards** to Cloudflare's servers.
Cloudflare gives you a random `https://something.trycloudflare.com` address. When someone opens it,
Cloudflare sends the request back over the already-open connection to cloudflared, which passes it
on to the frontend.

- HTTPS is provided by Cloudflare, for free.
- The containers **still run on your machine**; Cloudflare is only a gateway.
- The URL is temporary: you get a new address on every restart.

Here cloudflared runs as a **Swarm service** (`tunnel`) pointing at `frontend:80` on the overlay
network. It doesn't count as one of the three required services; it's just a convenience add-on.

---

## 11. File by file

| File | What it does |
|---|---|
| `api/main.py` | REST API: task CRUD, `/api/info` (which replica, which version, is the DB alive), `/health`. At startup it waits for the DB and creates the table. An *advisory lock* makes sure two replicas don't try to create it at the same time. |
| `api/Dockerfile` | Python image: dependencies, code, non-root user, uvicorn start. The version comes in as a `--build-arg`. |
| `api/requirements.txt` | Pinned Python package versions. |
| `frontend/nginx.conf` | Static file serving, `/api/` proxy, `/healthz`, `X-Frontend-Host` header. |
| `frontend/Dockerfile` | Nginx image with our config and the static files. |
| `frontend/static/*` | The UI: HTML, the JavaScript (the `fetch` calls), CSS. |
| `compose.yml` | Local run and build. Bridge networks, `depends_on` with health conditions, secret from a file. |
| `stack.yml` | Swarm deployment: replicas, restart, update, rollback, resource limits, overlay networks, external secret, volume, tunnel. |
| `scripts/build-and-push.sh` | `docker compose build` + `push` to the registry. |
| `scripts/deploy.sh` | `swarm init` (if needed), secret creation (if needed), `stack deploy`. |
| `scripts/demo.sh` | The mandatory tests step by step (as a cheat sheet and for saving the outputs). |

---

## 12. Your steps, one by one

1. **Install Docker Desktop** (macOS or Windows), or Docker Engine on Linux.
   Check: `docker version`, `docker compose version`.
2. **Create a GitHub repo** (e.g. `task-manager-swarm`) and push this folder to it.
3. **Run it locally:**
   ```bash
   printf 'some-strong-password' > secrets/db_password.txt
   docker compose up --build
   ```
   Open http://localhost:8080 and add some tasks. Then `docker compose down`.
4. **GHCR token:** GitHub → Settings → Developer settings → Personal access tokens (classic) →
   `write:packages` scope. Log in:
   `echo <TOKEN> | docker login ghcr.io -u <username> --password-stdin`
5. **Build and push:**
   ```bash
   export IMAGE_PREFIX=ghcr.io/<username> TAG=1.0.0
   ./scripts/build-and-push.sh
   ```
   Then on GitHub: your profile → **Packages** → each package → *Package settings* → *Change visibility* → **Public**.
6. **Deploy to Swarm:** `./scripts/deploy.sh`, or by hand following section 6 of the README.
   Practise it by hand too, because that's how you'll do it in the demo.
7. **For the rolling update**, build a second version as well:
   `TAG=1.0.1 ./scripts/build-and-push.sh`
8. **Tests and evidence:** `./scripts/demo.sh | tee docs/test-output.txt`, and take screenshots along the way
   (the UI, the Infrastructure panel with 3 replicas, the trycloudflare URL on your phone).
9. **PDF documentation** (2–5 pages): architecture diagram (the README's Mermaid diagram), the role of each service,
   the deployment steps, the test table with results, screenshots and command outputs, known limitations.
   It can easily be put together from the README.
10. **Put the current public URL in the README**, and submit the repo link and the URL.

---

## 13. Demo script (about 10–12 minutes)

**Preparation before the demo:** laptop plugged in, sleep mode off. Images on GHCR, the
`db_password` secret created. Two terminals open, the browser at `localhost:8080`, your phone
at hand. As a fallback, a mobile hotspot.

1. **Architecture (1 min):** show the README diagram: three services, two overlay networks, one volume, only the frontend is public.
2. **Docker (1–2 min):** open `api/Dockerfile` and explain the layers and the pinned version.
   Run: `docker images | grep task-manager`.
3. **Docker Compose (1 min):** `docker compose config`, or a quick `docker compose up -d`, then `docker compose ps` and `docker compose down`.
   Say: "This is single-machine, for development; Swarm comes next."
4. **Swarm deployment from scratch (2 min):**
   ```bash
   docker stack rm project        # (if it was running)
   docker node ls
   docker stack deploy -c stack.yml project
   docker stack services project
   docker stack ps project
   ```
5. **Functional test:** add a task in the browser, then refresh. Show the Infrastructure panel.
6. **Scaling:** `docker service scale project_api=3`, then the "20 requests" button: three different hostnames appear.
7. **Self-healing:** `docker ps` → `docker kill <one api container>` → `docker service ps project_api`.
   You can see the *Failed* task and the new *Running* one. The UI keeps working the whole time.
8. **Persistence:** `docker service update --force project_db`, wait a bit, refresh: the data is still there.
   Show: `docker volume ls`.
9. **External access:** get the URL from `docker service logs project_tunnel`. Open it on your phone,
   **over mobile data**, and add a task from there too. It shows up on the laptop as well.
10. **Bonus – rolling update:** `docker service update --image ghcr.io/<name>/task-manager-api:1.0.1 project_api`,
    and watch the API version in the UI change from 1.0.0 to 1.0.1 without downtime.
11. **To finish:** stop the tunnel (`docker service rm project_tunnel`), as the assignment asks.

---

## 14. Likely questions – with short answers

**What's the difference between `docker compose up` and `docker stack deploy`?**
Compose runs on one machine and can build. Stack deploy hands the desired state to Swarm:
replicas, overlay networking, self-healing, rolling updates. It works from ready-made images and doesn't build.

**Why don't you replicate the database?**
Because it's stateful. Two instances on the same volume would corrupt the data, and on separate volumes
the datasets would drift apart. That needs DB-level replication (e.g. Postgres streaming replication).

**What happens if I kill a container?**
The task becomes *Failed*. Swarm sees that the actual replica count is below the desired count and starts
a new task. Meanwhile the VIP routes to the remaining replica, so the user notices nothing.

**What's the difference between a healthcheck and a restart policy?**
The restart policy acts when the container has exited. The healthcheck acts when it's running but not working properly.

**What's an overlay network?**
A virtual network spanning several nodes. Containers reach each other by name, regardless of which node they're on.

**How does Nginx know where the API is?**
From Docker's built-in DNS (127.0.0.11). The name `api` resolves to the service's virtual IP,
and behind it Swarm distributes requests across the replicas.

**Why does only the frontend publish a port?**
The principle of least privilege. Whatever isn't published can't be attacked from outside.

**How do you handle the password?**
With a Docker secret. It's not in the repo, it's not visible as an environment variable, and only `db` and `api`
receive it, as a file under `/run/secrets`.

**What does a single node prove?**
Container-level fault tolerance and scaling. Node-level fault tolerance would need at least 3 nodes
(because of the manager quorum) and shared storage for the DB.

**Why do you need a registry?**
Because Swarm doesn't build. With several nodes, every node must be able to pull the same image.

**How does TryCloudflare work from behind a router?**
cloudflared opens an outbound connection to Cloudflare, and requests come back over it. No port
forwarding is needed, and Cloudflare provides HTTPS.

**Why is the update order `start-first`?**
So the new replica starts first and the old one stops only afterwards, meaning there's no downtime during the update.
That's also why the DB uses `stop-first`.

**Why are there two overlay networks?**
For segmentation: the frontend can't reach the DB, and `backend-net` is `internal`, meaning it has no internet access.

---

## 15. Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `docker swarm init` fails because of multiple IP addresses | `docker swarm init --advertise-addr <the machine's IP>` |
| The service stays at `0/2` replicas, task error *No such image* | The image is private or the name is wrong. Set the GHCR package to Public, check `IMAGE_PREFIX`, use the `--with-registry-auth` flag. |
| `stack deploy` says "secret not found" | First: `printf '...' \| docker secret create db_password -` |
| `IMAGE_PREFIX` is empty in stack.yml | `stack deploy` doesn't read `.env`. Before it: `export IMAGE_PREFIX=...` |
| The API keeps restarting | `docker service logs project_api`. Most likely the DB is unreachable or the password is wrong. If you changed the password, the old volume still holds the old one: `docker stack rm project && docker volume rm project_db-data`. |
| The UI loads but the API returns errors | `docker service ps project_api --no-trunc` and `docker service logs project_frontend` |
| No trycloudflare URL | `docker service logs project_tunnel`. The university network may block it; try a mobile hotspot. |
| The same frontend replica always answers | Normal: the browser reuses its connection (keep-alive). The distribution shows on the API side, because Nginx opens a new connection for each request. |

---

## 16. Where the points come from

| Criterion (points) | How it's met |
|---|---|
| Working application, 3 different services (20) | frontend + api + db, real CRUD |
| Dockerfile, images, reproducible deployment (25) | 2 own Dockerfiles, pinned versions, GHCR, `stack.yml`, `deploy.sh`, live deployment from scratch |
| Networking, storage, security (15) | 2 overlay networks (one internal), name-based access, 1 public port, volume, secret, non-root, resource limits |
| Scaling, recovery, tests (15) | 2→3 replicas, kill → replacement, healthcheck, restart policy, persistence test, rolling update and rollback |
| Public access (10) | TryCloudflare tunnel, tested over mobile data |
| Documentation and demo (15) | README + diagram, PDF, `demo.sh`, this note for preparation |
