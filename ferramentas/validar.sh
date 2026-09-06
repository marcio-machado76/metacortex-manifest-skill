#!/usr/bin/env bash
# Roda localmente a mesma validacao da CI. Use antes de abrir o PR.
#
# Tres passos, nesta ordem:
#   1. o verificador nos manifests conformes  — tem que passar
#   2. o scan de configuracao do pipeline     — tem que passar
#   3. o teste negativo no contraexemplo      — tem que REPROVAR\n#   4. a cobertura: nenhuma das 19 regras sem dono documentado
#
# O passo 3 existe porque verificador que nunca reprova nada passa despercebido.
set -uo pipefail

AQUI="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${AQUI}"
FALHOU=0

titulo() { printf '\n\033[1m== %s\033[0m\n' "$1"; }

titulo "1/4  verificador do padrao em manifests/"
if python3 ferramentas/conferir-padrao.py manifests/; then
  echo "OK — nenhum desvio."
else
  echo "FALHOU — ha desvio do padrao em manifests/."
  FALHOU=1
fi

titulo "2/4  trivy config em manifests/"
if command -v trivy >/dev/null 2>&1; then
  if trivy config --exit-code 1 --ignorefile .trivyignore.yaml manifests/; then
    echo "OK — nenhum achado alem dos ignorados com justificativa."
  else
    echo "FALHOU — o scan encontrou achado nao justificado."
    FALHOU=1
  fi
else
  echo "PULADO — trivy nao instalado."
  echo "  curl -sfL https://raw.githubusercontent.com/aquasecurity/trivy/main/contrib/install.sh \\"
  echo "    | sh -s -- -b \"\$HOME/.local/bin\""
fi

titulo "3/4  teste negativo: o contraexemplo tem que reprovar"
if python3 ferramentas/conferir-padrao.py contraexemplo/ >/dev/null 2>&1; then
  echo "FALHOU — o contraexemplo passou. O verificador parou de verificar."
  FALHOU=1
else
  echo "OK — reprovou, como esperado."
fi

titulo "4/4  cobertura: as 19 regras do padrao estao todas enderecadas"
REGRAS="1.1 1.2 1.3 1.4 1.5 1.6 2.1 2.2 2.3 2.4 2.5 2.6 3.1 3.2 3.3 3.4 3.5 3.6 3.7"
AUSENTES=""
for r in ${REGRAS}; do
  grep -qF "${r}" docs/cobertura-das-regras.md || AUSENTES="${AUSENTES} ${r}"
done
if [ -z "${AUSENTES}" ]; then
  echo "OK — as 19 regras aparecem em docs/cobertura-das-regras.md."
else
  echo "FALHOU — regra sem cobertura documentada:${AUSENTES}"
  FALHOU=1
fi

titulo "resultado"
if [ "${FALHOU}" -eq 0 ]; then
  echo "Tudo passou. Pode abrir o PR."
else
  echo "Ha falha acima. Corrija, ou escreva a justificativa no PR conforme a"
  echo "secao Excecoes do padrao."
fi
exit "${FALHOU}"
