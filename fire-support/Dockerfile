FROM python:3.11-slim

WORKDIR /code
COPY ./requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY . /code

CMD ["python", "./main.py"]