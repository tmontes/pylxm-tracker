FROM ghcr.io/astral-sh/uv:python3.14-trixie-slim

# Setup uv env dir, and add its bin directory to the PATH.
ENV UV_PROJECT_ENVIRONMENT=/app
ENV PATH="$UV_PROJECT_ENVIRONMENT/bin:$PATH"

# Install dbt
RUN --mount=type=bind,target=/src-ro <<EOF
    set -e
    cd /src-ro
    uv sync --no-dev --no-editable
EOF

CMD ["/app/bin/pylxm-tracker", "run"]
