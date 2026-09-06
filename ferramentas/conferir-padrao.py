#!/usr/bin/env python3
"""Verifica manifestos contra o Padrao de Manifests da Metacortex (rev. 2026-07-29).

Escopo deliberado: este script cobre as regras que a varredura do pipeline NAO
conhece. A divisao nao foi suposta, foi medida — `trivy config` no anti-padrao
de contraexemplo/ produz 18 achados que colapsam em quatro regras (2.1, 3.1, 3.2 e,
ao contrario, a 3.7). As demais o Trivy nao menciona, e sao estas aqui.

Fica de fora de proposito:
  2.1, 3.1, 3.2, 3.6  o Trivy ja cobre; reimplementar so duplica manutencao
  2.6                 depende de saber quanto a aplicacao demora para drenar
  o "1,5x a 2x"da 2.1 depende do consumo observado em regime, que nao esta no YAML
  o alvo real da 2.2  depende de saber quais endpoints a aplicacao expoe

Uso:
    python3 ferramentas/conferir-padrao.py manifests/

Saida:
    ERRO   regra obrigatoria ou proibida — reprova, sai com codigo 1
    AVISO  regra recomendada — nao reprova, mas exige justificativa no PR
"""
import pathlib
import re
import sys

import yaml

KEBAB = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
NAMESPACE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*-(dev|stg|prod)$")
ROTULOS = (
    "app.kubernetes.io/name",
    "app.kubernetes.io/instance",
    "app.kubernetes.io/part-of",
    "app.kubernetes.io/managed-by",
)
MANAGED_BY = {"platform", "argocd", "helm"}
REGISTRY = "registry.metacortex.io/"
WORKLOADS = {"Deployment", "StatefulSet", "DaemonSet", "Job", "CronJob", "ReplicaSet"}
NOMES_GENERICOS = {"app", "main", "container", "server"}

# Regra 3.3 — heuristica. Nao decide se o valor e sensivel, so levanta suspeita
# forte o bastante para o revisor olhar. O julgamento continua humano.
CHAVE_SENSIVEL = re.compile(
    r"(pass|senha|secret|token|api[-_]?key|credential|private|dsn)", re.I
)
URL_COM_SENHA = re.compile(r"[a-z][a-z0-9+.-]*://[^/\s:]+:[^/\s@]+@", re.I)

erros: list[str] = []
avisos: list[str] = []


def erro(onde: str, regra: str, msg: str) -> None:
    erros.append(f"ERRO  {regra:<4} {onde} — {msg}")


def aviso(onde: str, regra: str, msg: str) -> None:
    avisos.append(f"AVISO {regra:<4} {onde} — {msg}")


def ambiente(ns: str | None) -> str | None:
    m = NAMESPACE.match(ns or "")
    return m.group(2) if m else None


def pod_template(obj: dict) -> tuple[dict, dict]:
    """Devolve (metadata, spec) do template de pod, ou ({}, {})."""
    spec = obj.get("spec") or {}
    if obj.get("kind") == "CronJob":
        spec = ((spec.get("jobTemplate") or {}).get("spec")) or {}
    tpl = spec.get("template") or {}
    return (tpl.get("metadata") or {}), (tpl.get("spec") or {})


def containers(pod_spec: dict) -> list[dict]:
    return (pod_spec.get("containers") or []) + (pod_spec.get("initContainers") or [])


def checa_metadata(onde: str, obj: dict) -> None:
    md = obj.get("metadata") or {}
    nome = md.get("name", "")

    # 1.1 — nome em kebab-case
    if not KEBAB.match(nome):
        erro(onde, "1.1", f"nome '{nome}' nao esta em kebab-case")

    # 1.2 — namespace <cliente>-<ambiente>
    ns = nome if obj.get("kind") == "Namespace" else md.get("namespace")
    if ns and not NAMESPACE.match(ns):
        erro(onde, "1.2", f"namespace '{ns}' fora do formato <cliente>-<ambiente>")

    # 1.3 — os quatro rotulos, em todo objeto
    labels = md.get("labels") or {}
    faltando = [r for r in ROTULOS if r not in labels]
    if faltando:
        erro(onde, "1.3", "faltam os rotulos: " + ", ".join(faltando))
    mb = labels.get("app.kubernetes.io/managed-by")
    if mb and mb not in MANAGED_BY:
        erro(onde, "1.3", f"managed-by '{mb}' fora de {sorted(MANAGED_BY)}")
    if "app" in labels and not faltando:
        aviso(onde, "1.3", "rotulo curto 'app' presente; so vale por compatibilidade")

    # 1.5 — anotacao de dono (recomendado)
    if not (md.get("annotations") or {}).get("metacortex.io/owner"):
        aviso(onde, "1.5", "sem anotacao metacortex.io/owner")


