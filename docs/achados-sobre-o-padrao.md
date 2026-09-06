# Achados sobre o padrão

Oito pontos em que o texto do wiki, seguido literalmente, não produz o resultado
que promete. Nenhum deles contraria o que a regra quer — todos são sobre a
distância entre o que está escrito e o que o cluster faz.

Estão agrupados pelo tipo de problema, porque o tipo determina a correção: regra
que não aplica precisa de exemplo novo, regra que descreve mal o sintoma precisa
de texto novo, e buraco precisa de regra nova.

**Como reproduzir.** `bash laboratorio/experimentos.sh` roda os cinco primeiros
achados contra um cluster e imprime a saída transcrita abaixo. O ambiente é kind
com Kubernetes v1.31.0, três nós, Pod Security `restricted` nos namespaces. A
execução completa está em `evidencias/experimentos.txt`.

---

# Regras que não aplicam como estão escritas

## 1 · O bloco da regra 3.2 não diz em que nível entra, e no nível errado não sobe

A 3.2 apresenta um `securityContext` de cinco campos sem indicar se ele vai no
pod ou no container. Três deles só existem em `SecurityContext`, de container —
`PodSecurityContext` não os tem. Quem copiar o bloco para `spec.securityContext`,
que é a leitura natural de um exemplo sem indentação de contexto, leva:

```
$ kubectl apply --dry-run=server -f teste-sc-nivel-pod.yaml
Error from server (BadRequest): Pod in version "v1" cannot be handled as a Pod:
  strict decoding error:
  unknown field "spec.securityContext.allowPrivilegeEscalation",
  unknown field "spec.securityContext.capabilities",
  unknown field "spec.securityContext.readOnlyRootFilesystem"
```

A mensagem não menciona nível em momento nenhum, então quem está chegando na
plataforma — que é justamente o público que o Bloco 4 diz atender — não tem como
sair dali sozinho.

**Correção:** publicar o exemplo já dividido. No pod, `runAsNonRoot`,
`runAsUser`, `runAsGroup` e `fsGroup`; no container, `allowPrivilegeEscalation`,
`readOnlyRootFilesystem` e `capabilities.drop`. É o formato de
`manifests/nyx-prod/10-api-deployment.yaml`.

## 2 · Cumprir a 3.2 integralmente não basta para o pod entrar

Suponha o achado 1 já resolvido: os cinco campos da regra colocados cada um no
nível correto, nada a mais e nada a menos. O pod ainda assim não entra em
namespace com Pod Security `restricted`:

```
$ kubectl apply --dry-run=server -f teste-sem-seccomp.yaml
Error from server (Forbidden): pods "teste-sem-seccomp" is forbidden:
  violates PodSecurity "restricted:latest": seccompProfile
  (pod or container "api" must set securityContext.seccompProfile.type
   to "RuntimeDefault" or "Localhost")
```

O scan do pipeline cobra a mesma ausência por dois checks, KSV-0030 e KSV-0104.
Ou seja: seguir a 3.2 ao pé da letra produz um manifesto que o cluster recusa e
que nasce com dois achados abertos na varredura que a própria Segurança &
Compliance mantém.

**Correção:** o campo faltante é `seccompProfile`, com valor `RuntimeDefault`.
Ele pertence ao nível de pod, então entra no mesmo bloco que a correção anterior
já cria. São duas linhas que fazem a regra passar a produzir manifesto aplicável.

## 3 · O `runAsUser: 10001` do exemplo virou requisito sem ter sido escrito como um

A 3.2 fixa `runAsUser: 10001` no exemplo. O Postgres da imagem alpine não sobe com
esse UID: os arquivos do banco pertencem ao usuário 70, e é com ele que o processo
precisa rodar. Usando o UID que funciona, o scan acusa:

```
KSV-0020 (LOW): Runs with UID <= 10000
KSV-0021 (LOW): Runs with GID <= 10000
```

O que a regra exige de fato — `runAsNonRoot: true` — está atendido, e o PSA
`restricted` do namespace confirma que está. O número específico era ilustração e
passou a ser lido como piso, inclusive por ferramenta.

