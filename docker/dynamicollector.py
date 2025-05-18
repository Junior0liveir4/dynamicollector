import os
import csv
import time
import json
from kubernetes import client, config
from typing import List, Dict, Optional, TypedDict
import requests

# Define os tipos esperados para o endpoint e spans
class LocalEndpoint(TypedDict):
    serviceName: str
    port: Optional[int]

class Span(TypedDict):
    traceId: str
    id: str
    name: str
    timestamp: int
    duration: int
    parentId: Optional[str]
    localEndpoint: LocalEndpoint
    tags: Optional[Dict[str, str]]

Trace = List[Span]
ZipkinResponse = List[Trace]

# Define o formato de requisição esperado pelo Zipkin
class ZipkinRequest(TypedDict):
    endTs: int
    lookback: int
    limit: int
    serviceName: Optional[str]
    spanName: Optional[str]

# Cliente para interação com o Zipkin
class ZipkinClient:
    def __init__(self, zipkin: str, lookback: int, drift: int, limit: int) -> None:
        self._zipkin = zipkin
        self._lookback = lookback
        self._drift = drift
        self._limit = limit

    def fetch(self, service: str, span: str = None) -> ZipkinResponse:
        try:
            response = requests.get(
                url=f'{self._zipkin}/api/v2/traces',
                params=self.payload(service=service, span=span),
                timeout=7,
            )
            response.raise_for_status()
            traces: ZipkinResponse = response.json()
            return traces
        except requests.RequestException as e:
            print(f"Erro ao buscar spans para o serviço {service}: {e}")
            return []

    @property
    def timestamp(self) -> int:
        return round(time.time() * 1000)

    def payload(self, service: str, span: str = None) -> ZipkinRequest:
        payload = ZipkinRequest(
            endTs=self.timestamp - self._drift,
            lookback=self._lookback,
            limit=self._limit,
            serviceName=service,
        )
        if span:
            payload['spanName'] = span
        return payload

# Função para buscar o pod baseado no nome parcial
def find_pod_by_partial_name(namespace, partial_name_pod):
    try:
        config.load_incluster_config()
        api_instance = client.CoreV1Api()
        pod_list = api_instance.list_namespaced_pod(namespace)
        for pod in pod_list.items:
            if partial_name_pod in pod.metadata.name:
                print(f"Pod encontrado: {pod.metadata.name}")
                return pod.metadata.name
        print(f"Pod '{partial_name_pod}' não encontrado.")
        return None
    except Exception as e:
        print(f"Erro ao obter o pod: {e}")
        return None

# Função para obter os parâmetros de recursos do pod
def get_limits_pod(namespace, name_pod):
    try:
        config.load_incluster_config()
        api_instance = client.CoreV1Api()
        pod_info = api_instance.read_namespaced_pod(name_pod, namespace)
        for container in pod_info.spec.containers:
            if container.resources.limits:
                cpu = container.resources.limits.get('cpu')
                memory = container.resources.limits.get('memory')
                return cpu, memory
    except Exception as e:
        print(f"Erro ao obter informações do Pod: {e}")
        return None, None

# Função para obter o número de réplicas do deployment
def get_replicas_deployment(namespace, name_deployment):
    try:
        config.load_incluster_config()
        api_instance = client.AppsV1Api()
        deployment_info = api_instance.read_namespaced_deployment(name_deployment, namespace)
        replicas = deployment_info.spec.replicas
        return replicas, deployment_info.metadata.name
    except Exception as e:
        print(f"Erro ao obter informações do Deployment: {e}")
        return None, None

# Função para salvar dados em um arquivo CSV
def save_data_csv(final_list, cpu, memory, replicas, deploy):
    name_file = f"{deploy}.csv"

    # Salvar todos os itens de final_list no arquivo CSV
    with open(name_file, mode='a', newline='') as file:
        writer = csv.writer(file)
        # Salvar a linha com as métricas, CPU, memória e réplicas na mesma linha
        final_list.extend([cpu, memory, replicas])
        writer.writerow(final_list)
    print(f"Dados atualizados e salvos em {name_file}")

