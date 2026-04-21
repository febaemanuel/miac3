#!/bin/sh

cd `dirname $0`/../

REGISTRY="${REGISTRY:-localhost:5000}"

# build da imagem
docker build -f docker/Dockerfile . -t "${REGISTRY}/miac-app:latest"

# subir imagem para o registry
docker push "${REGISTRY}/miac-app:latest"
