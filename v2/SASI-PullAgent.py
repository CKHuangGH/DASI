import time
from requests import post
from kubernetes import config
import kubernetes.client
import asyncio
import requests
from aiohttp import ClientSession
from prometheus_api_client import PrometheusConnect
import math
import statistics

ipdict={}
portdict={}
timedict={}
metricstypedict={}
cpustatus={}
ramstatus={}
record5s=[]
errorlist=["go_gc_duration_seconds_sum","go_gc_duration_seconds_count"]

timeout_seconds = 30

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
        f = open("exectime", 'a')
        f.write(text+"\n")
        f.close()
    except:
        print("Write error")

def logwriter(text):
    try:
        f = open("scrapetime", 'a')
        f.write(text+"\n")
        f.close()
    except:
        print("Write error")

def posttogateway(clustername,data):
    # start = time.perf_counter()
    gateway_host="127.0.0.1"
    gateway_port="9091"

    url = "http://" + str(gateway_host) + ":" + str(gateway_port) + "/metrics/job/" + clustername
    post(url=url,data=data,headers={'Content-Type': 'application/octet-stream'})
    # end = time.perf_counter()
    # timewriter("posttogateway" + " " + str(end-start))

def parse_ip_port_name(member):
    origdata = member.strip('\n')
    parseddata = origdata.split(":")
    return str(parseddata[0]), int(parseddata[1]), str(parseddata[2]),str(parseddata[3])

def read_member_cluster():
    f = open("/root/member", 'r')
    for member in f.readlines():
        ip, port, cluster, maxlevel=parse_ip_port_name(member)
        ipdict[cluster]=ip
        portdict[cluster]=port
        timedict[cluster]=1
    f.close()
    return int(maxlevel)
    

def parsemetrics(text):
    origdata = text.strip('\n')
    if "}" in origdata:
        firstparse = origdata.split("}")
        secondparse= firstparse[1].split(" ")
    metric=firstparse[0]+"} "+secondparse[1]+"\n"
    return str(metric)

def parsenameandtype(text):
    origdata = text.strip('\n')
    parseddata = origdata.split(" ")
    if parseddata[0]=="#":
        return str(parseddata[2])
    else:
        return str(parseddata[0]),str(parseddata[1])

def getname(text):
    origdata = text.strip('\n')
    if "{" in origdata:
        firstparse = origdata.split("{")
    return str(firstparse[0])

def findthevalue(text):
    origdata = text.strip('\n')
    if "}" in origdata:
        firstparse = origdata.split("}")
        secondparse= firstparse[1].split(" ")
    return float(secondparse[1])

def removetime(text,cluster):
    final_metrics=""
    cpulist=[]
    ramlist=[]
    ramalllist=[]
    avgcpu=0
    for line in text.splitlines(True):
        if line[0] == "#":
            name=parsenameandtype(line)
            if name in metricstypedict:
                newtype="# TYPE "+str(name)+" "+str(metricstypedict[name]+"\n")
                final_metrics+=newtype
            elif name not in errorlist:
                final_metrics+=line
        else:
            nameforcheck=getname(line)
            if nameforcheck == "record5s":
                cpulist.append(findthevalue(line))
            if nameforcheck == "node_memory_MemFree_bytes":
                ramlist.append(findthevalue(line))
            if nameforcheck == "node_memory_MemTotal_bytes":
                ramalllist.append(findthevalue(line))
            if nameforcheck not in errorlist:
                final_metrics+=parsemetrics(line)
    avgcpu=statistics.mean(cpulist)
    ram=statistics.mean(ramlist)
    ramall=statistics.mean(ramalllist)
    cpustatus[cluster]=100-avgcpu
    ramstatus[cluster]=(ramall-ram)/ramall
    #print(avgcpu,ram)
    return final_metrics

async def fetch(link, session, requestclustername):
    try:
        prom_header = {'Accept-Encoding': 'gzip'}
        async with session.get(url=link,headers=prom_header) as response:
            html_body = await response.text()
            final_metrics=removetime(html_body,requestclustername)
            strtobyte=bytes(final_metrics,'utf-8')
            posttogateway(requestclustername,strtobyte)
    except:
        print("Get metrics failed"+str(requestclustername))

async def asyncgetmetrics(links,requestclustername):
    async with ClientSession() as session:
        tasks = [asyncio.create_task(fetch(link, session, requestclustername[links.index(link)])) for link in links]
        await asyncio.gather(*tasks)

def gettargets(cluster):
    # start = time.perf_counter()
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
    # end = time.perf_counter()
    # timewriter("gettargets" + " " + str(end-start))
    
    return scrapeurl

def parsetargetip(text):
    origdata = text.strip('\n')
    parseddata = origdata.split("/")
    return str(parseddata[2])

