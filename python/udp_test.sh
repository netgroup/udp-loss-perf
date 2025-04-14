#!/bin/bash

readonly SHUTDOWN_DATE="2025-04-12 00:14:00"
readonly SHUTDOWN_DATE_SECONDS="$(date -d "$SHUTDOWN_DATE" +%s)"

__run_collect()
{
	rsync \
		-avz \
		--remove-source-files \
		--include='*.pcap' --include='*.json'  \
		--exclude='*' \
		-e "ssh -i /home/smarts/tmp-key" \
		--progress /root/data/ \
		tempuser@139.28.149.89:client

	rsync \
		-avz \
		--include='*.txt' \
		--exclude='*' \
		-e "ssh -i /home/smarts/tmp-key" \
		--progress /root/data/ \
		tempuser@139.28.149.89:client
}

__run_udp_test()
{
	/home/smarts/udp-loss-perf/python/client.py \
		-z 139.28.149.89 -n 60000 -r 2000 -d up --interface enp3s0

	sleep 10

	/home/smarts/udp-loss-perf/python/client.py \
		-z 139.28.149.89 -n 120000 -r 4000 -d down

	sleep 10

	__run_collect
}

run_udp_progressive_rate_test()
{
	local step
	local rate
	local irate

	for step in 10 100 1000 10000; do
		irate=$((step/10))

		for rate in $(seq "${irate}" "${irate}" "$((step - 1))"); do
			local npackets="$((rate * 60))"

			/home/smarts/udp-loss-perf/python/client.py \
				-z 139.28.149.89 \
				-n "${npackets}" -r "${rate}" \
				-d up --interface enp3s0

			__run_collect
		done
	done
}

__run_collect_old()
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
    run_rate_test)
	run_udp_progressive_rate_test
	;;
    *)
        echo "Error: Invalid parameter '$1'."
        echo "Valid parameters are: run_test, run_collect, run_rate_test"
	exit 1
        ;;
esac
