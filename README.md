# RootBlood 🩸

![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)
![Python Version](https://img.shields.io/badge/python-3.10+-blue.svg)
![Status](https://img.shields.io/badge/status-v2%20Refactor%20(WIP)-brightgreen.svg)

An open-source platform for creating persistent, secure, and multi-tenant development environments, accessible entirely from a web browser.

---

## 🚀 Core Concept

RootBlood is not just a web terminal; it's a miniature **Platform-as-a-Service (PaaS)**. It provides users with isolated, stateful Linux environments (powered by Docker) complete with persistent home directories, a shared global file space, and `git`-based collaboration.

The vision is a "Linux MMO"—a place to code, collaborate, and persist your work entirely in the browser, built on a secure, multi-tenant backend architecture.

## ✨ Key Features

* **Secure Multi-Tenant Architecture:** Creates isolated environments per user. The backend orchestrator (v2 design) ensures users cannot access other users' data or the host system via path traversal attacks by using non-user-facing hashes (`userhash`) for internal resource naming.
* **Persistent User Storage:** Each user receives a dedicated, persistent home directory (`/home/<userhash>`) that is securely mapped to a Docker volume, allowing work to survive container restarts and new sessions.
* **Infrastructure as Code:** The entire container lifecycle is managed programmatically. A [Flask/FastAPI] backend service acts as an orchestrator, using the Docker SDK to create, start, stop, and (eventually) garbage-collect container sessions via a REST API.
* **Git-Powered Collaboration:** Replaced a custom v1 `rsync`/`diff` system with native `git` integration. A shared `/global` volume allows users to clone, read, and collaborate on projects using the industry-standard tools they already know.
* **Secure Container Execution:** Containers are run with a dedicated, non-root user (`appuser`). The backend uses `docker run` parameters to map host UIDs to container UIDs, ensuring Linux file permissions are correctly enforced between the container and the host's persistent volumes.

## 🛠️ Tech Stack & Architecture

This project is a **Systems Integration** challenge, combining multiple services to create a single, cohesive platform.

* **Backend:** [Flask] (Python)
* **Orchestration:** Docker SDK (Python)
* **Database:** [SQLite]
* **Version Control:** `git` (for user collaboration)
* **Frontend Terminal:** `ttyd` (a C++ web-terminal multiplexer)
* **Core:** Linux (POSIX permissions, `chown`/`chmod` orchestration)

### Architecture Flow

1.  A user request hits the `/session` endpoint on the **[Flask/FastAPI]** server.
2.  The API authenticates the user and generates a `userhash`.
3.  The **`UserManager`** service is called. It checks the **[PostgreSQL/SQLite]** database for an existing user.
4.  The `UserManager` uses the **Docker SDK** to find or create a container:
    * If no container exists, it runs a new one from the `chaospine:1.0.0` image.
    * It securely mounts the user's persistent home volume (`home_<userhash>`) and the shared `/global` volume.
    * It starts the container using the **host's UID/GID** (`user=...`) to solve the UID/GID mapping conflict between the host and container, ensuring file permissions are respected.
5.  The service retrieves the dynamically mapped `ttyd` port from the container.
6.  The API returns the unique session URL (`http://127.0.0.1:<host_port>`) to the user.

## 🏃‍♂️ How to Run (Local Development)

1.  **Build the Container Image:**
    ```bash
    # This image contains ttyd, bash, nvim, git, etc.
    docker build -t chaospine:1.0.0 .
    ```
2.  **Install Dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
3.  **Initialize the Database:**
    ```bash
    # (Instructions for initializing your DB, e.g., flask db init/migrate/upgrade)
    python init_db.py
    ```
4.  **Run the Orchestrator:**
    ```bash
    python app.py
    ```

## 🚧 Project Status & Roadmap

RootBlood is currently a WIP (v2 architecture) used for learning and demonstration. The insecure v1 prototype has been discarded.

**Key Goals for v2.0:**
* [ ] Migrate the database from `SQLite` to `PostgreSQL` for production-readiness.
* [ ] Refactor the `Flask` API to `FastAPI` for improved performance and async capabilities.
* [ ] Implement the "Download as Tarball" feature for user data portability.
* [ ] Implement a robust **Garbage Collector** (based on `ActiveSession` DB) to automatically stop and remove idle containers.

## ⚖️ License

This project is licensed under the MIT License. See the `LICENSE` file for details.
