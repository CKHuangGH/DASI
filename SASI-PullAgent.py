import time
from requests import post
from kubernetes import config
import kubernetes.client
import logging
import asyncio
import requests
import urllib.parse
from aiohttp import ClientSession

ipdict={}
portdict={}
timedict={}
clusterdict={}
metricsnamedict={}
errorlist=["go_gc_duration_seconds_sum","go_gc_duration_seconds_count"]
timeout_seconds = 30

logging.basicConfig(level=logging.INFO)

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

def timewriter(text):
    try:
        f = open("exectime_management", 'a')
        f.write(text+"\n")
        f.close()
    except:
        print("Write error")

def posttogateway(clustername,instance,name):
    start = time.perf_counter()
    gateway_host="127.0.0.1"
    gateway_port="9091"

    url = "http://" + str(gateway_host) + ":" + str(gateway_port) + "/metrics/job/" + clustername
    res = post(url=url,data=name,headers={'Content-Type': 'application/octet-stream'})
    # with open("data","rb") as fp:
    #     res = post(url=url,data=fp,headers={'Content-Type': 'application/octet-stream'})
    print(res)
    end = time.perf_counter()
    timewriter("posttogateway" + " " + str(end-start))

def parse_ip_port_name(data):
    origdata = data.strip('\n')
    parseddata = origdata.split(":")
    return str(parseddata[0]), int(parseddata[1]), str(parseddata[2])

def read_member_cluster():
    f = open("/root/member", 'r')
    for line in f.readlines():
        ip, port, cluster=parse_ip_port_name(line)
        ipdict[cluster]=ip
        portdict[cluster]=port
        clusterdict[cluster]=cluster
        timedict[cluster]=0
    f.close()

# def parsemetrics(textline):
#     origdata = textline.strip('\n')
#     labels=""
#     if "{" in origdata:
#         firstparse = origdata.split("{")
#         secondparse=firstparse[1].split("}")
#         thridparse=secondparse[0].split(",")
#         #print(secondparse)
#         value=secondparse[1].split(" ")
#         for item in thridparse:
#             # if item!="job=\"node-exporter\"" or item!="container=\"node-exporter\"" or item!="endpoint=\"http-metrics\"" or item!="namespace=\"monitoring\"" or item!="endpoint=\"http-metrics\"":
#             #     labels+=item+","
#             findinstance=item.split("=")
#             #print(findinstance[0])
#             if findinstance[0] == "instance":
#                 labels+="server="+findinstance[1]+","
#             elif item!="job=\"node-exporter\"":
#                 labels+=item+","
#     metric=firstparse[0]+"{"+str(labels[:-1])+"} "+value[1]+"\n"
#     return str(metric)

def parsemetrics(textline):
    origdata = textline.strip('\n')
    labels=""
    if "}" in origdata:
        firstparse = origdata.split("}")
        secondparse= firstparse[1].split(" ")
    metric=firstparse[0]+"} "+secondparse[1]+"\n"
    return str(metric)

def parsenameandtype(data):
    origdata = data.strip('\n')
    parseddata = origdata.split(" ")
    if parseddata[0]=="#":
        return str(parseddata[2])
    else:
        return str(parseddata[0]),str(parseddata[1])

def getname(textline):
    origdata = textline.strip('\n')
    if "{" in origdata:
        firstparse = origdata.split("{")
    return str(firstparse[0])


def removetime(text):
    final_metrics=""
    for line in text.splitlines(True):
        if line[0] == "#":
            #final_metrics+=line
            name=parsenameandtype(line)
            #print(name)
            if name in metricsnamedict:
                newtype="# TYPE "+str(name)+" "+str(metricsnamedict[name]+"\n")
                final_metrics+=newtype
            elif name not in errorlist:
                final_metrics+=line
            
        else:
            nameforcheck=getname(line)
            if nameforcheck not in errorlist:
                final_metrics+=parsemetrics(line)

    return final_metrics

async def fetch(link, session, requestclustername):
    # try:
    prom_header = {'Accept-Encoding': 'gzip'}
    async with session.get(url=link,headers=prom_header) as response:
        html_body = await response.text()
        final_metrics=removetime(html_body)
        strtobyte=bytes(final_metrics,'utf-8')
        posttogateway(requestclustername,ipdict[requestclustername],strtobyte)
        #removetime(html_body)
    # except:
    #     print("Get metrics failed")

async def asyncgetmetrics(links,requestclustername):
    async with ClientSession() as session:
        tasks = [asyncio.create_task(fetch(link, session, requestclustername[links.index(link)])) for link in links]  # 建立任務清單
        await asyncio.gather(*tasks)

def gettargets(cluster):
    start = time.perf_counter()
    prom_host=ipdict[cluster]
    prom_port = 30090
    prom_url = "http://" + str(prom_host) + ":" + \
                            str(prom_port) + "/api/v1/targets"
    prom_header = {'Accept-Encoding': 'gzip'}
    r = requests.get(url=prom_url,headers=prom_header)
    data = r.json()
    nomaster=str(prom_host) +":9100"
    scrapeurl = []
    for item in data["data"]["activeTargets"]:
        if item["labels"]["job"] == "node-exporter":
            if item["labels"]["instance"] != nomaster:
                scrapeurl.append(item["scrapeUrl"])
    end = time.perf_counter()
    timewriter("gettargets" + " " + str(end-start))
    return scrapeurl

def parsetargetip(data):
    origdata = data.strip('\n')
    parseddata = origdata.split("/")
    return str(parseddata[2])

def getrequesturl(cluster,scrapeurl):
    scrapeip=[]
    for url in scrapeurl:
        scrapeip.append(parsetargetip(url))
    prom_host=ipdict[cluster]
    prom_port=30090
    fullurl="http://"+str(prom_host)+":"+str(prom_port)+"/federate?"
    for ipwithport in scrapeip:
        fullurl=fullurl+"match[]={instance=~\""+ipwithport+"\"}&"
    final_url=fullurl[:-1]
    return final_url

def read_type():
    f = open("/root/type", 'r')
    for line in f.readlines():
        name,type=parsenameandtype(line)
        metricsnamedict[name]=type
    f.close()

if __name__ == "__main__":
    read_member_cluster()
    read_type()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    #while 1:
    requestclustername=[]
    requesturl=[]
    for cluster in ipdict:
        if timedict[cluster]==0:
            scrapeurl=gettargets(cluster)
            requesturl.append(getrequesturl(cluster,scrapeurl))
            requestclustername.append(cluster)
    loop.run_until_complete(asyncgetmetrics(requesturl,requestclustername))






# if __name__ == "__main__":
#     perparestart = time.perf_counter()
#     read_member_cluster()
#     clientMessage = "acala:1"
#     BUFFER_SIZE=16324
#     loop = asyncio.new_event_loop()
#     asyncio.set_event_loop(loop)
#     perpareend = time.perf_counter()
#     timewriter("perpare" + " " + str(perpareend-perparestart))
#     while True:
#         totaltimestart = time.perf_counter()
#         clientMessage=loop.run_until_complete(tcp_echo_client(scrapelist,clientMessage))
#         totaltimeend = time.perf_counter()
#         timewriter("onescrapetotaltime" + " " + str(totaltimeend-totaltimestart))
#         time.sleep(5)