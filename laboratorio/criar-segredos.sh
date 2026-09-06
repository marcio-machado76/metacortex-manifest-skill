#!/usr/bin/env bash
# A regra 3.3 proibe versionar segredo. No parque quem cria e o cofre da
# plataforma; no laboratorio, este script faz o papel dele.
#
# Por isso os valores estao aqui e nao em manifests/: este arquivo e do
# laboratorio, nao e manifesto que sobe para cluster de cliente.
set -euo pipefail

kubectl create secret generic nyx-db \
  --namespace nyx-prod \
  --from-literal=username=kubedevnews \
  --from-literal=password="$(openssl rand -base64 18)" \
  --dry-run=client -o yaml | kubectl apply -f -

kubectl label secret nyx-db --namespace nyx-prod --overwrite \
  app.kubernetes.io/name=nyx-db \
  app.kubernetes.io/instance=nyx-prod \
  app.kubernetes.io/part-of=nyx \
  app.kubernetes.io/managed-by=platform >/dev/null

echo "Secret nyx-db criado em nyx-prod (rotulado conforme a regra 1.3)."
