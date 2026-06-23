# Bot Facebook Marketplace

Bot em Python que responde automaticamente no chat do Facebook Marketplace com base no horário de atendimento e FAQ configurável.

## Funcionalidades

- **Horário de atendimento automático** — respostas diferentes dentro e fora do expediente
- **FAQ automático** — detecta palavras-chave e responde sobre preço, frete, pagamento e garantia
- **Webhook Flask** — integração com a API do Facebook Messenger
- **Configuração em JSON** — todos os textos, horários e tokens em `config.json`
- **Endpoint `/status`** — verifica se a loja está aberta no momento

## Horário de atendimento padrão

| Dia         | Horário       |
|-------------|---------------|
| Seg – Sex   | 8h às 18h     |
| Sábado      | 9h às 13h     |
| Domingo     | Fechado       |

## Instalação

```bash
pip install -r requirements.txt
```

## Configuração

1. Copie `.env.example` para `.env`:
   ```bash
   cp .env.example .env
   ```

2. Preencha as variáveis no `.env`:
   - `FB_PAGE_ACCESS_TOKEN` — token de acesso da página do Facebook
   - `FB_VERIFY_TOKEN` — token de verificação do webhook (você define)
   - `FB_APP_SECRET` — segredo do app Facebook

3. Edite `config.json` para personalizar horários, mensagens e FAQ.

## Executando

```bash
# Desenvolvimento
python bot.py

# Produção
gunicorn bot:app --bind 0.0.0.0:5000
```

## Configuração do Webhook no Facebook

1. No [Facebook Developers](https://developers.facebook.com), acesse seu app
2. Vá em **Messenger → Configurações**
3. Em **Webhooks**, adicione a URL: `https://seu-dominio.com/webhook`
4. Defina o **Verify Token** igual ao `FB_VERIFY_TOKEN` do seu `.env`
5. Assine os eventos: `messages`, `messaging_postbacks`

## Estrutura do projeto

```
├── bot.py           # Aplicação principal (webhook + lógica)
├── config.json      # Horários, mensagens e FAQ
├── requirements.txt # Dependências Python
├── .env.example     # Exemplo de variáveis de ambiente
└── .gitignore
```
