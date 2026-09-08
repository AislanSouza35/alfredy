---
name: lancando-notas-sigeduc
description: Use when lancando, importando, conferindo ou salvando notas de alunos no SIGEduc a partir de planilha, especialmente em Diario de Classe Digital, Lancar Resultados, unidades e avaliacoes.
---

# Lancando Notas no SIGEduc

Use esta skill para preencher notas no SIGEduc com seguranca operacional e cuidado com dados sensiveis. A regra principal e: leia as notas da planilha, confirme o destino com o usuario, mapeie por nome do aluno e verifique os campos antes de qualquer gravacao.

## Principios

- Trate notas, frequencia, situacao de aluno e dados do sistema escolar como informacoes sensiveis. Antes de digitar ou enviar notas no SIGEduc, peca confirmacao explicita do usuario para a disciplina/componente, unidade, avaliacao e origem dos dados.
- Nunca peca, armazene, veja ou digite a senha do usuario. Quando o SIGEduc abrir confirmacao por senha, pare e deixe o usuario preencher a senha e confirmar.
- Nao escolha opcoes de dialogos finais como "Sim", "Nao", "Confirmar" ou equivalentes sem uma instrucao explicita do usuario naquele momento.
- Nao confie na ordem das linhas da planilha como igual a ordem do SIGEduc. Sempre relacione as notas pelo nome normalizado do aluno.
- Preserve ausencias ou notas em branco conforme a planilha e o pedido do usuario. Em campos numericos, deixe em branco quando o dado for "AUSENTE", vazio ou equivalente.

## Preparacao

- Leia a planilha com uma ferramenta propria para arquivos `.xlsx` quando disponivel. Extraia, no minimo, disciplina/aba, nome do aluno e nota.
- Normalize nomes para comparacao: remover acentos, converter para maiusculas, colapsar espacos e aparar pontuacao irrelevante. Mantenha o nome original para relatorios ao usuario.
- Identifique a disciplina/componente exata no SIGEduc. Se a planilha tiver nomes abreviados ou diferentes, confirme a correspondencia com o usuario antes de preencher.
- Se houver mais de uma unidade ou avaliacao, confirme qual coluna/campo deve receber a nota. Para colunas com escala, como `NOTA (0-6)`, confira no SIGEduc o campo da avaliacao com valor maximo correspondente.

## Navegacao no SIGEduc

- Use o navegador conectado que tenha a sessao do usuario. Se a sessao expirar, a pagina ficar preta ou o sistema voltar para login/vinculos, recarregue e deixe o usuario autenticar.
- Quando houver escolha de vinculo, selecione apenas o vinculo confirmado pelo usuario. Para trabalhos no Colegio Modelo Luis Eduardo Magalhaes, o vinculo usado anteriormente foi matricula `92094759`, lotacao `COLEGIO MODELO LUIS EDUARDO MAGALHAES`; confirme se isso ainda e o destino correto.
- No portal docente, encontre a linha do componente pelo texto da disciplina e abra `Lancar Resultados`. Em paginas com varios icones iguais, use a linha do componente como contexto e confira o titulo depois de abrir.
- Para mudar unidade, prefira acionar o link/aba real. No SIGEduc, a aba `2a Unidade` pode estar em um seletor como `a[href="#formulario:tab1j_id_1"]`; clicar apenas no texto interno pode falhar.

## Preenchimento

- Localize as linhas de estudantes visiveis/editaveis no formulario. Para cada linha, capture o nome do estudante e os campos `input.avaliacao` visiveis e habilitados.
- Escolha o campo da avaliacao pelo cabecalho/valor maximo quando isso estiver disponivel. Quando a coluna da planilha for `NOTA (0-6)`, o campo correto costuma ser a avaliacao de valor `6.0`; so use atalhos como "terceiro campo editavel" depois de confirmar que esse e o campo correto naquela tela.
- Digite as notas por interacao de teclado, pois o SIGEduc pode rejeitar `fill`, `paste` ou atribuicao direta por JavaScript. Procedimento confiavel: focar o campo, `Control+A`, `Backspace`, depois pressionar os digitos da nota sem copiar/colar; por exemplo, para `5.1`, pressionar `5` e `1` e deixar a mascara formatar.
- Nao sobrescreva outros campos de avaliacao, medias, recuperacao ou resultados finais que nao sejam o destino confirmado.
- Se um aluno da planilha nao aparecer no SIGEduc, ou se aparecer aluno no SIGEduc sem nota correspondente, pare antes de salvar e reporte a divergencia.

## Verificacao e gravacao

- Depois de preencher, leia os valores exibidos nos campos e compare com as notas esperadas. Informe qualquer divergencia e corrija antes de continuar.
- So clique em `Gravar` quando o usuario tiver autorizado. Se abrir modal de senha, diga ao usuario que ele deve digitar a senha e confirmar.
- Se aparecer uma tela de verificacao de avaliacoes nao realizadas por causa de campos em branco, explique quais alunos ficaram sem nota e aguarde a escolha do usuario.
- Depois que o usuario confirmar que salvou, registre no resumo qual disciplina, unidade e avaliacao foram preenchidas, quais alunos ficaram em branco e se houve divergencias.

## Recuperacao

- Se a pagina recarregar antes da gravacao, considere que valores nao salvos podem ter sido perdidos. Releia a tela e refaca a verificacao antes de concluir.
- Se houver multiplas abas do SIGEduc abertas, use a aba ativa que corresponde ao formulario correto e evite criar duplicatas sem necessidade.
- Em caso de instabilidade visual, como tela preta, tente recarregar a aba ou voltar ao portal docente; se a autenticacao for exigida, devolva o controle ao usuario.
