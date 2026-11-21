# secrets/

This is where the database password goes for **local** (Docker Compose) runs:

```bash
printf 'some-strong-password' > secrets/db_password.txt
```

`*.txt` files are excluded by `.gitignore`, so they never reach GitHub.
In Swarm the password lives as a **Docker secret**, and this file is not needed:

```bash
printf 'some-strong-password' | docker secret create db_password -
```
