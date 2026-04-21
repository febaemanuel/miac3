#!/bin/sh

cd `dirname $0`/../

REGISTRY="${REGISTRY:-localhost:5000}"
IMAGE="$REGISTRY/miac-app:latest"

# build da imagem
docker build -f docker/Dockerfile . -t "$IMAGE"

# subir imagem para o registry
docker push "$IMAGE"