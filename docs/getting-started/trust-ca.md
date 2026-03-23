# Trust the Homelab CA

All services in the homelab are served over HTTPS using certificates issued by an internal Certificate Authority (CA). To avoid browser warnings about self-signed certificates, you need to trust this CA on each machine that will access homelab services. This is a one-time setup per machine.

## How the CA Chain Works

The homelab uses cert-manager to manage TLS certificates:

1. **Self-signed root CA** -- cert-manager creates a self-signed Certificate Authority called `homelab-ca`. The CA certificate and private key are stored in a Kubernetes Secret (`homelab-ca-secret` in the `cert-manager` namespace).
2. **ClusterIssuer** -- A ClusterIssuer named `homelab-ca-issuer` is configured to use the `homelab-ca` root CA to sign certificates.
3. **Per-ingress certificates** -- When an Ingress resource requests a TLS certificate (via the `cert-manager.io/cluster-issuer` annotation), cert-manager automatically generates a certificate signed by `homelab-ca-issuer` and stores it as a Secret referenced by the Ingress.

Because the root CA is self-signed, browsers and operating systems will not trust it by default. Adding the CA certificate to your system trust store resolves this.

## Export the CA Certificate

From your local machine with `kubectl` configured:

```bash
export KUBECONFIG=$(pwd)/kubeconfig
kubectl get secret homelab-ca-secret -n cert-manager \
  -o jsonpath='{.data.tls\.crt}' | base64 -d > homelab-ca.crt
```

This writes the root CA certificate to `homelab-ca.crt` in your current directory.

## Install the CA Certificate

### macOS

```bash
sudo security add-trusted-cert -d -r trustRoot \
  -k /Library/Keychains/System.keychain homelab-ca.crt
```

You may be prompted for your macOS user password.

### Linux (Debian / Ubuntu)

```bash
sudo cp homelab-ca.crt /usr/local/share/ca-certificates/
sudo update-ca-certificates
```

### Clean Up

Once the certificate is installed, remove the local copy:

```bash
rm homelab-ca.crt
```

## Restart Your Browser

After installing the CA certificate, **restart your browser** for the change to take effect. All `https://*.homelab.local` sites will then show valid certificates with no warnings.

!!! note
    Some browsers (notably Firefox) maintain their own certificate store and may not use the system trust store. In Firefox, you can import the CA certificate manually under **Settings > Privacy & Security > Certificates > View Certificates > Import**.
