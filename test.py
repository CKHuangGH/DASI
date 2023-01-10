from kubernetes import client, config
import requests
import yaml
import kubernetes.client
import base64
import time
timeout_seconds=30

def getControllerMasterIP():
    config.load_kube_config()
    api_instance = kubernetes.client.CoreV1Api()
    master_ip = ""
    try:
        nodes = api_instance.list_node(pretty=True, _request_timeout=timeout_seconds)
        nodes = [node for node in nodes.items if
                 'node-role.kubernetes.io/master' in node.metadata.labels]
        # get all addresses of the master
        addresses = nodes[0].status.addresses

        master_ip = [i.address for i in addresses if i.type == "InternalIP"][0]
    except:
        print("Connection timeout after " + str(timeout_seconds) + " seconds to host cluster")

    return master_ip

def getconfigstatus():
    prom_host = getControllerMasterIP()
    prom_port = 30090
    url= "http://" + str(prom_host) + ":" + str(prom_port) + "/api/v1/status/config"
    response = requests.get(url)
    firstlayer = yaml.full_load(response.text)
    secondlayer = yaml.full_load(firstlayer['data']['yaml'])
    for item in secondlayer['scrape_configs']:
        if item['job_name']=='cluster1':
            return item['scrape_interval']
    
def getsecret():
    config.load_kube_config()
    api_instance = kubernetes.client.CoreV1Api()
    namespace="monitoring"
    name=getsecretname()

    resp=api_instance.read_namespaced_secret(name=name, namespace=namespace)
    return resp

def getsecretname():
    config.load_kube_config()
    api_instance = kubernetes.client.CoreV1Api()
    namespace="monitoring"
    label_selector="app=kube-prometheus-stack-prometheus-scrape-confg"

    try:
        resp=api_instance.list_namespaced_secret(namespace=namespace, label_selector=label_selector,timeout_seconds=timeout_seconds)
    except:
        print("Connection timeout after " + str(timeout_seconds) + " seconds to host cluster")
    
    return resp.items[0].metadata.name

def updateSecret(code):
    config.load_kube_config()
    api_instance = kubernetes.client.CoreV1Api()
    secret = getsecret()
    namespace="monitoring"
    name = getsecretname()
    secret.data['additional-scrape-configs.yaml'] = code
    api_instance.patch_namespaced_secret(name=name, namespace=namespace, body=secret)

def modifyconfig(scrtime):
    config.load_kube_config()
    api_instance = kubernetes.client.CoreV1Api()
    #min_key = min(scrapetime, key = scrapetime.get)
    value="'" + str(int(scrtime+5))+"s'"
    print(value)
    secret = getsecret()
    config_base64=secret.data['additional-scrape-configs.yaml']
    config_decode=base64.b64decode(config_base64)
    yaml_config=yaml.full_load(config_decode.decode())
    for item in yaml_config:
        item['scrape_interval']=value
    config_encode=base64.b64encode(str(yaml_config).encode("utf-8"))
    encodedStr=config_encode.decode("UTF-8")
    code=encodedStr
    updateSecret(code)

def changereloadtime(scrtime):
    config.load_kube_config()
    api_instance = kubernetes.client.CoreV1Api()
    #min_key = min(scrapetime, key = scrapetime.get)
    value="" + str(int(scrtime+5))+"s"
    print(value)
    secret = getsecret()
    config_base64=secret.data['additional-scrape-configs.yaml']
    config_decode=base64.b64decode(config_base64)
    yaml_config=yaml.full_load(config_decode.decode())
    for item in yaml_config:
        print(item)
        item['scrape_interval']=value
    config_encode=base64.b64encode(str(yaml_config).encode("utf-8"))
    encodedStr=config_encode.decode("UTF-8")
    code=encodedStr
    updateSecret(code)

def checkconfigreloadtime():
    prom_host = getControllerMasterIP()
    prom_port = 30090
    url= "http://" + str(prom_host) + ":" + str(prom_port) + "/api/v1/status/config"
    response = requests.get(url)
    firstlayer = yaml.full_load(response.text)
    secondlayer = yaml.full_load(firstlayer['data']['yaml'])
    for item in secondlayer['scrape_configs']:
        if item['job_name']=='cluster1':
            return item['scrape_interval']

def inittime():
    scrtime=getconfigstatus()
    scrtime=scrtime.strip("s") 
    changereloadtime(int(scrtime))
    print(checkconfigreloadtime())
    savefirst=time.perf_counter()

    print(str(int(scrtime)+5) + 's')
    while 1:
        if checkconfigreloadtime() == str(int(scrtime)+5) + 's':
            saveend=time.perf_counter()
            print(checkconfigreloadtime())
            break
        else:
            time.sleep(0.2)
            print(checkconfigreloadtime())

    print(saveend+180)
    print(scrtime)

inittime()