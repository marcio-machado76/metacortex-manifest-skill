# Cobertura das regras

O padrão tem 19 regras acionáveis. Este documento diz, para cada uma, quem
responde por ela: o scan que já roda no pipeline, o verificador deste repositório,
ou a pessoa que revisa o PR.

A ordem aqui não é a do wiki. Agrupar por bloco temático serve para escrever a
regra; agrupar por quem verifica é o que serve para decidir o que automatizar.

## De onde saiu esta divisão

Antes de escrever uma linha de verificador, rodamos o scan no contraexemplo para
saber o que ele já resolvia. O resultado está em `evidencias/trivy-antipadrao.txt`:

```
18 achados, em 17 checks distintos
```

Parece muito até você mapear cada achado de volta para as regras do padrão. Os 18
se concentram em **quatro**: 2.1, 3.1, 3.2 e — ao contrário, como se verá — a 3.7.
As outras quinze o scan não menciona uma única vez.

Duas ausências pesam mais que as outras, porque são justamente os dois piores
desvios do contraexemplo:

| Regra | Gravidade no padrão | O scan diz |
| --- | --- | --- |
| 3.3 senha em `env.value` | proibido | nada — nem com `trivy fs --scanners secret` |
| 1.4 seletor que não casa | obrigatório | nada — zero menções a `selector` na saída |

Foi essa medição, e não uma suposição sobre o que a ferramenta faria, que definiu
o escopo de `ferramentas/conferir-padrao.py`.

## As 19 regras e quem responde

| Regra | Peso | Scan | Verificador | Revisão |
| --- | --- | :-: | :-: | :-: |
| 1.1 kebab-case | obrigatório | | ● | |
| 1.2 namespace `<cliente>-<ambiente>` | obrigatório | | ● | |
| 1.3 quatro rótulos | obrigatório | | ● | |
| 1.4 seletor casa com o pod | obrigatório | | ● | |
| 1.5 anotação de dono | recomendado | | ○ | |
| 1.6 nome do container | recomendado | | ○ | |
| 2.1 requests e limits | obrigatório | ● | | ● |
| 2.2 as duas probes | obrigatório | | ● | ● |
| 2.3 replicas ≥ 2 em prod | obrigatório | | ● | |
| 2.4 estratégia de rollout | obrigatório em prod | | ● | |
| 2.5 PDB em prod | recomendado | | ○ | |
| 2.6 grace period | recomendado | | | ● |
| 3.1 `:latest` | proibido | ● | | |
| 3.2 securityContext | obrigatório | ● | | |
| 3.3 segredo em texto puro | proibido | | ◐ | ● |
| 3.4 token desmontado | obrigatório | | ● | ● |
| 3.5 ServiceAccount dedicada | recomendado | | ○ | ● |
| 3.6 hostNetwork / hostPID / privileged | proibido | ● | | |
| 3.7 registry interno | obrigatório | | ● | |

● responde · ○ avisa, não reprova · ◐ levanta suspeita, não decide

## O que o scan já resolve

Quatro regras, e nenhuma delas foi reimplementada no verificador. Duplicar
detecção custa manutenção e cria divergência: no dia em que as duas discordarem,
ninguém sabe qual está certa.

| Regra | Checks que a cobrem |
| --- | --- |
| 2.1 | KSV-0011, KSV-0015, KSV-0016, KSV-0018 |
| 3.1 | KSV-0013 |
| 3.2 | KSV-0001, KSV-0003, KSV-0004, KSV-0012, KSV-0014, KSV-0106, KSV-0118 |
| 3.6 | coberto pelo catálogo do scan e recusado pelo PSA `restricted` do namespace |

A 3.2 tem uma segunda linha de defesa que não é ferramenta nenhuma: os rótulos
`pod-security.kubernetes.io/enforce: restricted` nos Namespaces fazem o cluster
recusar o pod na admissão. Regra escrita e regra aplicada são coisas diferentes,
e essa é a diferença.

## O que o verificador acrescenta

Catorze regras. O critério para entrar foi um só: **a resposta está inteiramente
dentro do YAML, e nenhuma ferramenta de mercado tem como saber a convenção da
casa.** Nomenclatura, formato de namespace, rótulos e registry interno são da
Metacortex, não do Kubernetes.

### Identidade

`1.1` compara `metadata.name` com `^[a-z0-9]+(-[a-z0-9]+)*$`.
`1.2` exige que o namespace termine em `-dev`, `-stg` ou `-prod`.
`1.3` cobra os quatro rótulos em todo objeto **e** no template do pod — é comum
rotular só o Deployment e esquecer o pod que ele gera.

