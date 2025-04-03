#!/bin/bash

# +---------+         +---------------------+         +---------+
# |   foo   |         |         bar         |         |   qux   |
# |         |         |                     |         |         |
# |  veth0  +---------+  veth1      veth2   +---------+  veth3  |
# +---------+         |                     |         +---------+
#                     |                     |
#                     +---------------------+

tmux kill-session -t test 2>/dev/null

# Cleanup: remove existing network namespaces if they exist
for ns in foo bar qux; do
    if ip netns list | grep -q $ns; then
        ip netns delete $ns
    fi
done

# Create network namespaces
ip netns add foo
ip netns add bar
ip netns add qux

# Create veth pairs
ip link add veth0 type veth peer name veth1
ip link add veth2 type veth peer name veth3

# Move veth interfaces to the respective namespaces
ip link set veth0 netns foo
ip link set veth1 netns bar
ip link set veth2 netns bar
ip link set veth3 netns qux

# Bring up the loopback interfaces
ip netns exec foo ip link set dev lo up
ip netns exec bar ip link set dev lo up
ip netns exec qux ip link set dev lo up

# Enable IPv4 forwarding in each namespace
ip netns exec foo sysctl -w net.ipv4.ip_forward=1
ip netns exec bar sysctl -w net.ipv4.ip_forward=1
ip netns exec qux sysctl -w net.ipv4.ip_forward=1

# Assign IP addresses
ip netns exec foo ip addr add 10.0.0.1/24 dev veth0
ip netns exec bar ip addr add 10.0.0.2/24 dev veth1
ip netns exec bar ip addr add 192.0.2.1/24 dev veth2
ip netns exec qux ip addr add 192.0.2.2/24 dev veth3

# Bring up the interfaces
ip netns exec foo ip link set dev veth0 up
ip netns exec bar ip link set dev veth1 up
ip netns exec bar ip link set dev veth2 up
ip netns exec qux ip link set dev veth3 up

# Set TC (traffic control)
ip netns exec foo tc qdisc add dev veth0 root netem delay 300ms loss 15%
ip netns exec bar tc qdisc add dev veth1 root netem delay 150ms loss 1%

# Set up NAT on bar for traffic destined to qux
ip netns exec bar iptables -t nat -A POSTROUTING -o veth2 -j MASQUERADE

# Set default route in foo to point to bar
ip netns exec foo ip route add default via 10.0.0.2

# Create a tmux session with three windows, naming them after the namespaces
tmux new-session -d -s test -n foo "ip netns exec foo bash"
tmux new-window -t test:1 -n bar "ip netns exec bar bash"
tmux new-window -t test:2 -n qux "ip netns exec qux bash"
tmux set-option -g mouse on

# Attach to the tmux session
tmux attach-session -t test
