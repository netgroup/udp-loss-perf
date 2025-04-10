#!/usr/bin/env python3

import socket
import threading
import time
import json
import struct
import os
import datetime
import traceback
import argparse
import common
import subprocess
import signal
from collections import defaultdict

class PacketManager:
    def __init__(self, packet_info, tcpdump_processes, session_timeout=60,
                 gc_timeout=30):
        self.tcpdump_processes = tcpdump_processes
        self.session_timeout = session_timeout
        self.cleanup_interval = gc_timeout
        self.packet_info = packet_info
        self.running = True
        # This will act as our hashmap
        self.data = {}

        threading.Thread(target=self.cleanup_sessions, daemon=True).start()

    # Add a new MSession object for the given key
    def add(self, key):
        if key not in self.data:
            self.data[key] = common.MSession()

    # Count a packet for the given key and number
    def count_packet(self, key, number):
        if key in self.data:
            return self.data[key].count_packet(number)
        else:
            # If the key doesn't exist, create a new session and count the
            # packet
            self.add(key)
            return self.data[key].count_packet(number)

    # Periodically clean up old sessions
    def cleanup_sessions_core(self):
        while self.running:
            current_time = time.time()
            keys_to_delete = []
            for key, session in self.data.items():
                if current_time - session.timestamp > self.session_timeout:
                    keys_to_delete.append(key)

            for key in keys_to_delete:
                del self.data[key]
                # mark the packet info element as dying...
                self.packet_info[key]['dying'] = True

                # Stop tcpdump if session is dying
                if key in self.tcpdump_processes:
                    tcpdump_pid = self.tcpdump_processes[key]
                    try:
                        os.kill(tcpdump_pid, signal.SIGTERM)
                        # This will clean up the zombie process
                        os.waitpid(tcpdump_pid, 0)
                    except OSError:
                        pass  # Process may have already terminated

                    del self.tcpdump_processes[key]

            time.sleep(self.cleanup_interval)

    def cleanup_sessions(self):
        try:
            self.cleanup_sessions_core()
        except Exception as e:
            # other exceptions are fatal?! NO MERCY!
            tb_exception = traceback.TracebackException.from_exception(e)
            print("An exception occurred:")
            print(''.join(tb_exception.format()))
            os._exit(1)

    # Stop the background cleanup thread
    def stop(self):
        self.running = False

