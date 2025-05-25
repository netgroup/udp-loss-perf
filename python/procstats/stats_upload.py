import json
import statistics
import csv

# Load JSON data from a file named 'allstats.json'
with open('allstats.json', 'r') as file:
    json_data = json.load(file)

# Create a dictionary to map total_packets to a list of corresponding counts and rates
total_packets_count = {}

# Iterate over the JSON data, checking for direction == 0
for key, value in json_data.items():
    if value['direction'] == 0:
        # only consider the upload side
        total_packets = value['total_packets']
        count = value['count']
        packet_rate = value['packet_rate']

        if total_packets not in total_packets_count:
            total_packets_count[total_packets] = {'counts': [], 'rates': [], 'num_elements': 0}

        total_packets_count[total_packets]['counts'].append(count)
        total_packets_count[total_packets]['rates'].append(packet_rate)
        total_packets_count[total_packets]['num_elements'] += 1

# Calculate average, standard deviation, and ratio for each total_packets value
results = {}
for total_packets, data in total_packets_count.items():
    counts = data['counts']
    rates = data['rates']
    num_elements = data['num_elements']

    average = statistics.mean(counts)
    stddev = statistics.stdev(counts) if len(counts) > 1 else 0  # Stdev is 0 if there's only one count
    average_rate = statistics.mean(rates)

    # Calculate the ratio of count to total_packets for the average count
    # The ratio is only meaningful if total_packets is not zero
    ratio = average / total_packets if total_packets > 0 else 0

    results[total_packets] = {
        'num_elements': num_elements,
        'average': round(average, 4),
        'standard_deviation': round(stddev, 4),
        'average_packet_rate': round(average_rate, 4),
        'ratio': round(ratio, 4),
    }

# Write the results to a CSV file
with open('results.csv', 'w', newline='') as csvfile:
    fieldnames = ['Number of Matching Elements', 'Total Packets', 'Average Count', 'Standard Deviation',
                  'Average Packet Rate', 'Count/Total Packets Ratio']
    writer = csv.DictWriter(csvfile, fieldnames=fieldnames, delimiter=';')

    # Write the header
    writer.writeheader()

    # Write the data rows with formatted numbers
    for total_packets, stats in results.items():
        # XXX: note that it would have been better to use locale, but it means
        # that locale must be properly configured everywhere...
        writer.writerow({
            'Number of Matching Elements': stats['num_elements'],
            'Total Packets': total_packets,
            'Average Count': str(stats['average']).replace('.', ','),
            'Standard Deviation': str(stats['standard_deviation']).replace('.', ','),
            'Average Packet Rate': str(stats['average_packet_rate']).replace('.', ','),
            'Count/Total Packets Ratio': str(stats['ratio']).replace('.', ','),
        })

print("Results have been written to results.csv")
