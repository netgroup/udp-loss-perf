import time
import datetime
import os

def get_timestamp_filename(name):
    current_time = datetime.datetime.now()
    formatted_time = current_time.strftime("%Y%m%d%H%M%S")
    filename = f"data/{formatted_time}_{name}.json"

    # Create the directories if they don't exist
    os.makedirs(os.path.dirname(filename), exist_ok=True)

    return filename

def get_pcap_fullpath(pcap_name):
    return f"data/{pcap_name}"

# Control the sending rate
def send_rate_sleep(packet_rate):
    time.sleep(1 / packet_rate)

class MSession:
    def __init__(self, packet_id, max_packets):
        self.packet_id = packet_id
        # This dictionary will act as the hashtable to track seen numbers
        self.seen_numbers = {}
        self.timestamp = time.time()  # Store the current timestamp
        self.max_packets = max_packets  # Maximum number of packets

    # Check if the number has been seen and update the count
    def count_packet(self, number):
        # Update the timestamp every time count_packet is called
        self.timestamp = time.time()
        start_tx_num = (2 ** 32) - 1

        if number == start_tx_num:
            # this is a packet required for starting a communication
            return start_tx_num

        if number in self.seen_numbers:
            self.seen_numbers[number] += 1
            # Return the count of how many times it has been seen
            return self.seen_numbers[number]

        # Return 1 since this is the first time it's seen
        self.seen_numbers[number] = 1
        return 1

    def get_missing_packets_seqnum(self):
        # Generate full range of expected packets
        expected_range = range(self.max_packets)
        missing_numbers = []

        # Find missing numbers
        for num in expected_range:
            if num not in self.seen_numbers:
                missing_numbers.append(num)

        # Compress the missing numbers into ranges
        compressed_ranges = []

        if not missing_numbers:
            return compressed_ranges  # No missing packets

        # Initialize with the first missing number
        start = missing_numbers[0]
        prev = start

        for current in missing_numbers[1:]:
            if current != prev + 1:
                # Sequence broken, append the previous range as (start, prev)
                compressed_ranges.append((start, prev))
                start = current
            prev = current

        # Append the last range
        compressed_ranges.append((start, prev))

        return compressed_ranges

    def write_missing_packets(self):
        key = self.packet_id
        filename = f"data/missing_packets_{key}.txt"

        data_list = self.get_missing_packets_seqnum()
        if not data_list:
            # missing packet list is empty, e.g., no packet missing
            return

        with open(filename, 'w') as file:
            # Write the 'header' tuple at the beginning
            file.write("(start, end)\n")
            # Write each tuple in the data_list
            for item in data_list:
                file.write(f"{item}\n")
