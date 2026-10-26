FROM python:3.12-slim
WORKDIR /app
COPY forge_lang/registry_server.py /app/registry_server.py
ENV FORGE_REGISTRY_DIR=/data
ENV PORT=8765
EXPOSE 8765
CMD ["sh", "-c", "python3 registry_server.py --dir $FORGE_REGISTRY_DIR --port $PORT --token $FORGE_REGISTRY_TOKEN"]
