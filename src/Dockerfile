FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
RUN pip install --no-cache-dir psycopg2-binary==2.9.10
WORKDIR /app
COPY . /app/src
CMD ["python", "-m", "src.main"]
