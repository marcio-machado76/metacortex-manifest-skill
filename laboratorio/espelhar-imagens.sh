#!/usr/bin/env bash
# O Loom em miniatura: puxa a imagem publica, republica no registry interno.
#
# A regra 3.7 exige que todo image: aponte para registry.metacortex.io. Esse
# dominio nao existe fora da ficcao, entao o laboratorio o materializa: aqui a
# imagem publica e reetiquetada e empurrada para o registry local, e o
# hosts.toml escrito por subir.sh faz o containerd de cada no procura-la la.
#
# Efeito pratico: os manifests de manifests/ obedecem a 3.7 ao pe da letra e
# ainda assim sobem num cluster de verdade.
set -euo pipefail

REGISTRY_LOCAL=localhost:5001
DOMINIO=registry.metacortex.io

# origem publica                     destino no parque
ESPELHAR=(
  "fabricioveronez/kube-news:v1      ${DOMINIO}/nyx/api:2.9.1"
  "postgres:16-alpine                ${DOMINIO}/nyx/postgres:16-alpine"
)

for linha in "${ESPELHAR[@]}"; do
  read -r origem destino <<<"${linha}"
  local_tag="${destino/${DOMINIO}/${REGISTRY_LOCAL}}"
  echo "==> ${origem}"
  docker pull --quiet "${origem}"
  docker tag "${origem}" "${local_tag}"
  docker push --quiet "${local_tag}"
  echo "    republicado como ${destino}"
done

echo
echo "Catalogo do registry interno:"
curl -s "http://${REGISTRY_LOCAL}/v2/_catalog"
