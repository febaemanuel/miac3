#!/bin/sh

cd `dirname $0`/../

# build da imagem
docker build -f docker/Dockerfile . -t hg.huwc.ufc.br:5000/miac-app:latest

# subir imagem para o registry
docker push hg.huwc.ufc.br:5000/miac-app:latest