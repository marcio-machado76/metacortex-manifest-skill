# metacortex-padrao-manifests

O **Padrão de Manifests da Metacortex** já existe e está escrito — e mesmo assim
manifesto torto continua chegando na revisão. Uma página de wiki é boa para
guardar decisão; é ruim para conferir regra a regra no meio de uma tarefa.

Este repositório transforma aquela página em três coisas que ela não consegue ser:

1. **Três ambientes (dev, stg, prod) que cumprem as 19 regras** e sobem num
   cluster de verdade, para copiar em vez de reler.
2. **Um conferidor** que reprova o que dá para reprovar por máquina — e que sabe
   exatamente onde parar, porque o limite foi medido e não estimado.
3. **Um relatório do que aconteceu** quando o texto do padrão foi aplicado ao pé
   da letra contra um Kubernetes real. Oito pontos não sobreviveram ao teste.

A revisão coberta é a de **2026-07-29**, preservada em
[`docs/padrao-de-manifests.md`](docs/padrao-de-manifests.md).

## O que tem aqui

| Caminho | O que é |
| --- | --- |
| `manifests/nyx-prod/` | Produção do cliente nyx: API HTTP e banco, cumprindo as 19 regras |
| `manifests/nyx-stg/` | Homologação, espelhando a postura de produção — ver abaixo |
| `manifests/nyx-dev/` | Desenvolvimento, no mínimo que o padrão autoriza |
| `contraexemplo/` | Um manifesto fora do padrão, montado com os exemplos "errado" do próprio wiki. Não aplique — ele é alvo, não modelo |
| `ferramentas/conferir-padrao.py` | Confere as regras que a varredura do pipeline não conhece |
| `ferramentas/validar.sh` | Executa a bateria completa; é o que a CI chama |
| `.trivyignore.yaml` | Os dois pontos em que a varredura e o padrão discordam, com justificativa escrita |
| `laboratorio/` | Cluster kind e o registry interno que faz `registry.metacortex.io` existir |
| `evidencias/` | Saída bruta de cada execução; a única edição é o `$HOME` no lugar do caminho pessoal |
| `docs/cobertura-das-regras.md` | Regra a regra: quem responde por ela e por quê |
| `docs/achados-sobre-o-padrao.md` | Oito pontos em que o padrão não produz o resultado que promete |

Dentro de cada ambiente os arquivos são numerados na ordem em que precisam ser
aplicados — namespace, contas, configuração, workloads, exposição. Um
`kubectl apply -f manifests/nyx-prod/` respeita essa ordem sem ajuda.

### Por que `stg` não é uma cópia de `dev`

Só três regras distinguem ambiente, e as três separam produção do resto: a 2.3
(duas réplicas), a 2.4 (rollout sem queda de capacidade) e a 2.5 (PDB). A leitura
preguiçosa é tratar `stg` como `dev`, já que a 2.3 diz que "em dev e stg, uma
réplica é aceitável".

Só que aceitável não é obrigatório — o padrão põe um piso em produção, não um teto
em homologação. E um `stg` modelado como `dev` produz um efeito ruim: as três
regras que só valem em produção passam a estrear justamente no deploy de produção,
sem nunca terem sido exercitadas.

Aqui `stg` adota a postura de produção de propósito. O resultado é que cada
ambiente responde por uma coisa diferente:

| Ambiente | Réplicas | `maxUnavailable` | PDB | Serve para |
| --- | :-: | :-: | :-: | --- |
| `nyx-dev` | 1 | 1 | não | O mínimo que o padrão aceita |
| `nyx-stg` | 2 | 0 | sim | Ensaiar as regras de produção antes de produção |
| `nyx-prod` | 2 | 0 | sim | O que o padrão exige |

## Antes de abrir o PR

```bash
bash ferramentas/validar.sh
```

Três etapas, e a terceira é a que costuma faltar em repositório assim:

| Etapa | O que roda | Passa quando |
| --- | --- | --- |
| 1 | `conferir-padrao.py manifests/` | não acha desvio |
| 2 | `trivy config manifests/` | não acha nada além do que está justificado |
| 3 | `conferir-padrao.py contraexemplo/` | **acha** desvio |

A etapa 3 existe porque conferidor que nunca reprova nada é indistinguível de
conferidor quebrado. Se alguém mexer numa regra de detecção e ela parar de
disparar, é aqui que aparece — e não seis meses depois, num incidente.

Sem o Trivy instalado, a etapa 2 avisa e as outras três seguem — quem está
começando não fica travado. Só que numa esteira automatizada esse silêncio é
perigoso: uma instalação que falhasse deixaria a validação passar verde com as
regras 2.1, 3.1, 3.2 e 3.6 sem ninguém por elas. Por isso existe
`TRIVY_OBRIGATORIO=1`, que transforma a ausência em reprovação:

```bash
TRIVY_OBRIGATORIO=1 bash ferramentas/validar.sh
```

A CI em `.github/workflows/padrao.yml` chama esse mesmo script com a variável
ligada. Se algum dia as duas divergirem, o script é a versão correta; a CI só o
executa.

## Rodando no laboratório

Análise estática não responde tudo. Admissão, Pod Security e Service sem endpoint
só aparecem contra um cluster:

