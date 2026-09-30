# One image for all components; compose.yaml selects the component with the command.
ARG PYTHON_IMAGE=python:3.13-slim
FROM ${PYTHON_IMAGE}
RUN pip install --no-cache-dir uv==0.12.19
ENV UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY photo-data photo-data
COPY 04-microservices/pyproject.toml 04-microservices/uv.lock 04-microservices/.python-version 04-microservices/
WORKDIR /app/04-microservices
RUN uv sync --locked --no-dev && uv run --no-sync photo-data > /dev/null
COPY 04-microservices/*.py ./
ENTRYPOINT ["uv", "run", "--no-sync", "python", "services.py"]
