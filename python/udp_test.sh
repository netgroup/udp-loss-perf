/home/smarts/udp-loss-perf/python/client.py -z 139.28.149.89 -n 60000 -r 1000 -d up

sleep 10

tcpdump -i br0 -w /root/data/capture-down-%Y-%m-%d_%H:%M:%S.pcap -G 65 -W 1 &
/home/smarts/udp-loss-perf/python/client.py -z 139.28.149.89 -n 60000 -r 1000 -d down

sleep 10
