# Bot Facebook Marketplace

Bot em Python que responde automaticamente às mensagens do Facebook Marketplace usando automação de browser (sem API oficial).

## Como funciona

O bot abre o Chrome, faz login no Facebook e monitora a caixa de entrada do Marketplace. A cada intervalo configurável, verifica se há novas mensagens e responde automaticamente com base no horário de atendimento e FAQ.

## Funcionalidades

- **Horário de atendimento automático** — respostas diferentes dentro e fora do expediente
- **FAQ automático** — detecta palavras-chave e responde sobre preço, frete, pagamento e garantia
- **Digitação humanizada** — simula comportamento humano para evitar detecção
- **Intervalo configurável** — define de quantos em quantos segundos verifica novas mensagens
- **Modo headless** — pode rodar sem abrir janela do browser

## Horário de atendimento padrão

| Dia         | Horário       |
|-------------|---------------|
| Seg – Sex   | 8h às 18h     |
| Sábado      | 9h às 13h     |
| Domingo     | Fechado       |

## Requisitos

- Python 3.10+
- Google Chrome instalado

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
   ```
   FB_EMAIL=seu_email@facebook.com
   FB_PASSWORD=sua_senha_aqui
   ```

3. Edite `config.json` para personalizar horários, mensagens e FAQ.

   Configurações principais:
   - `check_interval_seconds` — intervalo entre verificações (padrão: 60s)
   - `headless` — `true` para rodar sem abrir janela do Chrome

## Executando

```bash
python bot.py
```

## Estrutura do projeto

```
├── bot.py           # Lógica principal (automação + respostas)
├── config.json      # Horários, mensagens e FAQ
├── requirements.txt # Dependências Python
├── .env.example     # Modelo de variáveis de ambiente
└── .gitignore
```

## Aviso

Este bot usa automação de browser para interagir com o Facebook. Use com responsabilidade e dentro dos termos de uso da plataforma.