```bash
bash laboratorio/subir.sh              # registry interno + cluster kind
bash laboratorio/espelhar-imagens.sh   # publica as imagens no registry do parque
kubectl apply -f manifests/nyx-prod/00-namespace.yaml
bash laboratorio/criar-segredos.sh     # o cofre da plataforma, em miniatura
kubectl apply -f manifests/nyx-prod/
```

E `bash laboratorio/experimentos.sh` reproduz, um a um, os achados de
[`docs/achados-sobre-o-padrao.md`](docs/achados-sobre-o-padrao.md) — para que a
crítica ao padrão seja verificável em vez de opinião.

## Onde passa a linha entre varredura, script e revisão

Essa divisão foi medida antes de ser decidida. Rodando `trivy config` no
contraexemplo, saem 18 achados — que parecem muitos até você mapeá-los de volta
para as regras: eles se concentram em **quatro das 19**. As outras quinze a
varredura não menciona.

E o que ela deixa passar não é periferia. A senha em texto puro (regra 3.3,
classificada como **proibida**) sai limpa até do scanner dedicado a segredos, e o
seletor que não casa (1.4) não aparece uma única vez na saída.

| Quem responde | Regras | Por quê |
| --- | --- | --- |
| `trivy config` | 2.1, 3.1, 3.2, 3.6 | Já vem pronto no catálogo. Reescrever só cria duas fontes de verdade que podem divergir |
| `conferir-padrao.py` | 1.1 a 1.6, 2.2 a 2.5, 3.3, 3.4, 3.5, 3.7 | São convenções da Metacortex, não do Kubernetes — nenhuma ferramenta de mercado tem como conhecê-las |
| Revisão no PR | 2.6, e a parte semântica de 2.1, 2.2, 3.3, 3.4 e 3.5 | O dado que decide está fora do YAML: consumo em regime, rotas da aplicação, se ela fala com o apiserver |

O detalhamento está em
[`docs/cobertura-das-regras.md`](docs/cobertura-das-regras.md).

## Credenciais

Nenhum `Secret` é versionado aqui — é o que a regra 3.3 exige. Os workloads
apontam para um que precisa existir no namespace antes do deploy:

| Secret | Chaves | Quem consome |
| --- | --- | --- |
| `nyx-db` | `username`, `password` | `nyx-api`, via `DB_USERNAME` e `DB_PASSWORD`; e `nyx-postgres`, na inicialização |

No parque, quem cria é o cofre da plataforma. No laboratório o papel é de
`laboratorio/criar-segredos.sh`, que sorteia a senha na hora — e é por isso que
ele mora em `laboratorio/` e não em `manifests/`: ele não é manifesto que sobe
para cluster de cliente.

A regra 3.3 encerra com um aviso que vale reproduzir na íntegra:

> Lembre que Secret do Kubernetes é base64, não criptografia. O padrão vale para
> não versionar o segredo no Git; a proteção em repouso é assunto do cluster.

Ou seja: cumprir a 3.3 resolve o vazamento por repositório, e só ele. Quem tiver
leitura de `Secret` no namespace lê o valor.

O `conferir-padrao.py` cobre a 3.3 por heurística — procura URL com credencial
embutida e nome de variável que pareça sensível, em `env.value` e em `ConfigMap`.
Ela aponta onde olhar. Decidir se aquele valor é mesmo segredo continua sendo
leitura humana, e o script não finge o contrário.

## Imagens e o registry do parque

Toda imagem referenciada aqui vive em `registry.metacortex.io` (regra 3.7), e
sempre por tag imutável (regra 3.1). Nada que nasça fora do parque é apontado
direto: passa antes pelo Loom, que copia para dentro, submete ao scan e republica
com o nome interno.

| Referência no manifesto | Origem pública |
| --- | --- |
| `registry.metacortex.io/nyx/api:2.9.1` | `fabricioveronez/kube-news:v1` |
| `registry.metacortex.io/nyx/postgres:16-alpine` | `postgres:16-alpine` |

Esse domínio não existe fora do parque, o que normalmente condena manifesto
conforme a nunca sair do papel: dá para validá-lo com `--dry-run=server`, mas não
para vê-lo rodando. O laboratório contorna isso materializando o registry —
`laboratorio/subir.sh` sobe um registry local e configura o containerd de cada nó
do kind para resolver `registry.metacortex.io` nele, e
`laboratorio/espelhar-imagens.sh` faz o trabalho que o Loom faria.

O resultado é que os manifests deste repositório cumprem a 3.7 literalmente **e**
sobem num cluster de verdade, sem camada de sobreposição e sem exceção escrita:

```
Successfully pulled image "registry.metacortex.io/nyx/api:2.9.1" in 1.313s
```

Isso produz um efeito colateral que acabou virando achado. A varredura marca as
quatro imagens com KSV-0125, "untrusted registry" — o domínio do parque não consta
da lista dela. Quer dizer que acertar a regra 3.7 gera pendência na ferramenta que
a mesma área de Segurança & Compliance opera, e o custo disso não é o achado em si:
é o hábito de ignorar MEDIUM que ele ensina.

A exclusão e o raciocínio por trás dela estão em `.trivyignore.yaml`; a correção
que encerraria o assunto está descrita em
[`docs/achados-sobre-o-padrao.md`](docs/achados-sobre-o-padrao.md).
