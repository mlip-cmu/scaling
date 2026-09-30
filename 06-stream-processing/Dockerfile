# One image for all components; compose.yaml selects the component with the command.
ARG PYTHON_IMAGE=python:3.13-slim
FROM ${PYTHON_IMAGE}
RUN pip install --no-cache-dir uv==0.12.19
ENV UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY photo-data photo-data
COPY 06-stream-processing/pyproject.toml 06-stream-processing/uv.lock 06-stream-processing/.python-version 06-stream-processing/
WORKDIR /app/06-stream-processing
RUN uv sync --locked --no-dev && uv run --no-sync photo-data > /dev/null
COPY 06-stream-processing/*.py ./
ENTRYPOINT ["uv", "run", "--no-sync", "python", "components.py"]