`1.4` é a que mais rende, mas não pelo motivo que o padrão dá. O apiserver já
rejeita `matchLabels` divergente do template; quem sobe calado é o **Service**,
que é criado sem reclamação e nasce sem endpoint. Por isso o verificador cruza o
seletor de cada Service com os rótulos dos pods do mesmo namespace, que é a
verificação que o cluster não faz por você. O detalhe está em
`achados-sobre-o-padrao.md`.

### Resiliência

`2.2` confere que as duas probes existem e reprova quando são idênticas — que é a
forma detectável do problema que o padrão descreve. Se as duas apontam para o
mesmo lugar e esse lugar toca o banco, banco lento vira reinício, e reinício não
conserta banco.

`2.3` e `2.4` só são cobradas quando o namespace termina em `-prod`, que é
exatamente como o padrão as escreve. `2.5` avisa quando falta PDB num workload de
prod com mais de uma réplica.

Vale notar o que essa condicional implica para os três ambientes deste
repositório. O conferidor não cobra nada de `nyx-stg` nessas três regras — e
`nyx-stg` as cumpre assim mesmo, com duas réplicas, `maxUnavailable: 0` e PDB. A
regra 2.3 estabelece um piso para produção ("uma réplica é aceitável" em dev e
stg), não um teto para homologação, e ensaiar em stg o comportamento que só é
obrigatório em prod é o que dá sentido a ter um stg.

`nyx-dev`, no extremo oposto, fica no mínimo autorizado: uma réplica, rollout com
folga e nenhum PDB. A ausência do PDB ali é decisão e não esquecimento — sobre um
workload de réplica única, `minAvailable: 1` impede qualquer drenagem de nó, e o
objeto passa a bloquear manutenção em vez de proteger contra ela.

### Segurança

`3.3` é heurística e o verificador não finge o contrário: procura URL com
credencial embutida e nome de variável que pareça sensível, em `env.value` e em
`ConfigMap`. Ela aponta o lugar; dizer se aquilo é mesmo segredo continua sendo
leitura humana.

`3.4` confere o campo no pod. `3.5` avisa quando o workload usa a ServiceAccount
`default`. `3.7` compara o prefixo da imagem com o registry do parque — e essa é
`verificador` e não `scan` de propósito, porque o catálogo do scan tem lista
própria de registries confiáveis, que não inclui o domínio da casa.

## O que só a revisão resolve

Cinco resíduos. Em todos, o dado que decide a resposta está fora do manifesto:

| Regra | O que falta para automatizar |
| --- | --- |
| 2.1 | O consumo em regime, para saber se o limite está entre 1,5x e 2x dele |
| 2.2 | Saber quais endpoints a aplicação expõe, e o que cada um checa |
| 2.6 | Saber quanto a aplicação demora para drenar, e se ela trata SIGTERM |
| 3.4 / 3.5 | Saber se a aplicação fala com o apiserver — a regra 3.4 é condicional |
| 3.3 | Julgar se o valor apontado pela heurística é sensível, ou o contrário |

Nenhum desses vira script sem que a ferramenta passe a ler o código da aplicação
ou consultar métrica de runtime — que é outro problema, com outro custo.

## O que ficou de fora

**O Bloco 4 inteiro.** São oito verbetes de vocabulário — Pod, ReplicaSet,
Deployment, Service, `port` × `targetPort`, Endpoints, ConfigMap e Secret, probes
— escritos para quem está chegando. Nenhum deles aprova ou reprova manifesto
nenhum. É um terço da página e zero regra.

Isso não quer dizer que foi ignorado: o que o Bloco 4 explica aparece **aplicado**
nos manifests, com o número da regra no comentário. A 4.5 no `targetPort: http`,
a 4.7 na separação entre ConfigMap e Secret, a 4.8 na `startupProbe`.

**NetworkPolicy, Ingress, HPA e RBAC detalhado.** O padrão não fala de nenhum
deles. Acrescentar regra que o documento não tem transformaria o verificador em
opinião de quem o escreveu, e criaria desvio onde a casa não vê desvio.

**Onde a fronteira ficou explícita.** O `.trivyignore.yaml` registra, com
justificativa escrita, os dois pontos em que o scan e o padrão discordam. Não é
exceção ao padrão: é exceção à ferramenta, e a diferença está documentada lá e em
`achados-sobre-o-padrao.md`.