**Correção:** dizer na 3.2 que o UID do exemplo é ilustrativo e que o requisito é
não rodar como root. Se a casa quiser mesmo um piso numérico, escrevê-lo como
regra própria e reconhecer que imagem de terceiro nem sempre permite.

---

# Uma regra que descreve o sintoma errado

## 4 · Na 1.4, o caso silencioso é só o Service

A regra descreve o problema assim:

> É o erro mais comum do parque, e o mais silencioso: o objeto sobe, a revisão
> passa, e o serviço simplesmente não tem para onde mandar tráfego.

E ilustra com um `matchLabels` de Deployment divergindo dos rótulos do template.

A descrição está certa, o exemplo não. Num Deployment esse desencontro não chega
a ser silencioso — nem chega a existir, porque o objeto é rejeitado na entrada:

```
$ kubectl apply --dry-run=server -f teste-seletor.yaml
The Deployment "teste-seletor" is invalid: spec.template.metadata.labels:
  Invalid value: map[string]string{"app":"nyxapi"}:
  `selector` does not match template `labels`
```

Quem some sem avisar é o Service. Criado sem uma linha de reclamação, e o objeto
de endereços aparece vazio de conteúdo:

```
$ kubectl apply -f teste-serv-seletor-errado.yaml
service/teste-serv-seletor-errado created

$ kubectl get endpoints teste-serv-seletor-errado -o yaml
apiVersion: v1
kind: Endpoints
metadata:
  name: teste-serv-seletor-errado
  namespace: lab-experimentos
```

De passagem, a saída acima confirma um detalhe que a 4.6 acerta e que costuma
pegar quem automatiza em cima da API: não existe lista vazia de endereços. A
chave some por inteiro, e código que espera `subsets: []` quebra.

A consequência prática é sobre o que vale automatizar. Verificar o `matchLabels`
duplica trabalho que o apiserver já faz; verificar o seletor do Service contra os
pods do namespace é a única metade que acrescenta alguma coisa.

**Correção:** trocar o exemplo por um par Service/pod, que é onde o sintoma
descrito de fato ocorre. O caso do `matchLabels` merece uma linha à parte,
informando que ele é impossível de aplicar — saber que uma classe inteira de erro
já está bloqueada poupa tempo de quem revisa.

---

# Uma regra que colide com outra coisa mantida pela mesma área

## 5 · Obedecer à 3.7 gera achado na varredura do Bloco 3

O catálogo do scan tem lista própria de registries confiáveis, e o domínio do
parque não está nela. Toda imagem que cumpre a regra é marcada:

```
KSV-0125 (MEDIUM): Container api in deployment nyx-api uses an image from
an untrusted registry.
```

Nos manifests conformes deste repositório são quatro ocorrências, uma por imagem,
todas geradas por acertar. O Bloco 3 abre dizendo que a varredura e esta página se
complementam; neste ponto elas se contradizem, e as duas são da mesma área.

O custo não é o achado em si, é o hábito: um MEDIUM permanente que todo mundo
aprende a ignorar leva junto o MEDIUM que importava.

**Correção definitiva:** declarar `registry.metacortex.io` entre os registries
confiáveis na configuração do scan. É uma linha, e vale para o parque inteiro.

Até lá, este repositório trata o conflito em dois lugares: a exclusão está em
`.trivyignore.yaml` acompanhada da justificativa, e a checagem de fato da regra
3.7 vive no conferidor, que sabe qual é o registry da casa.

---

# O que o padrão não cobre

## 6 · Não há vocabulário para carga com estado

Duas regras tropeçam no mesmo ponto quando o workload tem estado.

A **1.3** enumera os objetos que carregam os quatro rótulos: "Deployment,
Service, ConfigMap, Secret, Job, CronJob". StatefulSet não está, e Namespace
também não, embora os dois subam para o cluster como qualquer outro. Nos rótulos
em si a lacuna reaparece: `app.kubernetes.io/name` descreve "o componente", e um
Namespace não é componente de nada — o valor que se escolher ali é arbitrário.

