FROM debian:bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# System deps. ogdf-python wheels link against libstdc++ and require
# build tools to compile from source on minor-version bumps; graphviz
# powers the dot-ortho backend; libxml2/libxslt are pulled in by
# networkx graphml IO and the geg package.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        cmake \
        git \
        graphviz \
        libgraphviz-dev \
        libxml2-dev \
        libxslt1-dev \
        python3.11 \
        python3.11-dev \
        python3-pip \
        python3-venv \
        wget \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN python3.11 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --upgrade pip wheel

WORKDIR /app

# Pre-copy the project metadata so dependency install caches separately
# from the source tree. The actual source mounts at /app/src at runtime.
COPY pyproject.toml /app/pyproject.toml
COPY config/ /app/config/

# Install the package itself (editable in dev; non-editable for the
# paper-artifact image build the user ships).
RUN pip install --upgrade pip \
    && pip install \
        "geg-metrics>=0.2.2" \
        "networkx>=3.2" "numpy>=1.24" "scipy>=1.11" \
        "pyyaml>=6.0" "tqdm>=4.66" "pandas>=2.1" \
        "matplotlib>=3.8" "seaborn>=0.13" "pydot>=2.0" \
        "ssgetpy>=0.1" "requests>=2.31" \
        "pytest>=7.0"

# OGDF and HOLA: ogdf-python is the maintained Python binding for
# OGDF; HOLA needs a separate libdialect/HOLA package or binary.
# Best-effort install — they may need the user's local index/config.
RUN pip install ogdf-python || echo "ogdf-python install skipped"

COPY src/ /app/src/
COPY tests/ /app/tests/

ENV PYTHONPATH=/app/src \
    EFFECTS_OUT=/app/output

ENTRYPOINT ["python", "-m", "graph_generation.cli"]
CMD ["run", "all"]
