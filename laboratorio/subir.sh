#!/usr/bin/env bash
# Sobe o laboratorio: registry interno + cluster kind que sabe resolve-lo.
#
# Idempotente: rodar duas vezes nao quebra nada.
set -euo pipefail

CLUSTER=metacortex
REGISTRY=metacortex-registry
REGISTRY_PORT=5001
DOMINIO=registry.metacortex.io
AQUI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# O kind abre um watch de inotify por kubelet e por containerd. O padrao de
# muitas distros (128 instancias) nao aguenta dois clusters na mesma maquina: o
# segundo sobe o control-plane e trava no join, com "kubelet is not healthy".
# O sintoma nao diz inotify em lugar nenhum, por isso a checagem esta aqui.
echo "==> preflight: limites de inotify"
INSTANCIAS=$(sysctl -n fs.inotify.max_user_instances)
WATCHES=$(sysctl -n fs.inotify.max_user_watches)
echo "    max_user_instances=${INSTANCIAS} (minimo 512)"
echo "    max_user_watches=${WATCHES} (minimo 524288)"
if [ "${INSTANCIAS}" -lt 512 ] || [ "${WATCHES}" -lt 524288 ]; then
  cat >&2 <<'AVISO'

    Limites baixos demais. O join dos workers vai falhar com
    "kubelet is not healthy after 4m0s". Corrija com:

      sudo sysctl -w fs.inotify.max_user_instances=512
      sudo sysctl -w fs.inotify.max_user_watches=524288

    Para persistir entre reinicios:

      echo -e "fs.inotify.max_user_instances=512\nfs.inotify.max_user_watches=524288" \
        | sudo tee /etc/sysctl.d/99-kind.conf

AVISO
  echo "    seguindo mesmo assim — com um unico cluster costuma passar" >&2
fi

echo "==> registry interno (${DOMINIO} -> ${REGISTRY}:5000)"
if [ "$(docker inspect -f '{{.State.Running}}' "${REGISTRY}" 2>/dev/null || true)" != "true" ]; then
  docker run -d --restart=always --name "${REGISTRY}" \
    -p "127.0.0.1:${REGISTRY_PORT}:5000" registry:2 >/dev/null
  echo "    criado"
else
  echo "    ja rodando"
fi

echo "==> cluster kind '${CLUSTER}'"
if kind get clusters 2>/dev/null | grep -qx "${CLUSTER}"; then
  echo "    ja existe"
else
  kind create cluster --config "${AQUI}/kind.yaml"
fi

echo "==> hosts.toml em cada no"
for no in $(kind get nodes --name "${CLUSTER}"); do
  docker exec "${no}" mkdir -p "/etc/containerd/certs.d/${DOMINIO}"
  docker exec -i "${no}" cp /dev/stdin "/etc/containerd/certs.d/${DOMINIO}/hosts.toml" <<TOML
[host."http://${REGISTRY}:5000"]
  capabilities = ["pull", "resolve"]
  skip_verify = true
TOML
  echo "    ${no}"
done

echo "==> conectando o registry a rede do kind"
if [ "$(docker inspect -f '{{json .NetworkSettings.Networks.kind}}' "${REGISTRY}")" = "null" ]; then
  docker network connect kind "${REGISTRY}"
  echo "    conectado"
else
  echo "    ja conectado"
fi

echo
echo "Pronto. Contexto: kind-${CLUSTER}"
kubectl --context "kind-${CLUSTER}" get nodes