A **2.3** exige duas réplicas em prod sem qualificar o tipo de carga. Para um
banco de escrita única a regra não tem como ser cumprida no espírito: subir uma
segunda réplica de Postgres com volume próprio não produz disponibilidade,
produz um segundo banco divergindo do primeiro.

A 4.3 chega perto de reconhecer o problema quando define Deployment como o objeto
de "aplicação sem estado", mas o padrão não continua a frase: não diz o que
escrever quando a aplicação tem estado.

Neste repositório o `nyx-postgres` é um StatefulSet de uma réplica em prod, com a
exceção anotada no próprio objeto — que é o que a seção Exceções exige de desvio
a regra obrigatória, junto de aprovação escrita e prazo de validade.

**Correção:** incluir StatefulSet na enumeração da 1.3, restringir a 2.3 a carga
sem estado, e escrever uma regra separada para banco e afins.

## 7 · Nada trata de dependência que falha na inicialização

No primeiro start da API o processo termina em `CrashLoopBackOff`:

```
Error: getaddrinfo EAI_AGAIN nyx-postgres
```

O rastro está em `evidencias/cluster-nyx.txt`: em `nyx-stg`, a réplica
`nyx-api-5c5589df99-gk7pn` acumula duas reinicializações aos 78s de vida,
enquanto a outra réplica, do mesmo Deployment e da mesma idade, tem zero. A
diferença é em qual nó o pod caiu antes de o `nyx-postgres` ficar pronto. A
mensagem acima foi lida com `kubectl logs --previous` durante a execução e não
está transcrita nas evidências.

O DNS de um Service só publica endereço de pod pronto. A aplicação resolve o
banco durante a subida, não encontra, e encerra o processo em vez de tentar de
novo. Ela se recupera sozinha no backoff seguinte, então não é defeito do
manifesto — mas todo deploy novo passa alguns minutos exibindo pod em CrashLoop, e
de plantão isso é indistinguível de um problema real.

`startupProbe` não resolve: o processo morre antes de qualquer probe ser
consultada.

**Correção:** um parágrafo na 2.2 ou na 4.8 dizendo que probe não cobre
dependência que falha na inicialização, e que a resposta é a aplicação repetir a
tentativa — não uma probe mais frouxa, que só atrasaria a detecção.

---

# Ajustes de redação

## 8 · Pontos menores, sem evidência de cluster

**Na 1.4, sobre a escolha dos rótulos do seletor.** O seletor de um Deployment não
pode ser alterado depois de criado. Isso torna arriscado colocar nele um rótulo
cujo valor muda com o tempo, e `managed-by` é o caso óbvio: o próprio padrão lista
três valores possíveis para ele, o que significa que a troca é prevista. Um
seletor que inclua rótulo mutável obriga a apagar e recriar o objeto no dia da
troca. Vale a regra recomendar `name` e `instance`, que não mudam.

**Entre a 2.3 e a 2.5, sobre o que o PDB não faz.** As duas regras juntas dão a
impressão de resolver disponibilidade, e elas resolvem metades diferentes. O PDB
atua sobre despejo voluntário; ele não tem influência nenhuma sobre onde o
escalonador coloca as réplicas. Duas réplicas que foram parar no mesmo nó
satisfazem a 2.3 e satisfazem o PDB, e ainda assim desaparecem juntas quando esse
nó sai. Vale a 2.5 recomendar `topologySpreadConstraints` por
`kubernetes.io/hostname`, que é o que fecha a lacuna.

**Na 2.5, sobre onde não aplicar.** Um PDB de `minAvailable: 1` sobre workload de
réplica única impede qualquer drenagem de nó — o objeto passa a bloquear
manutenção em vez de proteger contra ela. Vale a regra dizer que ele é para prod e
que não deve ser replicado para dev por simetria.

**Na 4.6, sobre a API citada.** O cluster avisa a cada consulta que `v1 Endpoints`
está sendo aposentado e que a informação equivalente vive em `EndpointSlice`. O
objeto continua sendo o caminho mais curto para descobrir Service sem tráfego, e
o verbete está correto, mas quem chegar agora vai encontrar `EndpointSlice` nas
ferramentas antes de encontrar `Endpoints`.
