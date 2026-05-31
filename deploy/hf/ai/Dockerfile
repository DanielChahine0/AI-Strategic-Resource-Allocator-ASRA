# ASRA — AI Model backend (Hugging Face Docker Space)
#
# Layout inside the image mirrors the monorepo so the engine's data lookups
# resolve. eval.py / rules.py read shared data via
#   Path(__file__).resolve().parents[2] / "sample_data" / ...
# With an EDITABLE install the package stays at /app/ai_model/asra_matcher/, so
# parents[2] == /app and /app/sample_data is found. A normal (non -e) install
# would relocate the package into site-packages and break that path.
FROM python:3.11-slim

# HF Spaces runs the container as UID 1000. Create that user up front so files
# we copy/own are writable by the runtime process.
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Engine source (the "AI Model/" folder, copied in as ai_model/) + shared data.
COPY --chown=user ai_model/        /app/ai_model/
COPY --chown=user sample_data/     /app/sample_data/
COPY --chown=user sample_data_v2/  /app/sample_data_v2/

# Editable install — keeps asra_matcher at /app/ai_model so the data path holds.
RUN pip install --no-cache-dir --user -e /app/ai_model

# HF routes to app_port (7860, declared in README.md frontmatter).
EXPOSE 7860
CMD ["python", "-m", "uvicorn", "asra_matcher.api:app", "--host", "0.0.0.0", "--port", "7860"]
