FROM python:3.11-slim-bookworm@sha256:94a8fee35252d06ab75856f15f12c7bae67b10e8a6da93c7fded82b2610926cd

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTEST_ADDOPTS="-p no:cacheprovider"

WORKDIR /app

COPY requirements.txt ./
RUN --mount=type=cache,target=/root/.cache/pip \
    python -m pip install --only-binary=:all: -r requirements.txt \
    && python -m pip check

RUN groupadd --gid 1000 iris \
    && useradd --uid 1000 --gid 1000 --create-home iris \
    && mkdir -p /app/reports \
    && chown iris:iris /app/reports

COPY --chown=iris:iris app/ ./app/
COPY --chown=iris:iris tests/ ./tests/
COPY --chown=iris:iris examples/ ./examples/

USER iris

CMD ["python", "-m", "app.runners.mining_restriction_runner", "tests/fixtures/mining_restrictions.geojson"]
