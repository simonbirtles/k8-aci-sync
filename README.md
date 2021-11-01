# ACI Synchronization Application for Kubernetes (WIP)

The purpose of the application is to synchronize the ACI APIC that is connected to a K8's cluster. The K8s bare metal cluster is connected to ACI leaf switches via a L3Out. 

The K8s cluster uses a CNI like Calico which peers with the ACI leafs nodes with eBGP, the K8s cluster also has a load balancer implementation like MetalLB to provision load balancer service IPs and to provide the LB function. Any CNI that is not integrated and where the K8s cluster connects to ACI via L3Outs should work with this solution. 

At a highlevel, the code basically does the following:
 - For a new K8 Deployment, intially creates the APIC L3Out - EEPG & External Subnets Managed Objects
 - During the lifetime of the K8 Deployment, will add or remove APIC managed objects for subnets
    - Subnets are created from K8 Pod IPs and K8 Service Load Balancer IPs
 - Keeps all APIC mamanged objects created by the synchronization code in an immutable state but only for relevent configuration items (more on this below) 
 - On a K8 Deployment or Pod or Service deletion, the APIC is updated correspondingly.

When a K8s 'Deployment' is applied with a specific annotation, the synchronization application will configure the ACI fabric via the connected L3Out to provide access to the deployment via the deployment Pod IPs and Service LB IPs.

The L3Outs are used in this scenario with Calico as BGP is used between ACI and the Calico CNI and network protocol peering with ACI only happens via L3outs.

This application will create ACI APIC managed objects for a deployment, pod(s) and services with type LoadBalancer. The mapping is as follows:

| K8 Object  | ACI Object Name | ACI Object Class | 
|---|---|---|
| Deployment | L3Out EEPG  | l3extInstP |
| Pod | L3Out EEPG Subnet  | l3extSubnet | 
| Service | L3Out EEPG Subnet  | l3extSubnet |

## Process

On a K8 event for a new deployment, the correct annotation must exist in the deployment as show below:
```
---
kind: Deployment

apiVersion: apps/v1

metadata:
  labels:
    app: mcast-app
  name: mcast
  namespace: multicast
  annotations:
    aci.haystacknetworks.com/l3o: '{ "tenant":"TEN_K8_C1", "l3out": "L3O_K8_C1", "epg":"EPG_K8_APP_MCAST"  }'

```
The annotation must have a key of `aci.haystacknetworks.com/l3o` to be considered as a deployment to synchronize, the value is encoded JSON with three mandatory keys. The `tenant` and `l3out` keys are names of an **existing** APIC tenant and l3out within the given tenant. The `epg` key is the name of an External EPG (l3extInstP) which is a child of the given L3out (`l3out` key). The EEPG (`epg`) does not have to exist on the APIC unlike the `tenant` and `l3out` managed objects, if the `epg` does not exist it will be created by the synchronization application.

Any APIC managed object created by the synchronization appliction will remain managed by the synchronization application, in that, significant changes to the managed object on the ACI APIC (via GUI or REST) will be reverted back to the state intially configured by the synchronization application. The application only does this for critical configration items, not for all items. For example:

If a EEPG Subnet is created by the synchronization application, it will be created with a configurable option of 'import-security' (External Subnets for the External EPG). If this option is removed, the synchronization application will put it back. If you add a different subnet option then this will be left as configured.

If any managed object is deleted from the APIC, the synchronization application will restore it. Using the EEPG example, if you created this manually before the deployment was applied in K8s, then the EEPG would not be managed. If you then deleted the EEPG in the APIC, the synchronization application would not restore it. If you have not created the EEPG before the K8s deployment had been applied and therefore for the synchronization application created the EEPG, if you then deleted the EEPG (and therefore implicitly deleting the child subnets l3extSubnet), the synchronization application would restore the EEPG and Subnets.

On a K8 Pod or Service creation, the synchronization application will create an EEPG subnet (l3extSubnet) for each Pod IP and each Service LoadBalancer IP. 

