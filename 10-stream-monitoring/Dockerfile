# One image for all components; compose.yaml selects the component with the command.
ARG PYTHON_IMAGE=python:3.13-slim
FROM ${PYTHON_IMAGE}
RUN pip install --no-cache-dir uv==0.12.19
ENV UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY photo-data photo-data
COPY 10-stream-monitoring/pyproject.toml 10-stream-monitoring/uv.lock 10-stream-monitoring/.python-version 10-stream-monitoring/
WORKDIR /app/10-stream-monitoring
RUN uv sync --locked --no-dev && uv run --no-sync photo-data > /dev/null
COPY 10-stream-monitoring/*.py ./
ENTRYPOINT ["uv", "run", "--no-sync", "python", "components.py"]
