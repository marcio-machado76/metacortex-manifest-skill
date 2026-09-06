#!/usr/bin/env bash
# Reproduz, contra um cluster de verdade, cada achado de docs/achados-sobre-o-padrao.md.
#
# Existe para que a critica ao padrao seja verificavel e nao opiniao: quem
# duvidar roda isto e ve a mesma saida. Nao aplica nada permanente — usa um
# namespace proprio e o remove no fim.
set -uo pipefail
NS=lab-experimentos

echo "############ preparo ############"
kubectl delete namespace "$NS" --ignore-not-found --wait=true >/dev/null 2>&1
kubectl create namespace "$NS" >/dev/null
kubectl label namespace "$NS" \
  pod-security.kubernetes.io/enforce=restricted \
  pod-security.kubernetes.io/enforce-version=latest >/dev/null
echo "namespace $NS criado com PSA restricted"

echo
echo "############ 1. o bloco da regra 3.2, copiado como esta, em nivel de pod ############"
cat <<'YAML' | kubectl -n "$NS" apply --dry-run=server -f - 2>&1 | head -8
apiVersion: v1
kind: Pod
metadata: {name: teste-sc-nivel-pod}
spec:
  securityContext:
    runAsNonRoot: true
    runAsUser: 10001
    allowPrivilegeEscalation: false
    readOnlyRootFilesystem: true
    capabilities:
      drop: ["ALL"]
  containers:
    - {name: api, image: registry.metacortex.io/nyx/api:2.9.1}
YAML

echo
echo "############ 2. a regra 3.2 exatamente como escrita, sem seccompProfile ############"
cat <<'YAML' | kubectl -n "$NS" apply --dry-run=server -f - 2>&1 | head -8
apiVersion: v1
kind: Pod
metadata: {name: teste-sem-seccomp}
spec:
  securityContext:
    runAsNonRoot: true
    runAsUser: 10001
  containers:
    - name: api
      image: registry.metacortex.io/nyx/api:2.9.1
      securityContext:
        allowPrivilegeEscalation: false
        readOnlyRootFilesystem: true
        capabilities:
          drop: ["ALL"]
YAML

echo
echo "############ 3. regra 1.4 — onde o erro e barrado e onde ele passa calado ############"
echo "--- 3a. Deployment com matchLabels que nao casa com o template ---"
cat <<'YAML' | kubectl -n "$NS" apply --dry-run=server -f - 2>&1 | head -5
apiVersion: apps/v1
kind: Deployment
metadata: {name: teste-seletor}
spec:
  replicas: 1
  selector:
    matchLabels: {app: nyx-api}
  template:
    metadata:
      labels: {app: nyxapi}
    spec:
      containers:
        - {name: api, image: registry.metacortex.io/nyx/api:2.9.1}
YAML

echo
echo "--- 3b. Service com seletor que nao casa com pod nenhum ---"
cat <<'YAML' | kubectl -n "$NS" apply -f - 2>&1
apiVersion: v1
kind: Service
metadata: {name: teste-serv-seletor-errado}
spec:
  selector: {app: nao-existe-ninguem-assim}
  ports: [{port: 80, targetPort: 8080}]
YAML
echo "\$ kubectl -n $NS get endpoints teste-serv-seletor-errado -o yaml"
kubectl -n "$NS" get endpoints teste-serv-seletor-errado -o yaml 2>&1 \
  | grep -vE '^\s*(creationTimestamp|resourceVersion|uid|managedFields|labels|annotations)' | head -12

echo
echo "############ limpeza ############"
kubectl delete namespace "$NS" --wait=false >/dev/null 2>&1
echo "namespace $NS removido"
