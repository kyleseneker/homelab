#!/usr/bin/env bash
set -euo pipefail

repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
lab_dir="$repo/.lab"
mkdir -p "$lab_dir"
chmod 700 "$lab_dir"
host_key="$HOME/.ssh/id_ed25519_homelab"
socket="$lab_dir/ssh-control"
host_ssh=(ssh -i "$host_key" -o IdentitiesOnly=yes -o BatchMode=yes)
lab_ssh=(ssh -i "$lab_dir/id_ed25519" -o IdentitiesOnly=yes -o BatchMode=yes
    -o "ProxyCommand=ssh -i $host_key -o IdentitiesOnly=yes -o BatchMode=yes -W %h:%p root@192.168.10.2")

case "${1:-}" in
    tunnel)
        if ! "${host_ssh[@]}" -S "$socket" -O check root@192.168.10.2 2>/dev/null; then
            "${host_ssh[@]}" -M -S "$socket" -fNT -o ExitOnForwardFailure=yes \
                -L 127.0.0.1:16443:172.26.0.10:6443 root@192.168.10.2
        fi
        ;;
    disconnect)
        "${host_ssh[@]}" -S "$socket" -O exit root@192.168.10.2
        ;;
    kubeconfig)
        umask 077
        tmp=$(mktemp "$lab_dir/kubeconfig.XXXXXX")
        trap 'rm -f "$tmp"' EXIT
        "${lab_ssh[@]}" labadmin@172.26.0.10 sudo cat /etc/kubernetes/admin.conf > "$tmp"
        kubectl --kubeconfig "$tmp" config set-cluster kubernetes \
            --server=https://127.0.0.1:16443 --tls-server-name=172.26.0.10 >/dev/null
        kubectl --kubeconfig "$tmp" config rename-context kubernetes-admin@kubernetes homelabrestore01 >/dev/null
        mv "$tmp" "$lab_dir/kubeconfig"
        echo "Lab kubeconfig: $lab_dir/kubeconfig (requires make lab-tunnel)"
        ;;
    ssh)
        exec "${lab_ssh[@]}" labadmin@172.26.0.10
        ;;
    *)
        echo "Usage: $0 {tunnel|disconnect|kubeconfig|ssh}" >&2
        exit 2
        ;;
esac
