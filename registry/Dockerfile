FROM python:3.12-slim
WORKDIR /app
COPY forge_lang/registry_server.py /app/registry_server.py
# The server reads PORT and FORGE_REGISTRY_TOKEN from the environment
# (see forge_lang/registry_server.py), so no secrets live in CMD.
# Render sets PORT itself; Fly uses internal_port 8765 (see fly.toml).
ENV PORT=8765
EXPOSE 8765
VOLUME /data
CMD ["python3", "registry_server.py", "--dir", "/data"]