# Define the UDP server
class UDPServer:
    def __init__(self, host='0.0.0.0', port=12345, tcpdump_interface=None,
                 output_file=None):
        # Each packet ID will map to a dictionary with count, first_seen,
        # last_seen, packet_rate, total_packets, direction and the remote
        # endpoint (e.g., the connecting client).
        self.packet_info = defaultdict(lambda: {
            'count': 0,
            'duplicates': 0,
            'first_seen': None,
            'last_seen': None,
            'packet_rate': 0,
            'total_packets': 0,
            'direction': 0,
            'dying': False,
            'remote': None,
        })
        self.tcpdump_processes = {}  # structure to hold tcpdump PIDs
        self.packet_manager = PacketManager(self.packet_info,
                                            self.tcpdump_processes)
        self.tcpdump_interface = tcpdump_interface
        self.server_address = (host, port)
        self.lock = threading.Lock()
        self.send_running = False
        self.running = True
        self.port = port

        self.output_file = (common.get_timestamp_filename("server")
                            if output_file is None else output_file)

    def start(self):
        # Create a UDP socket
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(self.server_address)

        # Start the display thread
        display_thread = threading.Thread(target=self.save_counts_to_file,
                                          daemon=True)
        display_thread.start()

        # Start the receiving thread
        rcv_thread = threading.Thread(target=self.receive_packets, daemon=True)
        rcv_thread.start()

    def send_packet(self, remote_address, packet_id, packet_num, packet_rate,
                    total_packets, direction):
        packet_data = struct.pack('!IIIII', packet_id, packet_num,
                                  packet_rate, total_packets,
                                  direction) + b'\x00' * (64 - 20)
        self.sock.sendto(packet_data, remote_address)

    # Control the sending rate
    def send_rate_sleep(self, packet_rate):
        time.sleep(1 / packet_rate)

    def send_packets_core(self, packet_id):
        current_time = time.time()

        with self.lock:
            self.packet_info[packet_id]['first_seen'] = current_time
            self.packet_info[packet_id]['last_seen'] = current_time

        remote_address = self.packet_info[packet_id]['remote']
        packet_rate = self.packet_info[packet_id]['packet_rate']
        total_packets = self.packet_info[packet_id]['total_packets']
        direction = self.packet_info[packet_id]['direction']

        for i in range(total_packets):
            packet_num = i
            self.packet_info[packet_id]['count'] += 1

            self.send_packet(remote_address, packet_id, packet_num, packet_rate,
                             total_packets, direction)

            common.send_rate_sleep(packet_rate)

    def send_packets_non_blocking(self, packet_id):
        current_time = time.time()

        with self.lock:
            if self.packet_info[packet_id]['first_seen'] is not None:
                # duplicated request packet for download. Send operation
                # already started.
                self.packet_info[packet_id]['last_seen'] = current_time
                # NOTE: lock is automatically released
                return

        rcv_thread = threading.Thread(target=self.send_packets_core,
                                      args=(packet_id,), daemon=True)
        rcv_thread.start()

    def start_tcpdump(self, packet_id):
        # Only start if interface is provided
        if self.tcpdump_interface:
            srchost, srcport = self.packet_info[packet_id]['remote']

            pcap_name = f"tcpdump_up_{packet_id}.pcap"
            pcap_fullname = common.get_pcap_fullpath(pcap_name)

            command = ['tcpdump', '-i', self.tcpdump_interface,
                        f'udp and src host {srchost} and src port {srcport} and dst port {self.port}',
                        '-w', f'{pcap_fullname}']
            process = subprocess.Popen(command)
            # Store the PID
            self.tcpdump_processes[packet_id] = process.pid

            return process.pid

    def stop_tcpdump(self, packet_id):
        if packet_id in self.tcpdump_processes:
            tcpdump_pid = self.tcpdump_processes[packet_id]
            try:
                os.kill(tcpdump_pid, signal.SIGTERM)
                # This will clean up the zombie process
                os.waitpid(tcpdump_pid, 0)
            except OSError:
                pass  # Process may have already terminated

            del self.tcpdump_processes[packet_id]

    def receive_packet_finish(self, packet_id, packet_number):
        current_time = time.time()

        if self.packet_info[packet_id]['first_seen'] is None:
            self.packet_info[packet_id]['first_seen'] = current_time

            # Start tcpdump when the packet_id is first seen
            proc_id = self.start_tcpdump(packet_id)
            self.packet_info[packet_id]['tcpdump_process'] = proc_id

        self.packet_info[packet_id]['last_seen'] = current_time

        packet_number_cnt = self.packet_manager.count_packet(packet_id,
                                                             packet_number)

        if packet_number_cnt == (2 ** 32) - 1:
            # control packet for starting tx, ignore it.
            return

        if packet_number_cnt == 1:
            # no duplicates
            self.packet_info[packet_id]['count'] += 1
        else:
            self.packet_info[packet_id]['duplicates'] += 1

    def receive_packets(self):
        while self.running:
            data, addr = self.sock.recvfrom(1024)  # Buffer size is 1024 bytes
            if len(data) >= 64:
                packet_id = int.from_bytes(data[:4], byteorder='big')
                if self.packet_info[packet_id]['dying']:
                    continue

                packet_rate = int.from_bytes(data[8:12], byteorder='big')
                total_packets = int.from_bytes(data[12:16], byteorder='big')
                direction = int.from_bytes(data[16:20], byteorder='big')

                self.packet_info[packet_id]['remote'] = addr
                self.packet_info[packet_id]['total_packets'] = total_packets
                self.packet_info[packet_id]['packet_rate'] = packet_rate
                self.packet_info[packet_id]['direction'] = direction

                if direction > 0:
                    self.send_packets_non_blocking(packet_id)
                    continue

                packet_number = int.from_bytes(data[4:8], byteorder='big')

                self.receive_packet_finish(packet_id, packet_number)

    def save_to_json(self):
        packet_info_copy = self.packet_info.copy()

        with open(self.output_file, 'w') as json_file:
            json.dump(packet_info_copy, json_file, indent=4)
            print(f"Saved packet counts to {self.output_file}")

    def save_counts_to_file(self):
        while self.running:
            time.sleep(5)
            self.save_to_json()

    def stop(self):
        self.running = False
        self.sock.close()
        self.packet_manager.stop()
        # save on disk
        self.save_to_json()
        # Stop tcpdump processes for all active sessions
        for packet_id in list(self.tcpdump_processes.keys()):
            self.stop_tcpdump(packet_id)

# Run the server
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="UDP Server")
    parser.add_argument('-b', '--bind', type=str, default="0.0.0.0",
                        help='Host binding address')
    parser.add_argument('-p', '--port', type=int, default=12345,
                        help='Local port')
    parser.add_argument('-i', '--interface', type=str,
                        help='Network interface for tcpdump')

    args = parser.parse_args()

    try:
        server = UDPServer(host=args.bind, port=args.port,
                           tcpdump_interface=args.interface)
        server.start()

        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        server.stop()
        exit(2)
    except Exception as e:
        print(e)
        exit(1)