def checa_workload(onde: str, obj: dict) -> None:
    kind = obj["kind"]
    spec = obj.get("spec") or {}
    md = obj.get("metadata") or {}
    ns = md.get("namespace")
    env = ambiente(ns)
    tpl_md, pod_spec = pod_template(obj)
    tpl_labels = tpl_md.get("labels") or {}

    # 1.3 — o template do pod tambem carrega os quatro rotulos
    faltando = [r for r in ROTULOS if r not in tpl_labels]
    if faltando:
        erro(onde, "1.3", "template do pod sem os rotulos: " + ", ".join(faltando))

    # 1.4 — matchLabels tem que casar com os rotulos do template
    match = ((spec.get("selector") or {}).get("matchLabels")) or {}
    if not match:
        erro(onde, "1.4", "sem spec.selector.matchLabels")
    for k, v in match.items():
        if k not in tpl_labels:
            erro(onde, "1.4", f"matchLabels tem '{k}' que o template do pod nao tem")
        elif tpl_labels[k] != v:
            erro(onde, "1.4",
                 f"matchLabels {k}='{v}' difere do template do pod '{tpl_labels[k]}'")

    # 2.3 e 2.4 — so cobradas em prod
    replicas = spec.get("replicas")
    if env == "prod" and kind in ("Deployment", "ReplicaSet"):
        if replicas is not None and replicas < 2:
            erro(onde, "2.3", f"replicas={replicas} em prod; o minimo e 2")
        strat = spec.get("strategy") or {}
        if strat.get("type") != "RollingUpdate":
            erro(onde, "2.4", "prod exige strategy.type RollingUpdate")
        else:
            ru = strat.get("rollingUpdate") or {}
            if ru.get("maxUnavailable") != 0:
                erro(onde, "2.4", f"maxUnavailable={ru.get('maxUnavailable')}; prod exige 0")
            if not ru.get("maxSurge"):
                erro(onde, "2.4", "prod exige maxSurge para compensar maxUnavailable: 0")

    # 3.4 — token da ServiceAccount desmontado quando nao fala com a API
    if pod_spec.get("automountServiceAccountToken") is not True:
        if pod_spec.get("automountServiceAccountToken") is None:
            erro(onde, "3.4", "sem automountServiceAccountToken: false no pod")

    # 3.5 — ServiceAccount dedicada (recomendado)
    sa = pod_spec.get("serviceAccountName")
    if not sa or sa == "default":
        aviso(onde, "3.5", "usa a ServiceAccount default do namespace")

    for c in containers(pod_spec):
        checa_container(f"{onde}/{c.get('name', '?')}", c)


def checa_container(onde: str, c: dict) -> None:
    nome = c.get("name", "")

    # 1.6 — nome do container igual ao componente (recomendado)
    if nome in NOMES_GENERICOS:
        aviso(onde, "1.6", f"container chamado '{nome}'; use o nome do componente")

    # 3.7 — imagem so do registry interno
    img = c.get("image", "")
    if not img.startswith(REGISTRY):
        erro(onde, "3.7", f"imagem '{img}' nao vem de {REGISTRY}")

    # 2.2 — as duas probes, em qualquer ambiente
    readiness, liveness = c.get("readinessProbe"), c.get("livenessProbe")
    if not readiness:
        erro(onde, "2.2", "sem readinessProbe")
    if not liveness:
        erro(onde, "2.2", "sem livenessProbe")
    if readiness and liveness and readiness == liveness:
        erro(onde, "2.2",
             "readiness e liveness sao identicas; se a checagem tocar o banco, "
             "banco lento reinicia o container e o reinicio nao conserta banco")

    # 3.3 — segredo em texto puro
    for e in c.get("env") or []:
        valor = e.get("value")
        if valor is None:
            continue
        nome_var = e.get("name", "")
        if URL_COM_SENHA.search(str(valor)):
            erro(onde, "3.3", f"env {nome_var} tem URL com credencial embutida")
        elif CHAVE_SENSIVEL.search(nome_var):
            erro(onde, "3.3", f"env {nome_var} parece sensivel e esta em value:")


