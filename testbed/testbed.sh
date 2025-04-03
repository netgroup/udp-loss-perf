#!/bin/bash

#
#  +---------------------+          +---------------------+
#  |    net namespace    |          |    net namespace    |
#  |         foo         |          |         bar         |
#  |                     |          |                     |
#  |      +---------+    |          |      +---------+    |
#  |      | veth0   |    |          |      | veth1   |    |
#  |      | 10.0.0.1|    |          |      | 10.0.0.2|    |
#  |      +--+------+    |          |      +--+------+    |
#  |         |           |          |         |           |
#  +---------------------+          +---------|-----------+
#            |                                |
#            |                                |
#            |                                |
#            +--------------------------------+

tmux kill-session -t test 2>/dev/null

# Cleanup: remove existing network namespaces if they exist
if ip netns list | grep -q foo; then
    ip netns delete foo
fi
if ip netns list | grep -q bar; then
    ip netns delete bar
fi

# Create network namespaces
ip netns add foo
ip netns add bar

# Create a veth pair
ip link add veth0 type veth peer name veth1

# Move veth interfaces to the respective namespaces
ip link set veth0 netns foo
ip link set veth1 netns bar

# Assign IP addresses
ip netns exec foo ip addr add 10.0.0.1/24 dev veth0
ip netns exec bar ip addr add 10.0.0.2/24 dev veth1

# Bring up the interfaces
ip netns exec foo ip link set dev veth0 up
ip netns exec bar ip link set dev veth1 up

# Bring up the loopback interfaces
ip netns exec foo ip link set dev lo up
ip netns exec bar ip link set dev lo up

# set TC
ip netns exec foo tc qdisc add dev veth0 root netem delay 300ms loss 15%
ip netns exec bar tc qdisc add dev veth1 root netem delay 150ms

# Create a tmux session with two windows
tmux new-session -d -s test "ip netns exec foo bash"
tmux new-window -t test:1 "ip netns exec bar bash"
tmux set-option -g mouse on

# Attach to the tmux session
tmux attach-session -t test
