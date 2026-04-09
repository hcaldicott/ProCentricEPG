# Kubernetes Deployment Guide (Kustomize)

This project can be deployed to Kubernetes in addition to Docker Compose using Kustomize manifests under `k8s/`.

## What Gets Deployed

- `epg-generator` deployment
- `ftp-server` deployment (SFTPGo)
- `epg-admin` deployment (merged Prometheus metrics endpoint)
- PVCs for bundle sharing and SFTPGo state
- ClusterIP services for:
  - FTP control/passive ports + SFTPGo admin/API + SFTPGo native metrics (`ftp-server`)
  - Combined metrics (`epg-admin`)

Probe configuration:
- `ftp-server`: `startupProbe`, `readinessProbe`, `livenessProbe` using native command `sftpgo ping`
- `epg-admin`: `startupProbe`, `readinessProbe`, `livenessProbe` on `http://:8081/healthz`

## Prerequisites

- Kubernetes cluster (v1.24+ recommended)
- `kubectl` with cluster access
- Kustomize support (`kubectl apply -k ...` or standalone `kustomize`)
- A storage class that supports `ReadWriteOnce` PVCs

## Directory Layout

```text
k8s/
  base/
  local/
    public-ftp/
```

## 1) Container Images (GHCR Default)

Base manifests pull prebuilt images from GHCR by default:

- `ghcr.io/hcaldicott/procentric-epg-generator:edge`
- `ghcr.io/hcaldicott/procentric-epg-epg-admin:edge`

If you need to pin a specific tag or use your own registry, add an `images:` override in your local kustomization:

```yaml
images:
  - name: ghcr.io/hcaldicott/procentric-epg-generator
    newName: ghcr.io/<owner>/procentric-epg-generator
    newTag: "1.2.3"
  - name: ghcr.io/hcaldicott/procentric-epg-epg-admin
    newName: ghcr.io/<owner>/procentric-epg-epg-admin
    newTag: "1.2.3"
```

If your registry is private, configure `imagePullSecrets` in your overlay.

## 2) Set SFTPGo Admin Credentials

Update:

- `k8s/base/secret-sftpgo-admin.yaml`

At minimum change:

- `stringData.username`
- `stringData.password`

The signing passphrase is auto-generated on first startup and persisted in `/var/lib/sftpgo/signing_passphrase` (PVC-backed), so no manual secret value is required.

## 3) Deploy Base Stack (Internal Services)

```bash
kubectl apply -k k8s/base
```

Check rollout:

```bash
kubectl -n procentric-epg get pods
kubectl -n procentric-epg get svc
```

Default scheduling strategy:
- `epg-bundles` uses `ReadWriteOnce`
- `epg-generator` and `epg-admin` are configured with required pod affinity to `ftp-server` on `kubernetes.io/hostname`
- all three pods must run on the same node

## 4) Expose FTP Externally (Optional)

Use the local override:

```bash
kubectl apply -k k8s/local/public-ftp
```

`k8s/local/` is intentionally gitignored for per-environment private overrides.
If `k8s/local/public-ftp` does not exist yet, create it first:

```bash
mkdir -p k8s/local/public-ftp
cat > k8s/local/public-ftp/kustomization.yaml <<'EOF'
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - ../../base
patches:
  - target:
      kind: Service
      name: ftp-server
    patch: |-
      - op: replace
        path: /spec/type
        value: LoadBalancer
      - op: add
        path: /spec/loadBalancerIP
        value: REPLACE_WITH_LB_IP
  - target:
      kind: Service
      name: epg-admin
    patch: |-
      - op: replace
        path: /spec/type
        value: LoadBalancer
      - op: add
        path: /spec/loadBalancerIP
        value: REPLACE_WITH_LB_IP
  - path: patch-ftp-server-passive-ip.local.yaml
EOF

cat > k8s/local/public-ftp/patch-ftp-server-passive-ip.local.yaml <<'EOF'
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ftp-server
  namespace: procentric-epg
spec:
  template:
    spec:
      containers:
        - name: ftp-server
          env:
            - name: SFTPGO_FTPD__BINDINGS__0__FORCE_PASSIVE_IP
              value: REPLACE_WITH_PUBLIC_IP
EOF
```

Before applying, set your externally reachable passive IP and load balancer IP in your local files:

- `k8s/local/public-ftp/kustomization.yaml`
- `k8s/local/public-ftp/patch-ftp-server-passive-ip.local.yaml`

The local override changes `ftp-server` and `epg-admin` services to `LoadBalancer`.

Important limitations:
- this is a single-node placement strategy
- if the node is unavailable, scheduling will block until `ftp-server` can run again

## Prometheus Scrape Target

Use `epg-admin` service as the single scrape endpoint:

```yaml
scrape_configs:
  - job_name: procentric-epg
    static_configs:
      - targets: ["epg-admin.procentric-epg.svc.cluster.local:8081"]
```

## Accessing EPG Admin

Within cluster:

- `http://epg-admin.procentric-epg.svc.cluster.local:8081/admin/login`

For local testing, use port-forward:

```bash
kubectl -n procentric-epg port-forward svc/epg-admin 8081:8081
```

Then open `http://127.0.0.1:8081/admin/login`.

SFTPGo built-in Web Admin UI is disabled by default (`SFTPGO_HTTPD__BINDINGS__0__ENABLE_WEB_ADMIN: "0"` in base deployment). Re-enable by patching that env var to `"1"` in your overlay if needed.

## Cleanup

```bash
kubectl delete -k k8s/local/public-ftp --ignore-not-found
kubectl delete -k k8s/base
```
