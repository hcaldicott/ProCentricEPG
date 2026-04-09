FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src ./src
COPY templates ./templates
COPY static ./static

ENV PORT=8081
EXPOSE 8081

CMD ["python", "/app/src/app.py"]
