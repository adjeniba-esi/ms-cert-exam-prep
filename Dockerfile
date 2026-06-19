FROM python:3.12-slim

RUN pip install --no-cache-dir yt-dlp

WORKDIR /app
COPY . .

EXPOSE 8080
CMD ["python", "bin/serve.py", "--port", "8080", "--host", "0.0.0.0"]
