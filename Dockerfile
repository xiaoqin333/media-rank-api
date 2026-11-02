FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOST=127.0.0.1 \
    PORT=8891

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir \
    --index-url https://mirrors.aliyun.com/pypi/simple \
    -r requirements.txt

COPY app.py .
COPY static ./static

EXPOSE 8891

CMD ["python", "app.py"]
