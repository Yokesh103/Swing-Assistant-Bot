# Swing Assistant Pro - Dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY . /app

# Install dependencies
RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt

# Set timezone and expose port for Render detection
ENV TZ=Asia/Kolkata
ENV PORT=10000
EXPOSE 10000

CMD ["python", "bot.py"]
