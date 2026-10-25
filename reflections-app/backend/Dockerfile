FROM python:3.11-slim

ENV PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
# Reflections runs inference on CPU. Install PyTorch from its CPU-only index
# first so sentence-transformers does not pull multi-gigabyte CUDA runtimes.
RUN pip install torch --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
