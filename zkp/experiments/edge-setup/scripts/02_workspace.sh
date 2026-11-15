set -euxo pipefail
test ! -e /home/infonetworking/csi-zkp
umask 077
mkdir -p /home/infonetworking/csi-zkp/{tools,downloads,cache,sources,packages,results,reports,scripts}
ls -ld /home/infonetworking/csi-zkp /home/infonetworking/csi-zkp/*