def checa_configmap(onde: str, obj: dict) -> None:
    # 3.3 — ConfigMap guarda o que nao e sensivel (regra 4.7)
    for k, v in (obj.get("data") or {}).items():
        if URL_COM_SENHA.search(str(v)):
            erro(onde, "3.3", f"chave {k} tem URL com credencial embutida")
        elif CHAVE_SENSIVEL.search(k):
            erro(onde, "3.3", f"chave {k} parece sensivel; use um Secret")


def checa_cruzamentos(objs: list[tuple[str, dict]]) -> None:
    """Regras que so se enxergam olhando mais de um objeto."""
    pods_por_ns: dict[str, list[tuple[str, dict]]] = {}
    for onde, o in objs:
        if o.get("kind") in WORKLOADS:
            tpl_md, _ = pod_template(o)
            ns = (o.get("metadata") or {}).get("namespace") or ""
            pods_por_ns.setdefault(ns, []).append((onde, tpl_md.get("labels") or {}))

    for onde, o in objs:
        md = o.get("metadata") or {}
        ns = md.get("namespace") or ""

        # 1.4 no Service — o caso silencioso. O apiserver rejeita matchLabels que
        # nao casa com o template, mas aceita sem reclamar um Service cujo seletor
        # nao encontra pod nenhum: ele sobe e fica sem endpoint.
        if o.get("kind") == "Service":
            sel = (o.get("spec") or {}).get("selector") or {}
            if not sel:
                continue
            casou = [
                alvo for alvo, labels in pods_por_ns.get(ns, [])
                if all(labels.get(k) == v for k, v in sel.items())
            ]
            if not casou:
                erro(onde, "1.4",
                     f"seletor {sel} nao casa com nenhum pod de '{ns}'; "
                     "o Service sobe e fica sem endpoint")

        # 2.5 — PDB em prod (recomendado)
        if o.get("kind") == "Deployment" and ambiente(ns) == "prod":
            if ((o.get("spec") or {}).get("replicas") or 1) > 1:
                tpl_md, _ = pod_template(o)
                labels = tpl_md.get("labels") or {}
                tem_pdb = any(
                    p.get("kind") == "PodDisruptionBudget"
                    and (p.get("metadata") or {}).get("namespace") == ns
                    and all(
                        labels.get(k) == v
                        for k, v in (((p.get("spec") or {}).get("selector") or {})
                                     .get("matchLabels") or {}).items()
                    )
                    for _, p in objs
                )
                if not tem_pdb:
                    aviso(onde, "2.5", "workload de prod com mais de uma replica sem PDB")


def carrega(caminhos: list[str]) -> list[tuple[str, dict]]:
    objs: list[tuple[str, dict]] = []
    for bruto in caminhos:
        p = pathlib.Path(bruto)
        arquivos = sorted(p.rglob("*.y*ml")) if p.is_dir() else [p]
        for arq in arquivos:
            try:
                docs = list(yaml.safe_load_all(arq.read_text()))
            except yaml.YAMLError as e:
                erros.append(f"ERRO  ----  {arq} — YAML invalido: {e}")
                continue
            for i, doc in enumerate(docs):
                if isinstance(doc, dict) and doc.get("kind"):
                    nome = (doc.get("metadata") or {}).get("name", f"doc{i}")
                    objs.append((f"{arq}:{doc['kind']}/{nome}", doc))
    return objs


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2

    objs = carrega(argv)
    if not objs:
        print("nenhum manifesto encontrado em: " + " ".join(argv), file=sys.stderr)
        return 2

    for onde, obj in objs:
        checa_metadata(onde, obj)
        if obj["kind"] in WORKLOADS:
            checa_workload(onde, obj)
        elif obj["kind"] == "ConfigMap":
            checa_configmap(onde, obj)
    checa_cruzamentos(objs)

    for linha in erros:
        print(linha)
    for linha in avisos:
        print(linha)

    print()
    print(f"{len(objs)} objetos · {len(erros)} erro(s) · {len(avisos)} aviso(s)")
    if erros:
        print("Reprovado. Regra obrigatoria ou proibida so passa com aprovacao "
              "escrita de Seguranca & Compliance no PR, com prazo de validade.")
    return 1 if erros else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
