#!/bin/bash

readonly SHUTDOWN_DATE="2025-04-12 00:14:00"
readonly SHUTDOWN_DATE_SECONDS="$(date -d "$SHUTDOWN_DATE" +%s)"

__run_udp_test()
{
	/home/smarts/udp-loss-perf/python/client.py \
		-z 139.28.149.89 -n 60000 -r 1000 -d up

	sleep 10

	# tcpdump -i br0 -w /root/data/capture-down-%Y-%m-%d_%H:%M:%S.pcap -G 65 -W 1 &
	/home/smarts/udp-loss-perf/python/client.py \
		-z 139.28.149.89 -n 60000 -r 1000 -d down

	sleep 10
}

__run_collect()
{
	local date_id=$(date '+%Y%m%d%H%M%S')
	local remote_dir_path="/home/tempuser/data/client/data_${date_id}"

	# Create the remote directory structure
	ssh -i /home/smarts/tmp-key \
		tempuser@139.28.149.89 "mkdir -p ${remote_dir_path}"

	# Transfer the file
	scp -i /home/smarts/tmp-key -r /root/data/*.json \
		tempuser@139.28.149.89:${remote_dir_path}
	sleep 1

	#scp -i /home/smarts/tmp-key -r /root/data/*.pcap \
	#	tempuser@139.28.149.89:${remote_dir_path}
}

expired()
{
        local now="$(date +%s)"

        if [ "${now}" -lt "${SHUTDOWN_DATE_SECONDS}" ]; then
                return 1
        fi

        # expired !!!
        return 0
}

run_udp_test()
{
	if ! expired; then
		__run_udp_test
	fi
}

run_collect()
{
	if ! expired; then
		__run_collect
	fi
}

# Check the command line parameter
case "$1" in
    run_test)
        run_udp_test
        ;;
    run_collect)
        run_collect
        ;;
    *)
        echo "Error: Invalid parameter '$1'."
        echo "Valid parameters are: run_test, run_collect."
	exit 1
        ;;
esac
