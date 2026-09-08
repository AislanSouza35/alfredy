# Política de Privacidade — ALF

*Última atualização: 8 de setembro de 2026*

O ALF é um assistente de voz que roda **no computador do próprio
usuário**. Ele não tem servidor, não tem banco de dados e não existe
nenhuma infraestrutura nossa por trás dele.

Este documento descreve o que o programa faz com dados, porque o Google
exige que aplicativos que usam contas Google publiquem essa informação.

## Quem opera este aplicativo

O ALF é usado por uma única pessoa, o autor, em suas próprias contas
Google. Não é distribuído como serviço e não há outros usuários.

## Que dados o ALF acessa

Com a sua autorização, e apenas enquanto você a mantiver, o ALF acessa:

- **Google Classroom** — suas turmas, atividades, lista de alunos e
  entregas, para consultar e para lançar notas nas atividades que ele
  mesmo criou.
- **Google Drive (somente leitura)** — os arquivos que os alunos
  entregam nas atividades, para que o conteúdo possa ser lido durante a
  correção.
- **Google Drive (arquivos do próprio app)** — para criar questionários,
  apresentações, documentos e planilhas, e para anexar arquivos às
  atividades. Este acesso alcança **apenas** os arquivos criados pelo
  ALF; o restante do seu Drive permanece fora do alcance dele.
- **Google Forms** — para criar questionários com gabarito.
- **Google Agenda (eventos)** — para criar, listar e cancelar
  compromissos. Não alcança as configurações das suas agendas.
- **Seu endereço de e-mail** — apenas para saber de qual conta é cada
  autorização, quando mais de uma está conectada.

O ALF também pode ler a tela do computador e a webcam, e enviar e-mail
por SMTP, quando o usuário pede. Nada disso envolve as APIs do Google.

## Onde os dados ficam

**Tudo fica no computador do usuário.** Os tokens de autorização são
gravados na pasta do programa, junto das preferências, contatos e
memórias que o usuário pedir para guardar.

Não enviamos dados para nenhum servidor nosso, porque não existe
servidor nosso.

## Com quem os dados são compartilhados

Apenas com os serviços necessários para o funcionamento, e apenas o que
cada um precisa:

- **Google** — as chamadas às APIs listadas acima.
- **Google Gemini** — o áudio da conversa, e as imagens ou textos que o
  usuário pedir para analisar. É o modelo de linguagem que dá voz ao
  assistente.
- **Provedor de e-mail do usuário** — quando ele pede para enviar uma
  mensagem.

Nenhum dado é vendido, cedido ou usado para publicidade, treinamento de
modelo próprio ou qualquer outra finalidade.

## O que o ALF nunca faz

- Não lê nem envia arquivos que aparentem conter senhas, chaves ou
  credenciais.
- Não apaga nem sobrescreve arquivos sem guardar uma cópia de
  segurança.
- Não envia e-mail nem lança nota sem confirmação explícita do usuário,
  dita em voz alta e em um passo separado.
- Não altera arquivos de alunos no Drive: esse acesso é somente
  leitura.

## Retenção e remoção

Os dados ficam no computador enquanto o usuário quiser. Para apagar
tudo:

1. Revogue o acesso do aplicativo em
   [myaccount.google.com/permissions](https://myaccount.google.com/permissions).
2. Apague os arquivos da pasta `memory/` do programa.

Não existe cópia em outro lugar para ser removida.

## Contato

Dúvidas sobre esta política: abra uma questão em
[github.com/AislanSouza35/alfredy/issues](https://github.com/AislanSouza35/alfredy/issues).
