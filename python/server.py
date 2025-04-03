#!/usr/bin/env python3

import socket
import threading
import time
import json
import struct
import os
import datetime
import argparse
from collections import defaultdict

def get_timestamp_filename(name):
    current_time = datetime.datetime.now()
    formatted_time = current_time.strftime("%Y%m%d%H%M%S")
    filename = f"{formatted_time}_{name}.json"
    return filename

# Define the UDP server
class UDPServer:
    def __init__(self, host='0.0.0.0', port=12345,
                 output_file=None):
        # Each packet ID will map to a dictionary with count, first_seen,
        # last_seen, packet_rate, total_packets, direction and the remote
        # endpoint (e.g., the connecting client).
        self.packet_info = defaultdict(lambda: {
            'count': 0,
            'first_seen': None,
            'last_seen': None,
            'packet_rate': 0,
            'total_packets': 0,
            'direction': 0,
            'remote': None,
        })
        self.server_address = (host, port)
        self.send_running = False
        self.running = True
        self.port = port

        self.output_file = get_timestamp_filename("server") if output_file is None else output_file

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

    def send_packet(self, remote_address, packet_id, packet_rate,
                    total_packets, direction):
            # Create the packet data
            packet_data = struct.pack('!IIII', packet_id, packet_rate,
                                      total_packets, direction) + b'\x00' * (64 - 16)
            self.sock.sendto(packet_data, remote_address)

    # Control the sending rate
    def send_rate_sleep(self, packet_rate):
        time.sleep(1 / packet_rate)

    def send_packets(self, packet_id):
        current_time = time.time()

        if self.packet_info[packet_id]['first_seen'] is not None:
            # duplicated request packet for download
            self.packet_info[packet_id]['last_seen'] = current_time
            return

        self.packet_info[packet_id]['first_seen'] = current_time
        self.packet_info[packet_id]['last_seen'] = current_time

        remote_address = self.packet_info[packet_id]['remote']
        packet_rate = self.packet_info[packet_id]['packet_rate']
        total_packets = self.packet_info[packet_id]['total_packets']
        direction = self.packet_info[packet_id]['direction']

        for i in range(total_packets):
            # Update the packet information
            self.packet_info[packet_id]['count'] += 1

            self.send_packet(remote_address, packet_id, packet_rate,
                             total_packets, direction)

            self.send_rate_sleep(packet_rate)

    def receive_packets(self):
        while self.running:
            data, addr = self.sock.recvfrom(1024)  # Buffer size is 1024 bytes
            if len(data) >= 64:
                packet_id = int.from_bytes(data[:4], byteorder='big')
                packet_rate = int.from_bytes(data[4:8], byteorder='big')
                total_packets = int.from_bytes(data[8:12], byteorder='big')
                direction = int.from_bytes(data[12:16], byteorder='big')
                current_time = time.time()

                self.packet_info[packet_id]['remote'] = addr

                self.packet_info[packet_id]['total_packets'] = total_packets
                self.packet_info[packet_id]['packet_rate'] = packet_rate
                self.packet_info[packet_id]['direction'] = direction

                if direction > 0:
                    # the client is in download mode
                    self.send_packets(packet_id)
                    continue

                if self.packet_info[packet_id]['first_seen'] is None:
                    self.packet_info[packet_id]['first_seen'] = current_time

                self.packet_info[packet_id]['last_seen'] = current_time

                # Update the packet information
                self.packet_info[packet_id]['count'] += 1

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
