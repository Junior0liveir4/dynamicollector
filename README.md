# 📊 DynamiCollector

**DynamiCollector** é um microserviço desenvolvido para **monitorar aplicações no Kubernetes**, com foco em coletar e organizar métricas exportadas por essas aplicações via **Zipkin**. Ele detecta alterações nos recursos (CPU, memória e réplicas) e registra as métricas associadas em um arquivo `.csv`, criando **séries temporais** que permitem análises posteriores de desempenho.

---

## 🎯 Objetivo

Este serviço foi criado para:

- Monitorar aplicações que exportam métricas via **Zipkin**, como a `RGB2Gray`.
- Detectar **mudanças nos recursos alocados** (CPU, memória, réplicas).
- Coletar as **tags dos spans** Zipkin durante essas alterações.
- Armazenar as informações coletadas em um arquivo `.csv`, agregando dados por janela de tempo.

---

## ⚙️ Arquitetura

- **Linguagem:** Python
- **Execução:** 1 pod Kubernetes (pode ser replicado)
- **Entrada:** API Zipkin (`/api/v2/traces`)
- **Saída:** Arquivo `.csv` com dados coletados
- **Dependências:** Kubernetes API + requests

---

## 📁 Estrutura dos Arquivos

| Arquivo                | Descrição |
|------------------------|----------|
| `dynamicollector.py`   | Código principal do coletor |
| `Dockerfile`           | Imagem da aplicação |
| `dynamicollector.yaml` | Manifesto Kubernetes com Role, RoleBinding e PersistentVolume |

---

## 📦 Dependências

A aplicação requer os seguintes pacotes:

```
kubernetes==26.1.0
requests
typing_extensions
```

---

## 🧠 Explicação dos Componentes

### Coleta de Métricas
- A aplicação utiliza a API REST do **Zipkin** para buscar spans exportados por serviços como `RGB2Gray`.
- As tags como `FPS` e `Tempo de Processamento` são agregadas ao longo de 2 segundos após a primeira detecção.
- Os dados são armazenados em um arquivo `.csv` com os seguintes campos:
  - Métricas extraídas dos spans
  - CPU, Memória e Réplicas atuais do pod monitorado

### Detecção de Mudanças
- O coletor monitora periodicamente o pod e o deployment usando a **Kubernetes API**.
- Caso detecte alteração em CPU, memória ou número de réplicas:
  - Aguarda 15 minutos para estabilização
  - Recoleta as métricas
  - Armazena nova entrada no `.csv`

---

## 📂 Requisitos no Kubernetes

### Role e RoleBinding

O DynamiCollector **precisa acessar a API do Kubernetes** para consultar pods e deployments. Isso é feito via:

- **Role**: Permissão para listar/ler pods e deployments no namespace.
- **RoleBinding**: Liga essa permissão ao `ServiceAccount` usado pelo pod.

### PersistentVolume

É necessário definir:

- **PersistentVolume** e **PersistentVolumeClaim** para permitir que o pod salve o arquivo `.csv` com persistência de dados, mesmo em caso de reinício do pod.

---

## 🛠️ Variáveis de Ambiente

Essas variáveis devem ser definidas no `yaml`:

```yaml
env:
  - name: NAMESPACE
    value: "<namespace onde a aplicação está rodando>"
  - name: POD_NAME
    value: "<parte do nome do pod alvo>"
  - name: DEPLOYMENT_NAME
    value: "<parte do nome do deployment>"
  - name: SERVICES
    value: "<nome dos services zipkin que a aplicação exporta>"
  - name: ZIPKIN_URL
    value: "http://zipkin:30200"
```

**Nota:** Não é necessário o nome completo do pod ou deployment — apenas uma parte que o identifique unicamente.

---

## ☁️ Execução no Kubernetes

### Passos:

1. **Ajuste o `dynamicollector.yaml`** com:
   - Nome do `namespace`
   - Nome parcial do pod e deployment
   - Nome dos serviços a serem monitorados (ex: `RGB2Gray`)
   - Endereço do Zipkin

2. **Aplique os recursos:**

```bash
kubectl apply -f dynamicollector.yaml
```

3. **Verifique o volume persistente e os arquivos `.csv` gerados.**

---

## 📌 Exemplo de Aplicação Monitorada

A aplicação `RGB2Gray` exporta tags como `FPS` e `Tempo de Processamento` para o Zipkin. O DynamiCollector:

- Detecta alterações nos recursos desse pod.
- Coleta métricas durante as transições.
- Armazena as informações para análise futura de desempenho.

---

## 🔄 Escalabilidade

A aplicação pode ser **replicada** para monitorar outras aplicações. Basta:

- Duplicar o deployment
- Ajustar as variáveis de ambiente para refletir o novo serviço alvo

---

## 📬 Contato

Para dúvidas ou sugestões, entre em contato com o time do **LabSEA**.
