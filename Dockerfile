# Swing Assistant Pro - Dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY . /app

RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt


# Ensure timezone and schedule runs correctly
ENV TZ=Asia/Kolkata

CMD ["python", "bot.py"]
