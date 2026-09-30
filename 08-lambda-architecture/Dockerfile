# One image for all components; compose.yaml selects the component with the command.
ARG PYTHON_IMAGE=python:3.13-slim
FROM ${PYTHON_IMAGE}
RUN pip install --no-cache-dir uv==0.12.19
ENV UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY photo-data photo-data
COPY 08-lambda-architecture/pyproject.toml 08-lambda-architecture/uv.lock 08-lambda-architecture/.python-version 08-lambda-architecture/
WORKDIR /app/08-lambda-architecture
RUN uv sync --locked --no-dev && uv run --no-sync photo-data > /dev/null
COPY 08-lambda-architecture/*.py ./
ENTRYPOINT ["uv", "run", "--no-sync", "python", "components.py"]
