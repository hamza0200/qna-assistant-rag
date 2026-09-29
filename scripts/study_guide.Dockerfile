# Tools image for building docs/Interview-Study-Guide.pdf (used by `make study-guide`).
# WeasyPrint needs Pango; Graphviz renders the diagrams; poppler-utils renders page
# previews for checking the output. Kept separate from the app images on purpose.
FROM python:3.12-slim
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 fonts-dejavu-core fonts-noto-core \
       graphviz poppler-utils \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir markdown==3.11 weasyprint==70.0
WORKDIR /work
