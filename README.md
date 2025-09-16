# 📂 Serasa - Data Processor Zendesk

Uma aplicação em **Python + PyQt5** para processamento automatizado de arquivos **ZIP contendo CSVs**, com tratamento de CPFs, consulta em API e exportação para Excel.

---

## 🚀 Funcionalidades

- Interface gráfica moderna e responsiva feita com **PyQt5**.
- Seleção de arquivos **ZIP** que contenham planilhas em CSV.
- Extração e tratamento de colunas específicas.
- **Normalização de CPFs** (remoção de caracteres não numéricos, preenchimento com zeros, validação de formato).
- Consulta em **API externa** (batch ou fallback por CPF).
- Geração de identificadores **SHA-256** para os usuários encontrados.
- Processamento em **background (thread separada)** com barra de progresso e opção de cancelamento.
- Exportação do resultado final para **Excel (.xlsx)**.
- Log detalhado do processamento exibido na interface.

---

## 🛠️ Tecnologias Utilizadas

- [Python 3.9+](https://www.python.org/)
- [PyQt5](https://pypi.org/project/PyQt5/)
- [Pandas](https://pandas.pydata.org/)
- [Requests](https://pypi.org/project/requests/)
- [Hashlib](https://docs.python.org/3/library/hashlib.html)
- [Zipfile](https://docs.python.org/3/library/zipfile.html)

---

## 📦 Instalação

1. Clone este repositório ou baixe os arquivos.
2. Crie e ative um ambiente virtual (opcional, mas recomendado):
   ```bash
   python -m venv venv
   source venv/bin/activate  # Linux/Mac
   venv\Scripts\activate     # Windows

3. Instale as dependências:
   pip install -r requirements.txt
   pip install pandas requests pyqt5

---

## ▶️ Como Usar

1. Execute a aplicação:
   python serasa_app.py

2. Na interface:

- Selecionar ZIP → escolha um arquivo .zip com um CSV interno.
- Processar Dados → inicia o processamento em background (com barra de progresso).
- Cancelar → interrompe o processamento.
- Exportar para Excel → salva os resultados processados em um arquivo .xlsx.

--- 

## 📊 Estrutura dos Dados

Durante o processamento, as seguintes transformações ocorrem:
- Preenchimento de colunas de CPF a partir de múltiplas origens (CPF, CPF.1, [RA] CPF).
- Seleção e renomeação das colunas principais:
     - CPF
     - ID
     - Data da Solicitacao
     - Formulario Ticket
       
- Validação e normalização de CPFs.
- Consulta na API (batch ou fallback individual).
- Criação das colunas finais:
     - cpf
     - userID
     - account_id (hash SHA-256 do userID)
     - status (CADASTRADO / SEM CADASTRO)
     - ID
     - Data da Solicitacao
     - Data da Resolucao
     - Formulario Ticket

 ---
 
## 📂 Estrutura do Projeto
```
├── serasa_app.py # Código principal da aplicação
├── icon/ # Pasta com ícones utilizados na interface
│ ├── logo.png
│ ├── zip.png
│ ├── open.png
│ ├── process.png
│ ├── export.png
│ └── cancel.png
└── README.md # Este arquivo
```

---

## ⚠️ Observações

O caminho dos ícones está configurado para C:/Users/c12511q/Documents/Serasa/icon/.
Ajuste os caminhos no código caso use em outro ambiente.

Certifique-se de ter conexão com a internet para que a consulta à API funcione corretamente.

O tempo de processamento pode variar dependendo do tamanho do arquivo e da resposta da API.

--- 

## 📜 Licença

Este projeto foi desenvolvido para uso interno e estudo.
Sinta-se livre para adaptá-lo conforme necessário.

---

## 👨‍💻 Desenvolvido com Python, Pandas e PyQt5