The EEPG does not have any contracts applied by the synchronization application, it is up to you to assign these. The synchronization application creates the bridge between ACI and K8s at a L3 layer only to help reomve the complexity, keep consistency and decrease deployment times. 

## Usage
As explained the K8 deployment must have a valid annotation and the APIC must have the given teant and L3Out created. In fact these muct exist as the K8 cluster will be connected via these. 

Currently this synchronization application runs on the master K8 node, only due to the fact that during dev I have the KUBE config file locally on that machine. Any machine that has a copy of the KUBE config and access to the K8s API IP and the APIC API IP will be sufficient. For the ACI credentials the following environmental variables should be set and accessiable to the application.

 - ACI_USERNAME: APIC username with admin access to the given tenant.
 - ACI_PASSWORD: Password for the given username in ACI_USERNAME
 - ACI_APIC:     A FQDN or IP address of one of the ACI APIC cluster members.

 Execute the file `./aci-sync/py` in the repository root which will by default use Python at `/usr/local/bin/python3.9`, therefore you should be using Python 3.9.6 or above. If you are not, the application will work on Python as low as 3.6.8 as long as you remove the versions from the requirements.txt file and apply the most recent for 3.6.8.

 ### Python Modules
 Use the requirements.txt files in the repository root to install required modules for use with Python 3.9.6 or above. Remove the versions from the requirements.txt file and apply the most recent for Python versions (>3.6.8 <3.9.6)
 
## Application Threads
The application runs a number of different threads outside of the main thread.

 - Main
 - Refresh Subscriptions
 - Print Subscriptions
 - K8 Deployment Event Watcher/Listener
 - K8 Pod Event Watcher/Listener
 - K8 Deployment Event Watcher/Listener
 - ACI APIC Subscription Event Listener

## References
These references are to two blogs I wrote on the subject on ACi and K8s. One considering the Cisco K8s CNI and the other considering the Calico CNI. Looking at the differences between these I felt there is a missing 'happy medium' between too much integration (Cisco K8s CNI) and no integration (Calico CNI). This prompted me to write this code.

### Cisco K8s CNI
 - https://haystacknetworks.com/acikubernetesk8scnione
 - https://haystacknetworks.com/acikubernetesk8scnitwo
### Calico CNI & MetalLB
 - https://haystacknetworks.com/acik8calicocnimetallbp1
 - https://haystacknetworks.com/acik8calicocnimetallbp2




 ## Outstanding Items - Priority

  - Initial K8s synchronization needs the list API `_continue` param honored so we dont miss anything on large clusters with many deployments, pods and service regardless if they are flagged for ACI sync as we must get them all on startup to check.
  - Clear old non managed MO subscriptions automatically (i.e. L3Out 'created' subscription)
  - Finish off application shutdown and graceful thread termination.
  - The application moved to a container deployment once stable and K8s native security will be used for K8 and ACI credentials.
  - Currently both Pod and Service IP's are exposed, future will have a flag to enable/disable Pod IP exposure only have the LB IP.
  - Possibly have code to figure out which Tenant/L3out to use for the EEPG as the K8s cluster is connected via the same.
  - Logging move from print to Logging module but still print out to stdout, stderr in readiness for K8 containerization.
  - Review all TODO comments.
  - More testing, code improvements (tidy up etc)


## Current Status

The application performs the tasks for which it is intended as described above. Certainly code tidy and optimization in some places to ensure that other ideas I have can be added in later without much headache. 

It does need some work finished before deploying as a container for real world use, its not practical to run as a service outside of K8s I would suggest, its perfectly possible and valid but I would feel running within the cluster and having automatic Pod management would be more benefical.

Of course, its goes without saying (but I will say it anyway)... testing, testing though different senarios, startup, running, missing updates due to not running etc.

## Contact
You can always use Git as usual for issues etc and/or contact me at simon.birtles@haystacknetworks.com. I have some other ideas to extend this application for other ACI integration / synchronization features and happy to hear other ideas too.
