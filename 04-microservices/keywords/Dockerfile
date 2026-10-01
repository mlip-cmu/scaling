# The keywords service (Python, FastAPI). compose.yaml gives the data as the build context "data".
FROM python:3.13-slim
RUN pip install --no-cache-dir uv==0.12.19
ENV UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --locked --no-dev
COPY --from=data photos.csv ./
COPY keywords.py ./
EXPOSE 8000
CMD ["uv", "run", "--no-sync", "uvicorn", "keywords:app", "--host", "0.0.0.0", "--port", "8000", "--log-level", "warning"]
