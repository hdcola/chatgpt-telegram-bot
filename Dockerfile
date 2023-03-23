FROM python:3.10-alpine

RUN apk --no-cache add ffmpeg

WORKDIR /app
COPY . .
RUN pip install -r requirements.txt --no-cache-dir

CMD ["python", "bot/main.py"]