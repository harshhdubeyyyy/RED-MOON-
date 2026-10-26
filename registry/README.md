# Forge dynamic registry — deploy

This is a dynamic registry: clients publish with POST, not git push.
It is a single Python file with no dependencies.

## Docker (one command, any VPS with Docker)

    docker build -t forge-registry -f registry/Dockerfile .
    docker run -d -p 8765:8765 -e FORGE_REGISTRY_TOKEN=secret \
      -v forge-data:/data forge-registry

Then clients use `http://<your-host>:8765`:

    forge pkg publish-remote http://<your-host>:8765 --token secret
    forge pkg add-remote http://<your-host>:8765 hostlib@0.1.0
    forge pkg list-remote http://<your-host>:8765

## Render / Fly / VPS without Docker

    python3 forge_lang/registry_server.py --dir ./data --port 8765 --token secret

Set the port from your host's PORT env var if required, and put a
reverse proxy (nginx/Caddy) with HTTPS in front for public use —
the server itself is HTTP only, and the token is a Bearer header,
so it must not be sent over plain HTTP on the public internet.

## What is NOT provided here

A host. This repo gives you the server and the deploy files, not
a VPS, Render account, or domain. Central hosting means you run
the above on a host you control, then share its URL.
