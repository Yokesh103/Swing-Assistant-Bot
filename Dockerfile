FROM python:3.11-slim

WORKDIR /app
COPY . /app

RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt

ENV TZ=Asia/Kolkata
ENV PORT=10000
EXPOSE 10000

CMD ["python", "bot.py"]
