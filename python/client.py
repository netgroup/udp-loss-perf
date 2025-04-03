#!/usr/bin/env python3

import socket
import threading
import time
import random
import struct
import json
import os
import sys
import traceback
import argparse
import datetime
from collections import defaultdict

def get_timestamp_filename(name):
    current_time = datetime.datetime.now()
    formatted_time = current_time.strftime("%Y%m%d%H%M%S")
    filename = f"{formatted_time}_{name}.json"
    return filename

class SenderDownloadError(Exception):
    """Exception raised for errors in the sender download process."""
    pass

# Define the UDP client
class UDPClient:
    def __init__(self, host, port=12345, packets_to_send=600,
                 rate=100, direction=0, id_file='used_ids.txt',
                 output_file=None):
        # Each packet ID will map to a dictionary with count, first_seen,
        # last_seen, packet_rate, total_packets, direction
        self.packet_info = defaultdict(lambda: {
            'count': 0,
            'first_seen': None,
            'last_seen': None,
            'packet_rate': 0,
            'total_packets': 0,
            'direction': 0,
        })
        self.packets_to_send = packets_to_send
        self.server_address = (host, port)
        self.local_address = ('', port)
        self.receive_running = False
        self.direction = direction
        self.id_file = id_file
        self.running = True
        self.rate = rate

        self.used_ids = self.load_used_ids()

        self.output_file = get_timestamp_filename("client") if output_file is None else output_file

    # Load used packet IDs from a file
    def load_used_ids(self):
        if os.path.exists(self.id_file):
            with open(self.id_file, 'r') as f:
                return set(int(line.strip()) for line in f if
                           line.strip().isdigit())
        return set()

    # Save a used packet ID to the file
    def save_used_id(self, packet_id):
        with open(self.id_file, 'a') as f:
            f.write(f"{packet_id}\n")

    # Generate a unique packet ID that hasn't been used before
    def generate_unique_id(self):
        while True:
            # Random ID between 1 and 1000000
            packet_id = random.randint(1, 1000000)
            if packet_id not in self.used_ids:
                self.used_ids.add(packet_id)  # Keep track of the used ID
                self.save_used_id(packet_id)   # Save the ID to the file
                return packet_id

    def send_packet(self, packet_id, packet_rate, total_packets, direction):
            # Create the packet data
            packet_data = struct.pack('!IIII', packet_id, packet_rate,
                                      total_packets,
                                      direction) + b'\x00' * (64 - 16)
            self.sock.sendto(packet_data, self.server_address)

    # Control the sending rate
    def send_rate_sleep(self):
        packet_rate = self.rate

        time.sleep(1 / packet_rate)

    def send_packets(self):
        # Prepare the packet header with the packet rate and total number of
        # packets
        packet_id = self.packet_id
        packet_rate = self.rate
        total_packets = self.packets_to_send
        direction = self.direction

        # Create a packet format: 4 bytes for packet ID, 4 bytes for packet
        # rate, 4 bytes for total packets, 4 byte for direction.
        # This is a total of 16 bytes, leaving 48 bytes for padding to reach at
        # least 64 bytes
        for i in range(self.packets_to_send):
            self.send_packet(packet_id, packet_rate, total_packets, direction)

            self.send_rate_sleep()

        self.sock.close()

    def send_download_request(self):
        total_packets = self.packets_to_send
        direction = self.direction
        packet_id = self.packet_id
        packet_rate = self.rate
        retry = 0

        # Send the control message packet for starting the Client DOWNLOAD
        while retry < total_packets:
            count = self.packet_info[packet_id]['count']
            if count and count > 0:
                # Client started to receive DOWNLOAD traffic from the server
                break

            self.send_packet(packet_id, packet_rate, total_packets, direction)

            self.send_rate_sleep()
            retry += 1

        if retry != total_packets:
            # the receiver is receiving download traffic
            return 0

        # Number of retries exceeded the threshold (fixed as the total number
        # of packets supposed to be sent by the server).
        self.sock.close()
        raise SenderDownloadError("sender download failed: no server response")


    def receive_packets_core(self):
        timeout = -1

        # Notify that receive_packets thread has been run
        self.receive_running = True

        while self.running:
            data, addr = self.sock.recvfrom(1024)  # Buffer size is 1024 bytes
            if len(data) >= 64:
                packet_id = int.from_bytes(data[:4], byteorder='big')
                packet_rate = int.from_bytes(data[4:8], byteorder='big')
                total_packets = int.from_bytes(data[8:12], byteorder='big')
                direction = int.from_bytes(data[12:16], byteorder='big')
                current_time = time.time()

                # Update the packet information
                self.packet_info[packet_id]['count'] += 1
                self.packet_info[packet_id]['total_packets'] = total_packets
                self.packet_info[packet_id]['packet_rate'] = packet_rate
                self.packet_info[packet_id]['direction'] = direction

                if self.packet_info[packet_id]['first_seen'] is None:
                    self.packet_info[packet_id]['first_seen'] = current_time

                self.packet_info[packet_id]['last_seen'] = current_time

                # To exit from this loop we have different conditions

                count = self.packet_info[packet_id]['count']
                if count == total_packets:
                    # exit when we received all the packets w/o waiting
                    return

                duration = total_packets/packet_rate
                if timeout >= 0:
                    # timeout has been already set, jump back to the beginning
                    # of the loop
                    continue

                timeout = duration
                self.sock.settimeout(2 * timeout)

    def receive_packets(self):
        try:
            self.receive_packets_core()
        except socket.timeout:
            # not all packets have been received, so a timeout on the socket
            # is triggered.
            pass
        except Exception:
            # other exceptions are fatal?! NO MERCY!
            os._exit(1)

    def start_download(self):
        # Start the display thread
        display_thread = threading.Thread(target=self.save_counts_to_file,
                                          daemon=True)
        display_thread.start()

        # Start the receiving thread
        rcv_thread = threading.Thread(target=self.receive_packets, daemon=True)
        rcv_thread.start()

        while not self.receive_packets:
            # busy wait until the receiving thread gets started
            time.sleep(0.1)

        # ask the server to start sending the traffic
        self.send_download_request()

        # now wait for the receiving completion
        rcv_thread.join()

        # stop the display thread and close the socket
        self.stop()

    def start(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(self.local_address)

        # Every time the program is started, a new ID is generated
        self.packet_id = self.generate_unique_id()
        direction = self.direction

        if direction == 0:
            # upload mode (this client sends traffic to the sever)
            self.send_packets()
            return

        # download mode (server sends traffic to this clien)
        self.start_download()

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

def validate_direction(value):
    if value == 'up':
        return 0
    elif value == 'down':
        return 1
    else:
        raise argparse.ArgumentTypeError(f"Invalid value for direction: '{value}'. Must be 'up' or 'down'.")

# Run the sender
if __name__ == "__main__":
    # Create the argument parser
    parser = argparse.ArgumentParser(description="UDP Client")

    # Add arguments
    parser.add_argument('-z', '--host', type=str, required=True,
                        help='Host value')
    parser.add_argument('-n', '--npackets', type=int, default=60,
                        help='Number of packets (default: 60)')
    parser.add_argument('-r', '--rate', type=int, default=1,
                        help='Packet rate (default: 1)')
    parser.add_argument('-d', '--direction', type=validate_direction,
                        required=True, help='Direction (up or down)')

    # Parse the arguments
    args = parser.parse_args()

    try:
        client = UDPClient(host=args.host, packets_to_send=args.npackets,
                           rate=args.rate, direction=args.direction)
        client.start()
    except KeyboardInterrupt:
        client.stop()
        exit(2)
    except Exception as e:
        print(e)
        exit(1)
