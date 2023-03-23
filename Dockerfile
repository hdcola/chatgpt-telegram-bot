FROM python:3.9-alpine

RUN apk --no-cache add ffmpeg

WORKDIR /app
COPY . .
RUN apk add build-base
RUN pip install wheel
RUN pip install -r requirements.txt --no-cache-dir

CMD ["python", "bot/main.py"]