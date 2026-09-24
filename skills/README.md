# Prompts

Instruções em texto puro, para serem entregues a um assistente de IA.
Não dependem de ferramenta específica: funcionam em qualquer assistente
com acesso ao repositório (Claude Code, Cursor, Copilot, aider,
Continue) e também colados num chat sem acesso a arquivos (ChatGPT,
Gemini, modelo local).

| prompt | para quê |
|---|---|
| [estender-o-damfe.md](estender-o-damfe.md) | adaptar o damfe a um projeto: declarar como os micro frontends se comunicam, e escrever o reconstrutor quando a tecnologia ainda não for suportada |

## Como usar

Cole o prompt inteiro no seu assistente e diga o que você precisa. Ele
começa por uma triagem, para descobrir se o seu caso exige só a
declaração de comunicação, só o reconstrutor, os dois, ou nada.

A partir daí ele conduz uma **entrevista**: pergunta o que precisa, uma
ou duas coisas por vez, até ter tudo — e só então produz o resultado.

Responda com **código real**, não com descrição. Descrição produz
resultado errado, e o prompt instrui o assistente a insistir nisso.

Ao final ele pede para você rodar a ferramenta e conferir a saída. Não
pule essa parte: é ela que distingue resultado correto de resultado
plausível.
