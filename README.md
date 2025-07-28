# Sveltos/NATS Demo

This repo serves as a demo for the integration between Sveltos and NATS, using the CloudEvents spec.

## Setup

There are a lot of steps, but that's because this is a complex-yet-scalable integration. For one demo, yeah, it may not seem worth it. But for event-driven automation in your production cluster? This is pure gold.

### KinD and Sveltos

Make sure you have KinD installed, and then create a KinD cluster using the config file `kind/kind-config.yaml`:

```sh
kind create cluster --config kind/kind-config.yaml -n sveltos-nats
```

Once that's up and running, yout Kubeconfig context should be pointing to the new KinD cluster. You can now install Sveltos using the public Helm chart:

```sh
helm install projectsveltos projectsveltos/projectsveltos \
  --create-namespace -n projectsveltos
```

Sveltos will automatically create a SveltosCluster (that's a [Sveltos-specific custom resource](https://projectsveltos.github.io/sveltos/latest/register/register-cluster/#programmatic-registration)) for the Kubernetes cluster into which it's been installed. Let's add a label to that SveltosCluster to make this explicitly tailored to our use case:

```sh
kubectl label sveltoscluster mgmt "projectsveltos.io/role=management" -n mgmt
```

Sveltos can then install NATS and ArgoCD using the two ClusterProfiles found in the `k8s-configs/` directory:

```sh
kubectl apply -f k8s-configs/cp-argo.yaml
kubectl apply -f k8s-configs/cp-nats.yaml
```

### Subscribe Sveltos to NATS Streams

Sveltos has to be configured as a Consumer on specific JetStream Streams, which we can do by declaring the Subjects that Sveltos will subscribe to.

**The following convention MUST be used:** create a secret called `sveltos-nats` in the `projectsveltos` namespace, which contains the Consumer configuration that Sveltos will use. We can do this by creating a static JSON file (which I did, in `k8s-configs/sveltos-nats/sveltos-nats.json`), and passing it in as a k/v pair in the `kubctl create secret` command:

```sh
kubectl create secret generic -n projectsveltos sveltos-nats --from-file=sveltos-nats=k8s-configs/sveltos-nats/sveltos-nats.json
```

For transparency purposes, here's the contents of that JSON file, which set up our NATS integration configuration for Sveltos:

```JSON
{
  "jetstream":
   {
     "configuration":
        {
            "url": "nats://nats.nats.svc.cluster.local:4222",
            "streams": [
                {
                    "name": "REPOS",
                    "subjects": ["repo.requested", "repo.error"]
                }
            ],
            "authorization": {
                "user": {
                    "user": "sveltos",
                    "password": "projectsveltos"
                }
            }
        }
   }
}
```

If you'd like to see the full list of configuration options, you can find those [in the Sveltos documentation](https://projectsveltos.github.io/sveltos/main/events/nats/#nats-and-jetstream-configuration-options).

Now you can push the other Sveltos resources that live in the `k8s-config/` directory, which set up the [EventSource](https://projectsveltos.github.io/sveltos/main/events/addon_event_deployment/#eventsource) and [EventTrigger](https://projectsveltos.github.io/sveltos/main/events/addon_event_deployment/#eventtrigger) that are bound to the NATS subjects we just configured.

```sh
kubectl apply -f k8s-configs/es-repo.yaml # the event source
kubectl apply -f k8s-configs/et-repo.yaml # the event trigger
```

### Expose the NATS Service

The ClusterProfile for installing NATS adds an extra configuration to the service that changes it to a LoadBalancer type.

KinD doesn't have the same features as your standard cloud provider like AWS and GCP. As such, it doesn't have any way of exposing services that are of the LoadBalancer type. 

You don't have to stick with using LoadBalancer services. In fact, if you prefer, you can stand up a service that's ClusterIP, and use port-forwarding to expose it on the local host network. You'll just have to modify the CluserProfile. I promise I won't be offended.

If you do want to use the LoadBalancer type, you'll need to install the [Cloud Provider KIND](https://kind.sigs.k8s.io/docs/user/loadbalancer) binary, which requires Golang to be installed locally. IMHO, it's a really good project to at least be aware of, if you're in the habit of using KinD.

Once it's installed, you'd simply run:

```sh
# you may have to run with sudo
cloud-provider-kind
```

That will create an IP mapping on your local host network that point to the NATS service running in your cluster.

Again, you may have an easier time just modifying the ClusterProfile (essentially deleting the secion that corresponds to the service configuration) and port-forwarding to expose the service.

### Configure the NATS CLI

This next part assumes that you have the NATS CLI installed. If you don't, you can find installation instructions [in the CLI repo's readme](https://github.com/nats-io/natscli?tab=readme-ov-file#installation).

Depeding on how you exposed the NATS service, you'll add the NATS context to the NATS CLI using the following command:

```sh
nats context add kind -s <exposed-lb-ip-or-localhost:4222> --user=admin --password=admin --description="KindWithSveltos" --select
```

Now you're all set to start working with your NATS installation via the CLI.

### Deploy the Repo Creator Service

The last thing we'll need to do to experience the full demo is to deploy the Python service that will watch NATS JetStream for repo creation requests, and then make API calls out to GitHub to create said repo.

The config files are in `k8s-configs/repo-creator/`, and the image has already been built.

**You'll need to update `k8s-configs/repo-creator/secret.yaml` with your own GitHub token.** I hope you'll understand why I'm not going to provide you with mine. Also, remember that it needs to be base64-encoded in the YAML file.

Once you've set your own GitHub token into the secret.yaml file, you can deploy the Python service by pushing everything in the folder:

```sh
kubectl apply -f k8s-configs/repo-creator/
```

Now you're ready to test out the demo project in all its glory.

### Optional: Configure the ArgoCD CLI

You can skip this part if you want. You don't necessarily need to interact with ArgoCD to prove that this works. You can fetch the custom resources at the end instead of querying ArgoCD directly.

This part assumes that you have the ArgoCD CLI installed. If not, you can follow the instructions [on the project website](https://argo-cd.readthedocs.io/en/stable/cli_installation/).

The ArgoCD installation in our KinD cluster comes with an initial admin password that you'll want to change before using ArgoCD in production. But, since this is KinD, we're ok fetching and using that initial admin password. Let's pull it using kubectl and store it in an environment variable:

```sh
export ARGOCD_PW=$(kubectl get secrets/argocd-initial-admin-secret -n argocd --template={{.data.password}} | base64 -d)
```

TBH, I forgot to expose ArgoCD as a service type LoadBalancer, so for that I just exposed it using port-forwarding:

```sh
kubectl port-forward service/argocd-server -n argocd 8080:80
```

Now you can log in using the initial admin credentials:

```sh
argocd login localhost:8080 --username=admin --password=${ARGOCD_PW}
```

## Run the Demo

This is everyone's favorite part!!!

**NOTE: Currently the success script is set up to create a repo in my demo `open-garlic` GitHub org.** Since you probably don't have access, you'll need to modify the success script to point to a GitHub org that you have access to. If you don't have one, consider making one. They're free.

Once you've modified the success script, you can push a success event with the following command:

```sh
sh sh-scripts/success-event.sh
```

You should see a repo created in GitHub. Now check Argo:

```sh
argocd app list
```

You should also see an ArgoCD application matching your new repo. Hooray!

To test the failure event, run:

```sh
sh sh-scripts/failure-event.sh
```

Quickly list your ArgoCD Applications to ensure that Sveltos properly added the new Application:

```sh
argocd app list
```

There should be two Applications now.

You likely don't have access to create repos in the Microsoft org, so you probably don't need to check to make sure that a repo wasn't created. But feel free.

After about 20 seconds, check again:

```sh
argocd app list
```

There should now be only one Application, the one that was created for the success event.
