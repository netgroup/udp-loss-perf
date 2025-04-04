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
from collections import defaultdict

class PacketManager:
    def __init__(self, packet_info, session_timeout=60, gc_timeout=30):
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

            # Wait for the specified interval before checking again
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
    def __init__(self, host='0.0.0.0', port=12345,
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
        self.packet_manager = PacketManager(self.packet_info)
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
            # Create the packet data
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
            # Update the packet information
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

    def receive_packet_finish(self, packet_id, packet_number):
        current_time = time.time()

        if self.packet_info[packet_id]['first_seen'] is None:
             self.packet_info[packet_id]['first_seen'] = current_time

        self.packet_info[packet_id]['last_seen'] = current_time

        packet_number_cnt = self.packet_manager.count_packet(packet_id,
                                                             packet_number);
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
                    # this measurement test has expired, ignore it
                    continue

                packet_rate = int.from_bytes(data[8:12], byteorder='big')
                total_packets = int.from_bytes(data[12:16], byteorder='big')
                direction = int.from_bytes(data[16:20], byteorder='big')

                self.packet_info[packet_id]['remote'] = addr
                self.packet_info[packet_id]['total_packets'] = total_packets
                self.packet_info[packet_id]['packet_rate'] = packet_rate
                self.packet_info[packet_id]['direction'] = direction

                if direction > 0:
                    # the client is in download mode
                    self.send_packets_non_blocking(packet_id)
                    continue

                # the client is in upload mode, a.k.a. the server is receiving
                # traffic from the client.

                packet_number = int.from_bytes(data[4:8], byteorder='big')

                self.receive_packet_finish(packet_id, packet_number)

    def save_to_json(self):
        packet_info_copy = self.packet_info.copy()

        with open(self.output_file, 'w') as json_file:
            # Pretty print the JSON
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

# Run the server
if __name__ == "__main__":
    # Create the argument parser
    parser = argparse.ArgumentParser(description="UDP Server")

    # Add arguments
    parser.add_argument('-b', '--bind', type=str, default="0.0.0.0",
                        help='Host binding address')
    parser.add_argument('-p', '--port', type=int, default=12345,
                        help='Local port')

    # Parse the arguments
    args = parser.parse_args()

    try:
        server = UDPServer(host=args.bind, port=args.port)
        server.start()

        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        server.stop()
        exit(2)
    except Exception as e:
        print(e)
        exit(1)
