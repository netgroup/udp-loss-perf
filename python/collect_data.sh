#!/bin/bash

DATE_ID=$(date '+%Y%m%d%H%M%S')
REMOTE_DIR_PATH="/home/tempuser/data/client/data_${DATE_ID}"

# Create the remote directory structure
ssh -i /home/smarts/tmp-key tempuser@139.28.149.89 "mkdir -p ${REMOTE_DIR_PATH}"

# Transfer the file
scp -i /home/smarts/tmp-key -r /root/data/*.json tempuser@139.28.149.89:${REMOTE_DIR_PATH}
sleep 1
scp -i /home/smarts/tmp-key -r /root/data/*.pcap tempuser@139.28.149.89:${REMOTE_DIR_PATH}
