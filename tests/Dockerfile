FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
WORKDIR /app
COPY . .
CMD ["python", "tests/run_tests.py"]
