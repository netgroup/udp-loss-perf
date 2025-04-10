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
    def __init__(self):
        # This dictionary will act as the hashtable to track seen numbers
        self.seen_numbers = {}
        self.timestamp = time.time()  # Store the current timestamp

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