# Função principal para monitorar os serviços no Zipkin e armazenar as tags
def monitoring_zipkin(namespace, partial_name_pod, services, name_deployment):
    zipkin_url = os.getenv("ZIPKIN_URL", "http://10.10.0.68:30200")
    client = ZipkinClient(zipkin=zipkin_url, lookback=3600000, drift=120000, limit=1000)

    print("Obtendo informações do Pod...")
    pod_name = find_pod_by_partial_name(namespace, partial_name_pod)
    if not pod_name:
        print("Pod não encontrado. Finalizando.")
        return

    # Inicializa os dicionários para armazenar as tags e o timestamp da primeira "FPS"
    all_tags = {service: [] for service in services}
    first_fps_timestamp = {service: None for service in services}  # Armazenar o tempo da primeira tag "FPS"

    while True:
        for service in services:
            traces = client.fetch(service=service)
            for trace in traces:
                for span in trace:
                    if 'tags' in span:
                        tags = span['tags']
                        if 'FPS' in tags and first_fps_timestamp[service] is None:
                            first_fps_timestamp[service] = time.time() * 1000  # Registra o timestamp da primeira "FPS"
                            print(f"Iniciando a coleta de métricas para o serviço: {service}")

                        if first_fps_timestamp[service] is not None:
                            elapsed_time = time.time() * 1000 - first_fps_timestamp[service]
                            if elapsed_time <= 2000:  # Armazena as tags durante 2 segundos
                                all_tags[service].append(tags)
                            else:
                                print(f"Tempo limite de 2 segundos excedido para o serviço {service}.")

        # Processa e limita a quantidade de métricas coletadas
        all_tags_list = []
        for values in all_tags.values():
            for entry in values:
                for value in entry.values():
                    try:
                        number = float(value)
                        formatted_number = round(number, 14)
                        if formatted_number.is_integer():
                            all_tags_list.append(int(formatted_number))
                        else:
                            all_tags_list.append(formatted_number)
                    except ValueError:
                        pass

        final_list = []
        float_sum = 0
        float_count = 0

        for item in all_tags_list:
            if isinstance(item, int):
                if float_count > 0:
                    float_average = round(float_sum / float_count, 14)
                    final_list.append(float_average)
                    float_sum = 0
                    float_count = 0
                final_list.append(item)
            elif isinstance(item, float):
                float_sum += item
                float_count += 1

        if float_count > 0:
            float_average = round(float_sum / float_count, 14)
            final_list.append(float_average)

        # Limita a quantidade de itens na final_list a 1000
        final_list = final_list[:1000]

        # Obtém os valores atuais de CPU, memória e réplicas
        name_pod = find_pod_by_partial_name(namespace, partial_name_pod)
        if not name_pod:
            print("Pod não encontrado. Encerrando monitoramento.")
            break

        cpu_actual, memory_actual = get_limits_pod(namespace, name_pod)
        replicas_actual, deploy = get_replicas_deployment(namespace, name_deployment)
        print(f"Parâmetros:\nCPU: {cpu_actual}\nMemória: {memory_actual}\nRéplicas: {replicas_actual}")

        # Salva os dados inicialmente
        if cpu_actual and memory_actual and replicas_actual and deploy:
            save_data_csv(final_list, cpu_actual, memory_actual, replicas_actual, deploy)

            # Verifica mudanças a cada 1 minuto
            while True:
                time.sleep(60)  # Aguarda 1 minuto
                print("Verificando se houve alterações nos recursos...")

                name_pod = find_pod_by_partial_name(namespace, partial_name_pod)
                if not name_pod:
                    print("Pod não encontrado. Encerrando monitoramento.")
                    break
                    
                # Obtém os novos valores de CPU, memória e réplicas
                cpu_new, memory_new = get_limits_pod(namespace, name_pod)
                replicas_new, _ = get_replicas_deployment(namespace, name_deployment)

                if cpu_new != cpu_actual or memory_new != memory_actual or replicas_new != replicas_actual:
                    print("Alterações detectadas.")
                    print(f"Parâmetros:\nCPU: {cpu_new}\nMemória: {memory_new}\nRéplicas: {replicas_new}")
                    time.sleep(15*60)  # Aguarda 15 minutos

                    # Atualiza a lista de métricas com novos dados após a alteração
                    all_tags = {service: [] for service in services}
                    first_fps_timestamp = {service: None for service in services}

                    # Recolhe novas métricas do Zipkin após a mudança nos recursos
                    for service in services:
                        traces = client.fetch(service=service)
                        for trace in traces:
                            for span in trace:
                                if 'tags' in span:
                                    tags = span['tags']
                                    if 'FPS' in tags and first_fps_timestamp[service] is None:
                                        first_fps_timestamp[service] = time.time() * 1000
                                        print(f"Iniciando coleta de novas métricas para o serviço: {service}")

                                    if first_fps_timestamp[service] is not None:
                                        elapsed_time = time.time() * 1000 - first_fps_timestamp[service]
                                        if elapsed_time <= 2000:
                                            all_tags[service].append(tags)

                    # Processa e atualiza a final_list com os novos valores de métricas
                    all_tags_list = []
                    for values in all_tags.values():
                        for entry in values:
                            for value in entry.values():
                                try:
                                    number = float(value)
                                    formatted_number = round(number, 14)
                                    if formatted_number.is_integer():
                                        all_tags_list.append(int(formatted_number))
                                    else:
                                        all_tags_list.append(formatted_number)
                                except ValueError:
                                    pass

                    final_list = []
                    float_sum = 0
                    float_count = 0

                    for item in all_tags_list:
                        if isinstance(item, int):
                            if float_count > 0:
                                float_average = round(float_sum / float_count, 14)
                                final_list.append(float_average)
                                float_sum = 0
                                float_count = 0
                            final_list.append(item)
                        elif isinstance(item, float):
                            float_sum += item
                            float_count += 1

                    if float_count > 0:
                        float_average = round(float_sum / float_count, 14)
                        final_list.append(float_average)

                    final_list = final_list[:1000]  # Limita novamente a lista a 1000 itens

                    # Salva os novos valores de CPU, memória, réplicas e métricas no CSV
                    save_data_csv(final_list, cpu_new, memory_new, replicas_new, deploy)

                    cpu_actual, memory_actual, replicas_actual = cpu_new, memory_new, replicas_new
                else:
                    print("Nenhuma alteração detectada.")


if __name__ == "__main__":
    namespace = os.getenv("NAMESPACE")
    partial_name_pod = os.getenv("POD_NAME")
    services = os.getenv("SERVICES").split(',')
    name_deployment = os.getenv("DEPLOYMENT_NAME")

    if namespace and partial_name_pod and services and name_deployment:
        monitoring_zipkin(namespace, partial_name_pod, services, name_deployment)
    else:
        print("Erro: Variáveis de ambiente NAMESPACE, POD_NAME, SERVICES ou DEPLOYMENT_NAME não estão definidas.")