def getrequesturl(cluster,scrapeurl):
    # start = time.perf_counter()
    
    scrapeip=[]
    for url in scrapeurl:
        scrapeip.append(parsetargetip(url))
    prom_host=ipdict[cluster]
    prom_port=30090
    fullurl="http://"+str(prom_host)+":"+str(prom_port)+"/federate?"
    for ipwithport in scrapeip:
        fullurl=fullurl+"match[]={instance=~\""+ipwithport+"\"}&"
    final_url=fullurl[:-1]

    # end = time.perf_counter()
    # timewriter("getrequesturl" + " " + str(end-start))
    return final_url

def read_type():
    f = open("/root/type", 'r')
    for line in f.readlines():
        name,type=parsenameandtype(line)
        metricstypedict[name]=type
    f.close()

def getformule(minlevel, timemax, maxlevel, timemin):
    global m
    m=(int(timemin)-int(timemax))/(int(maxlevel)-int(minlevel))
    global b
    b=(float(timemax)-(m*float(minlevel)))

def getresources(cluster):
    # start = time.perf_counter()
    prom_host = getControllerMasterIP()
    prom_port = 30090
    prom_url = "http://" + str(prom_host) + ":" + str(prom_port)
    pc = PrometheusConnect(url=prom_url, disable_ssl=True)
    querycpu="100-avg (record5s{job=\"" + cluster + "\"})"
    # querycpu="(1-sum(increase(node_cpu_seconds_total{job=\"" + cluster + "\",mode=\"idle\"}[2m]))/sum(increase(node_cpu_seconds_total{job=\"" + cluster + "\"}[2m])))*100"
    queryram="sum (node_memory_MemFree_bytes{job=\"" + cluster + "\"})"
    queryramall="sum (node_memory_MemTotal_bytes{job=\"" + cluster + "\"})"
    
    resultcpu = pc.custom_query(query=querycpu)
    if len(resultcpu) > 0:
        cpu = float(resultcpu[0]['value'][1])
    else:
        cpu=-1
    
    resultram = pc.custom_query(query=queryram)
    if len(resultram) > 0:
        ram = float(resultram[0]['value'][1])
    else:
        ram=-1

    resultramall = pc.custom_query(query=queryramall)
    if len(resultramall) > 0:
        ramall = float(resultramall[0]['value'][1])
    else:
        ramall=-1

    if cpu==-1 or cpu==0 or math.isnan(cpu):
        cpu=cpustatus[cluster]
    if ramall==-1 or ram==-1:
        ramperc=ramstatus[cluster]

    ramperc=(ramall-ram)/ramall
    cpustatus[cluster]=cpu
    ramstatus[cluster]=ramperc

    logwriter(str(cluster)+":"+str(cpustatus[cluster])+":"+str(ramstatus[cluster])+":"+str(time.time()))

    # print(cluster)
    # print("cpu-status: " + str(cpu)+"%")
    # print("ram-status: " + str(ramperc)+"%")
    # end = time.perf_counter()
    # timewriter("getresources" + " " + str(end-start))
    return max(cpu,ramperc)
    
def decidetime(nowstatus, minlevel, timemax, maxlevel, timemin):
    #start = time.perf_counter()
    if nowstatus >= minlevel and nowstatus < maxlevel: 
        answer=(m*nowstatus)+b
    elif nowstatus >= maxlevel:
        answer=timemin
    else:
        answer=timemax

    #end = time.perf_counter()
    # timewriter("decidetime" + " " + str(end-start))
    return answer

if __name__ == "__main__":
    maxlevel=read_member_cluster()
    read_type()
    minlevel, timemax, timemin=0,60,5
    getformule(minlevel, timemax, maxlevel, timemin)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    scrapeurldict={}
    requesturldict={}
    for cluster in ipdict:
        scrapeurldict.setdefault(cluster,gettargets(cluster))
        requesturldict.setdefault(cluster,getrequesturl(cluster,scrapeurldict[cluster]))
    
    init=1
    while 1:
        totalstart = time.perf_counter()
        requestclustername=[]
        requesturl=[]
        for cluster in ipdict:
            timedict[cluster]-=1
            if timedict[cluster]<=0:
                requesturl.append(requesturldict[cluster])
                requestclustername.append(cluster)
        if len(requesturl)>0:
            loop.run_until_complete(asyncgetmetrics(requesturl,requestclustername))
            for cluster in requestclustername:
                if init!=1:
                    nowstatus=max(cpustatus[cluster],ramstatus[cluster])
                    timedict[cluster]=decidetime(nowstatus, minlevel, timemax, maxlevel, timemin)
                    logwriter(str(cluster)+":"+str(timedict[cluster])+":"+str(cpustatus[cluster])+":"+str(ramstatus[cluster])+":"+str(time.time()))
                else:
                    cpustatus[cluster]=maxlevel
                    ramstatus[cluster]=maxlevel
                    timedict[cluster]=timemin
                    logwriter(str(cluster)+":"+str(timedict[cluster])+":"+str(cpustatus[cluster])+":"+str(ramstatus[cluster])+":"+str(time.time()))
        time.sleep(1)
        init=0