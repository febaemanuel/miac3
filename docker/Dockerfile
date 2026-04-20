# start by pulling the python image
FROM python:3.12.9-alpine

# Pacotes para compilar wheels nativos quando necessário
RUN apk add --no-cache \
    postgresql-dev \
    gcc \
    musl-dev \
    python3-dev

# copy the requirements file into the image
COPY ./requirements.txt /app/requirements.txt

# switch working directory
WORKDIR /app

# install the dependencies and packages in the requirements file
RUN pip install -r requirements.txt

# copy every content from the local file to the image
COPY . /app

EXPOSE 8090

# configure the container to run in an executed manner
ENTRYPOINT [ "python" ]

CMD ["novo2.py" ]
