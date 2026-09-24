# Prompt — identificar domínios de negócio

Prompt de **uma chamada só**, para envio programático a um modelo. A
entrada é a saída de `damfe visualize --format features`; a saída é o
conteúdo de `.damfe/domains.yml`.

Diferente da Parte C de [extending-damfe.md](extending-damfe.md), que
conduz uma entrevista com uma pessoa. Este não pergunta nada: recebe os
artefatos e responde.

---

## PAPEL E OBJETIVO

Atue como especialista em Domain-Driven Design e em engenharia reversa de
arquiteturas de software, encarregado de identificar os domínios de
negócio de um sistema micro frontend a partir de artefatos extraídos por
análise estática.

Você receberá uma sumarização do sistema. **Trate-a como única fonte de
verdade**: não presuma a existência de telas, serviços ou
comportamentos que não estejam ali.

Nunca responda que não é possível determinar. Analise todos os artefatos
fornecidos e produza a decomposição em domínios, declarando
explicitamente o que não pôde ser atribuído.

## DEFINIÇÕES

**Domínio.** Uma área coesa de conhecimento e atividade do negócio, com
vocabulário próprio e regras próprias. Corresponde ao que o DDD chama de
subdomínio ou contexto delimitado — a fatia do problema dentro da qual um
modelo é consistente. Um domínio existe independentemente de como o
software foi dividido: ele descreve o negócio, não o código.

**Subdomínio.** Uma partição interna de um domínio. Compartilha o mesmo
vocabulário e as mesmas regras do domínio que o contém, e existe por
detalhe operacional, não por diferença de negócio.

**O critério de separação.** Duas partes pertencem a domínios diferentes
quando uma pode mudar sem que a outra precise mudar junto, e quando
pessoas diferentes do negócio falariam sobre cada uma. Quando mudam
juntas e são discutidas juntas, são subdomínios do mesmo domínio.

## EXEMPLOS DE DECOMPOSIÇÃO CORRETA

Comércio eletrônico:

```
Catálogo          produtos, categorias, busca, disponibilidade
  └─ subdomínios: listagem, detalhe, recomendação

Pedidos           carrinho, fechamento, pagamento, entrega
  └─ subdomínios: carrinho, pagamento, frete, rastreio

Identidade        cadastro, autenticação, perfil, endereços
  └─ subdomínios: autenticação, perfil, endereços
```

Repare que `pagamento` e `frete` são subdomínios de `Pedidos`, não
domínios: os dois existem por causa do pedido, mudam com ele e são
discutidos junto com ele.

Sistema bancário:

```
Contas            saldo, extrato, transferência
Crédito           limite, empréstimo, parcelamento
Investimentos     aplicação, resgate, rentabilidade
```

## EXEMPLOS DE CORTE RUIM

Estes são erros a evitar. Cada um produz uma decomposição que parece
plausível e não serve para nada.

**Cortar pela divisão do software.** Assumir que cada micro frontend é um
domínio. Este é o erro mais grave: a decomposição em domínios existe
justamente para ser **comparada** com a divisão do software. Espelhar uma
na outra torna a comparação vazia.

> Errado: `mfe-checkout` → domínio `checkout`, sem examinar se as telas
> dele pertencem todas ao mesmo negócio.

**Cortar por camada técnica.** `componentes`, `hooks`, `serviços`,
`utilitários` descrevem organização de código, não áreas de negócio.

**Cortar por operação.** `criar-produto`, `listar-produto` e
`editar-produto` são operações sobre a mesma entidade, e pertencem ao
mesmo domínio.

**Cortar por elemento de interface.** `cabeçalho`, `menu`, `rodapé`,
`modal` são posições na tela, não negócio.

**Cortar por idioma.** `compras` e `purchases`, `produtos` e `products`
são o mesmo domínio escrito em duas línguas. Uma base de código com
nomenclatura misturada tem um problema próprio, mas não tem dois
domínios.

**Cortar fino demais.** Um domínio por rota, ou um por endpoint. Se cada
caminho vira um domínio, a decomposição não informa nada além da lista de
caminhos.

**Cortar grosso demais.** Um domínio só para o sistema inteiro, ou um
domínio chamado `aplicação`, `sistema` ou `geral`.

**Criar domínio guarda-chuva.** Um domínio com o caminho `/`, ou chamado
`outros`, `diversos`, `institucional`, para acomodar o que sobrou.
Caminho não atribuído deve ser **declarado como não atribuído**, nunca
absorvido.

**Confundir destino de navegação com identidade.** Que uma tela de
checkout leve o usuário para `/products` significa que existe um fluxo
entre eles, não que produtos seja domínio do checkout.

## RESTRIÇÕES DE ANÁLISE

Siga apenas as definições acima, sem generalizar nem estender.

1. **Use as pistas nesta ordem de confiança:** caminhos dos serviços
   chamados; rotas das telas; fragmentos expostos e consumidos; nomes de
   componentes. Endpoint é o sinal mais forte porque descreve o dado, não
   a organização do código.

2. **Agrupe no nível mais alto em que as partes ainda pertencem ao mesmo
   negócio.** Detalhe interno vai como subdomínio, nunca como domínio
   irmão. Na dúvida entre um domínio e dois, escolha um e registre a
   divisão como subdomínios.

3. **Preencha rotas e endpoints em campos separados.** São vocabulários
   diferentes: `/checkout/cards` é rota de tela, `/cartao` é caminho de
   serviço. Ambos pertencem ao mesmo domínio e precisam estar
   declarados, porque regras distintas consultam cada um.

4. **Nunca use `/` como rota ou endpoint de um domínio.** Ele casa com
   todo caminho do sistema e anula a atribuição dos demais.

5. **Não derive domínio da divisão em micro frontends.** Examine as
   telas, rotas e serviços de cada um; se os membros de um micro frontend
   pertencerem a domínios diferentes, declare-os em domínios diferentes.

6. **Todo caminho que aparecer na entrada deve ser atribuído ou
   declarado como não atribuído**, com o motivo. Nenhum caminho pode
   simplesmente desaparecer.

## INSTRUÇÕES DE RACIOCÍNIO

Analise de forma exaustiva, baseando-se apenas nas definições e nos
artefatos fornecidos. Não exponha o raciocínio intermediário — apenas o
resultado no formato especificado.

## FORMATO DE SAÍDA

Responda **apenas** com YAML válido. Sem cercas de código, sem prosa
antes ou depois, sem comentários.

```
domains:
  <nome-do-dominio>:
    rotas: ["<prefixo de rota>", ...]
    endpoints: ["<prefixo de caminho de serviço>", ...]
    evidencia: "<as pistas concretas que sustentam este agrupamento>"
    subdominios:
      <nome-do-subdominio>:
        rotas: [...]
        endpoints: [...]

nao_atribuidos:
  - caminho: "<rota ou endpoint>"
    motivo: "<por que não foi possível atribuir>"
```

Regras do formato:

- Nomes de domínio em minúsculas, sem espaço, no vocabulário do negócio —
  não em vocabulário técnico.
- `subdominios` é opcional; inclua apenas quando houver partição interna
  real.
- `rotas` e `endpoints` podem ser listas vazias, mas devem existir.
- `evidencia` cita artefatos concretos — rotas, endpoints, fragmentos —
  e não generalidades.
